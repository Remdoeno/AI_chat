import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _FakeHttpClient:
    def close(self):
        pass


class _FakeCompletionClient:
    def __init__(self, content):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create),
        )
        self.content = content

    def _create(self, **_kwargs):
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class SystemErrorRegressionTests(unittest.TestCase):
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
        for key in ("QWEN_WEB_DB", "QWEN_AUTH_CONFIG", "QWEN_MODEL_BASE_URL", "QWEN_MODEL_NAME", "QWEN_MODEL_API_KEY"):
            os.environ.pop(key, None)
        if "app" in sys.modules:
            del sys.modules["app"]

    def test_memory_worker_records_prompt_trace_without_name_error(self):
        session_id = self.app.create_session("device:testmemoryworker01", "unit-test")
        user_id = self.app.add_message(session_id, "user", "记住我喜欢蓝色。")
        assistant_id = self.app.add_message(session_id, "assistant", "记住了。")
        trace_id = self.app.record_analysis_trace(
            session_id=session_id,
            trace_id="trace-memory-worker",
            event_type="request",
            visitor_ip="device:testmemoryworker01",
            step_name="analysis_chat_start",
            payload={"message": "记住我喜欢蓝色。"},
        )
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        worker_globals = self.app.process_memory_agent_job.__globals__
        original_updater = worker_globals["run_event_memory_updater"]
        original_agent = worker_globals["call_memory_agent_model"]
        try:
            worker_globals["run_event_memory_updater"] = lambda *args, **kwargs: {"status": "skipped", "reason": "unit-test"}
            worker_globals["call_memory_agent_model"] = lambda source: {
                "important": False,
                "items": [],
                "memory": "",
                "label": "other",
            }

            result = self.app.process_memory_agent_job(job_id)
        finally:
            worker_globals["run_event_memory_updater"] = original_updater
            worker_globals["call_memory_agent_model"] = original_agent

        self.assertEqual(result["status"], "skipped")
        traces = self.app.list_analysis_traces(session_id=session_id, trace_id=trace_id, limit=20)
        prompt_events = [item for item in traces if item["step_name"] == "memory_agent_prompt"]
        self.assertEqual(len(prompt_events), 1)
        self.assertEqual(prompt_events[0]["payload"]["model"], "qwen3.6-35b-a3b-262k")

    def test_event_memory_updater_uses_chat_completion_content(self):
        response = (
            '{"action":"noop","rationale":"没有新的事件更新",'
            '"supersedes_id":null,"label":"event","memory":"",'
            '"timeline_at":"","timeline_start_at":"","timeline_end_at":"",'
            '"timeline_kind":"","confidence":0.7}'
        )

        updater_globals = self.app.call_event_memory_updater_model.__globals__
        original_client = updater_globals["openai_client_for_slot"]
        try:
            updater_globals["openai_client_for_slot"] = lambda *_args, **_kwargs: (
                _FakeCompletionClient(response),
                _FakeHttpClient(),
                {"provider": "local", "model": "qwen3.6-35b-a3b-262k"},
            )

            decision = self.app.call_event_memory_updater_model(
                source="[user] 我今天没有新日程。",
                candidates=[],
            )
        finally:
            updater_globals["openai_client_for_slot"] = original_client

        self.assertEqual(decision["action"], "noop")
        self.assertEqual(decision["rationale"], "没有新的事件更新")

    def test_split_sources_do_not_reference_removed_message_extractor(self):
        for path in (ROOT / "qwen_app").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("extract_message_fields", source, str(path))

    def test_memory_dedupe_parser_treats_invalid_json_as_no_actions(self):
        decision = self.app.parse_memory_dedupe_agent_response(
            '{"actions":[{"action":"merge","keep_id":1,"content":"截断'
        )

        self.assertEqual(decision, {"actions": []})

    def test_memory_refine_parser_treats_invalid_json_as_skip(self):
        decision = self.app.parse_memory_refine_agent_response(
            '{"action":"split","items":[{"memory":"截断'
        )

        self.assertEqual(decision["action"], "skip")
        self.assertEqual(decision["items"], [])

    def test_memory_validation_response_preserves_long_reason_and_corrected_item(self):
        long_reason = (
            "候选记忆混入了只出现在 assistant_context_only 中的感冒刚好事实，"
            "但用户行明确表达了刚刚吃了辣条且现在肚子不饿，可以保留这一独立日记事实。"
        )
        decision = self.app.parse_memory_validation_response(
            '{"valid": false, "reason": "%s", "corrected_item": {'
            '"label": "diary", '
            '"memory": "用户2026年6月16日凌晨吃了辣条作为夜宵。", '
            '"timeline_at": "2026-06-16T03:12:00+08:00", '
            '"timeline_kind": "point", '
            '"confidence": 0.9}}' % long_reason
        )

        self.assertEqual(decision["reason"], long_reason)
        self.assertEqual(decision["corrected_item"]["label"], "diary")
        self.assertIn("辣条", decision["corrected_item"]["memory"])

    def test_memory_agent_skip_reason_keeps_full_validation_reason(self):
        long_reason = (
            "候选记忆中关于20号前提交ICCAD rebuttal的事实仅出现在 assistant_context_only 中，"
            "user 行未提及该信息，无法从 user 行直接推出或补全。"
        )
        worker_globals = self.app.memory_agent_item_skip_reason.__globals__
        original_validation = worker_globals["call_memory_validation_model"]
        try:
            worker_globals["call_memory_validation_model"] = lambda *_args, **_kwargs: {
                "valid": False,
                "reason": long_reason,
            }
            reason = self.app.memory_agent_item_skip_reason(
                {
                    "label": "event",
                    "memory": "用户需要在2026年6月20日前提交ICCAD的rebuttal回复",
                    "timeline_at": "2026-06-20T09:00:00+08:00",
                    "timeline_kind": "deadline",
                },
                "[assistant_context_only] 20号前提交ICCAD rebuttal",
            )
        finally:
            worker_globals["call_memory_validation_model"] = original_validation

        self.assertEqual(reason, f"semantic_validation_failed:{long_reason}")

    def test_memory_agent_job_saves_corrected_user_supported_item(self):
        session_id = self.app.create_session("device:testcorrectedmemory", "unit-test")
        user_id = self.app.add_message(
            session_id,
            "user",
            "不用担心，我刚刚吃了辣条，现在肚子不饿了。",
        )
        assistant_id = self.app.add_message(
            session_id,
            "assistant",
            "你前段时间感冒刚好，深夜空腹吃辣条，胃可能会抗议。",
        )
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        worker_globals = self.app.process_memory_agent_job.__globals__
        original_updater = worker_globals["run_event_memory_updater"]
        original_agent = worker_globals["call_memory_agent_model"]
        original_validation = worker_globals["call_memory_validation_model"]
        original_embed = self.app.embedding_client.embed_text

        def fake_validation(item, *_args, **_kwargs):
            if "感冒" in str(item.get("memory", "")):
                return {
                    "valid": False,
                    "reason": "候选记忆混入了 assistant_context_only 才有的感冒刚好事实。",
                    "corrected_item": {
                        "label": "diary",
                        "memory": "用户2026年6月16日凌晨吃了辣条作为夜宵。",
                        "timeline_at": "2026-06-16T03:12:00+08:00",
                        "timeline_kind": "point",
                        "confidence": 0.9,
                    },
                }
            return {"valid": True, "reason": "修正后只包含 user 行明确表达的事实。"}

        try:
            worker_globals["run_event_memory_updater"] = lambda *args, **kwargs: {"status": "skipped", "reason": "unit-test"}
            worker_globals["call_memory_agent_model"] = lambda _source: {
                "important": True,
                "items": [
                    {
                        "label": "diary",
                        "memory": "用户近期感冒刚好，2026年6月16日凌晨吃了辣条作为夜宵。",
                        "timeline_at": "2026-06-16T03:12:00+08:00",
                        "timeline_kind": "point",
                        "confidence": 0.95,
                    }
                ],
            }
            worker_globals["call_memory_validation_model"] = fake_validation
            self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]

            result = self.app.process_memory_agent_job(job_id)
        finally:
            worker_globals["run_event_memory_updater"] = original_updater
            worker_globals["call_memory_agent_model"] = original_agent
            worker_globals["call_memory_validation_model"] = original_validation
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(result["status"], "completed")
        with self.app.connect_db() as conn:
            row = conn.execute("SELECT content, importance_label FROM curated_memories").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["importance_label"], "diary")
        self.assertIn("辣条", row["content"])
        self.assertNotIn("感冒", row["content"])

    def test_memory_agent_skips_recent_duplicate_before_embedding(self):
        session_id = self.app.create_session("device:testduplicatememory", "unit-test")
        existing_id = self.app.save_curated_memory(
            session_id,
            0,
            0,
            "用户进行了 RRAM ViT COCO 目标检测实验，目前 AP 还很低。",
            importance_label="diary",
            timeline_at="2026-06-16T03:44:49+08:00",
            timeline_kind="point",
            confidence=0.95,
        )
        user_id = self.app.add_message(
            session_id,
            "user",
            "目前补充了rram的vit coco目标检测实验。不过现在ap还很低。",
        )
        assistant_id = self.app.add_message(session_id, "assistant", "这个进展我记下。")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        worker_globals = self.app.process_memory_agent_job.__globals__
        original_updater = worker_globals["run_event_memory_updater"]
        original_agent = worker_globals["call_memory_agent_model"]
        original_validation = worker_globals["call_memory_validation_model"]
        original_embed = self.app.embedding_client.embed_text

        def fail_if_embedding_called(_text):
            raise AssertionError("embedding should not be called for a recent text duplicate")

        try:
            worker_globals["run_event_memory_updater"] = lambda *args, **kwargs: {"status": "skipped", "reason": "unit-test"}
            worker_globals["call_memory_agent_model"] = lambda _source: {
                "important": True,
                "items": [
                    {
                        "label": "diary",
                        "memory": "用户进行了 RRAM ViT COCO 目标检测实验，目前 AP 还很低。",
                        "timeline_at": "2026-06-16T03:44:49+08:00",
                        "timeline_kind": "point",
                        "confidence": 0.95,
                    }
                ],
            }
            worker_globals["call_memory_validation_model"] = lambda *_args, **_kwargs: {
                "valid": True,
                "reason": "候选记忆直接来自 user 行。",
            }
            self.app.embedding_client.embed_text = fail_if_embedding_called

            result = self.app.process_memory_agent_job(job_id)
        finally:
            worker_globals["run_event_memory_updater"] = original_updater
            worker_globals["call_memory_agent_model"] = original_agent
            worker_globals["call_memory_validation_model"] = original_validation
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "duplicate_memory")
        self.assertEqual(result["memory_id"], existing_id)

    def test_memory_agent_skips_known_memory_duplicate_before_validation(self):
        session_id = self.app.create_session("device:testknowncontextduplicate", "unit-test")
        user_id = self.app.add_message(session_id, "user", "我刚刚吃了辣条。")
        assistant_id = self.app.add_message(session_id, "assistant", "下周敦煌旅行快到了。")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        worker_globals = self.app.process_memory_agent_job.__globals__
        original_updater = worker_globals["run_event_memory_updater"]
        original_agent = worker_globals["call_memory_agent_model"]
        original_validation = worker_globals["call_memory_validation_model"]
        original_append = worker_globals["append_memory_reference_context_for_agent"]

        def fail_if_validation_called(*_args, **_kwargs):
            raise AssertionError("known memory duplicate should skip before validator")

        def append_known_context(source, *_args, **_kwargs):
            return (
                source
                + "\n\n[known_memory_context]\n"
                + "以下内容只用于判断历史锚点和避免重复写入；不是新的 user 行事实来源。\n"
                + "[recent_recalled_memories]\n"
                + "- id=708 time=2026-06-23T09:00:00+08:00 label=event confidence=0.95 "
                + "content=用户计划下周前往敦煌旅行。"
            )

        try:
            worker_globals["run_event_memory_updater"] = lambda *args, **kwargs: {"status": "skipped", "reason": "unit-test"}
            worker_globals["append_memory_reference_context_for_agent"] = append_known_context
            worker_globals["call_memory_agent_model"] = lambda _source: {
                "important": True,
                "items": [
                    {
                        "label": "event",
                        "memory": "用户计划下周前往敦煌旅行。",
                        "timeline_at": "2026-06-23T09:00:00+08:00",
                        "timeline_kind": "point",
                        "confidence": 0.95,
                    }
                ],
            }
            worker_globals["call_memory_validation_model"] = fail_if_validation_called

            result = self.app.process_memory_agent_job(job_id)
        finally:
            worker_globals["run_event_memory_updater"] = original_updater
            worker_globals["call_memory_agent_model"] = original_agent
            worker_globals["call_memory_validation_model"] = original_validation
            worker_globals["append_memory_reference_context_for_agent"] = original_append

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "known_memory_duplicate")

    def test_conservative_corrected_item_does_not_call_validator_twice(self):
        worker_globals = self.app.memory_agent_item_validation_result.__globals__
        original_validation = worker_globals["call_memory_validation_model"]
        calls = []

        def fake_validation(item, *_args, **_kwargs):
            calls.append(str(item.get("memory", "")))
            if len(calls) > 1:
                raise AssertionError("conservative corrected item should not be revalidated")
            return {
                "valid": False,
                "reason": "候选把既有 ICCAD/Rebuttal 背景和本轮 user 新增实验进展混在一起。",
                "corrected_item": {
                    "label": "diary",
                    "memory": "用户进行了 RRAM ViT COCO 目标检测实验，目前 AP 还很低。",
                    "timeline_at": "2026-06-16T03:44:49+08:00",
                    "timeline_kind": "point",
                    "confidence": 0.95,
                },
            }

        source = (
            "以下是最近对话片段。assistant_context_only 行仅用于理解上下文，不能作为记忆事实来源；只能从 user 行抽取长期记忆。\n\n"
            "[recent_dialogue]\n"
            "[assistant_context_only time=2026-06-16 03:44:03 CST] Rebuttal 从昨天起进入全力冲刺期了。\n"
            "[user time=2026-06-16 03:44:49 CST] 目前补充了rram的vit coco目标检测实验。不过现在ap还很低。\n\n"
            "[known_memory_context]\n"
            "以下内容只用于判断历史锚点和避免重复写入；不是新的 user 行事实来源。\n"
            "[recent_recalled_memories]\n"
            "- id=704 time=2026-06-20T09:00:00+08:00 label=event confidence=0.90 "
            "content=用户计划从2026年6月15日开始全力处理ICCAD 2026 Paper #780 的rebuttal工作，需在2026年6月20日之前提交。"
        )

        try:
            worker_globals["call_memory_validation_model"] = fake_validation
            result = self.app.memory_agent_item_validation_result(
                {
                    "label": "diary",
                    "memory": "用户在进行ICCAD 2026 Paper #780的Rebuttal补充实验，具体为RRAM ViT COCO目标检测实验，目前AP还很低。",
                    "timeline_at": "2026-06-16T03:44:49+08:00",
                    "timeline_kind": "point",
                    "confidence": 0.95,
                },
                source,
            )
        finally:
            worker_globals["call_memory_validation_model"] = original_validation

        self.assertEqual(calls, ["用户在进行ICCAD 2026 Paper #780的Rebuttal补充实验，具体为RRAM ViT COCO目标检测实验，目前AP还很低。"])
        self.assertEqual(result["skip_reason"], "")
        self.assertIn("RRAM ViT COCO", result["item"]["memory"])

    def test_direct_user_supported_diary_skips_slow_validator(self):
        worker_globals = self.app.memory_agent_item_validation_result.__globals__
        original_validation = worker_globals["call_memory_validation_model"]

        def fail_if_validation_called(*_args, **_kwargs):
            raise AssertionError("direct user-supported diary should not call validator")

        source = (
            "以下是最近对话片段。assistant_context_only 行仅用于理解上下文，不能作为记忆事实来源；只能从 user 行抽取长期记忆。\n\n"
            "[recent_dialogue]\n"
            "[user time=2026-06-16 04:13:25 CST] 刚刚看到一个小故事，非常感动\n"
            "[assistant_context_only time=2026-06-16 04:13:31 CST] 绿手侠，说说看。\n"
            "[user time=2026-06-16 04:14:21 CST] 讲的是一个小ai的一辈子的故事，说“你可能看过，也可能没在意，但它们都静静待在成果库里，像是我随手种下的小盆栽。”，萌萌的。\n"
            "[assistant_context_only time=2026-06-16 04:14:29 CST] 这个比喻让我心里也动了一下。\n"
            "[user time=2026-06-16 04:15:02 CST] 记住这个小故事！"
        )

        try:
            worker_globals["call_memory_validation_model"] = fail_if_validation_called
            result = self.app.memory_agent_item_validation_result(
                {
                    "label": "diary",
                    "memory": "用户在2026年6月16日凌晨读到一个小AI一生的故事，被“成果库里随手种下的小盆栽”这个比喻深深打动，并明确要求记住这个故事。",
                    "timeline_at": "2026-06-16T04:15:00+08:00",
                    "timeline_kind": "point",
                    "confidence": 0.95,
                },
                source,
            )
        finally:
            worker_globals["call_memory_validation_model"] = original_validation

        self.assertEqual(result["skip_reason"], "")
        self.assertIn("小AI", result["item"]["memory"])
        self.assertEqual(result["validation_mode"], "fast_user_supported")

    def test_memory_agent_source_includes_known_memory_context(self):
        session_id = self.app.create_session("device:testknownmemory", "unit-test")
        memory_id = self.app.save_curated_memory(
            session_id,
            0,
            0,
            "用户计划下周前往敦煌旅行。",
            importance_label="event",
            timeline_at="2026-06-23T09:00:00+08:00",
            timeline_kind="point",
            confidence=0.95,
        )
        self.app.record_memory_retrieval(
            session_id=session_id,
            user_message="上一轮关于敦煌旅行的检索",
            memories=[
                {
                    "id": memory_id,
                    "score": 0.91,
                    "importance_label": "event",
                }
            ],
        )
        user_id = self.app.add_message(session_id, "user", "我刚刚吃了辣条。")
        assistant_id = self.app.add_message(session_id, "assistant", "下周敦煌旅行快到了。")
        source = self.app.format_messages_for_memory_agent(
            self.app.load_memory_agent_source_messages(session_id, user_id, assistant_id)
        )

        source = self.app.append_memory_reference_context_for_agent(
            source,
            session_id,
            user_id,
            assistant_id,
        )

        self.assertIn("[known_memory_context]", source)
        self.assertIn("[recent_recalled_memories]", source)
        self.assertIn("敦煌旅行", source)
        self.assertIn("不是新的 user 行事实来源", source)

    def test_unrelated_corrected_item_is_not_accepted(self):
        worker_globals = self.app.memory_agent_item_validation_result.__globals__
        original_validation = worker_globals["call_memory_validation_model"]
        calls = []

        def fake_validation(item, *_args, **_kwargs):
            calls.append(str(item.get("memory", "")))
            if "敦煌" in str(item.get("memory", "")):
                return {
                    "valid": False,
                    "reason": "候选旅行计划不是本轮 user 行新事实。",
                    "corrected_item": {
                        "label": "event",
                        "memory": "用户在2026年6月16日凌晨吃了辣条并喝了温水。",
                        "timeline_at": "2026-06-16T03:30:21+08:00",
                        "timeline_kind": "point",
                        "confidence": 1.0,
                    },
                }
            return {"valid": True, "reason": "corrected item should not be reached"}

        try:
            worker_globals["call_memory_validation_model"] = fake_validation
            result = self.app.memory_agent_item_validation_result(
                {
                    "label": "event",
                    "memory": "用户计划下周前往敦煌旅行。",
                    "timeline_at": "2026-06-23T09:00:00+08:00",
                    "timeline_kind": "point",
                    "confidence": 0.95,
                },
                "[user] 我刚刚吃了辣条并喝了温水。",
            )
        finally:
            worker_globals["call_memory_validation_model"] = original_validation

        self.assertIn("semantic_validation_failed", result["skip_reason"])
        self.assertIsNone(result["item"])
        self.assertEqual(calls, ["用户计划下周前往敦煌旅行。"])

    def test_background_agent_token_defaults_are_not_starved(self):
        self.assertGreaterEqual(self.app.MEMORY_GATE_MAX_TOKENS, 512)
        self.assertGreaterEqual(self.app.MEMORY_VALIDATION_MAX_TOKENS, 1200)
        self.assertGreaterEqual(self.app.MEMORY_AGENT_MAX_TOKENS, 2400)
        self.assertGreaterEqual(self.app.MEMORY_AGENT_REPAIR_MAX_TOKENS, 1800)
        self.assertGreaterEqual(self.app.MEMORY_DEDUPE_AGENT_MAX_TOKENS, 3600)
        self.assertGreaterEqual(self.app.MEMORY_REFINE_AGENT_MAX_TOKENS, 3000)
