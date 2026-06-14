# 旺财 GitHub 发布固定流程

本文档用于以后发布 `Remdoeno/AI_chat`，避免每次重新排查 SSH、代理、敏感文件和 release 仓库位置。

## 固定事实

- 服务器入口：
  ```bash
  ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 -t 'cd /base/home/lizhzh && exec bash'
  ```
- 线上运行目录：
  ```text
  /base/home/lizhzh/Project3/qwen_web
  ```
- GitHub 发布仓库工作区：
  ```text
  /base/home/lizhzh/Project3/AI_chat_release
  ```
- GitHub 仓库：
  ```text
  git@github.com:Remdoeno/AI_chat.git
  ```
- 服务器上的 GitHub deploy key：
  ```text
  /root/.ssh/ai_chat_github
  ```
- GitHub SSH 推送走 443 + HTTP proxy：
  ```bash
  export GIT_SSH_COMMAND="ssh -i ~/.ssh/ai_chat_github -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o 'ProxyCommand=nc -X connect -x 59.66.22.107:7898 %h %p' -p 443"
  ```

## 发布原则

- 只从服务器端发布，避免 Mac 本地混入无关文件。
- `qwen_web` 是运行目录，不是 git 仓库；`AI_chat_release` 才是发布仓库。
- 同步代码时必须排除运行态文件：数据库、日志、模型权重、`.env`、备份目录、pid、上传临时目录。
- 每次发布前修改版本号，避免浏览器缓存吃旧静态资源。
- README 必须说明当前版本功能、私有配置不上传、模型和 embedding 由用户自行配置。
- 测试只在服务器跑，不在 Mac 本地跑。

## 标准命令

### 1. 进入服务器并确认 release 仓库

```bash
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107
cd /base/home/lizhzh/Project3

export GIT_SSH_COMMAND="ssh -i ~/.ssh/ai_chat_github -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o 'ProxyCommand=nc -X connect -x 59.66.22.107:7898 %h %p' -p 443"

if [ ! -d AI_chat_release/.git ]; then
  git clone ssh://git@ssh.github.com:443/Remdoeno/AI_chat.git AI_chat_release
fi

cd AI_chat_release
git status -sb
git pull --ff-only origin main
```

### 2. 从运行目录同步到 release 仓库

服务器没有 `rsync` 时，用 `tar` 管道同步：

```bash
cd /base/home/lizhzh/Project3/AI_chat_release
find . -mindepth 1 ! -path './.git' ! -path './.git/*' -exec rm -rf {} +

cd /base/home/lizhzh/Project3/qwen_web
tar \
  --exclude='.git' \
  --exclude='data' \
  --exclude='logs' \
  --exclude='log' \
  --exclude='backups' \
  --exclude='backup_*' \
  --exclude='__pycache__' \
  --exclude='.ipynb_checkpoints' \
  --exclude='__upload_tmp__' \
  --exclude='*.pid' \
  --exclude='*.sqlite3' \
  --exclude='*.sqlite3-*' \
  --exclude='*.log' \
  --exclude='models' \
  --exclude='.env' \
  --exclude='*.safetensors' \
  --exclude='*.bin' \
  --exclude='*.pt' \
  --exclude='*.pth' \
  --exclude='*.gguf' \
  -cf - . | tar -C /base/home/lizhzh/Project3/AI_chat_release -xf -
```

### 3. 恢复不该被同步删除的发布文档

如果 release 仓库里有只用于 GitHub 的文档或发布日志，而运行目录没有，需要恢复或重新创建。

```bash
cd /base/home/lizhzh/Project3/AI_chat_release
git status --short

# 示例：如果这些文件只是 qwen_web 没有，而不是本次要删除，就恢复
git checkout -- docs/superpowers/plans/2026-06-08-session-continuation-1-1.md log/wangcai_1.2_release_20260609.md 2>/dev/null || true
```

### 4. 修改版本号与 README

需要检查这些位置：

```bash
grep -R "旺财1\\|v=2026\\|VERSION\\|Analysis mode\\|Qwen3" -n README.md static app.py schemas.py tests | head -200
```

常见修改：

- `README.md` 标题和功能介绍。
- `static/index.html` 的 `<title>` 和静态资源 query string。
- `static/analysis.html`、`static/app.js`、`static/analysis.js` 中用于破缓存的版本字符串。
- 新增 `log/wangcai_版本_release_日期.md`，只写发布说明，不写私有运行日志。

### 5. 敏感文件检查

