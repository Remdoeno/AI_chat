#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WEB_HOST=${WEB_HOST:-0.0.0.0}
WEB_PORT=${WEB_PORT:-7777}
PYTHON=${PYTHON:-/opt/conda/bin/python3}
LOG_DIR=${LOG_DIR:-logs}
PID_FILE=${PID_FILE:-qwen_web.pid}
LOG_FILE="$LOG_DIR/qwen_web_${WEB_PORT}_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR" data

if [ -z "${QWEN_IDLE_STORY_SEEDS_FILE:-}" ] && [ -f "data/idle_story_seeds.txt" ]; then
  export QWEN_IDLE_STORY_SEEDS_FILE="$PWD/data/idle_story_seeds.txt"
fi

if [ -z "${QWEN_IDLE_ARTIFACT_TERM_REPLACEMENTS:-}" ] && [ -f "data/idle_artifact_term_replacements.json" ]; then
  export QWEN_IDLE_ARTIFACT_TERM_REPLACEMENTS="$(tr -d '\n' < data/idle_artifact_term_replacements.json)"
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "ERROR: qwen_web is already running with PID $OLD_PID"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(:|\\])${WEB_PORT}$"; then
  echo "ERROR: port $WEB_PORT is already in use."
  exit 1
fi

echo "Starting qwen_web on ${WEB_HOST}:${WEB_PORT}"
echo "Log file: $LOG_FILE"

nohup "$PYTHON" -m uvicorn app:app --host "$WEB_HOST" --port "$WEB_PORT" \
  > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"
sleep 2

if ! kill -0 "$PID" >/dev/null 2>&1; then
  echo "ERROR: qwen_web failed to start. Last log lines:"
  tail -n 80 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

echo "qwen_web started with PID $PID"
