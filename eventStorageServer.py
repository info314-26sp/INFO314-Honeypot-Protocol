import sys
import socket
import os
import time
import json

event_log_location = "eventLog.json"
node_log_location = "nodeLog.json"

# Acknowledges everything from central brain
def ack(msg_id, success, error_msg=""):
    return json.dumps(
        {
            "type": "ACK",
            "ack_for_msg_id": msg_id,
            "success": success,
            "error_msg": error_msg,
            "timestamp": int(time.time() * 1000) # milliseconds
        }
    ) + "\n"


# Probably stores
def store_event(event):
    
    if event["type"] == "STORE_EVENT":
        # load file's material
        try:
            with open(event_log_location, 'r') as file:
                events = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            events = []

        # Check duplicates for events
        if check_duplicate_event(events, event):
            return ack(event["msg_id"], False, f"Event {event["event_id"]} already logged")
        
        # Set logging location
        log_location = event_log_location
    elif event["type"] == "NODE_STATUS":
        # Load file. I don't think there's a need to check duplicate heartbeats
        try:
            with open(node_log_location, 'r') as file:
                events = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            events = []

        # Set log loc
        log_location = node_log_location

    # write file + add new event
    events.append(event) 
    try: 
        with open(log_location, 'w') as file:
            json.dump(events, file)
    except:
        return ack(event["msg_id"], False, f"Event {event["event_id"]} failed to log")

    return ack(event["msg_id"], True)

# Returns a requested record
def respond_query():
    print("hi")

# Checks the log file to check if event_id has already been logged
def check_duplicate_event(events, event):
    # try:
    #     with open(file_location, 'r') as file:
    #         events = json.load(file)
    # except FileNotFoundError:
    #     return False
    seen_events = [item["event_id"] for item in events]
    return (event["event_id"] in seen_events)

# Takes in incoming stream and converts it into event object (kson)
# Finishes recieving with }\n
def handle_connection(sock, addr):
    print("Recieving connection")

    recieved = b""
    while not recieved.endswith(b"}\n"):
        chunk = sock.recv(1024)
        if not chunk:
            return None
        recieved += chunk
        print(recieved)
    event = json.loads(recieved.decode("utf-8"))

    msg_type = event["type"]

    if (msg_type == "STORE_EVENT" or msg_type == "NODE_STATUS"):
        return store_event(event)
    elif msg_type == "QUERY":
        return respond_query(event)
    else:
        print("Uh oh... Invalid thing")


# Parameters:
# Self Host & Port
# Log location
# Trusted Central Node (?)

def main():
    if len(sys.argv) < 3:
        print("Expected arguments: <host> <port> <Log Location> <Central Node>")

    host = sys.argv[1]
    port = int(sys.argv[2])

    node_log_location = sys.argv[3] or node_log_location # Logging loc

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"Event store is now running. Host: {host}, Port: {port}.")

    # Todo: Accept packets from ONLY central guy
    while True:
        client_socket, client_address = server.accept()

        try:
            # all messages must end with }\n
            client_socket.sendall(handle_connection(client_socket, client_address).encode("utf-8"))
            
        finally:
            client_socket.close()


if __name__ == "__main__":
    main()
