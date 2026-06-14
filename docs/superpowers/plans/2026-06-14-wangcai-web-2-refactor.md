# Wangcai Web 2.0 Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `/base/home/lizhzh/Project3/wangcai_web` as the 2.0 refactor of the current `qwen_web`, preserving behavior while moving configuration, routing, services, and user-data export into focused modules.

**Architecture:** Start from a byte-for-byte server-side copy of `qwen_web`, then refactor in small compatibility-preserving moves. `app.py` becomes an entrypoint that imports `wangcai.web.app_factory:create_app`; existing behavior is preserved by moving code without changing algorithms, then replacing direct globals with config and service interfaces.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, sqlite3, Pydantic, httpx, OpenAI-compatible APIs, static HTML/CSS/JS, remote server execution via `ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107`.

---

## File Structure

Remote files created under `/base/home/lizhzh/Project3/wangcai_web`:

- `app.py`: FastAPI entrypoint, target under 500 lines.
- `wangcai/core/config.py`: JSON config dataclasses and environment overrides.
- `wangcai/core/paths.py`: Root, config, data, log, static path helpers.
- `wangcai/core/lifecycle.py`: startup/shutdown orchestration.
- `wangcai/core/interfaces.py`: Protocols for model, embedding, memory, artifact, and auth dependencies.
- `wangcai/web/app_factory.py`: builds FastAPI app, mounts static files, registers routers.
- `wangcai/web/static_pages.py`: static page route handlers.
- `wangcai/web/sse.py`: SSE formatting and streaming helpers.
- `wangcai/schemas/*.py`: request/response models split by domain.
- `wangcai/models/qwen_client.py`: OpenAI-compatible chat model client wrapper.
- `wangcai/models/embedding_client.py`: embedding client wrapper.
- `wangcai/persistence/sqlite.py`: connection, row conversion, schema helpers.
- `wangcai/persistence/legacy_compat.py`: compatibility paths and SQLite copy handling.
- `wangcai/auth/*`: auth service and routes.
- `wangcai/chat/*`: chat service, routes, prompt assembly, attachments, rate limits.
- `wangcai/memory/*`: memory repository, recall, vector store, prompts, dedupe.
- `wangcai/search/*`: web search parsing, planner, ranking.
- `wangcai/analysis/*`: trace recording, dashboard data, routes.
- `wangcai/artifacts/*`: artifact repository, idle worker, comments, routes.
- `wangcai/user_data/*`: JSON directory export stores.
- `config/*.json`: 2.0 configuration files.
- `data/legacy/`: copied SQLite/auth files for compatibility, never symlinked to `qwen_web`.
- `data/users/`, `data/devices/`, `data/exports/`: new export-oriented layout.
- `start_wangcai_web.sh`, `stop_wangcai_web.sh`: isolated service scripts.
- `tests/`: copied existing tests plus targeted refactor tests.

Local files modified:

- Create `docs/superpowers/plans/2026-06-14-wangcai-web-2-refactor.md` only for this planning step.
- During implementation, append run logs under local `/Users/rem/Documents/Qwen3部署/log/`.

## Global Execution Rules

- Never modify `/base/home/lizhzh/Project3/qwen_web`.
- Every remote command uses:

```bash
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 'cd /base/home/lizhzh/Project3 && <command>'
```

- Every local command that records work appends to a task-specific file under `/Users/rem/Documents/Qwen3部署/log/`.
- Do not run backend tests locally.
- Prefer remote compile/static tests after each move:

```bash
cd /base/home/lizhzh/Project3/wangcai_web
/opt/conda/bin/python3 -m py_compile app.py $(find wangcai -name '*.py' | sort)
/opt/conda/bin/python3 -m pytest tests/test_static_regressions.py -q
```

- Use test port `7788` for `wangcai_web` until the user explicitly switches traffic.

---

### Task 1: Create Isolated Server Copy

**Files:**
- Create remote: `/base/home/lizhzh/Project3/wangcai_web`
- Read-only source: `/base/home/lizhzh/Project3/qwen_web`
- Create local log: `/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task1-copy-YYYYMMDD.log`

- [ ] **Step 1: Record local task start**

Run locally:

```bash
mkdir -p /Users/rem/Documents/Qwen3部署/log
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task1-copy-$(date '+%Y%m%d').log"
printf 'task=wangcai_web_2_task1_copy\nstarted_at=%s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" > "$LOG"
```

Expected: log file exists and contains `task=wangcai_web_2_task1_copy`.

- [ ] **Step 2: Snapshot qwen_web before copying**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task1-copy-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 \
  'cd /base/home/lizhzh/Project3/qwen_web && git status --short && find . -maxdepth 2 -type f | sort | sha256sum' \
  | tee -a "$LOG"
```

Expected: `git status --short` prints no changed files for remote `qwen_web`; the command emits one SHA line for the file-list snapshot.

- [ ] **Step 3: Create wangcai_web without touching qwen_web**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task1-copy-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  set -euo pipefail
  cd /base/home/lizhzh/Project3
  if [ -e wangcai_web ]; then
    echo "ERROR: wangcai_web already exists"
    exit 1
  fi
  rsync -a --exclude logs --exclude log --exclude __pycache__ --exclude "*.pyc" qwen_web/ wangcai_web/
  mkdir -p wangcai_web/logs wangcai_web/data/legacy wangcai_web/data/users wangcai_web/data/devices wangcai_web/data/exports
  cp -a qwen_web/data/chat_history.sqlite3 wangcai_web/data/legacy/chat_history.sqlite3
  cp -a qwen_web/data/admin_auth.json wangcai_web/data/legacy/admin_auth.json
  find wangcai_web -maxdepth 2 -type d | sort | sed -n "1,120p"
' | tee -a "$LOG"
```

