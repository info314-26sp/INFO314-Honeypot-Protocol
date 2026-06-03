"""
Comprehensive integration test for central_brain.py <-> event_store.py

Launches both servers as subprocesses, then simulates multiple honeypot nodes
sending all protocol message types in randomized perpetual scenarios.

Usage:
    python3 test.py

Both servers start automatically. Press Ctrl+C to stop.
"""

import socket
import threading
import json
import time
import uuid
import random
import subprocess
import os
import sys

# ── Config ────────────────────────────────────────────────────────────────────
BRAIN_HOST = "127.0.0.1"
BRAIN_PORT = 9000
STORE_HOST = "127.0.0.1"
STORE_PORT = 9001
STORE_LOG   = "/tmp/test_eventlog.json"
HDP_SECRET  = ""   # matches default in central_brain.py

NUM_NODES   = 3    # concurrent simulated honeypot nodes

# ── ANSI colours ──────────────────────────────────────────────────────────────
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
MAGENTA= "\033[95m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
COLORS = [CYAN, MAGENTA, YELLOW]

print_lock = threading.Lock()

def log(tag, msg, color=RESET):
    ts = time.strftime("%H:%M:%S")
    with print_lock:
        print(f"{color}{BOLD}[{ts}][{tag}]{RESET} {msg}")


# ── Server launchers ──────────────────────────────────────────────────────────

