import socket
import threading
import json
import uuid
import time
import os

HDP_SECRET = os.environ.get("HDP_SECRET", "")

HEARTBEAT_TIMEOUT = 90       # 3 * 30s intervals before sending PING
PING_RESPONSE_TIMEOUT = 15   # seconds to wait for ECHO after PING
STORE_ACK_TIMEOUT = 5.0      # seconds to wait for store ACK
MAX_STORE_RETRIES = 3
BRUTE_FORCE_THRESHOLD = 3    # login attempts from same IP within window
PORT_SCAN_THRESHOLD = 5      # port probes from same IP within window
RATE_WINDOW_SECONDS = 60

nodes = {}            # node_id -> {status, last_seen, missed, conn}
seen_msg_ids = set()  # dedup cache
store_conn = None     # persistent connection to Event Store
lock = threading.Lock()
store_lock = threading.Lock()
pending_pings = {}    # node_id -> {msg_id, sent_at}
ip_events = {}        # source_ip -> [timestamp, ...]


def _send(conn, msg):
    conn.sendall((json.dumps(msg) + "\n").encode("utf-8"))


def start(host, port, store_host, store_port):
    global store_conn
    store_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    store_conn.connect((store_host, store_port))

    threading.Thread(target=monitor_heartbeats, daemon=True).start()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen()
    print(f"Central Brain listening on {host}:{port}")

    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_client, args=(conn,), daemon=True).start()


def handle_client(conn):
    buf = ""
    try:
        while True:
            data = conn.recv(4096).decode("utf-8")
            if not data:
                break
            buf += data
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_id = msg.get("msg_id")
                with lock:
                    if msg_id and msg_id in seen_msg_ids:
                        continue
                    if msg_id:
                        seen_msg_ids.add(msg_id)

                msg_type = msg.get("type")
                if msg_type == "AUTH":
                    handle_auth(msg, conn)
                elif msg_type == "HEARTBEAT":
                    handle_heartbeat(msg, conn)
                elif msg_type == "EVENT_REPORT":
                    handle_event_report(msg, conn)
                elif msg_type == "ECHO":
                    handle_echo(msg, conn)
                elif msg_type == "CMD_ACK":
                    handle_cmd_ack(msg, conn)
    finally:
        conn.close()


def handle_auth(msg, conn):
    node_id = msg.get("node_id")
    credentials = msg.get("credentials")

    if not node_id or credentials != HDP_SECRET:
        conn.close()
        return

    with lock:
        nodes[node_id] = {
            "status": "ONLINE",
            "last_seen": time.time(),
            "missed": 0,
            "conn": conn,
        }

    config_update = {
        "type": "CONFIG_UPDATE",
        "msg_id": str(uuid.uuid4()),
        "rec_node_id": node_id,
        "cu_commands": [{"command": "SET_HEARTBEAT_INTERVAL", "parameters": {"interval_s": 30}}],
        "timestamp": int(time.time() * 1000),
    }
    _send(conn, config_update)
    print(f"Node {node_id} authenticated and configured")


def handle_heartbeat(msg, conn):
    node_id = msg.get("node_id")
    with lock:
        node = nodes.get(node_id)
        if not node:
            return
        was_offline = node["status"] == "OFFLINE"
        node["last_seen"] = time.time()
        node["missed"] = 0
        node["status"] = "ONLINE"
        pending_pings.pop(node_id, None)

    if was_offline:
        print(f"Node {node_id} recovered via heartbeat")
        config_update = {
            "type": "CONFIG_UPDATE",
            "msg_id": str(uuid.uuid4()),
            "rec_node_id": node_id,
            "cu_commands": [{"command": "SET_HEARTBEAT_INTERVAL", "parameters": {"interval_s": 30}}],
            "timestamp": int(time.time() * 1000),
        }
        _send(conn, config_update)
        node_status = {
            "type": "NODE_STATUS",
            "msg_id": str(uuid.uuid4()),
            "node_id": node_id,
            "status": "ONLINE",
            "reason": "node_recovered",
            "timestamp": int(time.time() * 1000),
        }
        threading.Thread(target=send_to_store, args=(node_status,), daemon=True).start()


