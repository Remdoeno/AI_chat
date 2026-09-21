# Optional Qwen-Image-2.1 service

Separate environment and process from HiDream and Wangcai. Bind to loopback only.
The checkpoint is subject to the Qwen Research License; this deployment is for evaluation.

Runtime verified with Python 3.11, Diffusers source commit 80c7ed262aeffbeb43ef13ae04baeb9b84515a69,
Transformers 5.17.0. Use an isolated environment; do not upgrade the HiDream environment.
Download `Qwen/Qwen-Image-2.1` weights separately; never commit them.

Set QWEN_IMAGE_SERVICE_DIR, QWEN_IMAGE_MODEL_PATH and QWEN_IMAGE_GPU, then execute run.sh.
Health: GET /health. Generation: POST /v1/images/generations (one PNG per request).
The service accepts refs_b64 for optional reference images and returns data[].b64_json.
Only one GPU generation runs at a time; concurrent calls receive 429. The web app calls
sequentially for a multi-image batch. No automatic fallback to HiDream after Qwen failures.

Select “本地 Qwen-Image-2.1（对比试用）” in the existing image-model settings.
The system default stays unchanged; per-user model selection follows existing isolation.
