#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PID_FILE=${PID_FILE:-wangcai_ai/wangcai_embedding.pid}

if [ ! -f "$PID_FILE" ]; then
  echo "wangcai embedding pid file not found."
  exit 0
fi

PID=$(cat "$PID_FILE")
if [ -z "$PID" ]; then
  rm -f "$PID_FILE"
  echo "wangcai embedding pid file was empty."
  exit 0
fi

if ! kill -0 "$PID" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "wangcai embedding process $PID is not running."
  exit 0
fi

echo "Stopping wangcai embedding PID $PID"
kill "$PID"

for _ in $(seq 1 30); do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "wangcai embedding stopped."
    exit 0
  fi
  sleep 1
done

echo "wangcai embedding did not exit after 30s; sending SIGKILL."
kill -9 "$PID" || true
rm -f "$PID_FILE"
echo "wangcai embedding stopped."