```bash
cd /base/home/lizhzh/Project3/AI_chat_release
git status --short

git ls-files | grep -E '(^data/|^logs/|sqlite|admin_auth|idle_.*seed|HERO_SERIAL_SEED|CANJIMIAN|\\.env|safetensors|\\.gguf|\\.bin$|\\.pt$|\\.pth$)' && {
  echo "发现敏感文件，停止发布"
  exit 1
} || true
```

### 6. Docker/服务器部署环境验证固定流程

这个项目不要在 Mac 本地跑后端测试，也不要先在 Mac 上试 FastAPI。所有代码改动都应先进入 Docker/服务器部署环境验证：

```text
Mac 本地只做：
- 保存操作日志到 ./log/
- 必要时编辑临时发布文档
- 不跑后端、不跑 unittest、不启动服务

服务器部署环境做：
- 接收代码改动
- 重启 qwen_web
- 访问线上端口或内网端口验证
- 跑静态/行为测试
- 验证通过后，再从 qwen_web 同步到 AI_chat_release 发布仓库
```

固定部署验证目录：

```bash
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107
cd /base/home/lizhzh/Project3/qwen_web
```

每次有功能改动后的验证顺序：

```bash
cd /base/home/lizhzh/Project3/qwen_web

# 1. 语法检查，不依赖外部模型
/opt/conda/bin/python3 -m py_compile app.py schemas.py embedding_client.py memory.py vector_memory.py streaming_utils.py

# 2. 重启部署服务
./stop_qwen_web.sh || true
WEB_PORT=7777 ./start_qwen_web.sh
sleep 2

# 3. 端口与健康检查
ss -ltnp | grep ':7777'
curl -sS http://127.0.0.1:7777/api/health | head -c 2000
echo

# 4. 页面是否能返回
curl -sS -I http://127.0.0.1:7777/ | head
curl -sS -I http://127.0.0.1:7777/analysis | head
curl -sS -I http://127.0.0.1:7777/memory-admin | head
```

如果是前端布局改动，还要用浏览器访问公网入口验证：

```text
http://59.66.22.107:7777/
http://59.66.22.107:7777/analysis
```

如果是聊天、记忆、联网、多模态或成果逻辑改动，还要在服务器部署目录跑对应测试。注意仍然是在服务器，不是 Mac 本地：

```bash
cd /base/home/lizhzh/Project3/qwen_web
/opt/conda/bin/python3 -m unittest tests.test_static_regressions
/opt/conda/bin/python3 -m unittest tests.test_app_behaviors
```

失败时固定看这些日志：

```bash
cd /base/home/lizhzh/Project3/qwen_web
ls -ltr logs | tail
tail -200 logs/*.log
```

只有部署环境验证完成后，才进入下面的 GitHub release 同步。

### 7. Release 仓库验证固定流程

只在服务器跑验证：

```bash
cd /base/home/lizhzh/Project3/AI_chat_release
/opt/conda/bin/python3 -m unittest tests.test_static_regressions
```

如本次改了后端行为，再补充运行对应后端行为测试：

```bash
/opt/conda/bin/python3 -m unittest tests.test_app_behaviors
```

发布前最终验证顺序固定为：

1. `git status --short`
2. 敏感文件 grep
3. `python -m unittest tests.test_static_regressions`
4. 需要时 `python -m unittest tests.test_app_behaviors`
5. 需要时线上 `curl /api/health`

### 7. 提交与推送

```bash
cd /base/home/lizhzh/Project3/AI_chat_release
git diff --stat
git add README.md app.py schemas.py static tests scripts .gitignore log/wangcai_*.md
git status --short
git commit -m "Release Wangcai 版本号"
git push origin main
```

推送失败时先验证 deploy key：

```bash
ssh -i ~/.ssh/ai_chat_github \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o ConnectTimeout=8 \
  -o StrictHostKeyChecking=accept-new \
  -o 'ProxyCommand=nc -X connect -x 59.66.22.107:7898 %h %p' \
  -p 443 -T git@ssh.github.com
```

预期输出包含：

```text
Hi Remdoeno/AI_chat! You've successfully authenticated, but GitHub does not provide shell access.
```

## 旺财 1.3 本次发布检查项

- README 标题改为 `旺财1.3`。
- README 开头增加差异化功能点：长期记忆、成果系统、本地部署、私有数据、Analysis mode。
- README TODO 增加 `旺财1.4`：统一配置界面、集中管理联网大模型 API key、embedding 模型、成果生成频率等。
- 确认不上传 `data/`、`logs/`、模型权重、私有故事 seed、本地代理配置。
- 提交信息：
  ```text
  Release Wangcai 1.3
  ```
