# Wangcai 2.2 / 旺财2.2

![Wangcai](static/brand/wangcai-2.0-journey.png)

Wangcai 是一个面向个人和家庭本地部署的 AI Web 系统。它不是只会回答问题的聊天框，而是一个长期生活在你身边的 AI：能记住你，陪你聊天，帮你查资料，看图和画图，在空闲时写故事、诗歌、剧本和世界观，还能维护固定角色库，让角色在长期小剧场中持续成长。

它的目标可以很直接地概括为一句话：**做最温柔、最像理性中亲密伙伴的 AI。**

## 它和普通大模型聊天有什么不同

大多数聊天系统的核心是“本轮问答”：用户问，模型答，最多再加一点会话历史。Wangcai 的核心是“长期陪伴”：它会把聊天、记忆、事件、角色、成果、图片和后台创作放在同一个系统里，让 AI 不只是会说话，而是有连续生活感。

- **更像亲密伙伴**：它重视称呼、偏好、日程、关系、禁忌、长期设定和共同经历。它不会把你每次刷新都当陌生人，也不会只把记忆当关键词缓存。
- **更理性可观察**：分析模式能看到 prompt、记忆召回、联网搜索、图片 prompt 优化、模型调用和后台任务，让你知道它为什么这样回答，而不是只能相信黑盒输出。
- **更温柔但不失控制**：长期记忆、角色库、成果小剧场和后台创作都能被管理和修正。它会努力延续你的世界，但不强迫你接受它的脑补。
- **更重视创造**：普通聊天之外，它可以把空闲算力用来写图文作品，给作品配图，让固定角色持续登场。
- **更本地化**：聊天模型、后台模型、embedding、图像生成、数据库和管理员密码都可以放在自己的机器或内网服务器上。你也可以改用 OpenAI-compatible 的外部 API。

## 特色功能

### 长期记忆

Wangcai 会从用户发言中整理长期记忆，包括身份、偏好、规则、日程、事实、风险、diary 状态和未来事件。聊天时，它会先判断本轮是否需要记忆，再用 embedding 召回相关内容，而不是把所有历史粗暴塞进上下文。

典型用法：

```text
我下周三下午三点要交项目报告，提前一天提醒我。
以后叫我 Rem，别叫我的全名。
我不喜欢回答里出现太多鸡汤式总结。
```

### 聊天、联网搜索和图片输入

普通聊天支持流式输出、停止生成、加载上一段对话、设备身份和共享用户记忆。需要实时资料时可以开启联网搜索；搜索过程会进入分析模式，便于检查来源和摘要。图片上传会在服务端压缩后送入多模态模型。

### 画图模式

在聊天或分析模式里点击“画图”后，本轮消息会进入图像生成流程：

1. 将中文或混合输入转换成英文图像 prompt。
2. 判断输入是自然语言、专业 prompt，还是基于上一张图的补充修改。
3. 自然语言会被扩写成更适合图像模型的视觉指令。
4. 专业 prompt 会尽量直译保留，不强行重写。
5. 默认生成 4 张图，可预览和下载。

示例：

```text
画一个雨夜的校园咖啡厅，窗外有路灯，桌上放着一束快枯萎的玫瑰。
```

连续修改示例：

```text
把光线改暖一点，角色换成黑发，画面更像电影剧照。
```

### 固定角色库

角色库是 Wangcai 和普通“临时角色扮演”最大的区别之一。角色不是一次 prompt 里的名字，而是长期保存的演员。

角色库支持：

- 创建和编辑角色姓名、别名、背景、性格、关系、说话气质。
- 维护绘图 prompt、头像、参考照片和场景图。
- 用专用角色聊天补全设定、修正角色、生成头像或多角色同框图。
- 将固定角色同步为全局 `characters` 记忆，供聊天、绘图和成果小剧场按语义召回。
- 给角色写成果小剧场指令，例如“更适合在校园日常里登场”“不要总是作为解说者出现”。

角色库使用示例：

```text
创建角色：灿鸡面。她喜欢粉色洛丽塔风格，嘴上常说冷笑话，但遇到重要的人会非常认真。
```

```text
给灿鸡面补一张头像，保持粉色、校园、咖啡厅、轻微电影感。
```

