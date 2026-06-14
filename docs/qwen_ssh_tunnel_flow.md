# Qwen Web SSH 隧道与端口流程

本文说明从 Docker/服务器容器反向 SSH 到 Mac，到 Mac 通过 `10022` 进入容器，再启动 Web 服务并暴露浏览器访问端口的完整链路。

## 端口总览

| 端口 | 所在位置 | 用途 |
| --- | --- | --- |
| `22` | Docker/服务器容器内 | 容器 SSH 服务端口，供外部进入容器。 |
| `9922` | Mac 上 | Mac 的 SSH 服务端口，供 Docker 主动连回 Mac。 |
| `10022` | Mac 上 | 反向隧道创建的端口，访问它等于访问 Docker 的 `22`。 |
| `9922` | Docker/服务器容器内 | Qwen Web 服务端口，FastAPI/Uvicorn 监听这里。 |
| `19922` | Mac 上 | 浏览器访问端口，转发到 Docker 内的 Web `9922`。 |

注意：`10022` 不是 Web 服务端口。它是 SSH 入口，用来从 Mac 进入 Docker。Web 服务实际跑在 Docker 内 `9922`。

## 总体流量图

```text
用户浏览器
  |
  | http://183.172.57.234:19922/
  v
Mac:19922
  |
  | SSH 本地转发
  v
Docker:127.0.0.1:9922
  |
  | FastAPI / Uvicorn
  v
Qwen Web
```

SSH 管理链路是另一条：

```text
Mac:10022
  |
  | 反向 SSH 隧道
  v
Docker:localhost:22
```

## 第 1 步：Docker 内反向 SSH 到 Mac

运行位置：Docker/服务器容器内。

目的：让 Mac 上出现一个 `10022` 端口。以后在 Mac 访问 `127.0.0.1:10022`，就等于访问 Docker 内部的 `localhost:22`。

推荐使用 watchdog 脚本保护这条隧道，避免网络抖动后任务中断：

```bash
cd /base/home/lizhzh/Project3/qwen_web
chmod +x ./server_reverse_ssh_watchdog.sh
nohup ./server_reverse_ssh_watchdog.sh >> logs/reverse_ssh_watchdog.log 2>&1 &
```

这个 watchdog 会前台运行 SSH；一旦 SSH 断开退出，就等待几秒后自动重连。它还会用 `/tmp/qwen_reverse_ssh_watchdog.lock` 防止重复启动多个守护进程。

命令：

```bash
ssh -f -N -p 9922 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -R 10022:localhost:22 \
  rem@183.172.57.234
```

解释：

- `-p 9922`：Docker 去连接 Mac 的 SSH 服务，Mac 的 SSH 服务监听在 `183.172.57.234:9922`。
- `-R 10022:localhost:22`：在 Mac 上开一个 `10022` 端口，并把它转回 Docker 内的 `localhost:22`。
- `-f -N`：后台运行，不执行远程命令，只做隧道。
- `ServerAliveInterval/ServerAliveCountMax`：防止静默断线后长期假活。
- `ExitOnForwardFailure=yes`：如果端口没转发成功，直接失败，不假装启动成功。

这个裸命令只适合临时启动；长期使用应使用上面的 watchdog。

验证位置：Mac 本地终端。

```bash
ssh -i ~/.ssh/icfc -p 10022 root@127.0.0.1 'hostname'
```

如果能输出 Docker/服务器容器的 hostname，说明 `Mac:10022 -> Docker:22` 成功。

## 第 2 步：Mac 通过 10022 进入 Docker

运行位置：Mac 本地终端。

目的：使用反向隧道进入 Docker，管理 Web 服务和代码。

命令：

```bash
ssh -i ~/.ssh/icfc -p 10022 root@127.0.0.1 -t 'cd /base/home/lizhzh && exec bash'
```

解释：

