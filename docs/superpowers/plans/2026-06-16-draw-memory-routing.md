# Draw Memory Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let draw prompt optimization call the existing memory route and recall pipeline when useful.

**Architecture:** Add a draw-specific memory context helper in `qwen_app/functions/image_generation.py`. The helper reuses the existing memory gate, retrieval query builder, embedding recall pool, memory judge, text fallback, and context formatter. `qwen_app/routes/api.py` passes this context into `optimize_draw_prompt` before image generation.

**Tech Stack:** Existing FastAPI SSE route, SQLite memory store, OpenAI-compatible background model, existing embedding client.

---

### Task 1: Draw Memory Context Helper

**Files:**
- Modify: `qwen_app/functions/image_generation.py`

- [ ] Add `build_draw_memory_context(...)` that runs `resolve_memory_gate_decision` with recent planner context.
- [ ] If `needs_memory=false`, return empty context and debug counts.
- [ ] If `needs_memory=true`, build retrieval query, embed it, retrieve candidates, judge selected memories, record memory retrieval, and return `format_curated_memory_context(memories)`.
- [ ] On embedding/model failure, fall back to `retrieve_curated_memories_by_text`.
- [ ] Record analysis traces with `draw_memory_gate`, `draw_memory_query_embedding`, `draw_memory_text_fallback`.

### Task 2: Route Integration

**Files:**
- Modify: `qwen_app/routes/api.py`

- [ ] In draw mode, emit memory SSE status before prompt optimization.
- [ ] Build draw context by combining latest image prompt context, recent chat context, and draw memory context.
- [ ] Pass the combined context to `optimize_draw_prompt`.
- [ ] Include memory debug in `draw_prompt` trace payload.

### Task 3: Self Profile And Verification

**Files:**
- Modify: `qwen_app/prompts/self_profile.py`

- [ ] Add a high-level note that draw mode can call memory when the route decides it is useful.
- [ ] Run remote `py_compile` for touched Python files.
- [ ] Restart web and verify health.