```text
让灿鸡面和叶檀同框，画一张雨夜咖啡厅里两人隔着桌子对峙的场景图。
```

### 成果库和小剧场

成果库保存后台 idle agent 或用户触发生成的图文作品。它可以写小说、诗歌、剧本、世界观、角色档案、研究札记，也可以给成果规划封面图和正文插图。

小剧场不是随机写故事。Wangcai 会参考：

- 用户在成果页配置的创作 prompt。
- 固定角色库和角色关系。
- 隐藏成果导演指令。
- 最近成果和系列上下文。
- 避免重复的结构要求。
- 图像配图计划。

成果 prompt 的优先级最高。你可以直接指定方向：

```text
灿鸡面 dating 日记。每篇发生在校园咖啡厅，和不同优秀男/女青年约会。不要总写理性工程型对象，要换身份、目标和冲突来源。
```

连续作品示例：

```text
继续《玻璃温室侦探社》，写第 5 到第 8 集。每一集都要推进主线，但每集也要有独立事件。第 8 集收束第一季。
```

导演指令示例：

```text
以后成果里如果用到灿鸡面，不要只写她被别人评价穿搭；要让她主动做选择、改变局面。
```

配图指令示例：

```text
这个系列每篇至少一张封面图。封面要像电影海报，不要像立绘设定图。
```

### 分析模式

分析模式是给开发者和高级用户看的观察面板。它可以查看：

- 主聊天 prompt 和上下文。
- 记忆召回、筛选、压缩和写入过程。
- 联网搜索 query、结果、网页摘要和来源。
- 画图 prompt 翻译、分类、优化和图像生成状态。
- 后台 idle、记忆整理、去重、拆分、成果评论等任务。

当你觉得 AI 回答不对、记忆召回不对、搜索不准或图像 prompt 有问题时，分析模式是第一排查入口。

## 常见功能一览

- 网页聊天：流式输出、停止生成、reset、加载上一段对话。
- 多设备：浏览器本地 device id，共享用户 ID 和记忆绑定。
- 管理后台：管理员密码、记忆库、分析模式、warn 日志页。
- 模型配置：聊天模型、后台模型和图像模型可分别配置。
- 联网搜索：支持代理，搜索过程可观察。
- 图片：支持上传图片和图像生成。
- 成果：图文作品、评论、点赞、分类、排序、随机浏览、分页。
- 角色：固定角色库、头像/照片/场景图、全局角色索引。

## 本地部署条件

推荐环境：

- Linux 服务器、工作站、Mac 或 WSL2。
- Python 3.10+，推荐 Python 3.11。
- 可访问一个 OpenAI-compatible 聊天模型接口。
- 可访问一个 OpenAI-compatible embedding 接口。
- 可选：图像生成服务，例如 HiDream。
- 可选 GPU：本地运行大模型或图像模型时需要；只接外部 API 时不需要 GPU。

Web 服务最小依赖：

```bash
python3 -m pip install fastapi "uvicorn[standard]" pydantic httpx openai numpy pillow
```

如果你使用 vLLM 或 SGLang 启动本地模型，还需要在对应模型环境里单独安装它们。LM Studio、Ollama、云端 API 或自建网关也可以，只要能提供兼容 `/v1/chat/completions` 的接口。

## 安装

```bash
git clone https://github.com/Remdoeno/AI_chat.git wangcai_ai
cd wangcai_ai
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install fastapi "uvicorn[standard]" pydantic httpx openai numpy pillow
```

创建运行目录：

```bash
mkdir -p data logs
```

## 配置聊天模型

Wangcai 默认按 OpenAI-compatible API 调模型。最常用配置如下：

```bash
export WANGCAI_MODEL_BASE_URL="http://127.0.0.1:8000/v1"
export WANGCAI_MODEL_NAME="qwen3.6-35b-a3b-262k"
export WANGCAI_MODEL_API_KEY="EMPTY"
```

如果使用外部 API：

```bash
export WANGCAI_MODEL_BASE_URL="https://api.example.com/v1"
export WANGCAI_MODEL_NAME="provider-model-name"
export WANGCAI_MODEL_API_KEY="sk-..."
```