- `127.0.0.1:10022` 是 Mac 本地端口。
- 这个端口不是 Mac 自己的 SSH，而是第 1 步反向隧道转出来的 Docker SSH。
- 登录成功后，实际进入的是 Docker/服务器容器。

## 第 3 步：Docker 内启动 Qwen Web 服务

运行位置：Docker/服务器容器内。

目的：启动 FastAPI/Uvicorn，让 Web 服务监听 Docker 内 `0.0.0.0:9922`。

命令：

```bash
cd /base/home/lizhzh/Project3/qwen_web
./start_qwen_web.sh
```

验证：

```bash
curl http://127.0.0.1:9922/api/health
```

期望看到类似：

```json
{
  "ok": true,
  "db_ok": true,
  "model_ok": true,
  "model_name": "qwen3.6-35b-a3b-262k"
}
```

说明：

- Web 服务端口是 Docker 内 `9922`。
- 模型接口仍是 Docker 内 `http://127.0.0.1:8000/v1`。
- 数据库在 Docker 内 `/base/home/lizhzh/Project3/qwen_web/data/chat_history.sqlite3`。

## 第 4 步：Mac 把浏览器端口转发到 Docker Web

运行位置：Mac 本地终端。

目的：让浏览器访问 Mac 的 `19922`，实际转到 Docker 内的 `127.0.0.1:9922`。

推荐使用脚本：

```bash
cd /Users/rem/Documents/Qwen3部署
./scripts/local_start_qwen_tunnel.sh
```

等价核心命令：

```bash
ssh -i ~/.ssh/icfc \
  -f -N -g \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -p 10022 \
  -L 127.0.0.1:19922:127.0.0.1:9922 \
  -L 183.172.57.234:19922:127.0.0.1:9922 \
  root@127.0.0.1
```

解释：

- `-p 10022 root@127.0.0.1`：先通过 Mac 的 `10022` 登录 Docker。
- `-L 127.0.0.1:19922:127.0.0.1:9922`：Mac 本机浏览器可访问 `127.0.0.1:19922`。
- `-L 183.172.57.234:19922:127.0.0.1:9922`：校园网内其他设备可访问 `183.172.57.234:19922`。
- 这里右侧的 `127.0.0.1:9922` 是站在 Docker 视角看的地址，即 Docker 内的 Qwen Web。

为什么不用只绑定 `0.0.0.0:19922`：

当前 macOS/校园网环境里，`0.0.0.0:19922` 可能显示有监听，但外部访问 `183.172.57.234:19922` 会失败。实测显式绑定 `183.172.57.234:19922` 才稳定。

## 第 5 步：浏览器访问

本机访问：

```text
http://127.0.0.1:19922/
```

校园网内其他设备访问：

```text
http://183.172.57.234:19922/
```

健康检查：

```bash
curl http://127.0.0.1:19922/api/health
curl http://183.172.57.234:19922/api/health
```

成果页：

```text
http://183.172.57.234:19922/artifacts
```

记忆后台：

```text
http://183.172.57.234:19922/memory
```

## 一键化脚本

### Docker/服务器内脚本

路径：

```text
/base/home/lizhzh/Project3/qwen_web/server_start_reverse_ssh.sh
/base/home/lizhzh/Project3/qwen_web/server_reverse_ssh_watchdog.sh
```

如果脚本不存在，可以从 Mac 同步：

```bash
scp -i ~/.ssh/icfc -P 10022 \
  /Users/rem/Documents/Qwen3部署/scripts/server_start_reverse_ssh.sh \
  /Users/rem/Documents/Qwen3部署/scripts/server_reverse_ssh_watchdog.sh \
  root@127.0.0.1:/base/home/lizhzh/Project3/qwen_web/
```

运行：

```bash
cd /base/home/lizhzh/Project3/qwen_web
chmod +x ./server_start_reverse_ssh.sh
chmod +x ./server_reverse_ssh_watchdog.sh
./server_start_reverse_ssh.sh
```

