#!/usr/bin/env bash

# ─── Configuration ────────────────────────────────────────────────────────────

#PROJECT_DIR="/home/ecopipeline/PycharmProjects/ptr-pipe"
#WRAPPER="$PROJECT_DIR/run_watcher.sh"
WRAPPER="run_watcher.sh"
SCRIPT_PATTERN="thewatcher.py"
CHECK_INTERVAL=30

# ─── Launcher ────────────────────────────────────────────────────────────────

start_watcher() {
  echo "$(date +'%F %T') ▶ Starting watcher…"
  xfce4-terminal \
    --title="thewatcher.py" \
#    --working-directory="$PROJECT_DIR" \
    --hold \
    --command "bash -lc '$WRAPPER'"
}

# ─── Main Loop ───────────────────────────────────────────────────────────────

# 1) Kick off the first watcher
start_watcher

# 2) Poll every $CHECK_INTERVAL seconds
while sleep "$CHECK_INTERVAL"; do
  # Look for ANY python3 process running your script
  if ! pgrep -f "python3 .*$SCRIPT_PATTERN" >/dev/null; then
    echo "$(date +'%F %T') ⚠ watcher died—restarting…"
    start_watcher
  fi
done

