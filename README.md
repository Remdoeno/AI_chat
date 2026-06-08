# 旺财1.2

旺财1.2 是一个面向家庭本地部署的 AI 助手网页端。它把本地大模型、长期记忆、浏览器设备身份、联网搜索、多模态图片输入、后台空闲创作和管理员观察界面整合在一个 FastAPI 单体服务里。

本仓库只包含 Web 服务代码，不包含任何模型权重、数据库、聊天记录、记忆、日志、私有 prompt、代理地址或本地参数配置。

## 功能概览

- 网页聊天：浏览器打开即创建新会话，支持连续对话、流式输出、停止生成、reset。
- 上段对话续接：同一个浏览器设备可以加载更早 session，并把当前 session 变成旧 session 的延续。
- 设备身份：首次打开网页生成浏览器本地 `device_id`，用于区分不同用户。
- 长期记忆：后台从用户发言中整理身份、偏好、规则、事件、风险等记忆，并用 embedding 做召回。
- 未来事件提醒：带时间的 event 会在开场和相关对话里被读取，用于提醒日程、会议、截止时间等。
- 联网搜索：可按需开启搜索，搜索过程会在状态栏显示。
- 多模态图片：支持图片上传；过大图片会在服务端用 Pillow 压缩后再送入多模态模型。
- Analysis mode：管理员可查看完整 prompt、记忆召回、embedding 调用、搜索过程、网页摘要和模型调用时长。
- 成果页：空闲时后台 agent 可写小说、诗歌、剧本、世界观等作品，成果支持分类、点赞、排序、随机和分页展示。

## 旺财1.2 修复摘要

- 修复手机端聊天气泡偏移、用户时间戳缺失，以及“助手/你”标签占位导致气泡错位的问题。
- 修复聊天模式和 Analysis mode 的发送/停止按钮对齐问题；发送按钮在生成中直接变为停止按钮。
- 修复 Analysis mode 移动端滚动布局，保留后台明细，不再让固定区域抢占触摸滚动。
- 修复记忆整理 agent 只看单句用户输入导致漏记上下文偏好、要求和“这件事”的问题。
- 强化记忆整理 rationale 输出，便于在 Analysis mode 中追踪为什么保存或跳过记忆。
- 改进事件、偏好、规则等记忆标签的判断，降低第三方事实被误存为用户身份的概率。
- 补充公开部署文档，明确模型、embedding、代理、管理员密码、idle agent 和私有数据配置方式。

## 首次启动与管理员密码

第一次部署时不要在代码里写死管理员密码。启动 Web 服务后，首次访问主页会跳转到 `/auth`，设置管理员密码。这个密码用于管理 memory 和 analysis mode。

已经配置过密码后，也可以访问 `/auth`，输入旧管理员密码并修改为新的。密码 hash 保存到运行期文件：

```text
data/admin_auth.json
```

该文件已被 `.gitignore` 排除，不应上传到 GitHub。

## 模型与服务配置

你需要自己下载并启动本地模型服务。本项目默认按 OpenAI-compatible API 调用模型。

常用环境变量：

```bash
export QWEN_MODEL_BASE_URL="http://127.0.0.1:8000/v1"
export QWEN_MODEL_NAME="qwen3.6-35b-a3b-262k"
export QWEN_MODEL_API_KEY="EMPTY"
export QWEN_WEB_DB="./data/chat_history.sqlite3"
export QWEN_AUTH_CONFIG="./data/admin_auth.json"
export QWEN_MODEL_CONTEXT_CHAR_BUDGET=180000
```

如果使用本地 vLLM / SGLang / LM Studio 等 OpenAI-compatible 服务，通常 `QWEN_MODEL_API_KEY=EMPTY` 即可。

如果使用网络上的其他大模型 API，把 base URL、模型名和 key 改成供应商给出的值：

```bash
export QWEN_MODEL_BASE_URL="https://api.example.com/v1"
export QWEN_MODEL_NAME="provider-model-name"
export QWEN_MODEL_API_KEY="sk-..."
```

也可以不设置 `QWEN_MODEL_API_KEY`，改用通用的 `OPENAI_API_KEY`。如果两者都设置，优先使用 `QWEN_MODEL_API_KEY`。

