# Qwen Web Image Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add image upload support to the Qwen web chat so each user turn can include text plus one or more images, forwarded to the multimodal vLLM chat API.

**Architecture:** Keep the existing single FastAPI app and no-build frontend. Store user-uploaded images as base64 data URLs in the message metadata SQLite column, rebuild multimodal model messages only for current-session history, and keep assistant replies as text. The first version accepts images only and rejects unsupported file types client-side.

**Tech Stack:** FastAPI, SQLite, OpenAI-compatible vLLM `/v1/chat/completions`, plain HTML/CSS/JS, Python unittest.

---

### Task 1: Backend Multimodal Message Support

**Files:**
- Modify: `/base/home/lizhzh/Project3/qwen_web/app.py`
- Test: `/base/home/lizhzh/Project3/qwen_web/tests/test_app_behaviors.py`

- [ ] **Step 1: Write failing tests**

Add tests for a `ChatAttachment` payload, metadata persistence, and OpenAI multimodal message construction.

- [ ] **Step 2: Run target tests and verify RED**

Run:
`/opt/conda/bin/python3 -m unittest tests.test_app_behaviors.AppBehaviorTests.test_chat_payload_accepts_image_attachments tests.test_app_behaviors.AppBehaviorTests.test_model_messages_include_image_url_parts`

Expected: tests fail because attachment helpers do not exist.

- [ ] **Step 3: Implement minimal backend**

Add `ChatAttachment`, validate image data URLs, store attachments in `messages.metadata`, and build model messages where user messages with attachments use OpenAI content parts: text plus `{type:"image_url"}`.

- [ ] **Step 4: Run tests and full suite**

Run:
`/opt/conda/bin/python3 -m py_compile app.py vector_memory.py memory.py && /opt/conda/bin/python3 -m unittest discover -s tests -p "test_*.py"`

Expected: all tests pass.

### Task 2: Frontend Image Picker

**Files:**
- Modify: `/base/home/lizhzh/Project3/qwen_web/static/index.html`
- Modify: `/base/home/lizhzh/Project3/qwen_web/static/app.js`
- Modify: `/base/home/lizhzh/Project3/qwen_web/static/styles.css`

- [ ] **Step 1: Add no-build UI**

Add a small image attach button next to the input, a hidden `<input type="file" accept="image/*" multiple>`, thumbnails, remove controls, and send attached data URLs in the chat JSON body.

- [ ] **Step 2: Validate manually**

Fetch the static JS through `http://183.172.57.234:19922/static/app.js?...` and confirm attachment code is present.

### Task 3: Deploy and Verify

**Files:**
- Server runtime under `/base/home/lizhzh/Project3/qwen_web`

- [ ] **Step 1: Restart web**

Run:
`cd /base/home/lizhzh/Project3/qwen_web && ./stop_qwen_web.sh && ./start_qwen_web.sh`

- [ ] **Step 2: Verify services**

Run health checks for `9922`, `8000`, and external `19922`.

- [ ] **Step 3: Verify multimodal chat**

Post a 1x1 red PNG as an attachment through `/api/chat/stream` and confirm the response reaches `done`.
