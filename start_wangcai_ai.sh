#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WEB_HOST=${WEB_HOST:-0.0.0.0}
WEB_PORT=${WEB_PORT:-7777}
PYTHON=${PYTHON:-/opt/conda/bin/python3}
LOG_DIR=${LOG_DIR:-logs}
PID_FILE=${PID_FILE:-wangcai_ai.pid}
WATCHDOG_SCRIPT=${WANGCAI_BACKGROUND_WATCHDOG_SCRIPT:-$PWD/background_process_watchdog.sh}
WATCHDOG_PID_FILE=${WANGCAI_BACKGROUND_WATCHDOG_PID_FILE:-wangcai_background_watchdog.pid}
WATCHDOG_LOCK_DIR=${WANGCAI_BACKGROUND_WATCHDOG_LOCK_DIR:-/tmp/wangcai_background_process_watchdog.lock}
LOG_FILE="$LOG_DIR/wangcai_ai_${WEB_PORT}_$(date +%Y%m%d_%H%M%S).log"
WATCHDOG_LOG_FILE="$LOG_DIR/background_watchdog_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR" data

if [ -z "${WANGCAI_IDLE_STORY_SEEDS_FILE:-}" ] && [ -f "data/idle_story_seeds.txt" ]; then
  export WANGCAI_IDLE_STORY_SEEDS_FILE="$PWD/data/idle_story_seeds.txt"
fi

if [ -z "${WANGCAI_IDLE_ARTIFACT_TERM_REPLACEMENTS:-}" ] && [ -f "data/idle_artifact_term_replacements.json" ]; then
  export WANGCAI_IDLE_ARTIFACT_TERM_REPLACEMENTS="$(tr -d '\n' < data/idle_artifact_term_replacements.json)"
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "ERROR: wangcai_ai is already running with PID $OLD_PID"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(:|\\])${WEB_PORT}$"; then
  echo "ERROR: port $WEB_PORT is already in use."
  exit 1
fi

echo "Starting wangcai_ai on ${WEB_HOST}:${WEB_PORT}"
echo "Log file: $LOG_FILE"

nohup "$PYTHON" -m uvicorn app:app --host "$WEB_HOST" --port "$WEB_PORT" \
  > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"
sleep 2

if ! kill -0 "$PID" >/dev/null 2>&1; then
  echo "ERROR: wangcai_ai failed to start. Last log lines:"
  tail -n 80 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

echo "wangcai_ai started with PID $PID"

if [ -x "$WATCHDOG_SCRIPT" ]; then
  if [ -f "$WATCHDOG_PID_FILE" ]; then
    OLD_WATCHDOG_PID=$(cat "$WATCHDOG_PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_WATCHDOG_PID" ] && kill -0 "$OLD_WATCHDOG_PID" >/dev/null 2>&1; then
      kill "$OLD_WATCHDOG_PID" >/dev/null 2>&1 || true
      for _ in $(seq 1 20); do
        if ! kill -0 "$OLD_WATCHDOG_PID" >/dev/null 2>&1; then
          break
        fi
        sleep 0.1
      done
    fi
    rm -f "$WATCHDOG_PID_FILE"
  fi
  if [ -d "$WATCHDOG_LOCK_DIR" ]; then
    LOCK_PID=$(cat "$WATCHDOG_LOCK_DIR/pid" 2>/dev/null || true)
    if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" >/dev/null 2>&1; then
      echo "ERROR: background process watchdog lock belongs to live PID $LOCK_PID"
      exit 1
    fi
    rm -f "$WATCHDOG_LOCK_DIR/pid"
    rmdir "$WATCHDOG_LOCK_DIR" 2>/dev/null || true
  fi
  nohup env WANGCAI_PID_FILE="$PID_FILE" "$WATCHDOG_SCRIPT" \
    > "$WATCHDOG_LOG_FILE" 2>&1 &
  WATCHDOG_PID=$!
  echo "$WATCHDOG_PID" > "$WATCHDOG_PID_FILE"
  sleep 0.5
  if ! kill -0 "$WATCHDOG_PID" >/dev/null 2>&1; then
    echo "ERROR: background process watchdog failed to start. Last log lines:"
    tail -n 40 "$WATCHDOG_LOG_FILE" || true
    rm -f "$WATCHDOG_PID_FILE"
    exit 1
  fi
  echo "Background process watchdog started with PID $WATCHDOG_PID"
  echo "Watchdog log file: $WATCHDOG_LOG_FILE"
fi
