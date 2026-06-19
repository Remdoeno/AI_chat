#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=${PID_FILE:-wangcai_ai.pid}

if [ ! -f "$PID_FILE" ]; then
  echo "wangcai_ai pid file not found."
  exit 0
fi

PID=$(cat "$PID_FILE")
if [ -z "$PID" ]; then
  rm -f "$PID_FILE"
  echo "wangcai_ai pid file was empty."
  exit 0
fi

if ! kill -0 "$PID" >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "wangcai_ai process $PID is not running."
  exit 0
fi

echo "Stopping wangcai_ai PID $PID"
kill "$PID"

for _ in $(seq 1 20); do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "wangcai_ai stopped."
    exit 0
  fi
  sleep 0.5
done

echo "wangcai_ai did not exit after 10s; sending SIGKILL."
kill -9 "$PID" || true
rm -f "$PID_FILE"
echo "wangcai_ai stopped."
