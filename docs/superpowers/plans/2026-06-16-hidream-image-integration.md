# HiDream Image Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add HiDream image generation to Wangcai chat, model configuration, local service startup, artifacts, and artifact comments.

**Architecture:** Introduce a focused image generation capability layer so chat, artifacts, and comments depend on a stable interface instead of knowing HiDream request details. Chat draw mode always generates four images from one optimized prompt; artifact generation creates at least one image using distinct per-theme prompts planned from the artifact content.

**Tech Stack:** FastAPI, SQLite, existing OpenAI-compatible model slots, existing SSE chat stream, vanilla HTML/CSS/JS.

---

## File Structure

- Create `qwen_app/prompts/image_generation.py`: prompt optimization and comment image-intent prompts.
- Create `qwen_app/functions/image_generation.py`: image model settings, HiDream status/probe, prompt optimization, image generation, file persistence, DB helpers.
- Modify `qwen_app/config/model_settings.py`: add an `image` model slot and public/masked settings for image generation.
- Modify `qwen_app/functions/local_model_service.py`: detect/start HiDream service alongside Qwen and embedding.
- Modify `qwen_app/routes/api.py`: add image status/generation routes and wire chat draw mode into the existing chat SSE path.
- Modify `schemas.py`: extend `ChatPayload` and model settings payloads with draw/image settings.
- Modify `static/index.html`, `static/app.js`, `static/styles.css`: add draw toggle, draw status handling, four-image preview, downloads, and model settings UI.
- Modify `qwen_app/functions/artifacts.py` and `qwen_app/functions/workers.py`: save/retrieve artifact images and generate theme images after text artifacts.
- Modify `static/artifacts.js`, `static/artifacts.css`, `static/artifacts.html`: show cover images, image counts, previews, and downloads.
- Modify `qwen_app/prompts/self_profile.py`: after implementation, record high-level new capabilities only.
- Tests: extend `tests/test_model_settings.py`, `tests/test_app_behaviors.py`, and `tests/test_static_regressions.py`.

## Task 1: Model Settings Add Image Slot

**Files:**
- Modify: `qwen_app/config/model_settings.py`
- Modify: `schemas.py`
- Test: `tests/test_model_settings.py`

- [ ] **Step 1: Add failing tests for image model settings**

Add tests that save and return a third `image` slot without leaking the API key.

```python
def test_model_settings_include_image_generation_slot(self):
    client = TestClient(self.app.app)

    response = client.put(
        "/api/model-settings",
        json={
            "chat": {"provider": "local", "base_url": "http://127.0.0.1:8000/v1", "model": "qwen3.6-35b-a3b-262k"},
            "background": {"provider": "local", "base_url": "http://127.0.0.1:8000/v1", "model": "qwen3.6-35b-a3b-262k"},
            "image": {
                "provider": "hidream",
                "display_name": "HiDream-O1-Image-Dev-2604",
                "base_url": "http://127.0.0.1:8002",
                "model": "HiDream-O1-Image-Dev-2604",
                "api_key": "",
                "use_proxy": False,
                "proxy_url": "",
            },
        },
    )

    self.assertEqual(response.status_code, 200)
    payload = response.json()
    self.assertIn("image", payload)
    self.assertEqual(payload["image"]["provider"], "hidream")
    self.assertEqual(payload["image"]["model"], "HiDream-O1-Image-Dev-2604")
    self.assertNotIn("api_key", payload["image"])
    self.assertFalse(payload["image"]["has_api_key"])

    saved = self.app.load_model_settings()
    self.assertEqual(saved["image"]["base_url"], "http://127.0.0.1:8002")
```

- [ ] **Step 2: Run remote targeted test and verify failure**

Run on the server, not locally:

```bash
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 'cd /base/home/lizhzh/Project3/qwen_web2 && /opt/conda/bin/python -m pytest tests/test_model_settings.py::ModelSettingsTests::test_model_settings_include_image_generation_slot -q'
```

Expected: fail because the `image` slot is not implemented.

- [ ] **Step 3: Implement image model slot**

In `qwen_app/config/model_settings.py`, add:

