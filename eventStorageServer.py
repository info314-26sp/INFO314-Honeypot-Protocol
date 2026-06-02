import sys
import socket
import os
import time
import json

file_location = "eventLog.json"

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
    # load file's material
    try:
        with open(file_location, 'r') as file:
            events = json.load(file)
    except FileNotFoundError:
        events = []

    if check_duplicate_event(events, event):
        return ack(event["msg_id"], False, f"Event {event["event_id"]} already logged")

    # write file + add new event
    events.append(event) 
    try: 
        with open(file_location, 'w') as file:
            json.dump(events, file)
    except:  # I dont know what exceptions this can throw
        ack(event["msg_id"], False, f"Event {event["event_id"]} failed to log")

    return ack(event["msg_id"], True)

# Checks the log file to check if event_id has already been logged
def check_duplicate_event(events, event):
    # try:
    #     with open(file_location, 'r') as file:
    #         events = json.load(file)
    # except FileNotFoundError:
    #     return False
    seen_events = [events["event_id"] for item in events]
    print(seen_events)

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

    log_path = sys.argv[3] # Logging loc

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
            client_socket.sendall(handle_connection(client_socket, client_address).encodee("utf-8"))
            
        finally:
            client_socket.close()


if __name__ == "__main__":
    main()