def handle_event_report(msg, conn):
    node_id = msg.get("node_id")
    source_ip = msg.get("source_ip")
    source_port = msg.get("source_port")
    service = msg.get("service")
    event_type = msg.get("event_type")
    payload = msg.get("payload", {})
    timestamp = msg.get("timestamp", int(time.time() * 1000))

    now = time.time()
    with lock:
        events = ip_events.setdefault(source_ip, [])
        events.append(now)
        ip_events[source_ip] = [t for t in events if now - t <= RATE_WINDOW_SECONDS]
        recent_count = len(ip_events[source_ip])

    classification, severity = _classify(event_type, payload, recent_count)

    store_msg = {
        "type": "STORE_EVENT",
        "msg_id": str(uuid.uuid4()),
        "event_id": str(uuid.uuid4()),
        "node_id": node_id,
        "source_ip": source_ip,
        "source_port": source_port,
        "service": service,
        "event_type": event_type,
        "classification": classification,
        "severity": severity,
        "payload": payload,
        "timestamp": timestamp,
    }
    threading.Thread(target=send_to_store, args=(store_msg,), daemon=True).start()

    if severity >= 6:
        command = _response_command(classification)
        if command:
            ctrl_cmd = {
                "type": "CONTROL_COMMAND",
                "msg_id": str(uuid.uuid4()),
                "rec_node_id": node_id,
                "cc_commands": [command],
                "timestamp": int(time.time() * 1000),
            }
            _send(conn, ctrl_cmd)
            print(f"Dispatched {command['command']} to node {node_id} ({classification}, severity {severity})")


def _classify(event_type, payload, recent_count):
    if event_type == "LOGIN_ATTEMPT":
        if recent_count >= BRUTE_FORCE_THRESHOLD:
            return "BRUTE_FORCE", 8
        return "LOGIN_ATTEMPT", 3
    elif event_type == "PORT_PROBE":
        if recent_count >= PORT_SCAN_THRESHOLD:
            return "PORT_SCAN", 6
        return "PORT_PROBE", 2
    elif event_type == "HTTP_REQUEST":
        sql_keywords = ["SELECT", "UNION", "DROP", "INSERT", "--", "';"]
        data_str = json.dumps(payload).upper()
        if any(kw in data_str for kw in sql_keywords):
            return "SQL_INJECTION", 7
        return "HTTP_REQUEST", 3
    return event_type, 3


def _response_command(classification):
    if classification == "BRUTE_FORCE":
        return {"command": "SLOW_RESPONSE", "parameters": {"delay_ms": 5000}}
    if classification == "SQL_INJECTION":
        return {"command": "SLOW_RESPONSE", "parameters": {"delay_ms": 3000}}
    if classification == "PORT_SCAN":
        return {"command": "SLOW_RESPONSE", "parameters": {"delay_ms": 1000}}
    return None


def handle_echo(msg, conn):
    node_id = msg.get("node_id")
    with lock:
        node = nodes.get(node_id)
        if not node:
            return
        was_offline = node["status"] == "OFFLINE"
        node["status"] = "ONLINE"
        node["last_seen"] = time.time()
        node["missed"] = 0
        pending_pings.pop(node_id, None)

    if was_offline:
        print(f"Node {node_id} responded to PING, marking ONLINE")
        config_update = {
            "type": "CONFIG_UPDATE",
            "msg_id": str(uuid.uuid4()),
            "rec_node_id": node_id,
            "cu_commands": [{"command": "SET_HEARTBEAT_INTERVAL", "parameters": {"interval_s": 30}}],
            "timestamp": int(time.time() * 1000),
        }
        _send(conn, config_update)
        node_status = {
            "type": "NODE_STATUS",
            "msg_id": str(uuid.uuid4()),
            "node_id": node_id,
            "status": "ONLINE",
            "reason": "node_recovered",
            "timestamp": int(time.time() * 1000),
        }
        threading.Thread(target=send_to_store, args=(node_status,), daemon=True).start()
    else:
        print(f"Node {node_id} confirmed alive via PING/ECHO")


