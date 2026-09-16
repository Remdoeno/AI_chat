import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class SharedUserIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmpdir.name)
        self.env = {
            "WANGCAI_WEB_DB": str(tmp_path / "chat_history.sqlite3"),
            "WANGCAI_AUTH_CONFIG": str(tmp_path / "admin_auth.json"),
            "WANGCAI_IDLE_AGENT_ENABLED": "0",
            "WANGCAI_MEMORY_DEDUPE_AGENT_ENABLED": "0",
            "WANGCAI_MEMORY_REFINE_AGENT_ENABLED": "0",
        }
        for key, value in self.env.items():
            os.environ[key] = value
        sys.modules.pop("app", None)
        self.app = importlib.import_module("app")
        self.app.init_db()
        self.client = TestClient(self.app.app)
        self.device_a = "shared_user_device_alpha_001"
        self.device_b = "shared_user_device_beta_002"

    def tearDown(self):
        self.client.close()
        self.tmpdir.cleanup()
        for key in self.env:
            os.environ.pop(key, None)
        sys.modules.pop("app", None)

    def headers(self, device_id):
        return {"X-Wangcai-Device-Id": device_id}

    def bind(self, device_id, shared_user_id, password):
        response = self.client.put(
            "/api/user-memory-binding",
            headers=self.headers(device_id),
            json={
                "shared_user_id": shared_user_id,
                "share_chat_history": True,
                "is_host": True,
                "inherit_assistant_profile": True,
                "password": password,
                "confirm_password": password,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def insert_artifact(self, owner, title):
        with self.app.connect_db() as conn:
            run = conn.execute(
                """
                INSERT INTO idle_agent_runs (
                    task_type, title, prompt_summary, status,
                    started_at, updated_at, owner_shared_user_id
                )
                VALUES ('story', ?, '', 'completed', ?, ?, ?)
                """,
                (title, self.app.utc_now(), self.app.utc_now(), owner),
            )
            cur = conn.execute(
                """
                INSERT INTO idle_agent_artifacts (
                    run_id, title, artifact_type, content, summary,
                    created_at, owner_shared_user_id
                )
                VALUES (?, ?, 'story', ?, ?, ?, ?)
                """,
                (
                    int(run.lastrowid),
                    title,
                    f"{title} content",
                    f"{title} summary",
                    self.app.utc_now(),
                    owner,
                ),
            )
        return int(cur.lastrowid)

    def insert_character(self, owner, name):
        with self.app.connect_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO hidden_character_profiles (
                    canonical_name, name_key, aliases_json, visual_prompt,
                    negative_prompt, personality, background, relationships_json,
                    reference_image_ids_json, avatar_image_ids_json,
                    source_session_id, source_message_ids_json, source_visitor_ip,
                    owner_shared_user_id, scope, status, confidence,
                    revision_count, created_at, updated_at
                )
                VALUES (?, ?, '[]', '', '', '', '', '[]', '[]', '[]',
                        '', '[]', '', ?, 'artifact_public', 'active', 0.8, 1, ?, ?)
                """,
                (
                    name,
                    self.app.scoped_character_name_key(owner, name),
                    owner,
                    self.app.utc_now(),
                    self.app.utc_now(),
                ),
            )
        return int(cur.lastrowid)

    def insert_memory(self, device_id, content):
        normalized_device = self.app.clean_device_id(device_id)
        now = self.app.utc_now()
        with self.app.connect_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO curated_memories (
                    source_session_id, start_message_id, end_message_id, source_hash,
                    content, importance_label, visitor_ip, created_at, updated_at
                )
                VALUES (?, 0, 0, ?, ?, 'fact', ?, ?, ?)
                """,
                (
                    f"admin-memory-test-{device_id}",
                    f"admin-memory-test-hash-{device_id}",
                    content,
                    normalized_device,
                    now,
                    now,
                ),
            )
        return int(cur.lastrowid)

    def test_binding_initializes_password_and_future_changes_verify_it(self):
        result = self.bind(self.device_a, "alpha", "alpha-secret")
        self.assertEqual(result["shared_user_id"], "alpha")
        self.assertTrue(self.app.verify_shared_user_password("alpha", "alpha-secret"))

        wrong = self.client.put(
            "/api/user-memory-binding",
            headers=self.headers(self.device_a),
            json={
                "shared_user_id": "alpha",
                "share_chat_history": False,
                "is_host": False,
                "inherit_assistant_profile": False,
                "password": "wrong-secret",
                "confirm_password": "",
            },
        )
        self.assertEqual(wrong.status_code, 401)
        binding = self.client.get(
            "/api/user-memory-binding",
            headers=self.headers(self.device_a),
        ).json()
        self.assertTrue(binding["share_chat_history"])
        self.assertTrue(binding["is_host"])

    def test_analysis_cookie_is_scoped_to_the_bound_shared_user(self):
        self.bind(self.device_a, "alpha", "alpha-secret")
        self.bind(self.device_b, "beta", "beta-secret")

        login = self.client.post(
            "/api/analysis/login",
            headers=self.headers(self.device_a),
            json={"password": "alpha-secret", "confirm_password": ""},
        )
        self.assertEqual(login.status_code, 200, login.text)
        status_a = self.client.get(
            "/api/analysis/auth/status",
            headers=self.headers(self.device_a),
        ).json()
        status_b = self.client.get(
            "/api/analysis/auth/status",
            headers=self.headers(self.device_b),
        ).json()
        self.assertTrue(status_a["authenticated"])
        self.assertFalse(status_b["authenticated"])

    def test_unicode_shared_user_can_open_public_artifacts_and_analysis(self):
        user_id = "中文用户"
        password = "unicode-secret"
        self.bind(self.device_a, user_id, password)
        artifact_id = self.insert_artifact(user_id, "public artifact")
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE idle_agent_artifacts SET is_public = 1 WHERE id = ?",
                (artifact_id,),
            )

        first_frequency = self.client.get(
            "/api/artifacts/idle-frequency",
            headers=self.headers(self.device_a),
        )
        second_frequency = self.client.get(
            "/api/artifacts/idle-frequency",
            headers=self.headers(self.device_a),
        )
        public_artifacts = self.client.get(
            "/api/public/artifacts",
            headers=self.headers(self.device_a),
        )
        login = self.client.post(
            "/api/analysis/login",
            headers=self.headers(self.device_a),
            json={"password": password, "confirm_password": ""},
        )
        auth_status = self.client.get(
            "/api/analysis/auth/status",
            headers=self.headers(self.device_a),
        )

        self.assertEqual(first_frequency.status_code, 200, first_frequency.text)
        self.assertEqual(second_frequency.status_code, 200, second_frequency.text)
        self.assertEqual(public_artifacts.status_code, 200, public_artifacts.text)
        self.assertTrue(public_artifacts.json()["items"][0]["is_owner"])
        self.assertEqual(login.status_code, 200, login.text)
        self.assertTrue(auth_status.json()["authenticated"])

    def test_artifacts_and_characters_are_isolated_by_shared_user(self):
        self.bind(self.device_a, "alpha", "alpha-secret")
        self.bind(self.device_b, "beta", "beta-secret")
        artifact_a = self.insert_artifact("alpha", "alpha artifact")
        artifact_b = self.insert_artifact("beta", "beta artifact")
        character_a = self.insert_character("alpha", "same name")
        character_b = self.insert_character("beta", "same name")

        artifacts_a = self.client.get(
            "/api/artifacts",
            headers=self.headers(self.device_a),
        )
        self.assertEqual(artifacts_a.status_code, 200, artifacts_a.text)
        self.assertEqual([item["id"] for item in artifacts_a.json()["items"]], [artifact_a])
        self.assertNotEqual(artifact_a, artifact_b)

        characters_a = self.client.get(
            "/api/characters",
            headers=self.headers(self.device_a),
        )
        self.assertEqual(characters_a.status_code, 200, characters_a.text)
        self.assertEqual([item["id"] for item in characters_a.json()["items"]], [character_a])
        self.assertNotEqual(character_a, character_b)

        cross_user_character = self.client.get(
            f"/api/characters/{character_b}",
            headers=self.headers(self.device_a),
        )
        cross_user_artifact = self.client.delete(
            f"/api/artifacts/{artifact_b}",
            headers=self.headers(self.device_a),
        )
        self.assertEqual(cross_user_character.status_code, 404)
        self.assertEqual(cross_user_artifact.status_code, 404)

    def test_analysis_trace_list_only_returns_the_current_shared_user(self):
        self.bind(self.device_a, "alpha", "alpha-secret")
        self.bind(self.device_b, "beta", "beta-secret")
        normalized_a = self.app.clean_device_id(self.device_a)
        normalized_b = self.app.clean_device_id(self.device_b)
        session_a = self.app.create_session(normalized_a, "unit-test")
        session_b = self.app.create_session(normalized_b, "unit-test")
        self.app.record_analysis_trace(
            session_id=session_a,
            trace_id="trace-alpha",
            event_type="model_call",
            visitor_ip=normalized_a,
            step_name="main_chat_stream",
            payload={"usage": {"total_tokens": 3}},
        )
        self.app.record_analysis_trace(
            session_id=session_b,
            trace_id="trace-beta",
            event_type="model_call",
            visitor_ip=normalized_b,
            step_name="main_chat_stream",
            payload={"usage": {"total_tokens": 5}},
        )
        self.client.post(
            "/api/analysis/login",
            headers=self.headers(self.device_a),
            json={"password": "alpha-secret", "confirm_password": ""},
        )

        response = self.client.get(
            "/api/analysis/traces",
            headers=self.headers(self.device_a),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["trace_id"] for item in response.json()["items"]], ["trace-alpha"])

    def test_admin_memory_mode_uses_admin_password_and_filters_global_memories_by_user(self):
        self.bind(self.device_a, "alpha", "alpha-secret")
        self.bind(self.device_b, "beta", "beta-secret")
        memory_a = self.insert_memory(self.device_a, "alpha memory")
        memory_b = self.insert_memory(self.device_b, "beta memory")
        self.app.save_admin_password("admin-secret-2026")

        analysis_login = self.client.post(
            "/api/analysis/login",
            headers=self.headers(self.device_a),
            json={"password": "alpha-secret", "confirm_password": ""},
        )
        self.assertEqual(analysis_login.status_code, 200, analysis_login.text)
        self.assertEqual(self.client.get("/api/admin/memories").status_code, 401)
        self.assertIn("记忆后台", self.client.get("/memory-admin").text)

        admin_login = self.client.post(
            "/api/admin/login",
            json={"password": "admin-secret-2026"},
        )
        self.assertEqual(admin_login.status_code, 200, admin_login.text)

        users = self.client.get("/api/admin/memory-users")
        self.assertEqual(users.status_code, 200, users.text)
        self.assertEqual(
            {item["shared_user_id"] for item in users.json()["items"]},
            {"alpha", "beta"},
        )

        global_memories = self.client.get("/api/admin/memories")
        self.assertEqual(global_memories.status_code, 200, global_memories.text)
        self.assertEqual(
            {item["id"] for item in global_memories.json()["items"]},
            {memory_a, memory_b},
        )

        alpha_memories = self.client.get(
            "/api/admin/memories",
            params={"shared_user_id_filter": "alpha"},
        )
        self.assertEqual(alpha_memories.status_code, 200, alpha_memories.text)
        self.assertEqual([item["id"] for item in alpha_memories.json()["items"]], [memory_a])
        self.assertEqual(alpha_memories.json()["items"][0]["shared_user_id"], "alpha")
        self.assertIn("全局记忆后台", self.client.get("/memory-admin").text)

    def test_character_upsert_uses_owner_scoped_unique_name_key(self):
        self.bind(self.device_a, "alpha", "alpha-secret")
        self.bind(self.device_b, "beta", "beta-secret")
        decision = {
            "action": "upsert",
            "reason": "test",
            "character": {"canonical_name": "shared display name", "aliases": []},
        }
        with mock.patch.object(self.app, "sync_character_global_memory", return_value={"status": "skipped"}):
            first = self.app.upsert_hidden_character_profile(
                decision,
                session_id="",
                visitor_ip=self.app.clean_device_id(self.device_a),
                source_message_ids=[],
                source_type="character_library",
                owner_shared_user_id="alpha",
            )
            second = self.app.upsert_hidden_character_profile(
                decision,
                session_id="",
                visitor_ip=self.app.clean_device_id(self.device_b),
                source_message_ids=[],
                source_type="character_library",
                owner_shared_user_id="beta",
            )
        self.assertEqual(first["status"], "create")
        self.assertEqual(second["status"], "create")
        self.assertNotEqual(first["character_id"], second["character_id"])


if __name__ == "__main__":
    unittest.main()
