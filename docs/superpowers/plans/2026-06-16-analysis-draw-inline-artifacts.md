# Analysis Draw Button And Inline Artifact Images Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add draw mode to analysis chat and render artifact images inline between text paragraphs instead of as a top image block.

**Architecture:** Reuse the existing `/api/chat/stream` draw mode and generated-image frontend components. Keep analysis mode changes inside `static/analysis.*`, and keep artifact rendering changes inside `static/artifacts.*`.

**Tech Stack:** FastAPI SSE backend already implemented, vanilla JS, CSS, static HTML.

---

### Task 1: Analysis Draw Toggle

**Files:**
- Modify: `static/analysis.html`
- Modify: `static/analysis.js`
- Modify: `static/analysis.css`

- [ ] Add `analysisDrawButton` after the analysis web search button.
- [ ] Add draw toggle state in `analysis.js`, make draw and web search mutually exclusive.
- [ ] Send `mode: "draw"` and `web_search: false` for draw turns.
- [ ] Handle `draw_status`, `draw_prompt`, `draw_image_batch`, and `draw_error` SSE events.
- [ ] Render generated images in analysis message body with download links.
- [ ] Bump `analysis.html` static CSS/JS version.

### Task 2: Inline Artifact Images

**Files:**
- Modify: `static/artifacts.js`
- Modify: `static/artifacts.css`
- Modify: `static/artifacts.html`

- [ ] Replace top-only artifact image grid in detail dialog with inline rendering.
- [ ] Split artifact text into paragraphs and insert centered images after spaced paragraph positions.
- [ ] Keep card cover image behavior unchanged.
- [ ] Bump artifact static version.

### Task 3: Self Profile And Verification

**Files:**
- Modify: `qwen_app/prompts/self_profile.py`

- [ ] Add high-level user-facing note: analysis mode also supports draw turns; artifact detail can render image/text interleaving.
- [ ] Run local static JS syntax checks only.
- [ ] Sync changed files to `/base/home/lizhzh/Project3/qwen_web2`.
- [ ] Run remote `py_compile` for self profile if touched and fetch static markers.
- [ ] Restart only web service on 7777 if static/cache needs it.