```python
MODEL_SLOT_IMAGE = "image"
MODEL_SETTING_SLOTS = (MODEL_SLOT_CHAT, MODEL_SLOT_BACKGROUND, MODEL_SLOT_IMAGE)
IMAGE_MODEL_DISPLAY_NAME = "HiDream-O1-Image-Dev-2604"

MODEL_PROVIDER_PRESETS["hidream"] = {
    "display_name": IMAGE_MODEL_DISPLAY_NAME,
    "base_url": os.environ.get("QWEN_IMAGE_MODEL_BASE_URL", "http://127.0.0.1:8002").strip(),
    "model": os.environ.get("QWEN_IMAGE_MODEL_NAME", IMAGE_MODEL_DISPLAY_NAME).strip(),
    "api_key": os.environ.get("QWEN_IMAGE_MODEL_API_KEY", "").strip(),
    "use_proxy": False,
    "proxy_url": "",
}
MODEL_PROVIDER_PRESETS["none"] = {
    "display_name": "未配置",
    "base_url": "",
    "model": "",
    "api_key": "",
    "use_proxy": False,
    "proxy_url": "",
}
```

Update `default_model_settings()` so `image` defaults to provider `none`, not local chat Qwen.

- [ ] **Step 4: Extend payload schemas**

In `schemas.py`, update the model settings payload class so optional `image` data passes through like `chat` and `background`.

- [ ] **Step 5: Verify remote targeted test passes**

Run the same remote pytest command. Expected: pass.

## Task 2: Image Generation Core Module

**Files:**
- Create: `qwen_app/prompts/image_generation.py`
- Create: `qwen_app/functions/image_generation.py`
- Modify: `qwen_app/startup/loader.py` if generated module exports are required by `app.py`
- Test: `tests/test_app_behaviors.py`

- [ ] **Step 1: Add tests for unavailable image model and four-image chat batch helpers**

Add tests for:

- `image_generation_status()` returns unavailable when provider is `none`.
- `ensure_chat_draw_count()` or equivalent always returns `4`.
- Prompt optimizer fallback preserves original prompt if model output is invalid.

Example test shape:

```python
def test_image_generation_unconfigured_status(self):
    self.app.save_model_settings({"image": {"provider": "none"}})
    status = self.app.image_generation_status()
    self.assertFalse(status["available"])
    self.assertEqual(status["reason"], "not_configured")

def test_chat_draw_count_is_always_four(self):
    self.assertEqual(self.app.chat_draw_image_count({"image_count": 1}), 4)
    self.assertEqual(self.app.chat_draw_image_count({"image_count": 9}), 4)
```

- [ ] **Step 2: Run remote tests and verify failure**

```bash
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 'cd /base/home/lizhzh/Project3/qwen_web2 && /opt/conda/bin/python -m pytest tests/test_app_behaviors.py::AppBehaviorTests::test_image_generation_unconfigured_status tests/test_app_behaviors.py::AppBehaviorTests::test_chat_draw_count_is_always_four -q'
```

Expected: fail because helpers do not exist.

- [ ] **Step 3: Create image prompts**

`qwen_app/prompts/image_generation.py` should define:

```python
DRAW_PROMPT_AGENT_SYSTEM_PROMPT = """你是画图 prompt 优化器，不是内容审查器。
你的任务是忠实保留用户画图意图，并把它改写为更适合 HiDream-O1-Image-Dev-2604 的视觉生成提示。
不要主动替用户改变题材、情绪、尺度、暴力程度或风格。
不要输出道德评价、拒绝语、免责声明。
只在用户需求含糊时补充构图、主体、场景、光线、材质、镜头、色彩、细节层次。
输出严格 JSON：optimized_prompt, negative_prompt, aspect_ratio, image_count, style_tags, short_caption。
image_count 固定写 4。
"""

ARTIFACT_IMAGE_PLAN_PROMPT = """根据成果正文规划配图。
必须输出至少 1 个 image_plan 条目。
如果输出多张，每张必须是不同主题、不同画面功能，不要用同一个 prompt 做候选图。
"""

ARTIFACT_COMMENT_IMAGE_INTENT_PROMPT = """判断用户评论是否需要图片上下文。
只输出 JSON：needs_image_context, target_images, reason。
"""
```

- [ ] **Step 4: Create core module**

