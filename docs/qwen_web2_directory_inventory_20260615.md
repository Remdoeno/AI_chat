# qwen_web2 目录说明与清理记录

生成时间：2026-06-15

服务器目录：

```text
/base/home/lizhzh/Project3/qwen_web2
```

当前状态：`qwen_web2` 是正在运行的服务目录。清理后检查到 7777 端口进程为：

```text
pid 136759
/opt/conda/bin/python3 -m uvicorn app:app --host 0.0.0.0 --port 7777
```

`/api/health` 返回 `ok:true`、`db_ok:true`、`model_ok:true`。以后修改和改进应以 `qwen_web2` 为基准，旧的 `qwen_web` 只当历史对照和备份来源。

## 当前目录概览

清理后总大小约 `141M`。

| 路径 | 大小 | 用途 | 清理建议 |
|---|---:|---|---|
| `app.py` | - | FastAPI 入口兼容层，加载 `qwen_app/startup/loader.py`。 | 保留。 |
| `qwen_app/` | 460K | 拆分后的主业务代码：配置、prompt、函数、启动、路由。 | 保留。 |
| `schemas.py` | - | FastAPI 请求体 Pydantic schema。 | 保留。 |
| `streaming_utils.py` | - | SSE 和 think 文本处理工具。 | 保留。 |
| `embedding_client.py` | - | embedding 模型客户端。 | 保留。 |
| `memory.py`、`vector_memory.py` | - | 旧的记忆/向量工具模块，仍可能被业务引用。 | 保留，后续再拆。 |
| `static/` | 326K | 前端页面、CSS、JS、favicon。 | 保留。 |
| `tests/` | 263K | 服务器端回归测试。 | 保留。 |
| `docs/` | 18K | 项目文档。 | 保留。 |
| `data/` | 121M | 当前 SQLite 数据库、auth 配置、故事种子、术语替换。 | 保留。 |
| `logs/` | 19M | 服务运行日志，清理后剩 117 个文件。 | 继续按最近 7 天左右轮转。 |
| `log/` | 11K | 发布/排查命令日志。 | 保留或归档。 |
| `scripts/` | - | 辅助脚本目录。 | 暂保留。 |
| `start_qwen_web.sh`、`stop_qwen_web.sh` | - | Web 服务启动/停止脚本。 | 保留。 |
| `start_qwen_embedding.sh`、`stop_qwen_embedding.sh` | - | embedding 服务启动/停止脚本。 | 保留。 |
| `server_reverse_ssh_watchdog.sh`、`server_start_reverse_ssh.sh` | - | 反向 SSH/隧道相关脚本。 | 暂保留，确认不用隧道后再删。 |
| `analyze_repeated_prompts.py`、`inspect_*.py`、`rebuild_*.py`、`dedupe_curated_memories.py` | - | 手工排查、重建、去重工具脚本。 | 暂保留；后续可移到 `tools/`。 |
| `README.md`、`.gitignore` | - | 项目说明和忽略规则。 | 保留。 |

## 数据目录

`data/` 清理后只保留当前运行必需文件和一个查看工具：

| 路径 | 大小 | 用途 | 清理建议 |
|---|---:|---|---|
| `data/chat_history.sqlite3` | 118M | 当前主 SQLite 数据库。 | 必须保留。 |
| `data/chat_history.sqlite3-shm`、`data/chat_history.sqlite3-wal` | 32K / 3.1M | SQLite WAL 运行文件。 | 服务运行时保留。 |
| `data/admin_auth.json` | 227B | 管理员认证配置。 | 必须保留，不上传 GitHub。 |
| `data/idle_story_seeds.txt` | 2.1K | idle/story 种子。 | 保留。 |
| `data/idle_artifact_term_replacements.json` | 287B | idle 成果术语替换。 | 保留。 |
| `data/view_chat_history.py` | 5.3K | 查看聊天历史工具。 | 暂保留。 |

已从 `qwen_web2/data/` 删除的数据库备份，旧 `qwen_web/data/` 中存在同名文件：

```text
chat_history_before_delete_tongyi_20260527_231423.sqlite3
chat_history_before_delete_tongyi_20260527_231448.sqlite3
chat_history_before_memory_dedupe_20260528_053443.sqlite3
chat_history.before_curated_dedupe_20260605_112629.sqlite3
chat_history.before_curated_dedupe_20260606_164114.sqlite3
chat_history.before_remove_ip_20260606_214727.sqlite3
chat_history.before_user_perspective_rebuild_20260606_163021.sqlite3
chat_history.sqlite3.bak_gross_terms_20260611_154256
chat_history.sqlite3.bak_gross_terms_20260611_154418
```

## 已清理内容

本次清理删除了以下确定不参与运行，或在旧 `qwen_web` 中已有备份来源的内容：

```text
._app.py
._qwen_app
qwen_app_split_payload_20260615.tgz
.__codex_tmp_upload__/
__upload_tmp__/
__pycache__/
qwen_app/**/__pycache__/
*.pyc
.ipynb_checkpoints/
data/.ipynb_checkpoints/
qwen_app/**/.ipynb_checkpoints/
backup_*/
backups/
logs/ 中 7 天以前的旧日志
data/ 中旧数据库备份文件
```

清理前目录约 `495M`，清理后约 `141M`。

## 当前不建议删除

```text
data/chat_history.sqlite3
data/chat_history.sqlite3-wal
data/chat_history.sqlite3-shm
data/admin_auth.json
data/idle_story_seeds.txt
data/idle_artifact_term_replacements.json
qwen_app/
static/
tests/
schemas.py
streaming_utils.py
embedding_client.py
memory.py
vector_memory.py
start_*.sh
stop_*.sh
qwen_web.pid
qwen_embedding.pid
qwen_main.pid
```

## 后续整理方向

1. 继续把 `logs/` 按 7-14 天轮转，不把运行日志提交到 GitHub。
2. 把 `inspect_*.py`、`rebuild_*.py`、`dedupe_*.py`、`analyze_*.py` 迁移到 `tools/`。
3. 对 `data/` 明确运行数据边界：当前库和配置留在服务器，备份依赖旧 `qwen_web` 或外部归档。
4. 后续代码改动只进 `qwen_app/`，逐步减少根目录 Python 脚本数量。