Expected: `wangcai_web` exists; `qwen_web` is not modified; copied runtime data lives under `wangcai_web/data/legacy`.

- [ ] **Step 4: Verify qwen_web still unchanged**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task1-copy-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 \
  'cd /base/home/lizhzh/Project3/qwen_web && git status --short' \
  | tee -a "$LOG"
```

Expected: no output after the command.

- [ ] **Step 5: Compile copied baseline remotely**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task1-copy-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 -m py_compile app.py schemas.py embedding_client.py memory.py vector_memory.py streaming_utils.py
' | tee -a "$LOG"
```

Expected: exit code 0, no Python syntax errors.

---

### Task 2: Add Package Skeleton and App Factory

**Files:**
- Create remote: `wangcai/__init__.py`
- Create remote: `wangcai/core/__init__.py`, `wangcai/core/paths.py`, `wangcai/core/lifecycle.py`
- Create remote: `wangcai/web/__init__.py`, `wangcai/web/app_factory.py`
- Modify remote: `app.py`

- [ ] **Step 1: Create package skeleton**

Run remotely in `/base/home/lizhzh/Project3/wangcai_web`:

```bash
mkdir -p wangcai/core wangcai/web
touch wangcai/__init__.py wangcai/core/__init__.py wangcai/web/__init__.py
cat > wangcai/core/paths.py <<'PY'
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = APP_ROOT / "static"
CONFIG_DIR = APP_ROOT / "config"
DATA_DIR = APP_ROOT / "data"
LOG_DIR = APP_ROOT / "logs"
PY
cat > wangcai/core/lifecycle.py <<'PY'
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app_legacy import init_db, start_background_workers

    init_db()
    start_background_workers()
    yield
PY
```

Expected: files exist and contain no imports from `qwen_web`.

- [ ] **Step 2: Preserve legacy app code under app_legacy.py**

Run remotely:

```bash
cp app.py app_legacy.py
```

Expected: `app_legacy.py` exists and matches the copied baseline `app.py`.

- [ ] **Step 3: Create app factory that reuses legacy app initially**

Run remotely:

```bash
cat > wangcai/web/app_factory.py <<'PY'
from fastapi import FastAPI


def create_app() -> FastAPI:
    from app_legacy import app

    return app
PY
cat > app.py <<'PY'
from wangcai.web.app_factory import create_app

app = create_app()
PY
```

Expected: `app.py` is under 10 lines and imports only the factory.

- [ ] **Step 4: Verify compatibility compile**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task2-app-factory-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name "*.py" | sort)
  wc -l app.py