也可以在网页里配置：聊天主页 1 秒内连续点击兔子 4 次，打开高级配置面板，分别设置聊天模型、后台模型、图像模型、供应商 API key 和联网代理。

内置供应商预设包括：

- 本地 OpenAI-compatible 服务。
- OpenAI。
- DeepSeek。
- 智谱 GLM。
- 通义千问 DashScope compatible mode。
- 豆包火山方舟。
- 自定义 OpenAI-compatible 服务。

### 本地聊天模型启动示例

Wangcai 不绑定某一种模型框架。你只需要把聊天模型暴露成 OpenAI-compatible API，然后让 `WANGCAI_MODEL_BASE_URL` 指向它。

vLLM 示例：

```bash
pip install vllm
vllm serve /path/to/your-chat-model \
  --served-model-name qwen3.6-35b-a3b-262k \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --trust-remote-code
```

对应配置：

```bash
export WANGCAI_MODEL_BASE_URL="http://127.0.0.1:8000/v1"
export WANGCAI_MODEL_NAME="qwen3.6-35b-a3b-262k"
export WANGCAI_MODEL_API_KEY="EMPTY"
```

SGLang 示例：

```bash
pip install "sglang[all]"
python -m sglang.launch_server \
  --model-path /path/to/your-chat-model \
  --served-model-name qwen3.6-35b-a3b-262k \
  --host 0.0.0.0 \
  --port 8000
```

LM Studio 示例：

1. 在 LM Studio 下载并加载模型。
2. 打开 Local Server。
3. 将 base URL 设为 `http://127.0.0.1:1234/v1`。
4. 将模型名设为 LM Studio 页面里显示的 model id。

Ollama 示例：

```bash
ollama pull qwen3:32b
ollama serve
export WANGCAI_MODEL_BASE_URL="http://127.0.0.1:11434/v1"
export WANGCAI_MODEL_NAME="qwen3:32b"
export WANGCAI_MODEL_API_KEY="ollama"
```

外部 API 示例：

```bash
export WANGCAI_MODEL_BASE_URL="https://api.openai.com/v1"
export WANGCAI_MODEL_NAME="gpt-5.5"
export WANGCAI_MODEL_API_KEY="sk-..."
```

## 配置 embedding 模型

长期记忆需要 embedding 服务。默认配置：

```bash
export WANGCAI_EMBEDDING_BASE_URL="http://127.0.0.1:8001/v1"
export WANGCAI_EMBEDDING_MODEL="qwen3-embedding-8b"
export WANGCAI_EMBEDDING_API_KEY=""
```

本地 vLLM 启动 embedding 的示例：

```bash
vllm serve /path/to/Qwen3-Embedding-8B \
  --served-model-name qwen3-embedding-8b \
  --host 0.0.0.0 \
  --port 8001 \
  --dtype bfloat16 \
  --runner pooling \
  --convert embed \
  --trust-remote-code
```

仓库里也包含一个服务器用脚本：

```bash
./start_wangcai_embedding.sh
```

这个脚本默认按项目作者的服务器目录组织模型路径；你可以通过环境变量覆盖：

```bash
export EMBED_MODEL_DIR="/path/to/Qwen3-Embedding-8B"
export EMBED_MODEL_NAME="qwen3-embedding-8b"
export EMBED_PORT=8001
./start_wangcai_embedding.sh
```

## 配置图像生成模型

没有图像服务时，普通聊天、搜索、记忆和成果浏览仍可使用；画图和配图会不可用。

HiDream 或其他图像服务可以按下面配置：

```bash
export WANGCAI_IMAGE_MODEL_BASE_URL="http://127.0.0.1:8002"
export WANGCAI_IMAGE_MODEL_NAME="HiDream-O1-Image-Dev-2604"
export WANGCAI_IMAGE_MODEL_API_KEY=""
```

图像服务只要被 `wangcai_app/functions/image_generation.py` 支持即可。网页高级配置面板也可以设置图像模型。

## 启动

默认端口是 `7777`：

```bash
PYTHON=.venv/bin/python ./start_wangcai_ai.sh
```

或显式指定：

```bash
PYTHON=.venv/bin/python WEB_PORT=7777 ./start_wangcai_ai.sh
```

