#!/bin/bash
# Starts all four HDP components in a tmux session with one pane each.
# Usage: ./run.sh
# Requires: tmux  (brew install tmux)

set -e

SESSION="hdp"
DIR="$(cd "$(dirname "$0")" && pwd)"

if ! command -v tmux &>/dev/null; then
    echo "tmux not found. Install with: brew install tmux"
    exit 1
fi

echo "Compiling HoneypotNode.java..."
javac -cp "$DIR/honeypot-node/lib/gson-2.13.1.jar" "$DIR/honeypot-node/HoneypotNode.java"
echo "Done."

# Kill any existing session
tmux kill-session -t $SESSION 2>/dev/null || true

# ┌──────────────────┬──────────────────┐
# │    Attacker      │  Honeypot Node   │
# ├──────────────────┼──────────────────┤
# │   Event Store    │  Central Brain   │
# └──────────────────┴──────────────────┘

# Pane 0 — Attacker (top-left)
tmux new-session -d -s $SESSION \
    "cd '$DIR/tests' && sleep 1.5 && python3 test.py; echo '[Attacker stopped]'; read"

# Pane 1 — Honeypot Node (top-right) — split right side first
tmux split-window -h -t "${SESSION}:0.0" \
    "cd '$DIR/honeypot-node' && sleep 1.0 && java -cp '.:lib/gson-2.13.1.jar' HoneypotNode localhost 9000 2222 2121 8080; echo '[Honeypot stopped]'; read"

# Pane 2 — Central Brain (bottom-right) — split the right pane before touching the left
tmux split-window -v -t "${SESSION}:0.1" \
    "cd '$DIR/central-brain' && sleep 0.5 && python3 central_brain.py; echo '[Central Brain stopped]'; read"

# Pane 3 — Event Store (bottom-left) — now split the left pane
tmux split-window -v -t "${SESSION}:0.0" \
    "cd '$DIR/event-store' && python3 event_store.py 127.0.0.1 9001; echo '[Event Store stopped]'; read"

tmux attach-session -t $SESSION
