#!/usr/bin/env bash
set -euo pipefail

# Run this inside the Qwen server/container.
# It keeps the reverse SSH tunnel alive:
#   Mac/jump host 10022 -> this container localhost:22
#
# Prefer running this script with nohup/tmux/screen, or with a process manager
# if the container has one.

JUMP_USER="${QWEN_JUMP_USER:-rem}"
JUMP_HOST="${QWEN_JUMP_HOST:-183.172.57.234}"
JUMP_SSH_PORT="${QWEN_JUMP_SSH_PORT:-9922}"
REMOTE_SSH_PORT="${QWEN_REMOTE_SSH_PORT:-10022}"
LOCAL_SSH_TARGET="${QWEN_LOCAL_SSH_TARGET:-localhost:22}"
RETRY_SECONDS="${QWEN_REVERSE_SSH_RETRY_SECONDS:-10}"
LOCK_DIR="${QWEN_REVERSE_SSH_LOCK_DIR:-/tmp/qwen_reverse_ssh_watchdog.lock}"
LOG_PREFIX="${QWEN_REVERSE_SSH_LOG_PREFIX:-reverse-ssh}"

if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  printf '%s [%s] watchdog already running: %s\n' "$(date -Is)" "${LOG_PREFIX}" "${LOCK_DIR}"
  exit 0
fi

cleanup() {
  rmdir "${LOCK_DIR}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

printf '%s [%s] watchdog started\n' "$(date -Is)" "${LOG_PREFIX}"
printf '%s [%s] target: %s@%s:%s -R %s:%s\n' \
  "$(date -Is)" "${LOG_PREFIX}" \
  "${JUMP_USER}" "${JUMP_HOST}" "${JUMP_SSH_PORT}" \
  "${REMOTE_SSH_PORT}" "${LOCAL_SSH_TARGET}"

while true; do
  printf '%s [%s] starting reverse tunnel\n' "$(date -Is)" "${LOG_PREFIX}"

  ssh -N \
    -p "${JUMP_SSH_PORT}" \
    -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=2 \
    -o TCPKeepAlive=yes \
    -o ConnectTimeout=15 \
    -R "${REMOTE_SSH_PORT}:${LOCAL_SSH_TARGET}" \
    "${JUMP_USER}@${JUMP_HOST}" || rc=$?

  rc="${rc:-0}"
  printf '%s [%s] tunnel exited rc=%s; retrying in %ss\n' \
    "$(date -Is)" "${LOG_PREFIX}" "${rc}" "${RETRY_SECONDS}"
  unset rc
  sleep "${RETRY_SECONDS}"
done