如果你的机器没有 `/opt/conda/bin/python3`，请像上面这样显式传入 `PYTHON=.venv/bin/python`。

访问：

```text
http://127.0.0.1:7777/
```

健康检查：

```bash
curl http://127.0.0.1:7777/api/health
```

停止：

```bash
./stop_wangcai_ai.sh
```

第一次打开网页会进入 `/auth` 设置管理员密码。管理员密码用于记忆库和分析模式。

## 常用环境变量

```bash
export WANGCAI_WEB_DB="./data/chat_history.sqlite3"
export WANGCAI_AUTH_CONFIG="./data/admin_auth.json"
export WANGCAI_MODEL_CONTEXT_CHAR_BUDGET=180000
export WANGCAI_WEB_SEARCH_PROXY=""
export WANGCAI_IDLE_AGENT_ENABLED=true
export WANGCAI_IDLE_AGENT_MIN_RUN_INTERVAL_SECONDS=300
export WANGCAI_IDLE_AGENT_MAX_TOKENS=24000
```

如果需要联网代理，可以在网页高级配置面板里填，也可以设置：

```bash
export WANGCAI_WEB_SEARCH_PROXY="http://127.0.0.1:7890"
```

## 小剧场 prompt 用法

成果页可以设置“后台创作 prompt”。它是小剧场创作的最高优先级，比历史系列、角色库、避重复规则和长期导演指令更高。

好的 prompt 应该包含：

- 主角或固定角色。
- 场景或题材。
- 作品形式：短篇、连续小说、剧本、诗歌、世界观、设定集等。
- 禁止重复的结构。
- 配图风格。
- 是否需要连续篇数或完结。

示例 1：校园约会系列

```text
灿鸡面 dating 日记。每篇发生在校园咖啡厅，和不同优秀男/女青年约会。每个约会对象都要有自己的目标、压力和改变，不要只是评价灿鸡面的工具人。每篇至少一张电影海报感封面。
```

示例 2：连续剧本

```text
写《玻璃温室侦探社》第一季第 1 到第 6 集。主角团每集解决一个独立事件，同时推进温室失踪案主线。第 6 集必须收束第一季，不要继续拖。
```

示例 3：角色成长

```text
后续成果如果使用叶檀，不要总让她当冷静旁观者。让她至少做一个会改变局面的决定，并承担后果。
```

示例 4：配图控制

```text
所有配图都走暖色电影摄影风格。封面表现人物关系和场景气氛，不要做单人立绘。正文插图只选关键动作或冲突转折。
```

## 角色库建议工作流

1. 先用角色库聊天创建角色。
2. 补齐背景、性格、关系和说话气质。
3. 生成头像或上传参考图。
4. 给角色写绘图 prompt。
5. 给角色写小剧场指令。
6. 在成果 prompt 中点名角色，或者让成果系统按语义选择角色。

角色创建示例：

```text
创建角色：林栖。建筑系研究生，外表冷淡但很在意细节。她不是负责解释概念的人，而是会因为自己手上的小事改变主角行动的人。
```

角色修改示例：

```text
把林栖的性格改得更不擅长表达，但不要让她变成高冷模板。她说话要短，做事要具体。
```

小剧场指令示例：

```text
如果林栖出现在成果里，不要每次都安排她做理性分析。让她有自己的麻烦、失误和想完成的小目标。
```

## 数据、隐私和发布边界

Wangcai 的运行期数据默认放在 `data/` 和 `logs/`。这些内容通常包括聊天数据库、记忆库、管理员密码 hash、成果数据、服务日志和本地故事种子。公开发布时只需要代码、静态资源、README 和 release log。

发布前可以检查：

```bash
git status --short
git ls-files | grep -E '(^data/|^logs/|sqlite|\\.db$|\\.pid$|\\.env|safetensors|\\.gguf|\\.bin$|\\.pt$|\\.pth$)'
```

如果命令输出了运行期数据或模型权重，应先移出版本控制再发布。

## 版本说明

具体版本更新记录放在 `log/` 目录，例如：

- `log/wangcai_2.0_release_20260617.md`
- `log/wangcai_2.1_release_20260618.md`
- `log/wangcai_2.2_release_20260621.md`

README 只介绍当前系统能力和部署方式；历史更新细节请看对应 release log。
