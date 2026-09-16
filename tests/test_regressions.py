import importlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class IsolatedAppTestCase(unittest.TestCase):
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

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in self.env_keys:
            os.environ.pop(key, None)
        sys.modules.pop("app", None)


class RecentRegressionTests(IsolatedAppTestCase):
    def test_idle_worker_tick_record_failure_does_not_stop_loop(self):
        worker_globals = self.app.idle_agent_worker_loop.__globals__

        class StopLoop(Exception):
            pass

        sleep_calls = {"count": 0}
        recorded_events = []
        task_calls = []

        def fake_sleep(_seconds):
            sleep_calls["count"] += 1
            if sleep_calls["count"] > 1:
                raise StopLoop()

        def fake_record_event(_session_id, event_type, _visitor_ip, payload):
            recorded_events.append((event_type, payload))
            raise OSError("disk I/O error")

        def fake_task(name):
            def _run(*_args, **_kwargs):
                task_calls.append(name)
                return {"status": "skipped", "reason": "unit-test"}

            return _run

        originals = {
            "sleep": worker_globals["time"].sleep,
            "record_event": worker_globals["record_event"],
            "run_opening_cache_refresh_once": worker_globals["run_opening_cache_refresh_once"],
            "run_memory_dedupe_agent_once": worker_globals["run_memory_dedupe_agent_once"],
            "run_memory_refine_agent_once": worker_globals["run_memory_refine_agent_once"],
            "run_idle_agent_once": worker_globals["run_idle_agent_once"],
        }
        try:
            worker_globals["time"].sleep = fake_sleep
            worker_globals["record_event"] = fake_record_event
            worker_globals["run_opening_cache_refresh_once"] = fake_task("opening_cache")
            worker_globals["run_memory_dedupe_agent_once"] = fake_task("memory_dedupe")
            worker_globals["run_memory_refine_agent_once"] = fake_task("memory_refine")
            worker_globals["run_idle_agent_once"] = fake_task("idle_write")

            with self.assertRaises(StopLoop):
                self.app.idle_agent_worker_loop()
        finally:
            worker_globals["time"].sleep = originals["sleep"]
            worker_globals["record_event"] = originals["record_event"]
            worker_globals["run_opening_cache_refresh_once"] = originals["run_opening_cache_refresh_once"]
            worker_globals["run_memory_dedupe_agent_once"] = originals["run_memory_dedupe_agent_once"]
            worker_globals["run_memory_refine_agent_once"] = originals["run_memory_refine_agent_once"]
            worker_globals["run_idle_agent_once"] = originals["run_idle_agent_once"]

        self.assertEqual(sleep_calls["count"], 2)
        self.assertEqual([event_type for event_type, _payload in recorded_events], ["idle_worker_tick", "idle_worker_error"])
        self.assertEqual(task_calls, [])

    def test_character_library_cancel_endpoint_marks_active_generation_cancelled(self):
        session_id = self.app.create_session("device:test-character-stop-regression", "unit-test")
        generation_token = self.app.acquire_generation_token(session_id)
        client = TestClient(self.app.app)

        response = client.post(f"/api/characters/sessions/{session_id}/cancel")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"cancelled": True})
        self.assertTrue(self.app.is_generation_cancelled(session_id, generation_token))

    def test_stale_active_generation_cleanup_unblocks_idle(self):
        session_id = self.app.create_session("device:test-stale-active-generation", "unit-test")
        token = self.app.acquire_generation_token(session_id)
        self.app.ACTIVE_GENERATION_STARTED_AT[session_id] = time.time() - 3600

        cleared = self.app.cleanup_stale_active_generations(max_age_seconds=30)

        self.assertEqual(cleared, 1)
        self.assertNotIn(session_id, self.app.ACTIVE_GENERATIONS)
        self.assertNotIn(session_id, self.app.ACTIVE_GENERATION_TOKENS)
        self.assertFalse(self.app.is_generation_cancelled(session_id, token))

    def test_invalid_memory_agent_json_parsers_fail_closed(self):
        dedupe = self.app.parse_memory_dedupe_agent_response(
            '{"actions":[{"action":"merge","keep_id":1,"content":"截断'
        )
        refine = self.app.parse_memory_refine_agent_response(
            '{"action":"split","items":[{"memory":"截断'
        )

        self.assertEqual(dedupe, {"actions": []})
        self.assertEqual(refine["action"], "skip")
        self.assertEqual(refine["items"], [])

    def test_idle_series_prompt_extracts_title_from_leading_clause(self):
        prompt = "Cora的泳装海边之旅，以类似小红书多图简短文字post的形式，展示Cora在海边休假的生活。连载50集。"

        directive = self.app.idle_series_directive_from_prompt(prompt)

        self.assertEqual(directive["series_title"], "Cora的泳装海边之旅")
        self.assertEqual(directive["target_count"], 50)
        self.assertTrue(directive["explicit_series"])

    def test_artifact_image_prompt_uses_character_visual_anchor_without_name(self):
        now = self.app.utc_now()
        with self.app.connect_db() as conn:
            conn.execute(
                """
                INSERT INTO hidden_character_profiles (
                    canonical_name, name_key, aliases_json, visual_prompt,
                    negative_prompt, personality, background, relationships_json,
                    reference_image_ids_json, avatar_image_ids_json, source_session_id,
                    source_message_ids_json, source_visitor_ip, scope, status,
                    confidence, revision_count, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '', '[]', '', 'artifact_public', 'active', 0.95, 1, ?, ?)
                """,
                (
                    "Cora",
                    self.app.character_name_key("Cora"),
                    json.dumps(["Cora"], ensure_ascii=False),
                    "A stunningly attractive 24-year-old woman named Cora from Northeast China who grew up in Beijing. "
                    "She has a black bob hairstyle with no bangs, visible forehead and hairline, a slender but strong fit physique, "
                    "thinner lips, a narrower nose, and a more three-dimensional facial structure.",
                    "wrong ethnicity, bangs, blonde hair",
                    "gentle, confident, spontaneous natural smile",
                    "excellent running ability and outdoor vacation energy",
                    "[]",
                    now,
                    now,
                ),
            )

        with self.app.connect_db() as conn:
            conn.execute("UPDATE hidden_character_profiles SET owner_shared_user_id='fixture_owner'")
        source = self.app.artifact_image_prompt_source(
            "Cora的海边假日",
            "Cora在浅海水里大笑。",
            "Cora湿着头发站在海水里，阳光很亮。",
            {"title": "封面", "brief": "Cora在浅海水里大笑，湿发，假日感", "role": "cover"},
            owner_shared_user_id="fixture_owner",
        )

        self.assertNotIn("Cora", source)
        self.assertNotIn("woman this character", source)
        self.assertIn("Northeast China", source)
        self.assertIn("grew up in Beijing", source)
        self.assertIn("black bob hairstyle with no bangs", source)
        self.assertIn("visible forehead and hairline", source)
        self.assertIn("thinner lips", source)
        self.assertIn("Character-specific negative constraints", source)
        self.assertIn("Use only generic labels in the final prompt. Do not output actual character names or aliases.", source)


if __name__ == "__main__":
    unittest.main()