' | tee "$LOG"
```

Expected: compile succeeds and `wc -l app.py` reports fewer than 500 lines.

---

### Task 3: Split Schemas, Streaming, Embedding, Memory Base Modules

**Files:**
- Create remote: `wangcai/schemas/*.py`
- Create remote: `wangcai/web/sse.py`
- Create remote: `wangcai/models/embedding_client.py`
- Create remote: `wangcai/memory/base_repository.py`
- Create remote: `wangcai/memory/vector_store.py`
- Modify remote: `app_legacy.py`

- [ ] **Step 1: Move schema classes into domain files**

Run remotely:

```bash
mkdir -p wangcai/schemas
touch wangcai/schemas/__init__.py
cp schemas.py wangcai/schemas/legacy.py
cat > wangcai/schemas/__init__.py <<'PY'
from .legacy import (
    AdminLoginPayload,
    ArtifactCommentPayload,
    AuthPasswordPayload,
    ChatAttachment,
    ChatPayload,
    IdlePromptPayload,
    IdleStatusPayload,
    MemoryAdminPayload,
    UserMemoryBindingPayload,
)

__all__ = [
    "AdminLoginPayload",
    "ArtifactCommentPayload",
    "AuthPasswordPayload",
    "ChatAttachment",
    "ChatPayload",
    "IdlePromptPayload",
    "IdleStatusPayload",
    "MemoryAdminPayload",
    "UserMemoryBindingPayload",
]
PY
```

Expected: existing schema imports can be switched to `wangcai.schemas`.

- [ ] **Step 2: Copy support modules into focused package locations**

Run remotely:

```bash
mkdir -p wangcai/models wangcai/memory
touch wangcai/models/__init__.py wangcai/memory/__init__.py
cp streaming_utils.py wangcai/web/sse.py
cp embedding_client.py wangcai/models/embedding_client.py
cp memory.py wangcai/memory/base_repository.py
cp vector_memory.py wangcai/memory/vector_store.py
```

Expected: copied files are identical to legacy modules.

- [ ] **Step 3: Update imports in app_legacy.py**

Run remotely:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("app_legacy.py")
text = p.read_text()
text = text.replace("import embedding_client\n", "from wangcai.models import embedding_client\n")
text = text.replace("import memory\n", "from wangcai.memory import base_repository as memory\n")
text = text.replace("import vector_memory\n", "from wangcai.memory import vector_store as vector_memory\n")
text = text.replace("from schemas import (", "from wangcai.schemas import (")
text = text.replace("from streaming_utils import ThinkStripper, format_sse, split_think_text", "from wangcai.web.sse import ThinkStripper, format_sse, split_think_text")
p.write_text(text)
PY
```

Expected: `app_legacy.py` imports moved modules; root copies remain for compatibility during transition.

- [ ] **Step 4: Run remote compile and targeted static tests**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task3-base-modules-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name "*.py" | sort)
  /opt/conda/bin/python3 -m pytest tests/test_static_regressions.py -q
' | tee "$LOG"
```

Expected: compile succeeds; static regression tests pass on the server.

---

### Task 4: Add JSON Configuration System

**Files:**
- Create remote: `wangcai/core/config.py`
- Create remote: `config/app.json`, `config/models.json`, `config/memory.json`, `config/search.json`, `config/idle_agent.json`, `config/auth.json`, `config/rate_limit.json`, `config/user_data.json`, `config/ui.json`
- Modify remote: `app_legacy.py`

- [ ] **Step 1: Create config loader**

Run remotely:

```bash
mkdir -p config
cat > wangcai/core/config.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Dict

from .paths import CONFIG_DIR, DATA_DIR


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RuntimeConfig:
    web_host: str
    web_port: int
    db_path: Path
    auth_config_path: Path
    model_base_url: str
    model_name: str
    model_api_key: str
    embedding_base_url: str
    embedding_model: str
    version: str


def load_config(config_dir: Path = CONFIG_DIR) -> RuntimeConfig:
    app = _read_json(config_dir / "app.json")
    models = _read_json(config_dir / "models.json")
    auth = _read_json(config_dir / "auth.json")
    ui = _read_json(config_dir / "ui.json")
    data = _read_json(config_dir / "user_data.json")
    legacy_dir = DATA_DIR / "legacy"
    return RuntimeConfig(
        web_host=os.environ.get("WEB_HOST", str(app.get("host", "0.0.0.0"))),
        web_port=int(os.environ.get("WEB_PORT", app.get("port", 7788))),
        db_path=Path(os.environ.get("QWEN_WEB_DB", data.get("legacy_db_path", str(legacy_dir / "chat_history.sqlite3")))),
        auth_config_path=Path(os.environ.get("QWEN_AUTH_CONFIG", auth.get("auth_config_path", str(legacy_dir / "admin_auth.json")))),
        model_base_url=os.environ.get("QWEN_MODEL_BASE_URL", models.get("chat", {}).get("base_url", "http://127.0.0.1:8000/v1")),
        model_name=os.environ.get("QWEN_MODEL_NAME", models.get("chat", {}).get("model_name", "qwen3.6-35b-a3b-262k")),
        model_api_key=os.environ.get("QWEN_MODEL_API_KEY", os.environ.get("OPENAI_API_KEY", models.get("chat", {}).get("api_key", "EMPTY"))).strip() or "EMPTY",
        embedding_base_url=os.environ.get("QWEN_EMBEDDING_BASE_URL", models.get("embedding", {}).get("base_url", "http://127.0.0.1:8001/v1")),
        embedding_model=os.environ.get("QWEN_EMBEDDING_MODEL", models.get("embedding", {}).get("model_name", "qwen3-embedding-8b")),
        version=str(ui.get("version", "2.0")),
    )
PY
```

Expected: `load_config()` returns a frozen config object.

- [ ] **Step 2: Create config JSON files**

Run remotely:

```bash
cat > config/app.json <<'JSON'
{"name":"旺财","version":"2.0","host":"0.0.0.0","port":7788,"timezone":"Asia/Shanghai","log_level":"info"}
JSON
cat > config/models.json <<'JSON'
{"chat":{"base_url":"http://127.0.0.1:8000/v1","model_name":"qwen3.6-35b-a3b-262k","api_key":"EMPTY","timeout":1200},"embedding":{"base_url":"http://127.0.0.1:8001/v1","model_name":"qwen3-embedding-8b","api_key":""}}
JSON
cat > config/memory.json <<'JSON'
{"curated_top_k":8,"curated_min_score":0.5,"recall_pool_size":18,"judge_timeout":45,"write_dedupe_threshold":0.88}
JSON
cat > config/search.json <<'JSON'
{"enabled":true,"proxy":"","max_results":5,"summary_max_chars":240}
JSON
cat > config/idle_agent.json <<'JSON'
{"enabled":true,"min_idle_seconds":90,"loop_seconds":30,"min_run_interval_seconds":300,"max_tokens":2400}
JSON
cat > config/auth.json <<'JSON'
{"auth_config_path":"data/legacy/admin_auth.json"}
JSON
cat > config/rate_limit.json <<'JSON'
{"chat_device_min_interval_seconds":5}
JSON
cat > config/user_data.json <<'JSON'
{"root":"data","legacy_db_path":"data/legacy/chat_history.sqlite3","users_path":"data/users","devices_path":"data/devices","exports_path":"data/exports"}
JSON
cat > config/ui.json <<'JSON'
{"version":"2.0","title":"旺财2.0 Ai助手聊天","cache_version":"20260614_wangcai_2_refactor"}
JSON
```

Expected: config directory contains nine JSON files.

- [ ] **Step 3: Apply config to legacy globals**

Run remotely:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("app_legacy.py")
text = p.read_text()
text = text.replace("from pathlib import Path\n", "from pathlib import Path\nfrom wangcai.core.config import load_config\n")
text = text.replace("APP_DIR = Path(__file__).resolve().parent\nSTATIC_DIR = APP_DIR / \"static\"\nDATA_DIR = APP_DIR / \"data\"\nDB_PATH = Path(os.environ.get(\"QWEN_WEB_DB\", DATA_DIR / \"chat_history.sqlite3\"))\nAUTH_CONFIG_PATH = Path(os.environ.get(\"QWEN_AUTH_CONFIG\", DATA_DIR / \"admin_auth.json\"))", "APP_DIR = Path(__file__).resolve().parent\nSTATIC_DIR = APP_DIR / \"static\"\nDATA_DIR = APP_DIR / \"data\"\nRUNTIME_CONFIG = load_config()\nDB_PATH = RUNTIME_CONFIG.db_path\nAUTH_CONFIG_PATH = RUNTIME_CONFIG.auth_config_path")
text = text.replace("BASE_URL = os.environ.get(\"QWEN_MODEL_BASE_URL\", \"http://127.0.0.1:8000/v1\")\nMODEL_NAME = os.environ.get(\"QWEN_MODEL_NAME\", \"qwen3.6-35b-a3b-262k\")\nMODEL_API_KEY = os.environ.get(\"QWEN_MODEL_API_KEY\", os.environ.get(\"OPENAI_API_KEY\", \"EMPTY\")).strip() or \"EMPTY\"", "BASE_URL = RUNTIME_CONFIG.model_base_url\nMODEL_NAME = RUNTIME_CONFIG.model_name\nMODEL_API_KEY = RUNTIME_CONFIG.model_api_key")
p.write_text(text)
PY
```

Expected: config object supplies DB/auth/model paths while environment overrides still work.

- [ ] **Step 4: Verify config and compile**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task4-config-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 - <<PY
from wangcai.core.config import load_config
c = load_config()
assert c.web_port == 7788
assert str(c.db_path).endswith("data/legacy/chat_history.sqlite3")
print(c)
PY
  /opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name "*.py" | sort)
' | tee "$LOG"
```

Expected: config prints with `web_port=7788`; compile succeeds.

---

### Task 5: Extract Static Page Routes and App Assembly

**Files:**
- Create remote: `wangcai/web/static_pages.py`
- Modify remote: `wangcai/web/app_factory.py`
- Modify remote: `app_legacy.py`

- [ ] **Step 1: Create static page router**

Run remotely:

```bash
cat > wangcai/web/static_pages.py <<'PY'
from fastapi import APIRouter
from fastapi.responses import FileResponse

from wangcai.core.paths import STATIC_DIR

router = APIRouter(include_in_schema=False)


def html_response(filename: str) -> FileResponse:
    return FileResponse(
        STATIC_DIR / filename,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )


@router.get("/")
def index() -> FileResponse:
    return html_response("index.html")


@router.get("/auth")
def auth_page() -> FileResponse:
    return html_response("auth.html")


@router.get("/memory")
def memory_page() -> FileResponse:
    return html_response("memory.html")


@router.get("/memory-admin")
def memory_admin_page() -> FileResponse:
    return html_response("memory_admin_login.html")


@router.get("/warn")
def warn_page() -> FileResponse:
    return html_response("warn.html")


@router.get("/artifacts")
def artifacts_page() -> FileResponse:
    return html_response("artifacts.html")


@router.get("/analysis")
def analysis_page() -> FileResponse:
    return html_response("analysis_login.html")


@router.get("/favicon.ico")
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")
PY
```

Expected: page routes exist in `static_pages.router`.

- [ ] **Step 2: Disable duplicate static page decorators in app_legacy.py**

Run remotely:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("app_legacy.py")
text = p.read_text()
for route in ['@app.get("/", include_in_schema=False)', '@app.get("/auth", include_in_schema=False)', '@app.get("/memory", include_in_schema=False)', '@app.get("/memory-admin", include_in_schema=False)', '@app.get("/warn", include_in_schema=False)', '@app.get("/artifacts", include_in_schema=False)', '@app.get("/analysis", include_in_schema=False)', '@app.get("/favicon.ico", include_in_schema=False)']:
    text = text.replace(route, "# moved to wangcai.web.static_pages\n# " + route)
p.write_text(text)
PY
```

Expected: legacy static route decorators are commented, API routes remain intact.

- [ ] **Step 3: Register static router after importing legacy app**

Run remotely:

```bash
cat > wangcai/web/app_factory.py <<'PY'
from fastapi import FastAPI

from .static_pages import router as static_pages_router


def create_app() -> FastAPI:
    from app_legacy import app

    app.include_router(static_pages_router)
    return app
PY
```

Expected: the same URLs are served by the new module.

- [ ] **Step 4: Verify route registration**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task5-static-routes-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name "*.py" | sort)
  /opt/conda/bin/python3 - <<PY
from app import app
paths = sorted({r.path for r in app.routes})
for expected in ["/", "/auth", "/memory", "/memory-admin", "/warn", "/artifacts", "/analysis", "/api/health"]:
    assert expected in paths, expected
print("routes ok", len(paths))
PY
' | tee "$LOG"
```

Expected: all listed paths are present.

---

### Task 6: Extract Auth, Memory Dashboard, and Artifact Routes Incrementally

**Files:**
- Create remote: `wangcai/auth/routes.py`
- Create remote: `wangcai/memory/routes.py`
- Create remote: `wangcai/artifacts/routes.py`
- Modify remote: `app_legacy.py`
- Modify remote: `wangcai/web/app_factory.py`

- [ ] **Step 1: Move auth routes as thin wrappers**

Run remotely:

```bash
mkdir -p wangcai/auth
touch wangcai/auth/__init__.py
cat > wangcai/auth/routes.py <<'PY'
from fastapi import APIRouter, Request

from wangcai.schemas import AdminLoginPayload, AuthPasswordPayload

router = APIRouter()


@router.get("/api/auth/status")
def auth_status():
    from app_legacy import auth_status as legacy_auth_status

    return legacy_auth_status()


@router.post("/api/auth/password")
def auth_password(payload: AuthPasswordPayload):
    from app_legacy import auth_password as legacy_auth_password

    return legacy_auth_password(payload)


@router.post("/api/admin/login")
def admin_login(payload: AdminLoginPayload, request: Request):
    from app_legacy import admin_login as legacy_admin_login

    return legacy_admin_login(payload, request)


@router.post("/api/analysis/login")
def analysis_login(payload: AdminLoginPayload, request: Request):
    from app_legacy import analysis_login as legacy_analysis_login

    return legacy_analysis_login(payload, request)
PY
```

Expected: auth routes call legacy implementations through module boundaries.

- [ ] **Step 2: Move memory dashboard routes as thin wrappers**

Run remotely:

```bash
cat > wangcai/memory/routes.py <<'PY'
from fastapi import APIRouter, Query, Request

from wangcai.schemas import MemoryAdminPayload

router = APIRouter()


@router.get("/api/memory/memories")
def memory_dashboard_memories(request: Request, limit: int = Query(50, ge=1, le=200)):
    from app_legacy import memory_dashboard_memories as legacy

    return legacy(request, limit)


@router.get("/api/memory/retrievals")
def memory_dashboard_retrievals(request: Request, limit: int = Query(50, ge=1, le=200)):
    from app_legacy import memory_dashboard_retrievals as legacy

    return legacy(request, limit)


@router.get("/api/memory/operations")
def memory_dashboard_operations(request: Request, limit: int = Query(50, ge=1, le=200)):
    from app_legacy import memory_dashboard_operations as legacy

    return legacy(request, limit)


@router.get("/api/admin/memories")
def admin_memories(request: Request, limit: int = Query(100, ge=1, le=500), label: str = ""):
    from app_legacy import admin_memories as legacy

    return legacy(request, limit, label)


@router.post("/api/admin/memories")
def admin_create_memory(payload: MemoryAdminPayload, request: Request):
    from app_legacy import admin_create_memory as legacy

    return legacy(payload, request)
PY
```

Expected: route functions remain thin, no SQL appears in `routes.py`.

- [ ] **Step 3: Move artifact list/status routes as thin wrappers**

Run remotely:

```bash
mkdir -p wangcai/artifacts
touch wangcai/artifacts/__init__.py
cat > wangcai/artifacts/routes.py <<'PY'
from fastapi import APIRouter, Query, Request

from wangcai.schemas import IdlePromptPayload, IdleStatusPayload

router = APIRouter()


@router.get("/api/artifacts")
def artifacts(request: Request, category: str = "", sort: str = "newest", limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    from app_legacy import artifacts as legacy

    return legacy(request, category, sort, limit, offset)


@router.get("/api/artifacts/runs")
def artifact_runs(request: Request, limit: int = Query(20, ge=1, le=100)):
    from app_legacy import artifact_runs as legacy

    return legacy(request, limit)


@router.get("/api/artifacts/prompt")
def artifact_prompt(request: Request):
    from app_legacy import artifact_prompt as legacy

    return legacy(request)


@router.put("/api/artifacts/prompt")
def update_artifact_prompt(payload: IdlePromptPayload, request: Request):
    from app_legacy import update_artifact_prompt as legacy

    return legacy(payload, request)


@router.get("/api/artifacts/idle-status")
def artifact_idle_status(request: Request):
    from app_legacy import artifact_idle_status as legacy

    return legacy(request)


@router.put("/api/artifacts/idle-status")
def update_artifact_idle_status(payload: IdleStatusPayload, request: Request):
    from app_legacy import update_artifact_idle_status as legacy

    return legacy(payload, request)
PY
```

Expected: initial artifact routing is module-owned while behavior stays legacy.

- [ ] **Step 4: Comment moved decorators and register routers**

Run remotely:

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("app_legacy.py")
text = p.read_text()
for path in [
    "/api/auth/status", "/api/auth/password", "/api/admin/login", "/api/analysis/login",
    "/api/memory/memories", "/api/memory/retrievals", "/api/memory/operations",
    "/api/admin/memories", "/api/artifacts", "/api/artifacts/runs",
    "/api/artifacts/prompt", "/api/artifacts/idle-status",
]:
    text = text.replace(f'@app.get("{path}"', f'# moved route\n# @app.get("{path}"')
    text = text.replace(f'@app.post("{path}"', f'# moved route\n# @app.post("{path}"')
    text = text.replace(f'@app.put("{path}"', f'# moved route\n# @app.put("{path}"')
p.write_text(text)
PY
cat > wangcai/web/app_factory.py <<'PY'
from fastapi import FastAPI

from wangcai.artifacts.routes import router as artifacts_router
from wangcai.auth.routes import router as auth_router
from wangcai.memory.routes import router as memory_router
from .static_pages import router as static_pages_router


def create_app() -> FastAPI:
    from app_legacy import app

    app.include_router(static_pages_router)
    app.include_router(auth_router)
    app.include_router(memory_router)
    app.include_router(artifacts_router)
    return app
PY
```

Expected: moved routes are registered from `wangcai`.

- [ ] **Step 5: Verify routes and compile**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task6-route-wrappers-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name "*.py" | sort)
  /opt/conda/bin/python3 - <<PY
from app import app
paths = sorted({r.path for r in app.routes})
for expected in ["/api/auth/status", "/api/memory/memories", "/api/artifacts", "/api/artifacts/prompt"]:
    assert expected in paths, expected
print("moved route wrappers ok")
PY
' | tee "$LOG"
```

Expected: compile succeeds; route list includes moved endpoints.

---

### Task 7: Add User Data Export Layout

**Files:**
- Create remote: `wangcai/user_data/export.py`
- Create remote: `wangcai/user_data/device_store.py`
- Create remote: `wangcai/user_data/user_store.py`
- Create remote: `tools/export_user_data.py`

- [ ] **Step 1: Create JSONL writer helpers**

Run remotely:

```bash
mkdir -p wangcai/user_data tools
touch wangcai/user_data/__init__.py
cat > wangcai/user_data/export.py <<'PY'
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Mapping


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
            count += 1
    return count


def export_legacy_sqlite(db_path: Path, output_root: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    stats = {"users": 0, "devices": 0, "sessions": 0, "messages": 0, "memories": 0, "artifacts": 0}
    devices = [dict(row) for row in conn.execute("SELECT * FROM visitor_identities ORDER BY id ASC").fetchall()] if _table_exists(conn, "visitor_identities") else []
    write_json(output_root / "devices" / "index.json", devices)
    stats["devices"] = len(devices)
    bindings = [dict(row) for row in conn.execute("SELECT * FROM user_memory_bindings ORDER BY id ASC").fetchall()] if _table_exists(conn, "user_memory_bindings") else []
    write_json(output_root / "users" / "users.json", bindings)
    stats["users"] = len(bindings)
    if _table_exists(conn, "sessions"):
        sessions = conn.execute("SELECT * FROM sessions ORDER BY created_at ASC").fetchall()
        stats["sessions"] = write_jsonl(output_root / "exports" / "sessions.jsonl", sessions)
    if _table_exists(conn, "messages"):
        messages = conn.execute("SELECT * FROM messages ORDER BY id ASC").fetchall()
        stats["messages"] = write_jsonl(output_root / "exports" / "messages.jsonl", messages)
    if _table_exists(conn, "curated_memories"):
        memories = conn.execute("SELECT * FROM curated_memories ORDER BY id ASC").fetchall()
        stats["memories"] = write_jsonl(output_root / "exports" / "curated_memories.jsonl", memories)
    if _table_exists(conn, "idle_agent_artifacts"):
        artifacts = conn.execute("SELECT * FROM idle_agent_artifacts ORDER BY id ASC").fetchall()
        stats["artifacts"] = write_jsonl(output_root / "exports" / "artifacts.jsonl", artifacts)
    conn.close()
    write_json(output_root / "exports" / "export_stats.json", stats)
    return stats


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return row is not None
PY
```

Expected: export helpers only read legacy SQLite and write JSON/JSONL files.

- [ ] **Step 2: Create export CLI**

Run remotely:

```bash
cat > tools/export_user_data.py <<'PY'
from pathlib import Path

from wangcai.core.config import load_config
from wangcai.user_data.export import export_legacy_sqlite


def main() -> int:
    config = load_config()
    output_root = Path("data")
    stats = export_legacy_sqlite(config.db_path, output_root)
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
```

Expected: CLI imports the config loader and export helper.

- [ ] **Step 3: Run read-only export against copied legacy DB**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task7-user-data-export-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 tools/export_user_data.py
  find data/exports data/users data/devices -maxdepth 2 -type f | sort | sed -n "1,80p"
' | tee "$LOG"
```

Expected: `data/exports/export_stats.json` exists; export reads `data/legacy/chat_history.sqlite3`, not `qwen_web/data/chat_history.sqlite3`.

---

### Task 8: Add Isolated Start/Stop Scripts

**Files:**
- Create remote: `start_wangcai_web.sh`
- Create remote: `stop_wangcai_web.sh`
- Modify remote: `README_WANGCAI_2.md`

- [ ] **Step 1: Create start script**

Run remotely:

```bash
cat > start_wangcai_web.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

WEB_HOST=${WEB_HOST:-0.0.0.0}
WEB_PORT=${WEB_PORT:-7788}
PYTHON=${PYTHON:-/opt/conda/bin/python3}
LOG_DIR=${LOG_DIR:-logs}
PID_FILE=${PID_FILE:-wangcai_web.pid}
LOG_FILE="$LOG_DIR/wangcai_web_${WEB_PORT}_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR" data data/legacy data/users data/devices data/exports

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    echo "ERROR: wangcai_web is already running with PID $OLD_PID"
    exit 1
  fi
  rm -f "$PID_FILE"
fi

if ss -ltn 2>/dev/null | awk '{print $4}' | grep -Eq "(:|\\])${WEB_PORT}$"; then
  echo "ERROR: port $WEB_PORT is already in use."
  exit 1
fi

export WEB_PORT
export QWEN_WEB_DB=${QWEN_WEB_DB:-"$PWD/data/legacy/chat_history.sqlite3"}
export QWEN_AUTH_CONFIG=${QWEN_AUTH_CONFIG:-"$PWD/data/legacy/admin_auth.json"}

echo "Starting wangcai_web on ${WEB_HOST}:${WEB_PORT}"
echo "Log file: $LOG_FILE"

nohup "$PYTHON" -m uvicorn app:app --host "$WEB_HOST" --port "$WEB_PORT" > "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"
sleep 2

if ! kill -0 "$PID" >/dev/null 2>&1; then
  echo "ERROR: wangcai_web failed to start. Last log lines:"
  tail -n 120 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  exit 1
fi

echo "wangcai_web started with PID $PID"
SH
chmod +x start_wangcai_web.sh
```

Expected: start script defaults to test port 7788 and legacy data copy.

- [ ] **Step 2: Create stop script**

Run remotely:

```bash
cat > stop_wangcai_web.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=${PID_FILE:-wangcai_web.pid}

if [ ! -f "$PID_FILE" ]; then
  echo "wangcai_web is not running: missing $PID_FILE"
  exit 0
fi

PID=$(cat "$PID_FILE")
if [ -z "$PID" ] || ! kill -0 "$PID" >/dev/null 2>&1; then
  echo "wangcai_web is not running: stale PID $PID"
  rm -f "$PID_FILE"
  exit 0
fi

kill "$PID"
for _ in $(seq 1 20); do
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    rm -f "$PID_FILE"
    echo "wangcai_web stopped"
    exit 0
  fi
  sleep 0.5
done

echo "wangcai_web did not stop gracefully; sending SIGKILL"
kill -9 "$PID" || true
rm -f "$PID_FILE"
SH
chmod +x stop_wangcai_web.sh
```

Expected: stop script only manages `wangcai_web.pid`.

- [ ] **Step 3: Document isolated startup**

Run remotely:

```bash
cat > README_WANGCAI_2.md <<'MD'
# Wangcai Web 2.0 Refactor Runtime

This directory is the isolated 2.0 refactor target. Do not edit `/base/home/lizhzh/Project3/qwen_web` during this migration.

Default test startup:

```bash
WEB_PORT=7788 ./start_wangcai_web.sh
curl http://127.0.0.1:7788/api/health
./stop_wangcai_web.sh
```

Runtime data defaults to `data/legacy/` while the refactor preserves qwen_web behavior.
MD
```

Expected: README documents port 7788 and no `qwen_web` writes.

---

### Task 9: Remote Smoke Test on Test Port

**Files:**
- Read remote: `logs/wangcai_web_7788_*.log`
- Read remote: `wangcai_web.pid`

- [ ] **Step 1: Start wangcai_web on port 7788**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task9-smoke-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  WEB_PORT=7788 ./start_wangcai_web.sh
' | tee "$LOG"
```

Expected: output includes `wangcai_web started with PID`.

- [ ] **Step 2: Probe health and pages**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task9-smoke-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  set -e
  curl -fsS http://127.0.0.1:7788/api/health
  printf "\n--- index title ---\n"
  curl -fsS http://127.0.0.1:7788/ | grep -E "<title>|styles.css|app.js"
  printf "\n--- analysis static ---\n"
  curl -fsS http://127.0.0.1:7788/analysis | grep -E "<title>|analysis.css|analysis.js"
' | tee -a "$LOG"
```

Expected: health request succeeds; pages include expected static references.

- [ ] **Step 3: Stop wangcai_web**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-task9-smoke-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  ./stop_wangcai_web.sh
' | tee -a "$LOG"
```

Expected: output includes `wangcai_web stopped` or stale PID cleanup.

---

### Task 10: Reduce app_legacy.py by Moving Services Out of Legacy

**Files:**
- Create/modify remote: `wangcai/search/*.py`, `wangcai/analysis/*.py`, `wangcai/chat/*.py`, `wangcai/artifacts/*.py`, `wangcai/memory/*.py`
- Modify remote: `app_legacy.py`

- [ ] **Step 1: Inventory function groups in app_legacy.py**

Run remotely:

```bash
cd /base/home/lizhzh/Project3/wangcai_web
/opt/conda/bin/python3 - <<'PY'
import ast
from pathlib import Path
tree = ast.parse(Path("app_legacy.py").read_text())
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        print(f"{node.lineno:05d} {type(node).__name__} {node.name}")
PY
```

Expected: a line-numbered list of all top-level functions/classes to guide moves.

- [ ] **Step 2: Move search parser/planner block first**

Move these existing definitions from `app_legacy.py` to `wangcai/search/service.py`, preserving function bodies exactly:

```text
SearchHTMLParser
PageTextParser
clean_search_text
clean_search_result_url
strip_html_fragment
should_skip_search_result
normalize_relative_years
extract_search_results
normalize_web_search_proxy
build_web_search_query
is_hot_search_query
is_youtube_trending_query
is_authoritative_fact_query
is_authority_url
extract_relevance_terms
search_required_terms
search_result_relevance
rank_search_results
source_confidence
decode_jsonish_text
extract_hot_search_items
fetch_hot_search_results
perform_general_web_search
parse_search_plan_response
fallback_search_plan
search_plan_display_query
format_search_planner_context
build_search_planner_user_prompt
build_search_plan
perform_web_search
fetch_web_page_summary
assign_source_registry
append_source_footer_if_missing
format_web_search_context
```

In `app_legacy.py`, replace the moved definitions with:

```python
from wangcai.search.service import (
    SearchHTMLParser,
    PageTextParser,
    clean_search_text,
    clean_search_result_url,
    strip_html_fragment,
    should_skip_search_result,
    normalize_relative_years,
    extract_search_results,
    normalize_web_search_proxy,
    build_web_search_query,
    is_hot_search_query,
    is_youtube_trending_query,
    is_authoritative_fact_query,
    is_authority_url,
    extract_relevance_terms,
    search_required_terms,
    search_result_relevance,
    rank_search_results,
    source_confidence,
    decode_jsonish_text,
    extract_hot_search_items,
    fetch_hot_search_results,
    perform_general_web_search,
    parse_search_plan_response,
    fallback_search_plan,
    search_plan_display_query,
    format_search_planner_context,
    build_search_planner_user_prompt,
    build_search_plan,
    perform_web_search,
    fetch_web_page_summary,
    assign_source_registry,
    append_source_footer_if_missing,
    format_web_search_context,
)
```

Expected: app behavior is unchanged because names remain available in `app_legacy.py`.

- [ ] **Step 3: Compile after search extraction**

Run remotely:

```bash
cd /base/home/lizhzh/Project3/wangcai_web
/opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name '*.py' | sort)
```

Expected: compile succeeds.

- [ ] **Step 4: Repeat exact-body moves by domain**

Move exact function bodies in this order, compiling after each domain:

```text
wangcai/memory/recall.py: memory retrieval query, gate, judge, recall formatting, curated memory selection
wangcai/memory/repository.py: curated memory CRUD, visitor binding, event memory update persistence
wangcai/analysis/service.py: trace recording, dashboard payload formatters, background activity formatting
wangcai/artifacts/service.py: artifact save/list/like/comment, idle artifact context, term replacement
wangcai/artifacts/idle_worker.py: idle worker loop, watchdog, background run orchestration
wangcai/chat/service.py: session creation/reset/close, message persistence, model message assembly, chat stream orchestration
```

Expected after each move: `app_legacy.py` imports the names from the new module; no business logic is changed during the move.

- [ ] **Step 5: Verify legacy file size reduction**

Run remotely:

```bash
cd /base/home/lizhzh/Project3/wangcai_web
wc -l app.py app_legacy.py
/opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name '*.py' | sort)
```

Expected: `app.py` remains under 500 lines; `app_legacy.py` is reduced substantially and contains route wrappers plus compatibility globals only.

---

### Task 11: Final Remote Verification

**Files:**
- Read remote: `/base/home/lizhzh/Project3/qwen_web`
- Read remote: `/base/home/lizhzh/Project3/wangcai_web`

- [ ] **Step 1: Verify qwen_web unchanged**

Run locally:

```bash
LOG="/Users/rem/Documents/Qwen3部署/log/wangcai-web-2-final-verify-$(date '+%Y%m%d').log"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 \
  'cd /base/home/lizhzh/Project3/qwen_web && git status --short' \
  | tee "$LOG"
```

Expected: no output from `git status --short`.

- [ ] **Step 2: Run wangcai_web compile and tests remotely**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-final-verify-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  /opt/conda/bin/python3 -m py_compile app.py app_legacy.py $(find wangcai -name "*.py" | sort)
  /opt/conda/bin/python3 -m pytest tests/test_static_regressions.py -q
  /opt/conda/bin/python3 -m pytest tests/test_app_behaviors.py -q
' | tee -a "$LOG"
```

Expected: compile and tests pass on the server.

- [ ] **Step 3: Verify app.py line count**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-final-verify-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 \
  'cd /base/home/lizhzh/Project3/wangcai_web && wc -l app.py' \
  | tee -a "$LOG"
```

Expected: line count is less than or equal to 500.

- [ ] **Step 4: Produce deployment inventory**

Run locally:

```bash
LOG="$(ls -t /Users/rem/Documents/Qwen3部署/log/wangcai-web-2-final-verify-*.log | head -1)"
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 '
  cd /base/home/lizhzh/Project3/wangcai_web
  find app.py wangcai config static -type f | sort | xargs wc -l
' | tee -a "$LOG"
```

Expected: inventory lists refactored source, config, and static files with line counts.

## Self-Review Checklist

- Spec coverage: Tasks cover isolated copy, app.py under 500 lines, config JSON, modular code movement, user data export layout, isolated scripts, remote verification, and qwen_web no-touch requirement.
- 空项扫描：没有未决占位说明，也没有未指定实现细节的任务。
- Type consistency: config loader uses `RuntimeConfig`; factory exposes `create_app`; route wrappers import from `wangcai.schemas`.
- Testing consistency: all backend tests are remote only; local work only records logs and writes docs.
