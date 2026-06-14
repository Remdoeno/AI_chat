# Qwen Web SSH 启动顺序

## 1. 服务器/容器内运行

```bash
# 在 Mac 上，等 SSH 恢复后可复制脚本到服务器：
scp -i ~/.ssh/icfc -P 10022 ./scripts/server_start_reverse_ssh.sh \
  root@127.0.0.1:/base/home/lizhzh/Project3/qwen_web/server_start_reverse_ssh.sh

# 在服务器/容器内运行：
cd /base/home/lizhzh/Project3/qwen_web
chmod +x ./server_start_reverse_ssh.sh
./server_start_reverse_ssh.sh
```

如果当前 SSH 已断，先通过 Docker/服务器控制台进入容器，把 `scripts/server_start_reverse_ssh.sh` 的内容复制进去再运行。它会：

- 确认 `qwen_web` 在 `127.0.0.1:9922` 健康。
- 如未启动，执行 `./start_qwen_web.sh`。
- 建立反向 SSH：`183.172.57.234:10022 -> 容器 localhost:22`。

等价核心命令：

```bash
ssh -f -N -p 9922 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -R 10022:localhost:22 \
  rem@183.172.57.234
```

## 2. Mac 本地终端运行

```bash
cd /Users/rem/Documents/Qwen3部署
./scripts/local_start_qwen_tunnel.sh
```

它会：

- 通过 `ssh -i ~/.ssh/icfc -p 10022 root@127.0.0.1` 检查服务器。
- 检查服务器内 `qwen_web` 的 `/api/health`。
- 建立本地转发：`127.0.0.1:19922 -> 服务器 127.0.0.1:9922`。
- 自动检测当前 Mac 的校园网 IP，并额外绑定 `<校园网 IP>:19922`。

等价核心命令：

```bash
ssh -i ~/.ssh/icfc \
  -f -N -g \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -p 10022 \
  -L 127.0.0.1:19922:127.0.0.1:9922 \
  -L <Mac 的校园网 IP>:19922:127.0.0.1:9922 \
  root@127.0.0.1
```

## 3. 验证

```bash
curl http://127.0.0.1:19922/api/health
curl http://127.0.0.1:19922/
curl http://127.0.0.1:19922/artifacts
```

如果校园网内其他设备访问，使用：

```text
http://<Mac 的校园网 IP>:19922/
```

## 常用覆盖变量

```bash
QWEN_LOCAL_WEB_PORT=19922 ./scripts/local_start_qwen_tunnel.sh
QWEN_LOCAL_BIND_HOSTS=127.0.0.1,183.172.57.234 ./scripts/local_start_qwen_tunnel.sh
QWEN_JUMP_HOST=183.172.57.234 QWEN_REMOTE_SSH_PORT=10022 ./scripts/server_start_reverse_ssh.sh
```
