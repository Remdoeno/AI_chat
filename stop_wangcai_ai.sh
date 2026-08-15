#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=${PID_FILE:-wangcai_ai.pid}
WATCHDOG_PID_FILE=${WANGCAI_BACKGROUND_WATCHDOG_PID_FILE:-wangcai_background_watchdog.pid}
WATCHDOG_LOCK_DIR=${WANGCAI_BACKGROUND_WATCHDOG_LOCK_DIR:-/tmp/wangcai_background_process_watchdog.lock}

if [ -f "$WATCHDOG_PID_FILE" ]; then
  WATCHDOG_PID=$(cat "$WATCHDOG_PID_FILE" 2>/dev/null || true)
  if [ -n "$WATCHDOG_PID" ] && kill -0 "$WATCHDOG_PID" >/dev/null 2>&1; then
    echo "Stopping background process watchdog PID $WATCHDOG_PID"
    kill "$WATCHDOG_PID" >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$WATCHDOG_PID" >/dev/null 2>&1; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "$WATCHDOG_PID" >/dev/null 2>&1; then
      echo "Background process watchdog did not exit after 2s; sending SIGKILL."
      kill -9 "$WATCHDOG_PID" >/dev/null 2>&1 || true
    fi
  fi
  rm -f "$WATCHDOG_PID_FILE"
  rm -f "$WATCHDOG_LOCK_DIR/pid"
  rmdir "$WATCHDOG_LOCK_DIR" 2>/dev/null || true
fi

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
