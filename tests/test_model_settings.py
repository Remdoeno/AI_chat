import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ModelSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["QWEN_WEB_DB"] = str(Path(self.tmpdir.name) / "chat_history.sqlite3")
        os.environ["QWEN_AUTH_CONFIG"] = str(Path(self.tmpdir.name) / "admin_auth.json")
        os.environ["QWEN_MODEL_BASE_URL"] = "http://127.0.0.1:8000/v1"
        os.environ["QWEN_MODEL_NAME"] = "qwen3.6-35b-a3b-262k"
        os.environ["QWEN_MODEL_API_KEY"] = "EMPTY"
        if "app" in sys.modules:
            del sys.modules["app"]
        self.app = importlib.import_module("app")
        self.app.init_db()

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in ("QWEN_WEB_DB", "QWEN_AUTH_CONFIG", "QWEN_MODEL_API_KEY"):
            os.environ.pop(key, None)
        if "app" in sys.modules:
            del sys.modules["app"]

    def test_default_model_settings_keep_local_qwen_display(self):
        settings = self.app.load_model_settings()

        self.assertEqual(settings["chat"]["provider"], "local")
        self.assertEqual(settings["background"]["provider"], "local")
        self.assertEqual(settings["chat"]["display_name"], "Qwen3.6")
        self.assertEqual(settings["background"]["display_name"], "Qwen3.6")
        self.assertEqual(settings["chat"]["model"], "qwen3.6-35b-a3b-262k")

    def test_model_settings_endpoint_masks_api_keys_and_keeps_slots_separate(self):
        client = TestClient(self.app.app)

        response = client.put(
            "/api/model-settings",
            json={
                "chat": {
                    "provider": "openai",
                    "display_name": "GPT-4.1",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4.1",
                    "api_key": "sk-chat-secret",
                    "use_proxy": True,
                    "proxy_url": "http://127.0.0.1:7890",
                },
                "background": {
                    "provider": "local",
                    "display_name": "",
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
        self.assertEqual(payload["chat"]["display_name"], "GPT-4.1")
        self.assertTrue(payload["chat"]["has_api_key"])
        self.assertNotIn("api_key", payload["chat"])
        self.assertEqual(payload["background"]["display_name"], "Qwen3.6")
        self.assertFalse(payload["background"]["has_api_key"])

        saved = self.app.load_model_settings()
        self.assertEqual(saved["chat"]["api_key"], "sk-chat-secret")
        self.assertEqual(saved["background"]["provider"], "local")

        clear_response = client.put(
            "/api/model-settings",
            json={
                "chat": {
                    "provider": "local",
                    "display_name": "",
                    "base_url": "http://127.0.0.1:8000/v1",
                    "model": "qwen3.6-35b-a3b-262k",
                    "use_proxy": True,
                    "proxy_url": "http://127.0.0.1:7890",
                },
                "background": {
                    "provider": "local",
                    "display_name": "",
                    "base_url": "http://127.0.0.1:8000/v1",
                    "model": "qwen3.6-35b-a3b-262k",
                    "use_proxy": False,
                    "proxy_url": "",
                },
            },
        )

        self.assertEqual(clear_response.status_code, 200)
        cleared = self.app.load_model_settings()
        self.assertEqual(cleared["chat"]["display_name"], "Qwen3.6")
        self.assertEqual(cleared["chat"]["api_key"], "")
        self.assertFalse(cleared["chat"]["use_proxy"])

    def test_local_model_service_status_reports_qwen_and_embedding_ports(self):
        client = TestClient(self.app.app)

        original_probe = self.app.probe_local_openai_models
        self.app.probe_local_openai_models = lambda base_url, timeout=2.0: {
            "ok": base_url.endswith(":8000/v1") or base_url.endswith(":8001/v1"),
            "models": ["qwen3.6-35b-a3b-262k"] if base_url.endswith(":8000/v1") else ["qwen3-embedding-8b"],
            "error": "",
        }
        try:
            response = client.get("/api/local-model-service/status")
        finally:
            self.app.probe_local_openai_models = original_probe

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["qwen"]["running"])
        self.assertTrue(payload["embedding"]["running"])
        self.assertEqual(payload["qwen"]["port"], 8000)
        self.assertEqual(payload["embedding"]["port"], 8001)
        self.assertEqual(payload["summary"], "已运行：Qwen 8000 / Embedding 8001")
        self.assertFalse(payload["settings_updated"])

    def test_local_model_service_status_does_not_change_model_settings_by_default(self):
        client = TestClient(self.app.app)
        self.app.save_model_settings(
            {
                "chat": {
                    "provider": "deepseek",
                    "display_name": "DeepSeek Chat",
                    "base_url": "https://api.deepseek.com/v1",
                    "model": "deepseek-chat",
                    "api_key": "test-key",
                    "use_proxy": True,
                    "proxy_url": "http://127.0.0.1:7890",
                },
                "background": {
                    "provider": "local",
                    "display_name": "Qwen3.6",
                    "base_url": "http://127.0.0.1:8000/v1",
                    "model": "qwen3.6-35b-a3b-262k",
                    "api_key": "",
                    "use_proxy": False,
                    "proxy_url": "",
                },
            }
        )

        original_probe = self.app.probe_local_openai_models
        self.app.probe_local_openai_models = lambda base_url, timeout=2.0: {
            "ok": True,
            "models": ["qwen3.6-35b-a3b-262k"] if base_url.endswith(":8000/v1") else ["qwen3-embedding-8b"],
            "error": "",
        }
        try:
            response = client.get("/api/local-model-service/status")
        finally:
            self.app.probe_local_openai_models = original_probe

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["settings_updated"])
        saved = self.app.load_model_settings()
        self.assertEqual(saved["chat"]["provider"], "deepseek")
        self.assertEqual(saved["chat"]["model"], "deepseek-chat")

    def test_local_model_service_start_updates_local_model_settings_when_services_ready(self):
        client = TestClient(self.app.app)

        original_probe = self.app.probe_local_openai_models
        original_start = self.app.start_missing_local_model_services
        self.app.probe_local_openai_models = lambda base_url, timeout=2.0: {
            "ok": True,
            "models": ["qwen3.6-35b-a3b-262k"] if base_url.endswith(":8000/v1") else ["qwen3-embedding-8b"],
            "error": "",
        }
        self.app.start_missing_local_model_services = lambda status: {
            "started": False,
            "commands": [],
            "message": "services already running",
        }
        try:
            response = client.post("/api/local-model-service/start")
        finally:
            self.app.probe_local_openai_models = original_probe
            self.app.start_missing_local_model_services = original_start

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["qwen"]["running"])
        self.assertTrue(payload["embedding"]["running"])
        self.assertTrue(payload["settings_updated"])
        saved = self.app.load_model_settings()
        self.assertEqual(saved["chat"]["provider"], "local")
        self.assertEqual(saved["chat"]["base_url"], "http://127.0.0.1:8000/v1")
        self.assertEqual(saved["background"]["model"], "qwen3.6-35b-a3b-262k")