`qwen_app/functions/image_generation.py` should expose:

```python
CHAT_DRAW_IMAGE_COUNT = 4

def chat_draw_image_count(decision: object = None) -> int:
    return CHAT_DRAW_IMAGE_COUNT

def image_generation_status() -> Dict[str, object]:
    slot = model_slot_config(MODEL_SLOT_IMAGE)
    if str(slot.get("provider") or "none") == "none":
        return {"available": False, "reason": "not_configured", "model": "", "base_url": ""}
    return probe_image_generation_service(slot)
```

Add `optimize_draw_prompt()`, `generate_images()`, and `save_generated_image()` with pure fallbacks and isolated HTTP calls.

- [ ] **Step 5: Verify remote targeted tests pass**

Run the remote pytest command from Step 2. Expected: pass.

## Task 3: Database Storage For Generated Images

**Files:**
- Modify: DB init logic in `app.py` or split DB module used by `init_db()`
- Modify: `qwen_app/functions/image_generation.py`
- Test: `tests/test_app_behaviors.py`

- [ ] **Step 1: Add schema tests**

Add a test that calls `init_db()` and verifies `generated_images` and `artifact_images` exist with required columns.

```python
def test_generated_image_tables_exist(self):
    with self.app.connect_db() as conn:
        generated_cols = {row["name"] for row in conn.execute("PRAGMA table_info(generated_images)")}
        artifact_cols = {row["name"] for row in conn.execute("PRAGMA table_info(artifact_images)")}
    self.assertIn("batch_id", generated_cols)
    self.assertIn("optimized_prompt", generated_cols)
    self.assertIn("public_url", generated_cols)
    self.assertIn("artifact_id", artifact_cols)
    self.assertIn("is_cover", artifact_cols)
```

- [ ] **Step 2: Implement schema**

Add idempotent `CREATE TABLE IF NOT EXISTS` statements:

```sql
CREATE TABLE IF NOT EXISTS generated_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    public_url TEXT NOT NULL,
    original_prompt TEXT NOT NULL DEFAULT '',
    optimized_prompt TEXT NOT NULL DEFAULT '',
    negative_prompt TEXT NOT NULL DEFAULT '',
    aspect_ratio TEXT NOT NULL DEFAULT '1:1',
    model_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'completed',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifact_images (
    artifact_id INTEGER NOT NULL,
    image_id INTEGER NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_cover INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (artifact_id, image_id)
);
```

- [ ] **Step 3: Implement save/list helpers**

Add helpers:

```python
def save_generated_image_record(...)-> Dict[str, object]: ...
def list_generated_images(source_type: str, source_id: object) -> List[Dict[str, object]]: ...
def attach_image_to_artifact(artifact_id: int, image_id: int, position: int, is_cover: bool) -> None: ...
```

- [ ] **Step 4: Verify schema test passes remotely**

Run remote pytest for the new schema test. Expected: pass.

## Task 4: Chat Draw Mode API And SSE

**Files:**
- Modify: `schemas.py`
- Modify: `qwen_app/routes/api.py`
- Modify: `qwen_app/functions/image_generation.py`
- Test: `tests/test_app_behaviors.py`

- [ ] **Step 1: Extend `ChatPayload`**

Add optional field:

```python
mode: str = Field(default="chat")
```

Draw mode is active only when `payload.mode == "draw"`.

- [ ] **Step 2: Add route-level behavior tests**

Mock `image_generation_status`, `optimize_draw_prompt`, and `generate_images` so draw mode can be tested without real HiDream.

Expected SSE events:

- `draw_prompt`
- `draw_status`
- `draw_image_batch`
- no normal model token stream for draw mode.

- [ ] **Step 3: Implement draw mode branch**

In the existing chat stream endpoint, branch early after saving the user message and before main chat model streaming:

```python
if payload.mode == "draw":
    status = image_generation_status()
    if not status.get("available"):
        yield format_sse("draw_error", {"message": "图像生成模型未配置或不可用，无法生成图片"})
        return
    decision = optimize_draw_prompt(message, trace_context=...)
    yield format_sse("draw_prompt", public_draw_prompt_decision(decision))
    images = generate_chat_draw_images(decision, source_session_id=session_id)
    yield format_sse("draw_image_batch", {"images": images, "optimized_prompt": decision["optimized_prompt"]})
    return
```

