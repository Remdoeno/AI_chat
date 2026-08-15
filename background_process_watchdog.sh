#!/usr/bin/env bash
set -uo pipefail

cd "$(dirname "$0")"

CHECK_INTERVAL_SECONDS=${WANGCAI_BACKGROUND_WATCHDOG_INTERVAL:-30}
RESTART_COOLDOWN_SECONDS=${WANGCAI_BACKGROUND_WATCHDOG_COOLDOWN:-180}
HIDREAM_MAX_THREADS=${WANGCAI_HIDREAM_MAX_THREADS:-1000}
HIDREAM_HIGH_THREAD_CHECKS_REQUIRED=${WANGCAI_HIDREAM_HIGH_THREAD_CHECKS_REQUIRED:-10}
HIDREAM_MISSING_CHECKS_REQUIRED=${WANGCAI_HIDREAM_MISSING_CHECKS_REQUIRED:-2}
WANGCAI_PID_FILE=${WANGCAI_PID_FILE:-wangcai_ai.pid}
HIDREAM_PID_FILE=${WANGCAI_HIDREAM_PID_FILE:-/base/home/lizhzh/Project3/imggen/hidream_o1_dev_8002.pid}
HIDREAM_START_SCRIPT=${WANGCAI_HIDREAM_START_SCRIPT:-/base/home/lizhzh/Project3/imggen/start_hidream_o1_dev_8002.sh}
HIDREAM_GPU=${WANGCAI_HIDREAM_GPU:-6}
LOCK_DIR=${WANGCAI_BACKGROUND_WATCHDOG_LOCK_DIR:-/tmp/wangcai_background_process_watchdog.lock}

log() {
  printf '%s [background-watchdog] %s\n' "$(date -Is)" "$*"
}

read_pid() {
  local path="$1"
  [ -f "$path" ] || return 1
  local pid
  pid=$(tr -cd '0-9' < "$path")
  [ -n "$pid" ] || return 1
  printf '%s' "$pid"
}

process_threads() {
  local pid="$1"
  awk '/^Threads:/ {print $2}' "/proc/$pid/status" 2>/dev/null
}

restart_hidream() {
  if [ ! -x "$HIDREAM_START_SCRIPT" ]; then
    log "cannot restart HiDream: missing executable $HIDREAM_START_SCRIPT"
    return 1
  fi
  log "restarting HiDream on GPU $HIDREAM_GPU"
  GPU="$HIDREAM_GPU" "$HIDREAM_START_SCRIPT"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  log "already running"
  exit 0
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"
cleanup_watchdog() {
  rm -f "$LOCK_DIR/pid"
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup_watchdog EXIT
trap 'exit 0' INT TERM

log "started; interval=${CHECK_INTERVAL_SECONDS}s hidream_max_threads=$HIDREAM_MAX_THREADS sustained_checks=$HIDREAM_HIGH_THREAD_CHECKS_REQUIRED"
hidream_high_thread_checks=0
hidream_missing_checks=0
last_restart_epoch=0

while true; do
  wangcai_pid=$(read_pid "$WANGCAI_PID_FILE" || true)
  if [ -z "$wangcai_pid" ] || ! kill -0 "$wangcai_pid" 2>/dev/null; then
    log "Wangcai is no longer running; watchdog exits"
    exit 0
  fi

  hidream_pid=$(read_pid "$HIDREAM_PID_FILE" || true)
  hidream_threads=""
  if [ -z "$hidream_pid" ] || ! kill -0 "$hidream_pid" 2>/dev/null; then
    hidream_missing_checks=$((hidream_missing_checks + 1))
    hidream_high_thread_checks=0
    log "HiDream process is missing (${hidream_missing_checks}/${HIDREAM_MISSING_CHECKS_REQUIRED})"
  else
    hidream_missing_checks=0
    hidream_threads=$(process_threads "$hidream_pid" || true)
    if [ -n "$hidream_threads" ] && [ "$hidream_threads" -gt "$HIDREAM_MAX_THREADS" ]; then
      hidream_high_thread_checks=$((hidream_high_thread_checks + 1))
      log "HiDream thread count remains high: pid=$hidream_pid threads=$hidream_threads (${hidream_high_thread_checks}/${HIDREAM_HIGH_THREAD_CHECKS_REQUIRED})"
    else
      hidream_high_thread_checks=0
    fi
  fi

  now_epoch=$(date +%s)
  if { [ "$hidream_missing_checks" -ge "$HIDREAM_MISSING_CHECKS_REQUIRED" ] \
      || [ "$hidream_high_thread_checks" -ge "$HIDREAM_HIGH_THREAD_CHECKS_REQUIRED" ]; } \
      && [ $((now_epoch - last_restart_epoch)) -ge "$RESTART_COOLDOWN_SECONDS" ]; then
    if restart_hidream; then
      last_restart_epoch=$now_epoch
      hidream_missing_checks=0
      hidream_high_thread_checks=0
    fi
  fi

  sleep "$CHECK_INTERVAL_SECONDS"
done
