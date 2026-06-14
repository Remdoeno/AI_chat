# Docker 内 Qwen3.6 与 Embedding 启动流程

以下命令都在 Docker 服务器里执行。先从 Mac 进入 Docker：

```bash
ssh -i ~/.ssh/icfc -p 10022 root@127.0.0.1 -t 'cd /base/home/lizhzh && exec bash'
```

## 1. 查看 GPU 与端口

优先使用靠后的空闲 GPU，例如 `5,6,7`。当前推荐：embedding 用 `5`，Qwen 主模型用 `6,7`。

```bash
cd /base/home/lizhzh/Project3
nvidia-smi
netstat -lntp 2>/dev/null | grep -E ':(8000|8001|9922)' || true
curl -sS --max-time 5 http://127.0.0.1:8000/v1/models || true
curl -sS --max-time 5 http://127.0.0.1:8001/v1/models || true
```

## 2. 启动 Embedding 服务，端口 8001

```bash
cd /base/home/lizhzh/Project3
./qwen_web/stop_qwen_embedding.sh || true
EMBED_GPUS=5 ./qwen_web/start_qwen_embedding.sh
curl -sS http://127.0.0.1:8001/v1/models
```

## 3. 启动 Qwen3.6 主模型，端口 8000

`ENABLE_COT=0` 表示不启用 reasoning parser，不让服务端主动暴露 CoT。

```bash
cd /base/home/lizhzh/Project3
LOG=qwen_web/logs/start_qwen36_8000_$(date +%Y%m%d_%H%M%S).launcher.log
nohup env \
  KILL_OLD=0 \
  INTERACTIVE=0 \
  GPUS=6,7 \
  TP_SIZE=2 \
  ENABLE_COT=0 \
  PORT=8000 \
  ./start_qwen36_35b_2gpu_262k.sh > "$LOG" 2>&1 &
echo $! > qwen_web/qwen_main.pid

tail -f "$LOG"
```

另开一个终端等待健康检查通过：

```bash
curl -sS http://127.0.0.1:8000/v1/models
curl -sS http://127.0.0.1:9922/api/health
```

## 4. 重启网页服务，端口 9922

```bash
cd /base/home/lizhzh/Project3/qwen_web
./stop_qwen_web.sh
./start_qwen_web.sh
curl -sS http://127.0.0.1:9922/api/health
```

公网检查入口：

```bash
curl -sS http://59.66.22.107:7777/api/health
```
