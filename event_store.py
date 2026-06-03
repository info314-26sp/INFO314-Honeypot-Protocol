import sys
import socket
import threading
import os
import time
import json
import uuid

file_location = "eventLog.json"
file_lock = threading.Lock()


# Acknowledges everything from central brain
def ack(ack_for_msg_id, success, error_msg=""):
    return json.dumps({
        "type": "ACK",
        "msg_id": str(uuid.uuid4()),
        "ack_for_msg_id": ack_for_msg_id,
        "success": success,
        "error_msg": error_msg if not success else "",
        "timestamp": int(time.time() * 1000)
    }) + "\n"


# Checks the log file to check if event_id has already been logged
def check_duplicate(events, record, msg_type):
    if msg_type == "STORE_EVENT":
        seen = [item.get("event_id") for item in events if item.get("record_type") == "STORE_EVENT"]
        return record.get("event_id") in seen
    if msg_type == "NODE_STATUS":
        return False
    return False


# Probably stores
def store_record(record, msg_type):
    msg_id = record.get("msg_id")
    # load file's material
    with file_lock:
        try:
            with open(file_location, 'r') as f:
                events = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            events = []

        if check_duplicate(events, record, msg_type):
            return ack(msg_id, False, f"Duplicate record {record.get('event_id')} already logged")

        # write file + add new event
        record["record_type"] = msg_type
        events.append(record)

        try:
            with open(file_location, 'w') as f:
                json.dump(events, f, indent=2)
        except Exception as e:  # I dont know what exceptions this can throw
            return ack(msg_id, False, f"Failed to write record: {e}")

    return ack(msg_id, True)


# Takes in incoming stream and converts it into event object (json)
# Finishes recieving with }\n
def handle_connection(conn, addr):
    print(f"Recieving connection from {addr}")
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
                    print(f"Malformed message from {addr}, skipping")
                    continue

                msg_type = msg.get("type")

                if msg_type in ("STORE_EVENT", "NODE_STATUS"):
                    response = store_record(msg, msg_type)
                    conn.sendall(response.encode("utf-8"))
                else:
                    print("Uh oh... Invalid thing")
    except Exception as e:
        print(f"Connection error from {addr}: {e}")
    finally:
        conn.close()


# Parameters:
# Self Host & Port
# Log location
# Trusted Central Node (?)
def main():
    if len(sys.argv) < 3:
        print("Expected arguments: <host> <port> <Log Location> <Central Node>")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2])

    # Todo: Accept packets from ONLY central guy
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"Event store is now running. Host: {host}, Port: {port}.")

    while True:
        client_socket, client_address = server.accept()
        threading.Thread(target=handle_connection, args=(client_socket, client_address), daemon=True).start()


if __name__ == "__main__":
    main()