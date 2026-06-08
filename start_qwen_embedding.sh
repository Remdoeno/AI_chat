#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

EMBED_HOST=${EMBED_HOST:-0.0.0.0}
EMBED_PORT=${EMBED_PORT:-8001}
EMBED_GPUS=${EMBED_GPUS:-1}
EMBED_MODEL_DIR=${EMBED_MODEL_DIR:-locomo_rram_memory/models/Qwen3-Embedding-8B}
EMBED_MODEL_NAME=${EMBED_MODEL_NAME:-qwen3-embedding-8b}
EMBED_GPU_MEMORY_UTIL=${EMBED_GPU_MEMORY_UTIL:-0.35}
EMBED_MAX_MODEL_LEN=${EMBED_MAX_MODEL_LEN:-40960}
LOG_DIR=${LOG_DIR:-qwen_web/logs}
PID_FILE=${PID_FILE:-qwen_web/qwen_embedding.pid}
LOG_FILE="$LOG_DIR/qwen_embedding_${EMBED_PORT}_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "ERROR: qwen embedding service already running with PID $OLD_PID"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if [ ! -f "$EMBED_MODEL_DIR/config.json" ]; then
  echo "ERROR: embedding model config not found: $EMBED_MODEL_DIR/config.json"
  exit 1
fi

export PATH=/opt/conda/bin:$PATH
export LD_LIBRARY_PATH=/opt/conda/lib:/opt/conda/lib64:${LD_LIBRARY_PATH:-}
export LIBRARY_PATH=/opt/conda/lib:/opt/conda/lib64:${LIBRARY_PATH:-}
export NO_PROXY=127.0.0.1,localhost,0.0.0.0
export no_proxy=127.0.0.1,localhost,0.0.0.0

echo "Starting Qwen embedding service on ${EMBED_HOST}:${EMBED_PORT}"
echo "Model: $EMBED_MODEL_DIR"
echo "GPU: $EMBED_GPUS"
echo "Log file: $LOG_FILE"

CUDA_VISIBLE_DEVICES="$EMBED_GPUS" nohup /opt/conda/bin/vllm serve "$EMBED_MODEL_DIR" \
  --served-model-name "$EMBED_MODEL_NAME" \
  --host "$EMBED_HOST" \
  --port "$EMBED_PORT" \
  --dtype bfloat16 \
  --runner pooling \
  --convert embed \
  --max-model-len "$EMBED_MAX_MODEL_LEN" \
  --gpu-memory-utilization "$EMBED_GPU_MEMORY_UTIL" \
  --trust-remote-code \
  > "$LOG_FILE" 2>&1 &

PID=$!
echo "$PID" > "$PID_FILE"
sleep 3

if ! kill -0 "$PID" >/dev/null 2>&1; then
  echo "ERROR: qwen embedding service failed to start. Last log lines:"
  tail -n 120 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

echo "qwen embedding service started with PID $PID"
