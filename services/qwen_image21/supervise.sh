#!/usr/bin/env bash
# Dedicated service supervisor. Do not manage or restart other model processes.
set -u
BASE=${QWEN_IMAGE_SERVICE_DIR:-/base/home/lizhzh/Project3/imggen/qwen_image21}
mkdir -p "$BASE/logs"
exec 9>"$BASE/supervisor.lock"
flock -n 9 || exit 0
child=""
trap 'if [ -n "$child" ]; then kill -TERM "$child" 2>/dev/null; wait "$child"; fi; exit 0' TERM INT
while true; do
  bash "$BASE/run.sh" >> "$BASE/logs/service.log" 2>&1 &
  child=$!
  echo "$child" > "$BASE/service.pid"
  wait "$child"
  child=""
  sleep 30 & child=$!
  wait "$child"
  child=""
done
