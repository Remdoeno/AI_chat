# Session Continuation 1.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add scroll-triggered loading of previous same-device sessions so the current session can continue older conversations, then publish as 旺财1.1.

**Architecture:** Add a small `session_context_links` table that links a current session to older source sessions without copying messages. Backend APIs expose previous-session lookup/loading; model message construction reads linked sessions before current session and trims old context when it exceeds budget. Frontend detects repeated overscroll at the top, inserts older messages above the current transcript, and preserves scroll position.

**Tech Stack:** FastAPI, SQLite, vanilla JS/CSS, unittest/static regression tests.

---

### Task 1: Backend Session Context Links

**Files:**
- Modify: `app.py`
- Test: `tests/test_app_behaviors.py`

- [x] Add failing tests for loading previous same-device sessions and model context continuation.
- [x] Run targeted tests on the server and confirm they fail before implementation.
- [x] Add `session_context_links`, previous-session lookup, load API, linked visible/model message loaders, and context trimming.
- [x] Run targeted backend tests and confirm they pass.

### Task 2: Frontend Scroll Loading

**Files:**
- Modify: `static/app.js`
- Modify: `static/styles.css`
- Modify: `static/index.html`
- Test: `tests/test_static_regressions.py`

- [x] Add static failing tests for version 1.1 and scroll-loading hooks.
- [x] Implement repeated top-overscroll trigger for touch and wheel.
- [x] Insert loaded previous-session messages at the top while preserving visual position.
- [x] Add subtle status/animation classes for arm/disarm/loading/no-history states.
- [x] Run static regression tests.

### Task 3: Version, Docs, Deploy, Git

**Files:**
- Modify: `README.md`
- Modify: `static/auth.html`
- Modify: `static/index.html`

- [x] Update visible version strings to 旺财1.1.
- [x] Sync changed files to the server and restart `WEB_PORT=7777`.
- [x] Verify `/api/health` and a live previous-session API smoke test.
- [ ] Commit and push to GitHub.
