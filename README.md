# 旺财1.4

旺财1.4 是一个面向家庭本地部署的 AI 助手网页端。它把本地大模型、长期记忆、浏览器设备身份、跨设备记忆绑定、联网搜索、多模态图片输入、后台空闲创作和管理员观察界面整合在一个 FastAPI 单体服务里。

和常见的云端聊天机器人或通用 Agent 不同，旺财的重点不是一次性问答，而是“长期生活在你家里的私人 AI”：

- 更重视记忆：豆包、DeepSeek、ChatGPT 一类产品通常以单次会话或云端账号记忆为中心；旺财围绕本地浏览器身份、长期记忆库、未来事件和用户偏好构建，可以把会议、称呼、习惯、禁忌和长期设定持续带入对话。
- 更重视成果：除了聊天，旺财会在空闲时创作小说、诗歌、剧本、世界观和连续作品；成果页支持分类、点赞、评论、排序和随机浏览，像一个会自己产出内容的家庭创作空间。
- 更重视本地化：模型、embedding、数据库、管理员密码和聊天记录都可以放在自己的机器或内网服务器上；仓库不包含任何模型权重、私有记忆、日志、代理地址或个人参数。
- 更重视可观察性：分析模式可以看到完整 prompt、记忆召回、embedding、联网搜索、网页摘要、模型调用时长和后台整理过程，适合调试一个真正有长期记忆的助手。
- 更重视可改造性：前端无构建步骤，后端是 FastAPI 单体，适合家庭服务器、宿舍服务器或个人工作站按自己的模型、代理和创作方向改造。

本仓库只包含 Web 服务代码，不包含任何模型权重、数据库、聊天记录、记忆、日志、私有 prompt、代理地址或本地参数配置。

## 功能概览

- 网页聊天：浏览器打开即创建新会话，支持连续对话、流式输出、停止生成、reset。
- 上段对话续接：同一个浏览器设备可以加载更早 session，并把当前 session 变成旧 session 的延续。
- 设备身份：首次打开网页生成浏览器本地 `device_id`，用于区分不同用户。
- 记忆绑定：多个设备可以绑定同一个共享用户 ID，按需共享记忆、事件和历史聊天记录。
- 长期记忆：后台从用户发言中整理身份、偏好、规则、事件、风险等记忆，并用 embedding 做召回。
- 未来事件提醒：带时间的 event 会在开场和相关对话里被读取，用于提醒日程、会议、截止时间等。
- 联网搜索：可按需开启搜索，搜索过程会在状态栏显示。
- 多模态图片：支持图片上传；过大图片会在服务端用 Pillow 压缩后再送入多模态模型。
- 分析模式：管理员可查看完整 prompt、记忆召回、embedding 调用、搜索过程、网页摘要和模型调用时长。
- 成果页：空闲时后台 agent 可写小说、诗歌、剧本、世界观等作品，成果支持分类、点赞、排序、随机和分页展示。

## 旺财1.4 更新摘要

- 新增 event 记忆实时维护：聊天中发现日程已完成、取消、时间地点或要求发生变化时，会生成修正版 event 并软替换旧记忆，避免旧提醒继续误导对话。
- 强化 diary 日记式记忆：用户主动分享身体状态、情绪、生活细节、已经发生的事件和短期愿望时，会按“日记本”方式记录；这类状态记忆可在多设备共享，并会进入近期关怀和开场提醒。
- 强化记忆整理上下文：记忆 agent 不再只看单句用户输入，而是结合最近几轮对话判断，但仍只保存用户实际表达的事实，禁止把助手脑补、玩笑或扩写当成用户记忆。
- 新增后台记忆去重 agent：空闲时会结合 embedding 和大模型判断重复、冲突或过期记忆，优先保留更完整、更晚、更准确的条目。
- 新增访问限流和告警页：每个 `device_id` 默认 5 秒最多发一条消息；`/warn` 可查看访问日志、限流和后台告警，页面支持滚动追溯。
- 改进 Markdown 渲染：聊天和分析模式支持表格、公式、分隔线、标题和常见 Markdown；普通闲聊不强制套用复杂 Markdown，避免正常聊天变得生硬。
- 改进凌晨相对日期理解：0 点附近提到“明天”时，会结合当前时间、开场上下文和用户后续解释处理，避免反复强制追问。
- 改进分析模式后台明细：idle worker、prompt 缓存、记忆去重、后台写作和故障诊断以更人类可读的摘要展示；长时间无事自检会合并，真正执行任务才展开细节。
- 改进成果页：空闲写作进度只展示最新 3 条并显示阶段进度；成果卡片更紧凑，支持分类、点赞、评论、删除和更合理的排序。
- 改进移动端布局：聊天页和分析模式的按钮、输入区、气泡、时间戳、标签和记忆绑定入口重新对齐，手机端可读性更好。

## 首次启动与管理员密码

第一次部署时不要在代码里写死管理员密码。启动 Web 服务后，首次访问主页会跳转到 `/auth`，设置管理员密码。这个密码用于管理 memory 和分析模式。

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

### 固定端口规则

**生产和日常部署一律使用 `7777` 端口。以后不要再用 `9922` 启动 qwen_web。**

当前外部访问入口、服务器本机监听和健康检查都按 `7777` 约定：

- 外部访问：`http://59.66.22.107:7777/`
- 服务监听：`0.0.0.0:7777`
- 本机健康检查：`http://127.0.0.1:7777/api/health`
- 告警/访问日志：`http://127.0.0.1:7777/warn`

`start_qwen_web.sh` 的默认端口已经是 `7777`，正常启动不要额外传 `WEB_PORT`：

```bash
./start_qwen_web.sh
```

如果需要显式写出端口，也只能写：

```bash
WEB_PORT=7777 ./start_qwen_web.sh
```

不要执行下面这种旧命令：

```bash
# 错误：旧端口，不要再用于 qwen_web
WEB_PORT=9922 ./start_qwen_web.sh
```

停止服务：

```bash
./stop_qwen_web.sh
```

健康检查：

```bash
curl http://127.0.0.1:7777/api/health
```

端口确认：

```bash
netstat -ltnp 2>/dev/null | grep ':7777'
```

## 续接上次聊天

旺财1.4 默认每次打开网页仍会创建一个新 session，这样普通刷新不会直接把旧聊天搬回来。需要续接时：

- 普通聊天：手机端和电脑端都可以在聊天区顶部触发“加载上一段对话”的提示，然后继续加载更早 session。
- 分析模式：顶部提供“加载上一段对话”按钮，避免移动端调试明细和触摸滚动互相抢占。
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

## TODO：旺财1.5 计划

旺财1.5 预计做一次配置系统大整理：

- 新增统一配置界面，把高级参数、代理、管理员设置、成果生成、模型配置等分散入口集中管理。
- 更方便地配置联网大模型 API key、base URL、模型名、temperature、top-p 和 max tokens。
- 更方便地配置 embedding 模型，包括本地 embedding、远程 embedding API、模型名和向量维度检查。
- 更细粒度控制成果生成频率、启停策略、最大 token、连续作品设定和空闲任务类型。
- 增加配置导入/导出能力，让家庭服务器迁移、备份和多设备部署更稳定。
