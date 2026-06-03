"""
HDP Integration Test — Attacker Simulator

Run each component in a separate terminal first:

  Terminal 1 (Event Store):
    python3 event_store.py 127.0.0.1 9001

  Terminal 2 (Central Brain):
    python3 central_brain.py

  Terminal 3 (Honeypot Node):
    javac -cp lib/gson-2.13.1.jar HoneypotNode.java
    java  -cp .:lib/gson-2.13.1.jar HoneypotNode localhost 9000 2222 2121 8080

Then run this file:
  python3 test.py
"""

import socket
import time

HONEYPOT_HOST = "127.0.0.1"
SSH_PORT  = 2222
FTP_PORT  = 2121
HTTP_PORT = 8080

CONNECT_TIMEOUT = 5  # seconds

BOLD    = "\033[1m"
RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
RESET   = "\033[0m"


def log(tag, msg, color=RESET):
    ts = time.strftime("%H:%M:%S")
    print(f"{color}{BOLD}[{ts}][{tag}]{RESET} {msg}")


def attack(port, label, payload_lines, pause=0.3):
    """Connect to a honeypot port as an attacker, receive the fake banner, send payload."""
    log("ATTACKER", f"Connecting to {label} on port {port}", CYAN)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(CONNECT_TIMEOUT)
            s.connect((HONEYPOT_HOST, port))
            banner = s.recv(4096).decode("utf-8", errors="replace").strip()
            log("ATTACKER", f"<-- FAKE_BANNER: {banner!r}", GREEN)
            for line in payload_lines:
                s.sendall((line + "\n").encode("utf-8"))
                log("ATTACKER", f"--> {line!r}")
            time.sleep(pause)
    except ConnectionRefusedError:
        log("ERROR", f"Connection refused on port {port} — is HoneypotNode running?", RED)
    except socket.timeout:
        log("ERROR", f"Timeout on port {port}", RED)
    except Exception as e:
        log("ERROR", str(e), RED)


def section(title):
    print(f"\n{MAGENTA}{BOLD}{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}{RESET}")


def main():
    print(f"\n{BOLD}{'='*60}")
    print("  HDP Integration Test — Attacker Simulator")
    print(f"{'='*60}{RESET}")
    print("Expected flow per attack:")
    print("  Attacker → FAKE_BANNER ← Honeypot")
    print("  Honeypot → EVENT_REPORT → Central Brain")
    print("  Brain    → STORE_EVENT  → Event Store")
    print("  Store    → ACK          → Brain")
    print("  Brain    → CONTROL_COMMAND → Honeypot  (if severity >= 6)")
    print()

    # ── Scenario 1: Normal service probes ─────────────────────────────────────
    section("Scenario 1 — Normal service probes (expect low-severity events)")

    log("SCENARIO", "SSH probe", YELLOW)
    attack(SSH_PORT, "SSH", ["guest"])
    time.sleep(1)

    log("SCENARIO", "FTP probe", YELLOW)
    attack(FTP_PORT, "FTP", ["USER anonymous", "PASS anon@example.com"])
    time.sleep(1)

    log("SCENARIO", "HTTP request", YELLOW)
    attack(HTTP_PORT, "HTTP", [
        "GET /index.html HTTP/1.1",
        "Host: target.local",
    ])
    time.sleep(2)

    # ── Scenario 2: SSH brute force ───────────────────────────────────────────
    # 3+ LOGIN_ATTEMPTs from same IP within 60s → BRUTE_FORCE (severity 8)
    # → Brain sends CONTROL_COMMAND SLOW_RESPONSE to honeypot
    section("Scenario 2 — SSH brute force (expect BRUTE_FORCE + CONTROL_COMMAND SLOW_RESPONSE)")

    for cred in ["root:admin", "root:password", "admin:12345", "pi:raspberry", "ubuntu:ubuntu"]:
        log("SCENARIO", f"SSH login attempt: {cred}", YELLOW)
        attack(SSH_PORT, "SSH", [cred])
        time.sleep(1)

    time.sleep(2)

    # ── Scenario 3: SQL injection via HTTP ────────────────────────────────────
    # SQL keywords in payload → SQL_INJECTION (severity 7)
    # → Brain sends CONTROL_COMMAND SLOW_RESPONSE to honeypot
    section("Scenario 3 — SQL injection via HTTP (expect SQL_INJECTION + CONTROL_COMMAND)")

    log("SCENARIO", "HTTP SQL injection", YELLOW)
    attack(HTTP_PORT, "HTTP", [
        "POST /login HTTP/1.1",
        "Host: target.local",
        "Content-Type: application/x-www-form-urlencoded",
        "",
        "user=admin&pass=' OR 1=1 --",
    ])
    time.sleep(2)

    # ── Scenario 4: FTP login attempts ────────────────────────────────────────
    section("Scenario 4 — FTP login attempts")

    for user in ["admin", "root", "ftp", "oracle", "postgres"]:
        log("SCENARIO", f"FTP login attempt: USER {user}", YELLOW)
        attack(FTP_PORT, "FTP", [f"USER {user}", "PASS wrong123"])
        time.sleep(1)

    time.sleep(2)

    # ── Scenario 5: Mixed burst ───────────────────────────────────────────────
    section("Scenario 5 — Mixed burst from same source IP")

    log("SCENARIO", "Port probe → SSH attempt → HTTP request", YELLOW)
    attack(SSH_PORT,  "SSH",  ["USER root"])
    time.sleep(0.5)
    attack(HTTP_PORT, "HTTP", ["GET /admin HTTP/1.1", "Host: target.local"])
    time.sleep(0.5)
    attack(FTP_PORT,  "FTP",  ["USER root", "PASS toor"])
    time.sleep(2)

    # ── Done ──────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}{'='*60}")
    print("  Test complete.")
    print("  Check server terminals for EVENT_REPORT, STORE_EVENT, ACK,")
    print("  and CONTROL_COMMAND logs.")
    print(f"{'='*60}{RESET}\n")


if __name__ == "__main__":
    main()