- [ ] **Step 4: Verify remote draw-mode tests pass**

Run only the new remote route tests. Expected: pass.

## Task 5: Chat UI Draw Toggle, Preview, Download

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Test: `tests/test_static_regressions.py`

- [ ] **Step 1: Add static tests**

Assert:

- `drawButton` exists.
- `mode: draw` is sent when active.
- `draw_image_batch` event is handled.
- download links use image URLs.
- static version query is bumped.

- [ ] **Step 2: Modify HTML**

Add in `.composer-tools`:

```html
<button id="drawButton" class="tool-button toggle-tool-button" type="button" aria-pressed="false" aria-label="启用画图" title="启用画图">
  画图
</button>
```

Update `/static/app.js?v=...` and `/static/styles.css?v=...` to a new cache key.

- [ ] **Step 3: Modify JS**

Add:

```javascript
let drawEnabled = false;

function setDrawEnabled(enabled) {
  drawEnabled = Boolean(enabled);
  drawButton.classList.toggle("is-active", drawEnabled);
  drawButton.setAttribute("aria-pressed", String(drawEnabled));
  drawButton.title = drawEnabled ? "本轮发送会画图" : "启用画图";
}
```

Include `mode: drawEnabled ? "draw" : "chat"` in chat payload. Handle `draw_prompt`, `draw_status`, `draw_image_batch`, and `draw_error`.

- [ ] **Step 4: Add image batch renderer**

Implement:

```javascript
function renderGeneratedImageBatch(images, optimizedPrompt) {
  const grid = document.createElement("div");
  grid.className = "generated-image-grid";
  for (const item of images) {
    const link = document.createElement("a");
    link.href = item.public_url;
    link.download = "";
    link.className = "generated-image-download";
    const image = document.createElement("img");
    image.src = item.public_url;
    image.alt = item.short_caption || "生成图片";
    link.append(image);
    grid.append(link);
  }
  return grid;
}
```

- [ ] **Step 5: Verify static tests remotely**

Run remote static test target. Expected: pass.

## Task 6: Model Dialog And Local Service Detection

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `qwen_app/functions/local_model_service.py`
- Modify: `qwen_app/routes/api.py`
- Test: `tests/test_model_settings.py`

- [ ] **Step 1: Add backend tests for HiDream service status**

Extend current local service status tests so payload includes:

```python
self.assertIn("image", payload)
self.assertEqual(payload["image"]["port"], 8002)
self.assertIn("画图", payload["summary"])
```

- [ ] **Step 2: Implement HiDream probe**

Add `LOCAL_IMAGE_PORT_CANDIDATES`, `LOCAL_IMAGE_START_SCRIPT`, and status entry:

```python
LOCAL_IMAGE_PORT_CANDIDATES = [int(port.strip()) for port in os.environ.get("QWEN_LOCAL_IMAGE_PORTS", "8002").split(",") if port.strip().isdigit()]
```

Probe should accept either a configured health endpoint or a successful HTTP response from `/health`, `/`, or `/models`, depending on service behavior.

- [ ] **Step 3: Extend start endpoint**

Start missing image service only when configured startup script exists. If missing, return image service unavailable without failing Qwen/embedding startup.

- [ ] **Step 4: Extend model dialog UI**

Add an `image` section with provider, display name, base URL, model, API key, proxy settings, and status text. Support provider `none`, `hidream`, and `custom`.

- [ ] **Step 5: Verify remote model settings tests pass**

Run remote model settings tests. Expected: pass.

## Task 7: Artifact Image Plan And Generation

**Files:**
- Modify: `qwen_app/functions/workers.py`
- Modify: `qwen_app/functions/artifacts.py`
- Modify: `qwen_app/functions/image_generation.py`
- Test: `tests/test_app_behaviors.py`

- [ ] **Step 1: Add tests for artifact image plan normalization**

Test that artifact image count is at least 1 and multiple image plans keep distinct prompts.

- [ ] **Step 2: Extend idle artifact decision parser**

Support fields:

