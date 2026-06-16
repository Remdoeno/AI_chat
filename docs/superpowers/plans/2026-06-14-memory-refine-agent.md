# Memory Refine Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a memory refinement agent that splits over-packed long memories into atomic curated memories, marks processed memories, and runs both as one-time migration and idle background maintenance.

**Architecture:** Extend `curated_memories` with lightweight refinement metadata. Add a model-backed `memory_refine_agent` that selects long unprocessed memories, asks Qwen to split or check them, writes new atomic memories with vectors, and supersedes the original when split. Hook it into the existing idle worker after dedupe and before idle writing.

**Tech Stack:** FastAPI app in `app.py`, SQLite, OpenAI-compatible local Qwen API, existing embedding client, existing idle worker event logs.

---

### Task 1: Schema and constants

**Files:**
- Modify: `app.py`

- [ ] Add `refine_status`, `refined_at`, `refined_from_id`, `refine_reason` columns to `curated_memories` using existing `ensure_column`.
- [ ] Add constants for refine candidate length, batch size, interval and model parameters.
- [ ] Add `MEMORY_REFINE_AGENT_SYSTEM_PROMPT` requiring atomic split, no assistant-derived facts, correct labels, and JSON output.

### Task 2: Refine agent functions

**Files:**
- Modify: `app.py`

- [ ] Add candidate loader for unprocessed long memories.
- [ ] Add parser for model output with actions: `split`, `checked`, `skip`.
- [ ] Add writer that creates split memories, embeds them, sets `supersedes_id` to original, and marks original `refined_split`.
- [ ] Add checked marker for memories that do not need splitting.

### Task 3: Worker integration and one-time migration

**Files:**
- Modify: `app.py`

- [ ] Add `run_memory_refine_agent_once(force=False)`.
- [ ] Insert it into `idle_agent_worker_loop` after `memory_dedupe` and before `idle_write`.
- [ ] Record readable `memory_refine_agent_run/error` events.

### Task 4: Docs and remote verification

**Files:**
- Modify: `docs/system_development.md`
- Create/Update log files under `log/`

- [ ] Document atomic memory rule and refine agent behavior.
- [ ] Sync to server `7777`, run remote `py_compile` and health check.
- [ ] Run a bounded one-time historical refine pass remotely.
