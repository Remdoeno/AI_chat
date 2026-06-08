#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=${PID_FILE:-qwen_web.pid}

if [ ! -f "$PID_FILE" ]; then
  echo "qwen_web pid file not found."
  exit 0
fi

PID=$(cat "$PID_FILE")
if [ -z "$PID" ]; then
  rm -f "$PID_FILE"
  echo "qwen_web pid file was empty."
  exit 0
fi

if ! kill -0 "$PID" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "qwen_web process $PID is not running."
  exit 0
fi

echo "Stopping qwen_web PID $PID"
kill "$PID"

for _ in $(seq 1 20); do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "qwen_web stopped."
    exit 0
  fi
  sleep 0.5
done

echo "qwen_web did not exit after 10s; sending SIGKILL."
kill -9 "$PID" || true
rm -f "$PID_FILE"
echo "qwen_web stopped."