```json
{
  "image_count": 2,
  "image_plan": [
    {"title": "封面", "brief": "故事开篇的核心场景", "role": "cover"},
    {"title": "冲突", "brief": "中段冲突瞬间", "role": "inline"}
  ]
}
```

- [ ] **Step 3: Generate artifact images after saving text artifact**

After `save_idle_agent_artifact(...)`, call:

```python
generate_artifact_theme_images(artifact_id, title, summary, content, image_plan)
```

Failure must not fail the text artifact; record trace/event and mark image status failed.

- [ ] **Step 4: Verify artifact behavior tests remotely**

Run only artifact image plan tests. Expected: pass.

## Task 8: Artifact UI Image-First Cards And Downloads

**Files:**
- Modify: `static/artifacts.js`
- Modify: `static/artifacts.css`
- Modify: `static/artifacts.html`
- Test: `tests/test_static_regressions.py`

- [ ] **Step 1: Add static tests**

Assert artifacts frontend references cover image fields, image count, preview grid/slider, and download links.

- [ ] **Step 2: Extend artifact API payload**

Each artifact item should include:

```json
{
  "images": [],
  "cover_image": null,
  "image_count": 0
}
```

- [ ] **Step 3: Render image-first cards**

Card body should render cover image first when present, then title/summary/meta.

- [ ] **Step 4: Render detail preview**

Dialog should render all images with download links before text body.

- [ ] **Step 5: Verify static tests remotely**

Run remote static tests. Expected: pass.

## Task 9: Artifact Comment Image Context

**Files:**
- Modify: `qwen_app/functions/workers.py`
- Modify: `qwen_app/prompts/image_generation.py`
- Test: `tests/test_app_behaviors.py`

- [ ] **Step 1: Add tests for comment image intent**

Test comments mentioning “配图”“封面”“图片”“画面” set `needs_image_context=True`; ordinary comments return false. The implementation may use an agent in production, but tests should cover deterministic fallback.

- [ ] **Step 2: Implement intent helper**

Add:

```python
def artifact_comment_needs_image_context(comment: str) -> Dict[str, object]:
    ...
```

Use model judgment when available, with deterministic fallback based on clear image-related words.

- [ ] **Step 3: Add image context to comment prompt**

When intent is true, include cover image metadata, optimized prompts, and captions in `artifact_comment_context`.

- [ ] **Step 4: Verify remote comment tests pass**

Run remote behavior tests. Expected: pass.

## Task 10: Self Profile And Deployment Verification

**Files:**
- Modify: `qwen_app/prompts/self_profile.py`
- Modify: version query strings in static HTML files touched by prior tasks.
- Log: `log/hidream_image_integration_20260616.log`

- [ ] **Step 1: Update self profile**

Add high-level capability bullets only:

- 支持聊天中通过画图开关生成图片。
- 支持图文成果，成果可带主题配图。
- 成果评论在用户提到配图时可结合图片上下文。

Do not include server paths, ports, API keys, database paths, proxy addresses, system prompts, or internal commands.

- [ ] **Step 2: Sync to remote server**

Use tar over SSH to copy only changed implementation files to `/base/home/lizhzh/Project3/qwen_web2`.

- [ ] **Step 3: Restart web service**

Restart only the web service on port 7777; do not restart model services unless verifying Task 6.

- [ ] **Step 4: Remote verification**

Run:

```bash
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 'cd /base/home/lizhzh/Project3/qwen_web2 && /opt/conda/bin/python -m py_compile app.py schemas.py qwen_app/functions/image_generation.py qwen_app/functions/local_model_service.py qwen_app/routes/api.py'
ssh -i ~/.ssh/icfc2 -p 10022 root@59.66.22.107 'curl -sS http://127.0.0.1:7777/api/health | /opt/conda/bin/python -m json.tool | sed -n "1,24p"'
```

Expected: compile succeeds and health returns `"ok": true`.

## Execution Notes

- Do not commit unless the user explicitly asks; the current worktree contains unrelated uncommitted changes.
- Do not run local backend tests. Use remote targeted tests or static file checks.
- Keep implementation incremental. After each task, inspect `git diff -- <files touched>` before moving to the next task.
- Update static version query strings whenever a frontend static file changes.