Embedding 服务配置由 `embedding_client.py` 管理。请在本机或服务器启动兼容的 embedding 模型，并按该文件中的环境变量指向对应接口：

```bash
export QWEN_EMBEDDING_BASE_URL="http://127.0.0.1:8001/v1"
export QWEN_EMBEDDING_MODEL="qwen3-embedding-8b"
export QWEN_EMBEDDING_API_KEY=""
```

如果 embedding 也使用网络 API，可以填写 `QWEN_EMBEDDING_API_KEY`；留空则不发送 `Authorization` 头。

模型权重目录建议放在仓库外，或放在已忽略的 `models/` 目录下。不要提交 `.safetensors`、`.bin`、`.pt`、`.pth`、`.gguf` 等权重文件。

## 联网搜索与代理

联网代理默认为空。普通部署不会默认使用任何私人代理地址。

如果需要代理，有两种方式：

1. 页面内配置：在聊天主页 1 秒内连续点击兔子 4 次，打开高级选项，填写联网代理、temperature 和 top-p，点“确定”保存到浏览器本地。
2. 服务端默认值：设置环境变量 `QWEN_WEB_SEARCH_PROXY`。

示例：

```bash
export QWEN_WEB_SEARCH_PROXY="http://127.0.0.1:7890"
```

## 空闲创作种子

仓库不包含任何私人故事设定。你可以用环境变量或外部文件配置空闲创作方向：

```bash
export QWEN_IDLE_STORY_SEEDS_FILE="./data/idle_story_seeds.txt"
```

`idle_story_seeds.txt` 可以写你自己的小说、角色、世界观、写作偏好或长期创作计划。该文件默认不上传。
如果 `data/idle_story_seeds.txt` 已存在，启动脚本和应用会自动读取它。

也可以在成果页里配置空闲创作 prompt，让 idle agent 在不聊天、不整理记忆时进行创作。

如果不想让 idle agent 在空闲时写作品，避免消耗网络模型 token，可以关闭它：

```bash
export QWEN_IDLE_AGENT_ENABLED=false
```

关闭后，后台空闲创作线程不会启动，手动 force 触发也会被跳过。聊天、记忆整理、联网搜索和成果页浏览不受影响。

如果只是想降低消耗而不是完全关闭，可以调大运行间隔或降低输出长度：

```bash
export QWEN_IDLE_AGENT_MIN_RUN_INTERVAL_SECONDS=3600
export QWEN_IDLE_AGENT_MAX_TOKENS=800
```

如果你的连续作品里有固定译名、角色名或术语，也可以配置结果归一化映射：

```bash
export QWEN_IDLE_ARTIFACT_TERM_REPLACEMENTS='{"旧术语":"标准术语"}'
```

也可以把同样的 JSON 写入 `data/idle_artifact_term_replacements.json`，该文件同样默认不上传。

## 启动 Web 服务

安装依赖后运行：

```bash
WEB_PORT=7777 ./start_qwen_web.sh
```

停止服务：

```bash
./stop_qwen_web.sh
```

健康检查：

```bash
curl http://127.0.0.1:7777/api/health
```

## 续接上次聊天

旺财1.2 默认每次打开网页仍会创建一个新 session，这样普通刷新不会直接把旧聊天搬回来。需要续接时：

- 普通聊天：手机端和电脑端都可以在聊天区顶部触发“加载上一段对话”的提示，然后继续加载更早 session。
- Analysis mode：顶部提供“加载上一段对话”按钮，避免移动端调试明细和触摸滚动互相抢占。
- 加载后，旧 session 会作为当前 session 的上下文前缀参与后续回答，并在页面顶部显示出来。

如果上下文过长，服务端会优先截掉更早的一部分历史，避免超过模型上下文预算。可通过 `QWEN_MODEL_CONTEXT_CHAR_BUDGET` 调整近似字符预算。

## 数据与隐私

以下内容都属于运行期私有数据，不应提交：

- `data/`：数据库、管理员密码 hash、本地故事种子。
- `logs/`：服务日志、模型日志、调试日志。
- `models/`：模型权重。
- `.env`：本地端口、代理、模型路径、token 等配置。

发布前请运行：

```bash
git status --short
git ls-files
```

确认没有数据库、日志、模型权重、私有 prompt 或本地配置被纳入版本控制。