def handle_cmd_ack(msg, _):
    node_id = msg.get("node_id")
    ack_for = msg.get("ack_for")
    applied = msg.get("applied")
    error_msg = msg.get("error_msg")
    if not applied:
        print(f"Node {node_id} failed to apply {ack_for}: {error_msg}")
    else:
        print(f"Node {node_id} applied {ack_for} successfully")


def monitor_heartbeats():
    while True:
        time.sleep(10)
        now = time.time()

        with lock:
            nodes_snapshot = {nid: dict(info) for nid, info in nodes.items()}
            pings_snapshot = dict(pending_pings)

        for node_id, info in nodes_snapshot.items():
            pending = pings_snapshot.get(node_id)

            if pending and now - pending["sent_at"] > PING_RESPONSE_TIMEOUT:
                if info["status"] != "OFFLINE":
                    with lock:
                        nodes[node_id]["status"] = "OFFLINE"
                    print(f"Node {node_id} is OFFLINE — no ECHO received")
                    node_status = {
                        "type": "NODE_STATUS",
                        "msg_id": str(uuid.uuid4()),
                        "node_id": node_id,
                        "status": "OFFLINE",
                        "reason": "missed_heartbeats",
                        "last_seen": int(info["last_seen"] * 1000),
                        "timestamp": int(now * 1000),
                    }
                    send_to_store(node_status)
                with lock:
                    pending_pings.pop(node_id, None)
                continue

            elapsed = now - info["last_seen"]
            if elapsed > HEARTBEAT_TIMEOUT and info["status"] == "ONLINE" and node_id not in pings_snapshot:
                node_conn = info.get("conn")
                if node_conn:
                    ping_id = str(uuid.uuid4())
                    ping = {
                        "type": "PING",
                        "msg_id": ping_id,
                        "target_node_id": node_id,
                        "timestamp": int(now * 1000),
                    }
                    try:
                        _send(node_conn, ping)
                        with lock:
                            pending_pings[node_id] = {"msg_id": ping_id, "sent_at": now}
                        print(f"Sent PING to node {node_id} after {elapsed:.0f}s without heartbeat")
                    except Exception as e:
                        print(f"Failed to PING node {node_id}: {e}")


def send_to_store(message):
    msg_id = message.get("msg_id")
    for attempt in range(MAX_STORE_RETRIES):
        with store_lock:
            try:
                _send(store_conn, message)
                store_conn.settimeout(STORE_ACK_TIMEOUT)
                buf = ""
                while "\n" not in buf:
                    chunk = store_conn.recv(4096).decode("utf-8")
                    if not chunk:
                        break
                    buf += chunk
                store_conn.settimeout(None)
                line = buf.split("\n")[0].strip()
                if line:
                    ack = json.loads(line)
                    if ack.get("type") == "ACK" and ack.get("ack_for_msg_id") == msg_id and ack.get("success"):
                        return True
                    print(f"Store NACK for {msg_id}: {ack.get('error_msg')}")
            except socket.timeout:
                print(f"Store ACK timeout for {msg_id}, attempt {attempt + 1}/{MAX_STORE_RETRIES}")
            except Exception as e:
                print(f"Store error for {msg_id}: {e}, attempt {attempt + 1}/{MAX_STORE_RETRIES}")
            finally:
                try:
                    store_conn.settimeout(None)
                except Exception:
                    pass
    print(f"STORAGE FAILURE ALERT: could not persist message {msg_id} after {MAX_STORE_RETRIES} attempts")
    return False


if __name__ == "__main__":
    start(
        host="0.0.0.0",
        port=9000,
        store_host="127.0.0.1",
        store_port=9001,
    )
