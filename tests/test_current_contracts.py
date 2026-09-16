import importlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class WangcaiAppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmpdir.name)
        self.env_keys = {
            "WANGCAI_WEB_DB": str(tmp_path / "chat_history.sqlite3"),
            "WANGCAI_AUTH_CONFIG": str(tmp_path / "admin_auth.json"),
            "WANGCAI_MODEL_BASE_URL": "http://127.0.0.1:8000/v1",
            "WANGCAI_MODEL_NAME": "qwen3.6-35b-a3b-262k",
            "WANGCAI_MODEL_API_KEY": "EMPTY",
            "WANGCAI_IDLE_AGENT_ENABLED": "0",
            "WANGCAI_MEMORY_DEDUPE_AGENT_ENABLED": "0",
            "WANGCAI_MEMORY_REFINE_AGENT_ENABLED": "0",
        }
        for key, value in self.env_keys.items():
            os.environ[key] = value
        sys.modules.pop("app", None)
        self.app = importlib.import_module("app")
        self.app.init_db()
        self.client = TestClient(self.app.app)

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in self.env_keys:
            os.environ.pop(key, None)
        sys.modules.pop("app", None)


class CurrentRuntimeContracts(WangcaiAppTestCase):
    def test_runtime_uses_wangcai_env_database_path(self):
        expected = Path(self.env_keys["WANGCAI_WEB_DB"])

        self.assertEqual(self.app.DB_PATH, expected)
        self.assertTrue(expected.exists())

    def test_connect_db_context_closes_connection(self):
        with self.app.connect_db() as conn:
            conn.execute("SELECT 1").fetchone()

        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1").fetchone()

    def test_basic_session_and_hidden_message_roundtrip(self):
        session_id = self.app.create_session("device:test-current-contract", "unit-test")
        self.app.add_message(session_id, "user", "可见用户消息", hidden=False)
        self.app.add_message(session_id, "user", "隐藏用户消息", hidden=True)
        self.app.add_message(session_id, "assistant", "助手消息", hidden=False)

        visible = self.app.load_messages(session_id)

        self.assertEqual([item["content"] for item in visible], ["可见用户消息", "助手消息"])
        self.assertNotIn("隐藏用户消息", [item["content"] for item in visible])

    def test_model_settings_default_and_public_masking(self):
        settings = self.app.load_model_settings()

        self.assertEqual(settings["chat"]["provider"], "local")
        self.assertEqual(settings["chat"]["display_name"], self.app.LOCAL_MODEL_DISPLAY_NAME)

        self.app.save_admin_password("release-fixture-password")
        login = self.client.post("/api/admin/login", json={"password":"release-fixture-password"})
        self.assertEqual(login.status_code, 200)
        response = self.client.put(
            "/api/model-settings?scope=system",
            json={
                "chat": {
                    "provider": "deepseek",
                    "display_name": "deepseek-v4-pro",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-v4-pro",
                    "api_key": "secret-chat-key",
                    "use_proxy": True,
                    "proxy_url": "http://127.0.0.1:7890",
                },
                "background": {
                    "provider": "local",
                    "display_name": "qwen3.6",
                    "base_url": "http://127.0.0.1:8000/v1",
                    "model": "qwen3.6-35b-a3b-262k",
                    "api_key": "",
                    "use_proxy": False,
                    "proxy_url": "",
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["chat"]["has_api_key"])
        self.assertNotIn("api_key", payload["chat"])
        saved = self.app.load_model_settings()
        self.assertEqual(saved["chat"]["api_key"], "secret-chat-key")

    def test_generation_token_cancel_lifecycle(self):
        session_id = self.app.create_session("device:test-token-cancel", "unit-test")
        token = self.app.acquire_generation_token(session_id)

        self.assertTrue(token)
        self.assertTrue(self.app.request_generation_cancel(session_id))
        self.assertTrue(self.app.is_generation_cancelled(session_id, token))
        self.app.release_generation_token(session_id, token)
        self.assertFalse(self.app.is_generation_cancelled(session_id, token))

    def test_character_library_cancel_endpoint_reuses_generation_cancel(self):
        session_id = self.app.create_session("device:test-character-cancel", "unit-test")
        token = self.app.acquire_generation_token(session_id)

        response = self.client.post(f"/api/characters/sessions/{session_id}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cancelled": True})
        self.assertTrue(self.app.is_generation_cancelled(session_id, token))

    def test_session_close_cancels_active_generation(self):
        session_id = self.app.create_session("device:test-close-generation", "unit-test")
        token = self.app.acquire_generation_token(session_id)

        response = self.client.post(f"/api/sessions/{session_id}/close")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["closed"], True)
        self.assertEqual(response.json()["cancelled_generation"], True)
        self.assertNotIn(session_id, self.app.ACTIVE_GENERATIONS)
        self.assertTrue(self.app.is_generation_cancelled(session_id, token))

    def test_create_session_records_timing_event(self):
        response = self.client.post(
            "/api/sessions",
            headers={"X-Wangcai-Device-Id": "device:test-session-timing"},
        )

        self.assertEqual(response.status_code, 200)
        session_id = response.json()["session_id"]
        with self.app.connect_db() as conn:
            row = conn.execute(
                """
                SELECT metadata_json
                FROM events
                WHERE session_id = ? AND event_type = 'session_create_timing'
                ORDER BY id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        metadata = json.loads(row["metadata_json"])
        self.assertIn("total_ms", metadata)
        self.assertIn("prepared_opening_ms", metadata)
        self.assertIn("memory_binding_ms", metadata)
        self.assertGreaterEqual(metadata["total_ms"], 0)

    def test_repeated_init_db_does_not_rerun_schema_setup(self):
        calls = {"memory": 0}
        original_init_memory_tables = self.app.memory.init_memory_tables

        def count_memory_init(_conn):
            calls["memory"] += 1

        self.app.memory.init_memory_tables = count_memory_init
        try:
            self.app.init_db()
            self.app.init_db()
        finally:
            self.app.memory.init_memory_tables = original_init_memory_tables

        self.assertEqual(calls["memory"], 0)

    def test_known_device_identity_fails_fast_when_database_is_locked(self):
        globals_dict = self.app.is_known_device_identity.__globals__
        original_connect_db = globals_dict["connect_db"]

        def locked_connect_db(*_args, **_kwargs):
            raise sqlite3.OperationalError("database is locked")

        globals_dict["connect_db"] = locked_connect_db
        try:
            self.assertFalse(self.app.is_known_device_identity("device:locked"))
        finally:
            globals_dict["connect_db"] = original_connect_db

    def test_opening_stream_does_not_require_database_before_tokens(self):
        globals_dict = self.app.opening_stream_endpoint.__globals__
        original_init_db = globals_dict["init_db"]
        original_iter_model_deltas = globals_dict["iter_model_deltas"]

        def unavailable_init_db():
            raise sqlite3.OperationalError("database is locked")

        def fake_iter_model_deltas(_messages, _max_tokens, _temperature, _top_p):
            yield "欢迎回来"

        globals_dict["init_db"] = unavailable_init_db
        globals_dict["iter_model_deltas"] = fake_iter_model_deltas
        try:
            response = self.client.post(
                "/api/opening/stream",
                headers={"X-Wangcai-Device-Id": "device:test-fast-opening"},
                json={
                    "opening_id": "test-fast-opening",
                    "opening_prompt": "这是浏览器打开时的隐藏首轮输入；已缓存用户画像。",
                    "max_tokens": 16,
                    "temperature": 0.6,
                    "top_p": 0.95,
                },
            )
        finally:
            globals_dict["init_db"] = original_init_db
            globals_dict["iter_model_deltas"] = original_iter_model_deltas

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: token", response.text)
        self.assertIn("欢迎回来", response.text)

    def test_fast_opening_stream_is_counted_in_background_agents(self):
        globals_dict = self.app.opening_stream_endpoint.__globals__
        original_iter_model_deltas = globals_dict["iter_model_deltas"]

        def fake_iter_model_deltas(_messages, _max_tokens, _temperature, _top_p):
            yield "欢迎回来"

        globals_dict["iter_model_deltas"] = fake_iter_model_deltas
        try:
            response = self.client.post(
                "/api/opening/stream",
                headers={"X-Wangcai-Device-Id": "device:test-fast-opening-trace"},
                json={
                    "opening_id": "test-fast-opening-trace",
                    "opening_prompt": "这是浏览器打开时的隐藏首轮输入；已缓存用户画像。",
                    "max_tokens": 16,
                    "temperature": 0.6,
                    "top_p": 0.95,
                },
            )
        finally:
            globals_dict["iter_model_deltas"] = original_iter_model_deltas

        self.assertEqual(response.status_code, 200)
        self.app.save_admin_password("background-test-password")
        self.client.cookies.set(self.app.ADMIN_COOKIE_NAME, self.app.admin_auth_token())
        overview = self.client.get("/api/background/overview")

        self.assertEqual(overview.status_code, 200)
        agent_row = next(
            item for item in overview.json()["agent_rows"] if item["step_name"] == "fast_opening_stream"
        )
        self.assertEqual(agent_row["hour"]["calls"], 1)
        self.assertEqual(agent_row["day"]["calls"], 1)
        self.assertEqual(agent_row["month"]["calls"], 1)
        self.assertGreater(agent_row["month"]["output_tokens"], 0)

    def test_regular_chat_stream_is_counted_in_background_agents_without_analysis_mode(self):
        session_id = self.app.create_session("device:test-regular-chat-background", "unit-test")
        globals_dict = self.app.chat_stream.__globals__
        original_iter_model_deltas = globals_dict["iter_model_deltas"]
        original_build_system_prompt = globals_dict["build_system_prompt"]

        def fake_iter_model_deltas(_messages, _max_tokens, _temperature, _top_p):
            yield "普通聊天回复"

        def fake_build_system_prompt(*_args, **_kwargs):
            return "system prompt"

        globals_dict["iter_model_deltas"] = fake_iter_model_deltas
        globals_dict["build_system_prompt"] = fake_build_system_prompt
        try:
            response = self.client.post(
                "/api/chat/stream",
                headers={"X-Wangcai-Device-Id": "device:test-regular-chat-background"},
                json={
                    "session_id": session_id,
                    "message": "普通聊天也应该被后台统计",
                    "analysis_mode": False,
                    "max_tokens": 16,
                    "temperature": 0.6,
                    "top_p": 0.95,
                },
            )
        finally:
            globals_dict["iter_model_deltas"] = original_iter_model_deltas
            globals_dict["build_system_prompt"] = original_build_system_prompt

        self.assertEqual(response.status_code, 200)
        self.assertIn("普通聊天回复", response.text)
        self.app.save_admin_password("background-test-password")
        self.client.cookies.set(self.app.ADMIN_COOKIE_NAME, self.app.admin_auth_token())
        overview = self.client.get("/api/background/overview")

        self.assertEqual(overview.status_code, 200)
        agent_row = next(
            item for item in overview.json()["agent_rows"] if item["step_name"] == "main_chat_stream"
        )
        self.assertEqual(agent_row["hour"]["calls"], 1)
        self.assertEqual(agent_row["day"]["calls"], 1)
        self.assertEqual(agent_row["month"]["calls"], 1)
        self.assertGreater(agent_row["month"]["output_tokens"], 0)

    def test_recent_user_state_context_is_injected_without_diagnostic_labels(self):
        session_id = self.app.create_session("device:test-recent-state", "unit-test")
        self.app.save_user_recent_state(
            "device:test-recent-state",
            7,
            {
                "state_summary": "用户近期一边想推进事情，一边容易被消耗。焦虑型人格。",
                "emotional_weather": "轻微紧绷，带有恢复需求",
                "core_needs": ["被稳定接住", "低压力推进"],
                "care_suggestions": ["先承认用户感受，再给结构化建议"],
                "avoid_suggestions": ["不要催促", "不要贴标签"],
                "confidence": 0.72,
            },
            source_memory_ids=[1, 2, 3],
        )

        prompt = self.app.build_system_prompt(
            session_id,
            "今天有点累",
            "device:test-recent-state",
            precomputed_memory_gate={"needs_memory": False, "needs_self_profile": False, "reason": "unit-test"},
        )

        self.assertIn("近期陪伴提示", prompt)
        self.assertIn("只作为温柔假设", prompt)
        self.assertIn("低压力推进", prompt)
        self.assertNotIn("焦虑型人格", prompt)

    def test_recent_user_state_refresh_is_daily_per_scope(self):
        scope_key = "device:test-recent-state-daily"
        first = self.app.utc_now()
        old = "2026-06-20T00:00:00+00:00"
        self.app.save_user_recent_state(
            scope_key,
            7,
            {"state_summary": "已有状态", "confidence": 0.6},
            source_memory_ids=[],
            updated_at=first,
        )
        next_day = (self.app.parse_utc_iso(first) + timedelta(days=1)).isoformat(timespec="seconds")

        self.assertFalse(self.app.should_refresh_user_recent_state(scope_key, 7, now_iso=first))
        self.assertTrue(self.app.should_refresh_user_recent_state(scope_key, 7, now_iso=next_day))
        self.app.save_user_recent_state(
            scope_key,
            30,
            {"state_summary": "旧状态", "confidence": 0.6},
            source_memory_ids=[],
            updated_at=old,
        )
        self.assertTrue(self.app.should_refresh_user_recent_state(scope_key, 30, now_iso=first))

    def test_todo_queries_inject_future_event_context(self):
        device_id = "device:test-todo-timeline"
        session_id = self.app.create_session(device_id, "unit-test")
        future_at = (datetime.now(self.app.local_timezone()) + timedelta(days=3)).isoformat(timespec="minutes")
        self.app.save_curated_memory(
            session_id,
            1,
            1,
            "用户需要补全测试投稿实验并重投。",
            importance_label="event",
            timeline_at=future_at,
            timeline_kind="deadline",
            confidence=0.9,
        )

        for query in ("我没有todo吗？为什么不提醒我", "待办事项有哪些", "我最近有什么要做"):
            with self.subTest(query=query):
                self.assertTrue(self.app.is_timeline_event_query(query))
                context = self.app.build_regular_timeline_events_context(query, device_id, session_id=session_id)
                self.assertIn("用户需要补全测试投稿实验并重投", context)
                self.assertIn("必须优先", context)

    def test_opening_future_events_are_must_mention_requirements(self):
        device_id = "device:test-opening-event"
        session_id = self.app.create_session(device_id, "unit-test")
        future_at = (datetime.now(self.app.local_timezone()) + timedelta(days=3)).isoformat(timespec="minutes")
        self.app.save_curated_memory(
            session_id,
            2,
            2,
            "用户需要补全测试投稿实验并重投。",
            importance_label="event",
            timeline_at=future_at,
            timeline_kind="deadline",
            confidence=0.9,
        )

        rendered = self.app.render_cached_opening_prompt(
            self.app.refresh_cached_opening_prompt(device_id),
            device_id,
        )
        fast_system = self.app.cached_opening_fast_system_prompt()

        self.assertIn("即将到来的事件/日程提醒（开篇必须提到）", rendered)
        self.assertIn("必须提到：用户需要补全测试投稿实验并重投", rendered)
        self.assertNotIn("开篇必须优先参考", rendered)
        self.assertIn("必须提到", fast_system)

    def test_idle_worker_activity_supports_offset_pagination(self):
        session_id = self.app.create_session("device:test-background-pagination", "unit-test")
        for index in range(25):
            self.app.record_event(session_id, "idle_worker_tick", "device:test-background-pagination", {"index": index})

        first_page = self.app.list_idle_worker_activity(limit=10, offset=0)
        second_page = self.app.list_idle_worker_activity(limit=10, offset=10)

        self.assertEqual(len(first_page), 10)
        self.assertEqual(len(second_page), 10)
        self.assertTrue({item["id"] for item in first_page}.isdisjoint({item["id"] for item in second_page}))
        self.assertGreater(first_page[0]["id"], second_page[0]["id"])

    def test_idle_worker_skip_events_are_coalesced(self):
        result = {
            "status": "skipped",
            "reason": "idle_wait",
            "started_at": self.app.utc_now(),
            "duration_ms": 10.0,
        }

        self.app.record_idle_worker_skip("memory_dedupe", result)
        self.app.record_idle_worker_skip("memory_dedupe", {**result, "duration_ms": 20.0})
        self.app.record_idle_worker_skip("memory_refine", result)

        with self.app.connect_db() as conn:
            rows = conn.execute(
                """
                SELECT event_type, metadata_json
                FROM events
                WHERE event_type = 'idle_worker_skip'
                ORDER BY id ASC
                """
            ).fetchall()

        self.assertEqual(len(rows), 2)
        first_metadata = json.loads(rows[0]["metadata_json"])
        second_metadata = json.loads(rows[1]["metadata_json"])
        self.assertEqual(first_metadata["task"], "memory_dedupe")
        self.assertEqual(first_metadata["skip_count"], 2)
        self.assertEqual(first_metadata["duration_ms"], 30.0)
        self.assertIn("first_seen_at", first_metadata)
        self.assertIn("last_seen_at", first_metadata)
        self.assertEqual(second_metadata["task"], "memory_refine")
        self.assertEqual(second_metadata["skip_count"], 1)

    def test_background_dashboard_requires_analysis_auth_and_returns_overview(self):
        unauthenticated_page = self.client.get("/background")

        self.assertEqual(unauthenticated_page.status_code, 200)
        self.assertIn("旺财后台观测", unauthenticated_page.text)
        self.assertIn("密码", unauthenticated_page.text)

        self.app.save_admin_password("background-test-password")
        self.client.cookies.set(self.app.ADMIN_COOKIE_NAME, self.app.admin_auth_token())
        authenticated_page = self.client.get("/background")

        self.assertEqual(authenticated_page.status_code, 200)
        self.assertIn("旺财后台观测", authenticated_page.text)

    def test_background_overview_reports_agents_models_database_and_resources(self):
        self.app.save_admin_password("background-test-password")
        self.client.cookies.set(self.app.ADMIN_COOKIE_NAME, self.app.admin_auth_token())
        session_id = self.app.create_session("device:test-background-overview", "unit-test")
        self.app.record_event(session_id, "idle_worker_tick", "device:test-background-overview", {"duration_ms": 12})
        self.app.record_analysis_trace(
            session_id=session_id,
            trace_id="trace-background-overview",
            event_type="model_call",
            visitor_ip="device:test-background-overview",
            step_name="memory_agent_model",
            duration_ms=123.0,
            payload={
                "model": "qwen3.6-35b-a3b-262k",
                "status": "completed",
                "usage": {"prompt_tokens": 7, "completion_tokens": 5, "total_tokens": 12},
            },
        )
        self.app.record_analysis_trace(
            session_id=session_id,
            trace_id="trace-background-overview-estimated",
            event_type="model_call",
            visitor_ip="device:test-background-overview",
            step_name="main_chat_stream",
            duration_ms=250.0,
            payload={
                "model": "deepseek-v4-pro",
                "status": "completed",
                "messages": [{"role": "user", "content": "请整理今天的计划"}],
                "answer_chars": 80,
            },
        )
        old_trace_at = (self.app.parse_utc_iso(self.app.utc_now()) - timedelta(days=2)).isoformat(timespec="seconds")
        with self.app.connect_db() as conn:
            for index in range(5):
                conn.execute(
                    """
                    INSERT INTO analysis_trace_events (
                        session_id, trace_id, event_type, visitor_ip, step_name,
                        duration_ms, payload_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        f"trace-background-overview-old-chat-{index}",
                        "model_call",
                        "device:test-background-overview",
                        "main_chat_stream",
                        100.0,
                        json.dumps(
                            {
                                "model": "deepseek-v4-pro",
                                "status": "completed",
                                "answer_chars": 20,
                            },
                            ensure_ascii=False,
                        ),
                        old_trace_at,
                    ),
                )
        for index in range(2):
            self.app.record_analysis_trace(
                session_id=session_id,
                trace_id=f"trace-background-overview-recent-embedding-{index}",
                event_type="embedding",
                visitor_ip="device:test-background-overview",
                step_name="memory_query_embedding",
                duration_ms=10.0,
                payload={
                    "model": "qwen3-embedding-8b",
                    "input_preview": "短期内的向量查询",
                    "dim": 4096,
                },
            )
        for page_index in (11, 12):
            self.app.record_analysis_trace(
                session_id=session_id,
                trace_id="trace-background-overview-page",
                event_type="web_page",
                visitor_ip="device:test-background-overview",
                step_name=f"read_page_{page_index}",
                duration_ms=50.0,
                payload={
                    "index": page_index,
                    "max_pages": 12,
                    "source": {"title": "示例网页", "url": "https://example.com"},
                    "page": {"page_excerpt": "网页摘要"},
                },
            )
        with self.app.connect_db() as conn:
            conn.execute(
                """
                INSERT INTO generated_images (
                    batch_id, source_type, source_id, file_path, public_url,
                    original_prompt, optimized_prompt, negative_prompt,
                    aspect_ratio, model_name, status, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "batch-background-overview",
                    "test",
                    "source-background-overview",
                    "/tmp/background-overview.png",
                    "/static/generated/background-overview.png",
                    "original prompt",
                    "optimized prompt",
                    "",
                    "1:1",
                    "HiDream-O1-Image-Dev-2604",
                    "completed",
                    "",
                    self.app.utc_now(),
                ),
            )

        response = self.client.get("/api/background/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        for key in (
            "generated_at",
            "summary",
            "agent_rows",
            "model_rows",
            "table_stats",
            "resource",
            "recent_windows",
        ):
            self.assertIn(key, payload)
        self.assertNotIn("workflow", payload)
        self.assertNotIn("processes", payload["resource"])
        self.assertGreaterEqual(payload["summary"]["messages"], 0)
        message_table = next(item for item in payload["table_stats"] if item["name"] == "messages")
        self.assertIn("聊天消息", message_table["description"])
        self.assertIn("recent_30d", message_table)
        self.assertIn("size_bytes", message_table)
        agent_row = next(item for item in payload["agent_rows"] if item["step_name"] == "memory_agent_model")
        self.assertIn("description", agent_row)
        self.assertEqual(agent_row["day"]["calls"], 1)
        self.assertEqual(agent_row["day"]["input_tokens"], 7)
        self.assertEqual(agent_row["day"]["output_tokens"], 5)
        self.assertEqual(agent_row["day"]["total_tokens"], 12)
        self.assertEqual(agent_row["month"]["total_duration_ms"], 123.0)
        chat_row = next(item for item in payload["agent_rows"] if item["step_name"] == "main_chat_stream")
        self.assertGreater(chat_row["day"]["input_tokens"], 0)
        self.assertGreater(chat_row["day"]["output_tokens"], 0)
        self.assertGreater(chat_row["day"]["total_tokens"], 0)
        self.assertEqual(payload["agent_rows"][0]["step_name"], "main_chat_stream")
        self.assertFalse(any(item["step_name"] == "read_page" for item in payload["agent_rows"]))
        self.assertFalse(any(item["step_name"] == "read_page_11" for item in payload["agent_rows"]))
        self.assertFalse(any(item["step_name"] == "main_chat_prompt" for item in payload["agent_rows"]))
        self.assertIn("大模型", agent_row["description"])
        model_row = next(item for item in payload["model_rows"] if item["model"] == "qwen3.6-35b-a3b-262k")
        self.assertIn("description", model_row)
        self.assertEqual(model_row["day"]["total_tokens"], 12)
        self.assertEqual(payload["model_rows"][0]["model"], "deepseek-v4-pro")
        image_model_row = next(item for item in payload["model_rows"] if item["model"] == "HiDream-O1-Image-Dev-2604")
        self.assertEqual(image_model_row["day"]["calls"], 1)
        self.assertEqual(image_model_row["description"], "本地画图模型")
        self.assertIn("cpu", payload["resource"])
        self.assertIn("memory", payload["resource"])
        self.assertIn("disk", payload["resource"])
        self.assertIn("current_process", payload["resource"])
        self.assertIn("gpus", payload["resource"])
        self.assertIn("image_storage", payload["resource"])
        self.assertIn("public_prefix", payload["resource"]["image_storage"])
        with mock.patch.dict(self.app.background_gpu_role_indices.__globals__, {"background_detect_gpu_role_indices": lambda: {}}), mock.patch.dict(os.environ, {}, clear=True):
            gpu_roles = self.app.background_gpu_role_indices()
        self.assertEqual(gpu_roles["6"], "本地 LLM")
        self.assertEqual(gpu_roles["7"], "本地 LLM")
        self.assertEqual(gpu_roles["5"], "Embedding")
        self.assertEqual(gpu_roles["4"], "本地画图")


class CurrentStaticContracts(unittest.TestCase):
    def test_character_library_stop_button_assets_are_wired(self):
        html = (ROOT / "static" / "characters.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "characters.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "characters.css").read_text(encoding="utf-8")

        self.assertIn("20260622_character_stop_button", html)
        self.assertIn("stopActiveCharacterGeneration", js)
        self.assertIn("/api/characters/sessions/", js)
        self.assertIn("is-stopping", css)
        self.assertIn("[已停止]", js)

    def test_split_loader_contract_replaces_old_monolith_scans(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        loader_py = (ROOT / "wangcai_app" / "startup" / "loader.py").read_text(encoding="utf-8")

        self.assertIn("_load_wangcai_namespace", app_py)
        self.assertIn("module.load_namespace()", app_py)
        self.assertIn("SOURCE_FILES", loader_py)
        self.assertIn("wangcai_app/routes/api.py", loader_py)

    def test_self_profile_mentions_character_library_stop_generation(self):
        profile = (ROOT / "wangcai_app" / "prompts" / "self_profile.py").read_text(encoding="utf-8")

        self.assertIn("角色库页面", profile)
        self.assertIn("支持上传图片、停止生成", profile)

    def test_password_visibility_assets_are_wired_to_password_pages(self):
        js = (ROOT / "static" / "password_visibility.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "password_visibility.css").read_text(encoding="utf-8")

        self.assertIn("password-visibility-toggle", js)
        self.assertIn("显示密码", js)
        self.assertIn("隐藏密码", js)
        self.assertIn(".password-input-wrap", css)
        for page in (
            "auth.html",
            "memory_admin_login.html",
            "analysis_login.html",
            "warn.html",
            "index.html",
        ):
            html = (ROOT / "static" / page).read_text(encoding="utf-8")
            self.assertIn("password_visibility.css?v=", html)
            self.assertIn("password_visibility.js?v=", html)

    def test_analysis_background_load_more_uses_offset_pagination(self):
        html = (ROOT / "static" / "analysis.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "analysis.js").read_text(encoding="utf-8")

        self.assertRegex(html, r"/static/analysis\.js\?v=[A-Za-z0-9_]+")
        self.assertIn("BACKGROUND_ACTIVITY_PAGE_SIZE", js)
        self.assertIn("backgroundNextOffset", js)
        self.assertIn("offset=${encodeURIComponent(offset)}", js)
        self.assertIn("traceRenderSignature", js)
        self.assertIn("backgroundRenderSignature", js)

    def test_opening_timing_payload_is_available_to_chat_stream(self):
        schema = (ROOT / "schemas.py").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("client_timing", schema)
        self.assertIn("openingTiming", js)
        self.assertIn("client_timing", js)

    def test_refresh_uses_cached_prompt_fast_opening_without_skipping_greeting(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertRegex(html, r"/static/app\.js\?v=[A-Za-z0-9_]+")
        self.assertIn("OPENING_PROMPT_STORAGE_KEY", js)
        self.assertIn("storeCachedOpeningPrompt", js)
        self.assertIn("readCachedOpeningPrompt", js)
        self.assertIn("startFastOpeningPrompt", js)
        self.assertIn("/api/opening/stream", js)
        self.assertIn("bootChatSession", js)
        self.assertNotIn("shouldDeferAutomaticSessionAfterReload", js)
        self.assertIn("window.addEventListener(\"pagehide\", handlePageHide)", js)

    def test_background_dashboard_uses_tables_and_preserves_login_target(self):
        background_html = (ROOT / "static" / "background.html").read_text(encoding="utf-8")
        background_js = (ROOT / "static" / "background.js").read_text(encoding="utf-8")
        background_css = (ROOT / "static" / "background.css").read_text(encoding="utf-8")
        login_html = (ROOT / "static" / "background_login.html").read_text(encoding="utf-8")

        self.assertIn("20260624_background_agent_height_align", background_html)
        self.assertIn("agentRows", background_html)
        self.assertIn("modelRows", background_html)
        self.assertIn("gpuDeployment", background_html)
        self.assertNotIn("workflowView", background_html)
        self.assertNotIn("agentPie", background_html)
        self.assertNotIn("modelPie", background_html)
        self.assertNotIn("slowAgents", background_html)
        self.assertNotIn("processStats", background_html)
        self.assertIn("agent_rows", background_js)
        self.assertIn("model_rows", background_js)
        self.assertIn("description", background_js)
        self.assertIn("recent_30d", background_js)
        self.assertIn("size_bytes", background_js)
        self.assertIn("近期活动", background_js)
        self.assertIn("图片目录", background_js)
        self.assertIn("agent-table-wrap", background_html)
        self.assertIn(".agent-table-wrap", background_css)
        self.assertIn("flex: 1 1 0", background_css)
        self.assertIn("position: sticky", background_css)
        self.assertIn('window.location.href = "/background"', login_html)


if __name__ == "__main__":
    unittest.main()
