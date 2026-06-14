#!/usr/bin/env bash
set -euo pipefail

# Run this on the Mac/local terminal after server_start_reverse_ssh.sh is active.
# It exposes the Qwen web app as http://127.0.0.1:19922/ and, with -g,
# also allows LAN clients to reach http://<this-mac-ip>:19922/.

SSH_KEY="${QWEN_SERVER_SSH_KEY:-$HOME/.ssh/icfc}"
SERVER_SSH_HOST="${QWEN_SERVER_SSH_HOST:-127.0.0.1}"
SERVER_SSH_PORT="${QWEN_SERVER_SSH_PORT:-10022}"
SERVER_USER="${QWEN_SERVER_USER:-root}"
LOCAL_WEB_PORT="${QWEN_LOCAL_WEB_PORT:-19922}"
LOCAL_TUNNEL_PORT="${QWEN_LOCAL_TUNNEL_PORT:-19923}"
REMOTE_WEB_HOST="${QWEN_REMOTE_WEB_HOST:-127.0.0.1}"
REMOTE_WEB_PORT="${QWEN_REMOTE_WEB_PORT:-9922}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_SCRIPT="${QWEN_IP_PROXY_SCRIPT:-${SCRIPT_DIR}/qwen_ip_proxy.py}"
LOG_DIR="${QWEN_TUNNEL_LOG_DIR:-${SCRIPT_DIR}/../log}"
PROXY_PID_FILE="${QWEN_IP_PROXY_PID_FILE:-${LOG_DIR}/qwen_ip_proxy_${LOCAL_WEB_PORT}.pid}"
PROXY_LOG_FILE="${QWEN_IP_PROXY_LOG_FILE:-${LOG_DIR}/qwen_ip_proxy_${LOCAL_WEB_PORT}.log}"
AUTO_BIND_HOST="$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" && $2 !~ /^169[.]254[.]/ {print $2; exit}')"
if [ -n "${QWEN_LOCAL_BIND_HOSTS:-}" ]; then
  LOCAL_BIND_HOSTS="${QWEN_LOCAL_BIND_HOSTS}"
elif [ -n "${AUTO_BIND_HOST}" ]; then
  LOCAL_BIND_HOSTS="127.0.0.1,${AUTO_BIND_HOST}"
else
  LOCAL_BIND_HOSTS="127.0.0.1"
fi

if ! ssh -i "${SSH_KEY}" \
  -p "${SERVER_SSH_PORT}" \
  -o BatchMode=yes \
  -o ConnectTimeout=8 \
  "${SERVER_USER}@${SERVER_SSH_HOST}" \
  "curl -fsS --max-time 8 http://${REMOTE_WEB_HOST}:${REMOTE_WEB_PORT}/api/health >/dev/null"; then
  printf '%s\n' "Server SSH or qwen_web health check failed."
  printf '%s\n' "First run scripts/server_start_reverse_ssh.sh inside the server/container."
  exit 1
fi

mkdir -p "${LOG_DIR}"

listener_pids="$(lsof -tiTCP:"${LOCAL_WEB_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
tunnel_pids="$(lsof -tiTCP:"${LOCAL_TUNNEL_PORT}" -sTCP:LISTEN 2>/dev/null || true)"
all_pids="$(printf '%s\n%s\n' "${listener_pids}" "${tunnel_pids}" | awk 'NF' | sort -u)"
if [ -n "${all_pids}" ]; then
  printf '%s\n' "Recreating listener(s) on ${LOCAL_WEB_PORT}/${LOCAL_TUNNEL_PORT}: ${all_pids}"
  kill ${all_pids}
  for _ in {1..20}; do
    remaining_pids="$(
      {
        lsof -tiTCP:"${LOCAL_WEB_PORT}" -sTCP:LISTEN 2>/dev/null || true
        lsof -tiTCP:"${LOCAL_TUNNEL_PORT}" -sTCP:LISTEN 2>/dev/null || true
      } | awk 'NF' | sort -u
    )"
    if [ -z "${remaining_pids}" ]; then
      break
    fi
    sleep 0.25
  done
  if [ -n "${remaining_pids:-}" ]; then
    printf '%s\n' "Listener(s) did not stop after SIGTERM, forcing: ${remaining_pids}"
    kill -9 ${remaining_pids}
    sleep 0.5
  fi
fi
if [ -f "${PROXY_PID_FILE}" ]; then
  old_proxy_pid="$(cat "${PROXY_PID_FILE}" 2>/dev/null || true)"
  if [ -n "${old_proxy_pid}" ]; then
    kill "${old_proxy_pid}" 2>/dev/null || true
  fi
  rm -f "${PROXY_PID_FILE}"
fi

ssh -i "${SSH_KEY}" \
  -f -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -p "${SERVER_SSH_PORT}" \
  -L "127.0.0.1:${LOCAL_TUNNEL_PORT}:${REMOTE_WEB_HOST}:${REMOTE_WEB_PORT}" \
  "${SERVER_USER}@${SERVER_SSH_HOST}"

/usr/bin/env python3 "${PROXY_SCRIPT}" \
  --bind-hosts "${LOCAL_BIND_HOSTS}" \
  --bind-port "${LOCAL_WEB_PORT}" \
  --upstream-host "127.0.0.1" \
  --upstream-port "${LOCAL_TUNNEL_PORT}" \
  --daemon \
  --pid-file "${PROXY_PID_FILE}" \
  --log-file "${PROXY_LOG_FILE}"

sleep 1
curl -fsS --max-time 8 "http://127.0.0.1:${LOCAL_WEB_PORT}/api/health" >/dev/null
printf '%s\n' "Qwen web ready: http://127.0.0.1:${LOCAL_WEB_PORT}/"
printf '%s\n' "Bind hosts: ${LOCAL_BIND_HOSTS}"
printf '%s\n' "IP proxy: ${LOCAL_WEB_PORT} -> local tunnel ${LOCAL_TUNNEL_PORT} -> ${REMOTE_WEB_HOST}:${REMOTE_WEB_PORT}"
