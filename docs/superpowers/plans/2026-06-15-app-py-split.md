# app.py Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the current server-baseline `app.py` into focused folders without changing runtime behavior.

**Architecture:** Keep the first refactor mechanical. `app.py` becomes a small entrypoint; `qwen_app.startup.loader` executes split source files in original order into one namespace and returns the original FastAPI `app`.

**Tech Stack:** Python, FastAPI, existing project modules, remote verification over SSH.

---

### Task 1: Create Split Package

**Files:**
- Create: `qwen_app/**`
- Modify: `app.py`

- [x] Create package folders for config, prompts, functions, startup, and routes.
- [x] Add a loader that compiles and executes split files in order using stable filenames.
- [x] Replace `app.py` with a tiny entrypoint that exposes `app`.

### Task 2: Mechanical Source Split

**Files:**
- Create: `qwen_app/config/runtime.py`
- Create: `qwen_app/prompts/system.py`
- Create: `qwen_app/functions/*.py`
- Create: `qwen_app/startup/app_setup.py`
- Create: `qwen_app/routes/*.py`

- [x] Split the verified server-baseline `app.py` by line ranges that preserve original execution order.
- [x] Keep prompt text and idle token constants exactly as they exist in the server baseline.
- [x] Preserve all existing function names and route decorators.

### Task 3: Remote Verification

**Files:**
- Read: all split files

- [x] Run local syntax-only checks only if they do not import FastAPI.
- [x] Upload/sync the changed tree to the server test location.
- [x] Run remote `py_compile` for `app.py` and all split files.
- [x] Run remote import smoke check that verifies `app` exists and routes register.

### Task 4: Publish

**Files:**
- Stage only intended project version files.

- [ ] Review git status and diff.
- [ ] Commit the split as a new version.
- [ ] Push to GitHub on a `codex/` branch.
- [ ] Create a draft PR if GitHub auth allows it.
