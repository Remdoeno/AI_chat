#!/usr/bin/env bash
set -euo pipefail
BASE=${QWEN_IMAGE_SERVICE_DIR:-/base/home/lizhzh/Project3/imggen/qwen_image21}
export CUDA_VISIBLE_DEVICES=${QWEN_IMAGE_GPU:-0}
export LD_LIBRARY_PATH=/opt/conda/lib:${LD_LIBRARY_PATH:-}
export QWEN_IMAGE_MODEL_PATH=${QWEN_IMAGE_MODEL_PATH:-$BASE/models/Qwen-Image-2.1}
export HF_HUB_OFFLINE=1
export PYTHONUNBUFFERED=1
cd "$BASE"
exec "$BASE/venv/bin/python" -m uvicorn server:app --host 127.0.0.1 --port 8003 --workers 1
