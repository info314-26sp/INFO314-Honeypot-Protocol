import sys
import socket
import os
import time

def ack(msg_id, success, error_msg=""):
    return(
        {
            "type": "ACK",
            "ack_for_msg_id": msg_id,
            "success": success,
            "error_msg": error_msg,
            "timpestamp": int(time.time() * 1000) # milliseconds
        }
    )

def store_event(event):
    print("Hi world and hello")

def check_duplicate_event(event):
    print("hi")

# Takes in decoded message and converts it into event object
def parse_event(yap):
    print("BYE world")

# Parameters:
# Self Host & Port
# Trusted Central Node
# Log location
def main():
    if len(sys.argv) < 3:
        print("Expected arguments: <host> <port> <Central Node> <Log Location>")

    host = sys.argv[1]
    port = sys.argv[2]

    log_path = sys.argv[3] # Logging loc

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"Event store is now running. Host: {host}, Port: {port}")

    try: 
        while True:
            client_socket, client_address = server.accept()
    finally:
        server.close()



