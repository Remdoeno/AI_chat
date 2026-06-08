#!/usr/bin/env bash
set -euo pipefail

# Run this inside the Qwen server/container.
# It keeps qwen_web on container port 9922 and exposes container SSH
# back to the Mac/jump host as 127.0.0.1:10022.

JUMP_USER="${QWEN_JUMP_USER:-rem}"
JUMP_HOST="${QWEN_JUMP_HOST:-183.172.57.234}"
JUMP_SSH_PORT="${QWEN_JUMP_SSH_PORT:-9922}"
REMOTE_SSH_PORT="${QWEN_REMOTE_SSH_PORT:-10022}"
LOCAL_SSH_TARGET="${QWEN_LOCAL_SSH_TARGET:-localhost:22}"
QWEN_WEB_DIR="${QWEN_WEB_DIR:-/base/home/lizhzh/Project3/qwen_web}"
QWEN_WEB_PORT="${QWEN_WEB_PORT:-9922}"
WATCHDOG_SCRIPT="${QWEN_REVERSE_SSH_WATCHDOG_SCRIPT:-${QWEN_WEB_DIR}/server_reverse_ssh_watchdog.sh}"
WATCHDOG_LOG="${QWEN_REVERSE_SSH_WATCHDOG_LOG:-${QWEN_WEB_DIR}/logs/reverse_ssh_watchdog.log}"

cd "${QWEN_WEB_DIR}"
mkdir -p logs

if ! curl -fsS --max-time 5 "http://127.0.0.1:${QWEN_WEB_PORT}/api/health" >/dev/null 2>&1; then
  ./start_qwen_web.sh
  sleep 2
fi

curl -fsS --max-time 10 "http://127.0.0.1:${QWEN_WEB_PORT}/api/health" >/dev/null

existing="$(pgrep -af "ssh .* -R ${REMOTE_SSH_PORT}:${LOCAL_SSH_TARGET} .*${JUMP_HOST}" || true)"
if [ -n "${existing}" ]; then
  printf '%s\n' "Reverse SSH tunnel already running:"
  printf '%s\n' "${existing}"
  exit 0
fi

if [ -x "${WATCHDOG_SCRIPT}" ]; then
  nohup "${WATCHDOG_SCRIPT}" >> "${WATCHDOG_LOG}" 2>&1 &
  printf '%s\n' "Reverse SSH watchdog started. Log: ${WATCHDOG_LOG}"
  sleep 1
else
  ssh -f -N \
    -p "${JUMP_SSH_PORT}" \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    -R "${REMOTE_SSH_PORT}:${LOCAL_SSH_TARGET}" \
    "${JUMP_USER}@${JUMP_HOST}"
fi

printf '%s\n' "Reverse SSH ready: ${JUMP_HOST}:${REMOTE_SSH_PORT} -> ${LOCAL_SSH_TARGET}"
