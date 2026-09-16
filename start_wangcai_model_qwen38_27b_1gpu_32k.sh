#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [ ! -d "locomo_rram_memory" ] && [ -d "../locomo_rram_memory" ]; then
  cd ..
fi

KILL_OLD=${KILL_OLD:-0}
MODEL_DIR=${MODEL_DIR:-locomo_rram_memory/models/Qwen3.8-27B}
MODEL_NAME=${MODEL_NAME:-qwen3.8-27b}
PORT=${PORT:-8000}
GPUS=${GPUS:-7}
TP_SIZE=${TP_SIZE:-1}
CONTEXT_LEN=${CONTEXT_LEN:-32768}
GPU_MEMORY_UTIL=${GPU_MEMORY_UTIL:-0.92}
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-8192}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-2}
GDN_PREFILL_BACKEND=${GDN_PREFILL_BACKEND:-triton}
ENABLE_COT=${ENABLE_COT:-0}

export PATH=/opt/conda/bin:$PATH
mkdir -p "$HOME/cuda_stub_lib"
CUDA_LIB=$(find /usr /opt /usr/local -name "libcuda.so.1" 2>/dev/null | head -n 1)
if [ -z "$CUDA_LIB" ]; then
  echo "ERROR: libcuda.so.1 not found."
  exit 1
fi
ln -sf "$CUDA_LIB" "$HOME/cuda_stub_lib/libcuda.so"

CU13_INC=/opt/conda/lib/python3.11/site-packages/nvidia/cu13/include
CU13_LIB=/opt/conda/lib/python3.11/site-packages/nvidia/cu13/lib
CUBLAS_INC=/opt/conda/lib/python3.11/site-packages/nvidia/cublas/include
CUBLAS_LIB=/opt/conda/lib/python3.11/site-packages/nvidia/cublas/lib

for include_dir in "$CU13_INC" "$CUBLAS_INC"; do
  if [ -d "$include_dir" ]; then
    export CPATH="$include_dir:${CPATH:-}"
    export CPLUS_INCLUDE_PATH="$include_dir:${CPLUS_INCLUDE_PATH:-}"
  fi
done

export LD_LIBRARY_PATH="$HOME/cuda_stub_lib:/opt/conda/lib:/opt/conda/lib64:${LD_LIBRARY_PATH:-}"
export LIBRARY_PATH="$HOME/cuda_stub_lib:/opt/conda/lib:/opt/conda/lib64:${LIBRARY_PATH:-}"
for library_dir in "$CU13_LIB" "$CUBLAS_LIB"; do
  if [ -d "$library_dir" ]; then
    export LD_LIBRARY_PATH="$library_dir:$LD_LIBRARY_PATH"
    export LIBRARY_PATH="$library_dir:$LIBRARY_PATH"
  fi
done

export NO_PROXY=127.0.0.1,localhost,0.0.0.0
export no_proxy=127.0.0.1,localhost,0.0.0.0
export NCCL_DEBUG=${NCCL_DEBUG:-WARN}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-8}
export VLLM_USE_FLASHINFER_SAMPLER=0

if [ ! -f "$MODEL_DIR/config.json" ] || [ ! -f "$MODEL_DIR/model.safetensors.index.json" ]; then
  echo "ERROR: incomplete model directory: $MODEL_DIR"
  exit 1
fi

port_pids=""
if command -v lsof >/dev/null 2>&1; then
  port_pids=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u || true)
fi
if [ -n "$port_pids" ]; then
  if [ "$KILL_OLD" != "1" ]; then
    echo "ERROR: port $PORT is already in use by PID(s): $port_pids"
    exit 1
  fi
  echo "Stopping existing service on port $PORT: $port_pids"
  kill $port_pids 2>/dev/null || true
  for _ in $(seq 1 30); do
    sleep 1
    remaining=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u || true)
    [ -z "$remaining" ] && break
  done
  remaining=$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u || true)
  if [ -n "$remaining" ]; then
    kill -9 $remaining 2>/dev/null || true
  fi
fi

LOG_DIR=${LOG_DIR:-locomo_rram_memory/logs}
LOG_FILE=${LOG_FILE:-$LOG_DIR/vllm_qwen38_27b_tp${TP_SIZE}_${CONTEXT_LEN}_gpu${GPUS//,/-}.log}
mkdir -p "$LOG_DIR"

VLLM_ARGS=(
  serve "$MODEL_DIR"
  --served-model-name "$MODEL_NAME"
  --host 0.0.0.0
  --port "$PORT"
  --dtype bfloat16
  --tensor-parallel-size "$TP_SIZE"
  --max-model-len "$CONTEXT_LEN"
  --gpu-memory-utilization "$GPU_MEMORY_UTIL"
  --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS"
  --max-num-seqs "$MAX_NUM_SEQS"
  --attention-backend FLASH_ATTN
  --gdn-prefill-backend "$GDN_PREFILL_BACKEND"
  --generation-config vllm
  --trust-remote-code
  --enforce-eager
  --disable-custom-all-reduce
)
if [ "$ENABLE_COT" = "1" ]; then
  VLLM_ARGS+=(--reasoning-parser qwen3)
fi

echo "Starting $MODEL_NAME from $MODEL_DIR on GPU $GPUS, port $PORT"
echo "Context=$CONTEXT_LEN, max sequences=$MAX_NUM_SEQS, memory utilization=$GPU_MEMORY_UTIL"
echo "Log file: $LOG_FILE"

CUDA_VISIBLE_DEVICES="$GPUS" /opt/conda/bin/vllm "${VLLM_ARGS[@]}" 2>&1 | tee "$LOG_FILE"
