#!/usr/bin/env bash

# ─── Configuration ────────────────────────────────────────────────────────────

#PROJECT_DIR="/home/ecopipeline/PycharmProjects/ptr-pipe"
#WRAPPER="$PROJECT_DIR/run_watcher.sh"
PIDFILE="thewatcher.pid"
WRAPPER="./run_watcher.sh"
SCRIPT_PATTERN="thewatcher.py"
CHECK_INTERVAL=30

# ─── Launcher ────────────────────────────────────────────────────────────────

start_watcher() {
  echo "$(date +'%F %T') ▶ Starting watcher…"
  xfce4-terminal \
    --title="thewatcher.py" \
    --hold \
    --command "bash -lc '$WRAPPER'"
}

watchdog_loop() {
  # If there's no PID file, or the process inside it is gone, restart
  if [[ ! -f "$PIDFILE" ]]; then
    echo "$(date +'%F %T') ⚠ PID file missing—starting watcher"
    start_watcher
    return
  fi

  pid=$(<"$PIDFILE")
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "$(date +'%F %T') ⚠ Process $pid not running—restarting watcher"
    start_watcher
  fi
}

# ─── Main Loop ───────────────────────────────────────────────────────────────

# 1) Kick off the first watcher
start_watcher

while sleep "$CHECK_INTERVAL"; do
  watchdog_loop
done

## 2) Poll every $CHECK_INTERVAL seconds
#while sleep "$CHECK_INTERVAL"; do
#  # Look for ANY python3 process running your script
#  if ! pgrep -f "python3 .*$SCRIPT_PATTERN" >/dev/null; then
#    echo "$(date +'%F %T') ⚠ watcher died—restarting…"
##    start_watcher
#  fi
#done

