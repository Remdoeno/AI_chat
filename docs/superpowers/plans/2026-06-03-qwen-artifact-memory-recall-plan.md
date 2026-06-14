# Qwen Artifact Memory Recall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add artifact memories, serialized idle-agent story support, timeline-aware memory, and active recall to the Qwen web app while keeping memory editor and artifacts page separate.

**Architecture:** Extend existing FastAPI single-file backend and static pages without splitting the deployed app. Add SQLite columns via `ensure_column`, generate concise artifact-labeled memories when artifacts are saved, inject timeline and active-recall context into the system prompt, and add artifacts metadata/search improvements to `/artifacts`.

**Tech Stack:** FastAPI, SQLite, OpenAI-compatible vLLM client, vanilla HTML/CSS/JS, Python unittest.

---

### Task 1: Artifact Memory and Series Metadata

**Files:** `/base/home/lizhzh/Project3/qwen_web/app.py`, `/base/home/lizhzh/Project3/qwen_web/tests/test_app_behaviors.py`, `/base/home/lizhzh/Project3/qwen_web/static/artifacts.*`

- [ ] Write failing tests for artifact memory creation and series metadata listing.
- [ ] Add `series_title`, `episode_index`, `summary` columns to `idle_agent_artifacts`.
- [ ] Add `create_artifact_memory` called from `save_idle_agent_artifact`.
- [ ] Add `artifact` label to memory lists and filters.

### Task 2: Idle Agent Serialized Hero Seed

**Files:** `/base/home/lizhzh/Project3/qwen_web/app.py`, `/base/home/lizhzh/Project3/qwen_web/tests/test_app_behaviors.py`

- [ ] Write failing test that idle prompt includes the superhero serial seed.
- [ ] Add non-exclusive hero serial seed to idle prompt.
- [ ] Parse optional `series_title`, `episode_index`, `summary` from idle agent JSON.

### Task 3: Timeline-Aware Memory

**Files:** `/base/home/lizhzh/Project3/qwen_web/app.py`, `/base/home/lizhzh/Project3/qwen_web/tests/test_app_behaviors.py`, `/base/home/lizhzh/Project3/qwen_web/static/memory*.js/html`

- [ ] Write failing tests for timeline fields and prompt ordering guidance.
- [ ] Add `timeline_at`, `supersedes_id`, `confidence` to curated memories.
- [ ] Include timeline metadata in API list responses and memory prompt formatting.
- [ ] Add `artifact` option and timeline metadata display to memory UIs.

### Task 4: Active Recall

**Files:** `/base/home/lizhzh/Project3/qwen_web/app.py`, `/base/home/lizhzh/Project3/qwen_web/tests/test_app_behaviors.py`

- [ ] Write failing tests for recall intent detection and active recall context injection.
- [ ] Add `is_active_recall_request`, `build_active_recall_context`, and prompt injection.
- [ ] Log active recall events without raw chat content.

### Task 5: Verification and Restart

- [ ] Run target tests.
- [ ] Run full unit tests.
- [ ] Restart qwen_web.
- [ ] Verify `/api/health`, `/memory-admin`, `/artifacts`, and chat page.