def start_servers():
    base = os.path.dirname(os.path.abspath(__file__))

    store_proc = subprocess.Popen(
        [sys.executable, "event_store.py", STORE_HOST, str(STORE_PORT), STORE_LOG],
        cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    threading.Thread(target=_relay_output, args=(store_proc, "STORE", GREEN), daemon=True).start()
    log("LAUNCHER", f"Event Store started (PID {store_proc.pid})", GREEN)

    time.sleep(0.4)

    brain_proc = subprocess.Popen(
        [sys.executable, "central_brain.py"],
        cwd=base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )
    threading.Thread(target=_relay_output, args=(brain_proc, "BRAIN", YELLOW), daemon=True).start()
    log("LAUNCHER", f"central_brain started (PID {brain_proc.pid})", YELLOW)

    time.sleep(0.6)   # give brain time to connect to store
    return brain_proc, store_proc


def _relay_output(proc, tag, color):
    for line in proc.stdout:
        log(tag, line.rstrip(), color)


# ── Honeypot Node Simulator ───────────────────────────────────────────────────

class HoneypotNode:
    """Simulates a single honeypot node communicating with central_brain."""

    def __init__(self, node_id, color):
        self.node_id  = node_id
        self.color    = color
        self.conn     = None
        self.running  = True
        self._buf     = ""
        self._buf_lock = threading.Lock()

    # ── Low-level send/recv ───────────────────────────────────────────────────

    def _send(self, msg):
        raw = json.dumps(msg) + "\n"
        try:
            self.conn.sendall(raw.encode("utf-8"))
        except Exception as e:
            log(self.node_id, f"Send error: {e}", RED)

    def _msg_id(self):
        return str(uuid.uuid4())

    def _ts(self):
        return int(time.time() * 1000)

    # ── Incoming message listener (runs in its own thread) ────────────────────

    def _listen(self):
        buf = ""
        while self.running:
            try:
                self.conn.settimeout(2)
                chunk = self.conn.recv(4096).decode("utf-8")
                if not chunk:
                    log(self.node_id, "Brain closed connection", RED)
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._handle_from_brain(msg)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log(self.node_id, f"Listen error: {e}", RED)
                break

    def _handle_from_brain(self, msg):
        mtype = msg.get("type")

        if mtype == "PING":
            log(self.node_id, f"<-- PING  msg_id={msg['msg_id'][:8]}", self.color)
            self._send_echo(msg)

        elif mtype == "CONTROL_COMMAND":
            cmds = msg.get("cc_commands", [])
            for cmd in cmds:
                log(self.node_id, f"<-- CONTROL_COMMAND {cmd['command']} params={cmd.get('parameters')}", self.color)
            self._send_cmd_ack(msg["msg_id"], applied=True)

        elif mtype == "CONFIG_UPDATE":
            cmds = msg.get("cu_commands", [])
            for cmd in cmds:
                log(self.node_id, f"<-- CONFIG_UPDATE {cmd['command']} params={cmd.get('parameters')}", self.color)
            self._send_cmd_ack(msg["msg_id"], applied=True)

        else:
            log(self.node_id, f"<-- Unknown msg type: {mtype}", RED)

    # ── Protocol message senders ──────────────────────────────────────────────

    def send_auth(self):
        msg = {
            "type":        "AUTH",
            "msg_id":      self._msg_id(),
            "node_id":     self.node_id,
            "credentials": HDP_SECRET,
            "timestamp":   self._ts(),
        }
        self._send(msg)
        log(self.node_id, f"--> AUTH", self.color)

    def send_heartbeat(self):
        msg = {
            "type":      "HEARTBEAT",
            "msg_id":    self._msg_id(),
            "node_id":   self.node_id,
            "timestamp": self._ts(),
        }
        self._send(msg)
        log(self.node_id, f"--> HEARTBEAT", self.color)

    def send_event_report(self, event_type, source_ip, source_port, service, payload=None):
        msg = {
            "type":        "EVENT_REPORT",
            "msg_id":      self._msg_id(),
            "node_id":     self.node_id,
            "source_ip":   source_ip,
            "source_port": source_port,
            "service":     service,
            "event_type":  event_type,
            "payload":     payload or {},
            "timestamp":   self._ts(),
        }
        self._send(msg)
        log(self.node_id, f"--> EVENT_REPORT type={event_type} ip={source_ip} svc={service}", self.color)

    def _send_echo(self, ping_msg):
        msg = {
            "type":      "ECHO",
            "msg_id":    self._msg_id(),
            "node_id":   self.node_id,
            "ping_id":   ping_msg.get("msg_id"),
            "timestamp": self._ts(),
        }
        self._send(msg)
        log(self.node_id, f"--> ECHO (reply to PING {ping_msg['msg_id'][:8]})", self.color)

    def _send_cmd_ack(self, ack_for, applied=True, error_msg=""):
        msg = {
            "type":      "CMD_ACK",
            "msg_id":    self._msg_id(),
            "node_id":   self.node_id,
            "ack_for":   ack_for,
            "applied":   applied,
            "error_msg": error_msg,
            "timestamp": self._ts(),
        }
        self._send(msg)
        log(self.node_id, f"--> CMD_ACK ack_for={ack_for[:8]} applied={applied}", self.color)

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def connect(self):
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.connect((BRAIN_HOST, BRAIN_PORT))
        threading.Thread(target=self._listen, daemon=True).start()
        log(self.node_id, "Connected to central_brain", self.color)

    def stop(self):
        self.running = False
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass


# ── Scenario library ──────────────────────────────────────────────────────────

ATTACKER_IPS = [
    "10.0.0.{}".format(i) for i in range(1, 20)
] + [
    "192.168.1.{}".format(i) for i in range(100, 120)
]

SQL_PAYLOADS = [
    {"path": "/login", "body": "' OR 1=1 --"},
    {"path": "/search", "query": "' UNION SELECT * FROM users --"},
    {"path": "/admin", "body": "'; DROP TABLE sessions; --"},
    {"path": "/api", "query": "INSERT INTO logs VALUES('x')"},
    {"path": "/items", "query": "SELECT * FROM secrets"},
]

NORMAL_HTTP_PAYLOADS = [
    {"path": "/index.html", "method": "GET"},
    {"path": "/about", "method": "GET"},
    {"path": "/login", "body": "user=guest&pass=guest"},
    {"path": "/api/data", "method": "POST"},
]

LOGIN_USERS = ["root", "admin", "pi", "ubuntu", "guest", "test", "oracle", "postgres"]


def scenario_normal_traffic(node):
    """Occasional normal-looking HTTP traffic."""
    ip = random.choice(ATTACKER_IPS)
    payload = random.choice(NORMAL_HTTP_PAYLOADS)
    node.send_event_report("HTTP_REQUEST", ip, random.randint(1024, 65535), "http", payload)


def scenario_single_login(node):
    """One login attempt — low severity, no alert."""
    ip = random.choice(ATTACKER_IPS)
    node.send_event_report(
        "LOGIN_ATTEMPT", ip, 22, "ssh",
        {"user": random.choice(LOGIN_USERS), "password": "letmein"}
    )


def scenario_brute_force(node):
    """Rapid login attempts from same IP → BRUTE_FORCE → SLOW_RESPONSE command."""
    ip = random.choice(ATTACKER_IPS)
    log(node.node_id, f"[SCENARIO] Brute-force burst from {ip}", RED)
    bursts = random.randint(4, 8)
    for _ in range(bursts):
        node.send_event_report(
            "LOGIN_ATTEMPT", ip, 22, "ssh",
            {"user": random.choice(LOGIN_USERS), "password": str(uuid.uuid4())[:8]}
        )
        time.sleep(random.uniform(0.8, 1.5))


def scenario_port_scan(node):
    """Multiple port probes from same IP → PORT_SCAN → SLOW_RESPONSE command."""
    ip = random.choice(ATTACKER_IPS)
    log(node.node_id, f"[SCENARIO] Port scan from {ip}", RED)
    ports = random.sample(range(1, 1024), random.randint(6, 12))
    for port in ports:
        node.send_event_report("PORT_PROBE", ip, port, "tcp", {"port": port})
        time.sleep(random.uniform(0.5, 1.2))


def scenario_sql_injection(node):
    """SQL injection attempt → SQL_INJECTION → SLOW_RESPONSE command."""
    ip = random.choice(ATTACKER_IPS)
    payload = random.choice(SQL_PAYLOADS)
    log(node.node_id, f"[SCENARIO] SQL injection from {ip}", RED)
    node.send_event_report("HTTP_REQUEST", ip, 80, "http", payload)


def scenario_mixed_burst(node):
    """Mixed event types from the same attacker IP."""
    ip = random.choice(ATTACKER_IPS)
    log(node.node_id, f"[SCENARIO] Mixed attack burst from {ip}", RED)
    for _ in range(random.randint(2, 4)):
        etype = random.choice(["LOGIN_ATTEMPT", "PORT_PROBE", "HTTP_REQUEST"])
        if etype == "HTTP_REQUEST":
            payload = random.choice(NORMAL_HTTP_PAYLOADS + SQL_PAYLOADS)
        elif etype == "LOGIN_ATTEMPT":
            payload = {"user": random.choice(LOGIN_USERS)}
        else:
            payload = {"port": random.randint(1, 1024)}
        node.send_event_report(etype, ip, random.randint(1, 65535), "ssh", payload)
        time.sleep(random.uniform(0.8, 2.0))


def scenario_go_silent(node):
    """Node stops sending heartbeats — brain will PING after HEARTBEAT_TIMEOUT.
    Node comes back after a random pause and resumes heartbeats."""
    silence = random.randint(5, 15)
    log(node.node_id, f"[SCENARIO] Going silent for {silence}s (brain should PING)", MAGENTA)
    time.sleep(silence)
    log(node.node_id, "[SCENARIO] Resuming heartbeat after silence", MAGENTA)


def scenario_cmd_ack_failure(node):
    """Simulate a node that fails to apply a command — sends CMD_ACK with applied=False."""
    fake_cmd_id = str(uuid.uuid4())
    log(node.node_id, "[SCENARIO] Sending failed CMD_ACK", MAGENTA)
    node._send_cmd_ack(fake_cmd_id, applied=False, error_msg="Permission denied")


SCENARIOS = [
    (scenario_normal_traffic,    25),   # weight
    (scenario_single_login,      20),
    (scenario_brute_force,       15),
    (scenario_port_scan,         15),
    (scenario_sql_injection,     10),
    (scenario_mixed_burst,       10),
    (scenario_go_silent,          3),
    (scenario_cmd_ack_failure,    2),
]

_scenario_pool = []
for fn, weight in SCENARIOS:
    _scenario_pool.extend([fn] * weight)


# ── Node runner ───────────────────────────────────────────────────────────────

def run_node(node_id, color):
    node = HoneypotNode(node_id, color)

    # retry connect in case brain isn't up yet
    for attempt in range(10):
        try:
            node.connect()
            break
        except ConnectionRefusedError:
            log(node_id, f"Brain not ready, retry {attempt+1}/10…", RED)
            time.sleep(1)
    else:
        log(node_id, "Could not connect to brain — giving up", RED)
        return

    node.send_auth()
    time.sleep(0.5)   # wait for CONFIG_UPDATE reply

    heartbeat_interval = 30   # seconds; brain may update this via CONFIG_UPDATE
    last_heartbeat = time.time()

    while node.running:
        # Heartbeat on schedule
        if time.time() - last_heartbeat >= heartbeat_interval:
            node.send_heartbeat()
            last_heartbeat = time.time()

        # Pick and run a random scenario
        scenario = random.choice(_scenario_pool)
        try:
            scenario(node)
        except Exception as e:
            log(node_id, f"Scenario error: {e}", RED)

        # Random wait between actions
        time.sleep(random.uniform(4.0, 9.0))

    node.stop()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    log("TEST", "Starting integration test — press Ctrl+C to stop", BOLD)

    brain_proc, store_proc = start_servers()

    threads = []
    for i in range(NUM_NODES):
        node_id = f"node-{i+1:03d}"
        color   = COLORS[i % len(COLORS)]
        t = threading.Thread(target=run_node, args=(node_id, color), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.3)   # stagger connection attempts

    log("TEST", f"{NUM_NODES} node(s) running — perpetual test in progress", GREEN)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("TEST", "Shutting down…", YELLOW)
    finally:
        brain_proc.terminate()
        store_proc.terminate()
        log("TEST", "Done.", YELLOW)


if __name__ == "__main__":
    main()
