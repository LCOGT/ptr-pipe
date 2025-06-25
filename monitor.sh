#!/usr/bin/env bash
set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────────────
PIDFILE="thewatcher.pid"      # run_watcher.sh must write this
HEARTBEAT="thewatcher.hbeat"  # thewatcher.py must touch this
WATCHER_LOG="watcher.log"     # thewatcher.py must append to this
WRAPPER="./run_watcher.sh"    # launcher, must be executable

CHECK_INTERVAL=60             # seconds between checks
STALE_LIMIT=$(( CHECK_INTERVAL * 2 ))  # seconds before we treat a file as stale

# ─── Helpers ─────────────────────────────────────────────────────────────────

start_watcher() {
  echo "$(date +'%F %T') ▶ Starting watcher…"
  rm -f "$HEARTBEAT"
  xfce4-terminal \
    --title="thewatcher.py" \
    --hold \
    --command "bash -lc '$WRAPPER'"
  sleep 2  # give watcher time to write PID, heartbeat, and first log entry
}

restart_watcher() {
  echo "$(date +'%F %T') ⚠ Restarting watcher…"
  [[ -f $PIDFILE ]] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
  rm -f "$PIDFILE" "$HEARTBEAT"
  start_watcher
}

check_pid() {
  [[ -f $PIDFILE ]] || { echo "   → PID file missing"; return 1; }
  pid=$(<"$PIDFILE")
  kill -0 "$pid" 2>/dev/null || { echo "   → PID $pid not running"; return 1; }
}

check_heartbeat() {
  [[ -f $HEARTBEAT ]] || { echo "   → Heartbeat missing"; return 1; }
  age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT") ))
  (( age <= STALE_LIMIT )) || { echo "   → Heartbeat stale (${age}s > ${STALE_LIMIT}s)"; return 1; }
}

check_log_activity() {
  [[ -f $WATCHER_LOG ]] || { echo "   → watcher.log missing"; return 1; }
  age=$(( $(date +%s) - $(stat -c %Y "$WATCHER_LOG") ))
  (( age <= STALE_LIMIT )) || { echo "   → watcher.log stale (${age}s > ${STALE_LIMIT}s)"; return 1; }
}

# ─── Main Loop ───────────────────────────────────────────────────────────────

# 1) Kick off the watcher
start_watcher

# 2) Health‐check loop
while true; do
  sleep "$CHECK_INTERVAL"
  echo "$(date +'%F %T') ● Monitor heartbeat: still running"

  if ! check_pid;          then restart_watcher; continue; fi
  if ! check_heartbeat;    then restart_watcher; continue; fi
  if ! check_log_activity; then restart_watcher; continue; fi

  echo "   → All checks passed"
done

