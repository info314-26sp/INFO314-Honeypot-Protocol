import socket
import json
import time

def send(sock, msg):
    sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("127.0.0.1", 9000))

auth = {
    "type": "AUTH",
    "msg_id": "test-msg-001",
    "node_id": "test-node-001",
    "credentials": "",
    "timestamp": int(time.time() * 1000)
}

send(sock, auth)
print("Sent AUTH")

response = b""
while not response.endswith(b"\n"):
    response += sock.recv(4096)

print(f"Received: {response.decode('utf-8')}")
sock.close()