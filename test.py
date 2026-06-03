"""
HDP Continuous Random Attack Test

Prerequisites (run each in a separate terminal):
  Terminal 1: python3 event_store.py 127.0.0.1 9001
  Terminal 2: python3 central_brain.py
  Terminal 3: java -cp .:lib/gson-2.13.1.jar HoneypotNode localhost 9000 2222 2121 8080

Then: python3 test.py
Press Ctrl+C to stop.
"""

import socket
import threading
import time
import random

HONEYPOT_HOST = "127.0.0.1"
SSH_PORT  = 2222
FTP_PORT  = 2121
HTTP_PORT = 8080

NUM_ATTACKERS   = 3
CONNECT_TIMEOUT = 5

BOLD    = "\033[1m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
RESET   = "\033[0m"
COLORS  = [CYAN, MAGENTA, YELLOW]

print_lock = threading.Lock()

def log(tag, msg, color=RESET):
    ts = time.strftime("%H:%M:%S")
    with print_lock:
        print(f"{color}{BOLD}[{ts}][{tag}]{RESET} {msg}")


# ── Low-level attacker connection ─────────────────────────────────────────────

def connect_and_send(tag, color, port, label, payload_lines):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(CONNECT_TIMEOUT)
            s.connect((HONEYPOT_HOST, port))
            banner = s.recv(4096).decode("utf-8", errors="replace").strip()
            log(tag, f"<-- [{label}] FAKE_BANNER: {banner!r}", color)
            for line in payload_lines:
                s.sendall((line + "\n").encode("utf-8"))
                log(tag, f"--> {line!r}", color)
    except ConnectionRefusedError:
        log(tag, f"Connection refused on {label}:{port} — is HoneypotNode running?", RED)
    except Exception as e:
        log(tag, f"Error on {label}: {e}", RED)


# ── Scenario library ──────────────────────────────────────────────────────────

LOGIN_USERS = ["root", "admin", "pi", "ubuntu", "guest", "test", "oracle", "postgres"]

SQL_PAYLOADS = [
    "user=admin&pass=' OR 1=1 --",
    "user=admin&pass=' UNION SELECT * FROM users --",
    "q='; DROP TABLE sessions; --",
    "id=1 AND 1=1 --",
    "name=x'; INSERT INTO logs VALUES('pwned'); --",
]

HTTP_PATHS = ["/", "/index.html", "/about", "/login", "/admin", "/api/data", "/config"]


def scenario_ssh_probe(tag, color):
    user = random.choice(LOGIN_USERS)
    log(tag, f"[SSH PROBE] user={user}", color)
    connect_and_send(tag, color, SSH_PORT, "SSH", [user])


def scenario_ssh_brute(tag, color):
    bursts = random.randint(3, 7)
    log(tag, f"[BRUTE FORCE] {bursts} rapid SSH attempts", RED)
    for _ in range(bursts):
        cred = f"{random.choice(LOGIN_USERS)}:{random.randint(1000, 9999)}"
        connect_and_send(tag, color, SSH_PORT, "SSH", [cred])
        time.sleep(random.uniform(0.5, 1.2))


def scenario_ftp_probe(tag, color):
    user = random.choice(LOGIN_USERS + ["anonymous", "ftp"])
    log(tag, f"[FTP PROBE] user={user}", color)
    connect_and_send(tag, color, FTP_PORT, "FTP", [f"USER {user}", "PASS wrong123"])


def scenario_ftp_brute(tag, color):
    bursts = random.randint(3, 5)
    log(tag, f"[FTP BRUTE] {bursts} attempts", RED)
    for _ in range(bursts):
        user = random.choice(LOGIN_USERS)
        connect_and_send(tag, color, FTP_PORT, "FTP", [f"USER {user}", f"PASS {random.randint(1000,9999)}"])
        time.sleep(random.uniform(0.6, 1.5))


def scenario_http_request(tag, color):
    path = random.choice(HTTP_PATHS)
    log(tag, f"[HTTP REQUEST] GET {path}", color)
    connect_and_send(tag, color, HTTP_PORT, "HTTP", [
        f"GET {path} HTTP/1.1",
        "Host: target.local",
    ])


def scenario_sql_injection(tag, color):
    payload = random.choice(SQL_PAYLOADS)
    log(tag, f"[SQL INJECTION] {payload[:50]}", RED)
    connect_and_send(tag, color, HTTP_PORT, "HTTP", [
        "POST /login HTTP/1.1",
        "Host: target.local",
        "Content-Type: application/x-www-form-urlencoded",
        "",
        payload,
    ])


def scenario_port_sweep(tag, color):
    ports = random.sample(
        [(SSH_PORT, "SSH"), (FTP_PORT, "FTP"), (HTTP_PORT, "HTTP")],
        k=random.randint(2, 3)
    )
    log(tag, f"[PORT SWEEP] hitting {[p[1] for p in ports]}", RED)
    for port, label in ports:
        connect_and_send(tag, color, port, label, ["probe"])
        time.sleep(random.uniform(0.3, 0.8))


def scenario_mixed_burst(tag, color):
    log(tag, "[MIXED BURST] varied attacks from same source", RED)
    for _ in range(random.randint(3, 5)):
        fn = random.choice([scenario_ssh_probe, scenario_ftp_probe, scenario_http_request])
        fn(tag, color)
        time.sleep(random.uniform(0.8, 2.0))


SCENARIOS = [
    (scenario_ssh_probe,    20),
    (scenario_ftp_probe,    15),
    (scenario_http_request, 20),
    (scenario_ssh_brute,    15),
    (scenario_ftp_brute,     8),
    (scenario_sql_injection, 12),
    (scenario_port_sweep,    5),
    (scenario_mixed_burst,   5),
]

_pool = []
for fn, weight in SCENARIOS:
    _pool.extend([fn] * weight)


# ── Attacker thread ───────────────────────────────────────────────────────────

def run_attacker(tag, color):
    log(tag, "Started", color)
    while True:
        scenario = random.choice(_pool)
        try:
            scenario(tag, color)
        except Exception as e:
            log(tag, f"Scenario error: {e}", RED)
        time.sleep(random.uniform(3.0, 8.0))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    print(f"\n{BOLD}{'='*60}")
    print("  HDP Continuous Random Attack Test")
    print(f"{'='*60}{RESET}")
    print(f"  {NUM_ATTACKERS} concurrent attackers → honeypot ports 2222/2121/8080")
    print("  Ctrl+C to stop.\n")

    for i in range(NUM_ATTACKERS):
        tag   = f"attacker-{i+1}"
        color = COLORS[i % len(COLORS)]
        t = threading.Thread(target=run_attacker, args=(tag, color), daemon=True)
        t.start()
        time.sleep(0.4)

    log("TEST", f"{NUM_ATTACKERS} attacker(s) running perpetually", GREEN)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("TEST", "Shutting down.", YELLOW)


if __name__ == "__main__":
    main()