`server_start_reverse_ssh.sh` 会优先用 `server_reverse_ssh_watchdog.sh` 启动受保护的反向隧道；如果 watchdog 脚本不存在，才退回一次性 `ssh -f -N`。

查看 watchdog 日志：

```bash
tail -f /base/home/lizhzh/Project3/qwen_web/logs/reverse_ssh_watchdog.log
```

停止 watchdog：

```bash
pkill -f server_reverse_ssh_watchdog.sh
pkill -f "ssh .* -R 10022:localhost:22"
rm -rf /tmp/qwen_reverse_ssh_watchdog.lock
```

### Mac 本地脚本

路径：

```text
/Users/rem/Documents/Qwen3部署/scripts/local_start_qwen_tunnel.sh
```

运行：

```bash
cd /Users/rem/Documents/Qwen3部署
./scripts/local_start_qwen_tunnel.sh
```

脚本会：

1. 检查 `10022` 是否能进入 Docker。
2. 检查 Docker 内 `9922/api/health`。
3. 清理旧的 `19922` 监听。
4. 同时绑定 `127.0.0.1:19922` 和当前校园网 IP 的 `19922`。

## 常见故障定位

### 1. `ssh -p 10022 root@127.0.0.1` 失败

说明第 1 步反向 SSH 没有建立，或者断了。

在 Docker/服务器容器内重新运行：

```bash
ssh -f -N -p 9922 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -R 10022:localhost:22 \
  rem@183.172.57.234
```

### 2. `10022` 能进，但 `19922` 打不开

说明 Docker SSH 可用，但 Mac 到 Docker Web 的本地转发断了。

在 Mac 上运行：

```bash
cd /Users/rem/Documents/Qwen3部署
./scripts/local_start_qwen_tunnel.sh
```

### 3. `19922` 有监听但浏览器打不开

可能是旧 SSH 隧道假活。

在 Mac 上查：

```bash
lsof -nP -iTCP:19922 -sTCP:LISTEN
```

然后重建：

```bash
cd /Users/rem/Documents/Qwen3部署
./scripts/local_start_qwen_tunnel.sh
```

### 4. `127.0.0.1:19922` 能打开，但 `183.172.57.234:19922` 不能

说明本地转发只绑定了 localhost，或 wildcard 绑定在当前网络下不可靠。

使用显式绑定：

```bash
QWEN_LOCAL_BIND_HOSTS=127.0.0.1,183.172.57.234 \
  /Users/rem/Documents/Qwen3部署/scripts/local_start_qwen_tunnel.sh
```

### 5. Web 服务本身挂了

能 SSH 进 Docker 后运行：

```bash
cd /base/home/lizhzh/Project3/qwen_web
./stop_qwen_web.sh
./start_qwen_web.sh
curl http://127.0.0.1:9922/api/health
```

## 最短恢复流程

如果整条链路都断了，按这个顺序恢复：

1. 在 Docker/服务器容器内建立反向 SSH：

```bash
cd /base/home/lizhzh/Project3/qwen_web
chmod +x ./server_reverse_ssh_watchdog.sh ./server_start_reverse_ssh.sh
./server_start_reverse_ssh.sh
```

2. 在 Mac 上确认能进 Docker：

```bash
ssh -i ~/.ssh/icfc -p 10022 root@127.0.0.1 'hostname'
```

3. 在 Docker 内确认 Web：

```bash
ssh -i ~/.ssh/icfc -p 10022 root@127.0.0.1 \
  'cd /base/home/lizhzh/Project3/qwen_web && ./start_qwen_web.sh && curl http://127.0.0.1:9922/api/health'
```

4. 在 Mac 上恢复浏览器访问：

```bash
cd /Users/rem/Documents/Qwen3部署
./scripts/local_start_qwen_tunnel.sh
```

5. 验证：

```bash
curl http://127.0.0.1:19922/api/health
curl http://183.172.57.234:19922/api/health
```
