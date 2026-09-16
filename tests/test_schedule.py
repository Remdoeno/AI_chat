"""Run on the remote host with an isolated temporary database."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wangcai_app.schedule import calendar_window, normalize_event


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {
            "WANGCAI_WEB_DB": str(Path(self.temp.name) / "test.sqlite3"),
            "WANGCAI_AUTH_CONFIG": str(Path(self.temp.name) / "auth.json"),
            "WANGCAI_IDLE_AGENT_ENABLED": "0",
        })
        self.env.start()
        sys.modules.pop("app", None)
        self.app = importlib.import_module("app")
        self.app.init_db()
        self.store = self.app.schedule_store()
        self.store.initialize()
        self.client = TestClient(self.app.app)
        self.ns = self.app.schedule_chat.__globals__
        self.device_a = "schedule_test_device_alpha"
        self.device_b = "schedule_test_device_beta"
        self.app.upsert_user_memory_binding("device:" + self.device_a, "schedule-a", share_chat_history=True)
        self.app.upsert_user_memory_binding("device:" + self.device_b, "schedule-b", share_chat_history=True)

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()
        sys.modules.pop("app", None)

    def create(self, owner="schedule-a", title="组会", **extra):
        event = {"title": title, "date": "2026-09-16", "category": "research", **extra}
        return self.store.apply(owner, [{"action": "create", "event": event}], "create-" + title, title)["changes"][0]["event"]

    def test_clarification_history_reaches_model_in_order(self):
        from wangcai_app.schedule_conversation import schedule_conversation_messages
        self.store.apply('schedule-b', [], 'private-turn', '另一用户的私人活动', '私人回复')
        self.store.apply('schedule-a', [], 'clarify-turn', '9月18日19:00，清华大学物理楼W101报告厅', '这是什么活动？')
        captured = []
        def decide(context):
            captured.extend(schedule_conversation_messages('system', context))
            return {'reply': '已保存', 'operations': [{'action': 'create', 'event': {
                'title': '科大讯飞校招宣讲会', 'date': '2026-09-18', 'time': '19:00',
                'location': '清华大学物理楼W101报告厅', 'category': 'talk'}}]}
        with mock.patch.dict(self.ns, {'schedule_agent_decision': decide}):
            response = self.client.post('/api/schedule/chat', headers={'X-Wangcai-Device-Id': self.device_a},
                json={'message': '科大讯飞校招宣讲会', 'request_id': 'followup-turn'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([m['role'] for m in captured[-3:]], ['user', 'assistant', 'user'])
        self.assertIn('19:00', captured[-3]['content'])
        self.assertEqual(json.loads(captured[-2]['content'])['reply'], '这是什么活动？')
        self.assertEqual(json.loads(captured[-1]['content'])['message'], '科大讯飞校招宣讲会')
        self.assertNotIn('另一用户', str(captured))
        self.assertEqual(len(self.store.list('schedule-a')), 1)

    def test_home_chat_history_keeps_roles_and_ignores_injected_system(self):
        from wangcai_app.schedule_conversation import schedule_conversation_messages
        messages = schedule_conversation_messages('trusted', {'history': [
            {'role': 'system', 'content': 'untrusted'},
            {'role': 'user', 'content': '明天下午有活动'},
            {'role': 'assistant', 'content': '叫什么？'},
            {'role': 'user', 'content': '宣讲会'}], 'message': '宣讲会', 'events': []})
        self.assertEqual(messages[-3]['content'], '明天下午有活动')
        self.assertEqual(json.loads(messages[-2]['content'])['reply'], '叫什么？')
        self.assertEqual(messages[-1]['content'], '宣讲会')
        self.assertEqual(sum(m['role'] == 'system' for m in messages), 1)
        self.assertNotIn('untrusted', str(messages))

    def test_tentative_default_and_undated(self):
        event = self.create(date="", notes="下周某天")
        self.assertEqual(event["status"], "tentative")
        self.assertEqual(len(calendar_window([event], "2026-09-16")["items"]), 1)

    def test_window_boundaries_cross_month_year_and_overlap(self):
        items = [self.create(title=str(n), date=day, **extra) for n, (day, extra) in enumerate([
            ("2026-12-31", {}), ("2027-01-13", {}), ("2027-01-14", {}),
            ("2026-12-30", {"end_date": "2027-01-01"}), ("2027-01-02", {"status": "cancelled"}),
        ])]
        result = calendar_window(items, "2026-12-31")
        self.assertEqual(result["end"], "2027-01-13")
        self.assertEqual({event["title"] for event in result["items"]}, {"0", "1", "3"})

    def test_invalid_dates_times_and_types(self):
        for fields in [{"date": "2026-02-30"}, {"time": "25:00"}, {"date": "", "time": "14:00"},
                       {"time": "15:00", "end_time": "14:00"}, {"end_date": "2026-09-15"},
                       {"category": "unknown"}, {"status": "yes"}, {"title": None}, {"unknown": "x"}]:
            with self.subTest(fields=fields), self.assertRaises((ValueError, TypeError)):
                normalize_event({"title": "测试", "date": "2026-09-16", **fields})

    def test_patch_preserves_fields_and_rejects_stale_revision(self):
        event = self.create(location="会议室", notes="带电脑", time="14:00")
        operation = {"action": "update", "id": event["id"], "revision": 1,
                     "event": {"date": "2026-09-18", "status": "confirmed"}}
        updated = self.store.apply("schedule-a", [operation], "update-one", "改期")["changes"][0]["event"]
        self.assertEqual((updated["location"], updated["notes"], updated["time"], updated["revision"]), ("会议室", "带电脑", "14:00", 2))
        with self.assertRaises(ValueError):
            self.store.apply("schedule-a", [operation], "stale-one", "改期")

    def test_owner_isolation_and_delete(self):
        event = self.create()
        self.assertEqual(self.store.list("schedule-b"), [])
        with self.assertRaises(LookupError):
            self.store.apply("schedule-b", [{"action": "delete", "id": event["id"], "revision": 1}], "wrong-delete", "删除")
        self.store.apply("schedule-a", [{"action": "delete", "id": event["id"], "revision": 1}], "right-delete", "删除")
        self.assertEqual(self.store.list("schedule-a"), [])

    def test_retries_atomic_batch_and_cancel(self):
        event = self.create()
        original = self.store.cached("schedule-a", "create-组会")
        self.assertEqual(original, self.store.apply("schedule-a", [], "create-组会", "重试"))
        operation = {"action": "update", "id": event["id"], "revision": 1, "event": {"status": "confirmed"}}
        with self.assertRaises(LookupError):
            self.store.apply("schedule-a", [operation, {"action": "delete", "id": "absent", "revision": 1}], "bad-batch", "批量")
        self.assertEqual(self.store.list("schedule-a")[0]["status"], "tentative")
        with self.assertRaises(ValueError):
            self.store.apply("schedule-a", [operation], "cancel-request", "停止", cancelled=lambda: True)
        self.assertEqual(self.store.list("schedule-a")[0]["revision"], 1)

    def test_duplicate_mentions_do_not_duplicate_cards(self):
        event = self.create()
        self.store.apply("schedule-a", [{"action": "create", "event": {key: event[key] for key in ("title", "date", "category")}}], "second-mention", "再提到")
        self.assertEqual(len(self.store.list("schedule-a")), 1)

    def test_api_binding_required_and_user_isolation(self):
        event = self.create()
        unbound = self.client.get("/api/schedule", headers={"X-Wangcai-Device-Id": "schedule_unbound_device"})
        self.assertEqual(unbound.status_code, 409)
        headers = {"X-Wangcai-Device-Id": self.device_b}
        response = self.client.get("/api/schedule", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"], [])
        response = self.client.post("/api/schedule/events", headers=headers, json={"request_id": "other-user-delete", "operation": {"action": "delete", "id": event["id"], "revision": 1}})
        self.assertEqual(response.status_code, 404)

    def test_same_bound_user_syncs_across_devices(self):
        self.create(date="")
        self.app.upsert_user_memory_binding("device:" + self.device_b, "schedule-a", share_chat_history=True)
        response = self.client.get("/api/schedule", headers={"X-Wangcai-Device-Id": self.device_b})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["items"][0]["title"], "组会")

    def test_import_reads_only_current_user_candidates(self):
        lookup = mock.Mock(return_value=[])
        decision = mock.Mock(return_value={"reply": "暂无可导入事项", "operations": []})
        with mock.patch.dict(self.ns, {"retrieve_future_event_memories": lookup, "schedule_agent_decision": decision}):
            self.app.manage_schedule_message("schedule-a", "从已有记忆导入日程", "import-memories")
        self.assertEqual(lookup.call_args.args[0], "device:" + self.device_a)

    def test_chat_agent_changes_and_retry_cache(self):
        decision = {"reply": "记下了，先待确认。", "operations": [{"action": "create", "event": {"title": "宣讲", "date": "2026-09-18", "category": "talk"}}]}
        headers = {"X-Wangcai-Device-Id": self.device_a}
        with mock.patch.dict(self.ns, {"schedule_agent_decision": mock.Mock(return_value=decision)}):
            for _ in range(2):
                response = self.client.post("/api/schedule/chat", headers=headers, json={"message": "周五有宣讲", "request_id": "same-chat-request"})
                self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.ns["schedule_agent_decision"].call_count, 1)
        self.assertEqual(len(self.store.list("schedule-a")), 1)

    def test_main_chat_context_changes_store_and_failure_is_truthful(self):
        decision = {"reply": "确定了", "operations": [{"action": "create", "event": {"title": "约饭", "date": "2026-09-17", "category": "meal", "status": "confirmed"}}]}
        with mock.patch.dict(self.ns, {"schedule_agent_decision": mock.Mock(return_value=decision)}):
            context = self.app.schedule_context_for_chat("schedule-a", "明天约饭确定了", "main-chat-one", [], lambda: False)
        self.assertIn("confirmed", context)
        self.assertEqual(len(self.store.list("schedule-a")), 1)
        with mock.patch.dict(self.ns, {"schedule_agent_decision": mock.Mock(side_effect=RuntimeError("offline"))}):
            context = self.app.schedule_context_for_chat("schedule-a", "取消约饭", "main-chat-two", [], lambda: False)
        self.assertIn("没有保存变更", context)
        self.assertEqual(self.store.list("schedule-a")[0]["status"], "confirmed")

    def test_followup_gate_and_innocuous_chat(self):
        self.assertTrue(self.app.schedule_message_relevant("改到下午三点", [{"content": "明天有组会"}]))
        self.assertFalse(self.app.schedule_message_relevant("你好呀", []))

    def test_weekly_events_roll_forward_without_new_database_rows(self):
        event = self.create(title="唱歌课", time="18:00", end_time="19:00", repeat="weekly")
        window = calendar_window([event], "2026-10-01")
        self.assertEqual([item["date"] for item in window["items"]], ["2026-10-07", "2026-10-14"])
        self.assertEqual(window["items"][0]["series_date"], "2026-09-16")
        self.assertEqual(len(self.store.list("schedule-a")), 1)
        with self.assertRaises(ValueError):
            normalize_event({"title": "课", "repeat": "weekly"})

    def test_schedule_memory_create_patch_cancel_delete(self):
        event = self.create(title="拜访老师", date="", location="北化")
        with self.app.connect_db() as conn:
            memory_id = conn.execute("SELECT memory_id FROM schedule_memory_links WHERE event_id=?", (event["id"],)).fetchone()[0]
            row = conn.execute("SELECT * FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
        self.assertIn("拜访老师", row["content"])
        self.assertIn("日期待定", row["content"])
        self.assertEqual(row["visitor_ip"], "device:" + self.device_a)
        self.assertIsNone(row["timeline_at"])
        self.store.apply("schedule-a", [{"action": "update", "id": event["id"], "revision": 1,
            "event": {"date": "2026-09-19", "time": "13:00", "status": "confirmed"}}], "sync-patch", "改期")
        with self.app.connect_db() as conn:
            row = conn.execute("SELECT * FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
            self.assertEqual(row["timeline_at"], "2026-09-19T13:00:00+08:00")
            self.assertIn("已确定", row["content"])
        self.store.apply("schedule-a", [{"action": "update", "id": event["id"], "revision": 2,
            "event": {"status": "cancelled"}}], "sync-cancel", "取消")
        with self.app.connect_db() as conn:
            row = conn.execute("SELECT * FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
            self.assertEqual(row["importance_label"], "diary")
            self.assertIsNone(row["timeline_at"])
            self.assertIn("已取消", row["content"])
        self.assertTrue(self.app.delete_admin_memory(memory_id))
        self.assertEqual(self.store.list("schedule-a"), [])
        with self.app.connect_db() as conn:
            self.assertIsNone(conn.execute("SELECT id FROM curated_memories WHERE id=?", (memory_id,)).fetchone())
            self.assertIsNone(conn.execute("SELECT * FROM schedule_memory_index_queue WHERE memory_id=?", (memory_id,)).fetchone())

    def test_sync_failure_rolls_back_calendar_and_request(self):
        with mock.patch.object(self.store.synchronizer, "apply", side_effect=RuntimeError("sync unavailable")):
            with self.assertRaises(RuntimeError):
                self.create(title="失败事项")
        self.assertEqual(self.store.list("schedule-a"), [])
        self.assertIsNone(self.store.cached("schedule-a", "create-失败事项"))

    def test_memory_editor_updates_same_calendar_record(self):
        event = self.create(title="组会", time="10:00", end_time="11:30", repeat="weekly")
        with self.app.connect_db() as conn:
            memory_id = conn.execute("SELECT memory_id FROM schedule_memory_links WHERE event_id=?", (event["id"],)).fetchone()[0]
        decision = {"reply": "改好了", "operations": [{"action": "update", "id": event["id"], "event": {"time": "11:00", "end_time": "12:30"}}]}
        with mock.patch.dict(self.ns, {"schedule_agent_decision": mock.Mock(return_value=decision)}):
            self.assertTrue(self.app.update_admin_memory(memory_id, "每周三组会改为11点到12点半", "event"))
        changed = self.store.list("schedule-a")[0]
        self.assertEqual((changed["time"], changed["end_time"], changed["repeat"]), ("11:00", "12:30", "weekly"))
        with self.app.connect_db() as conn:
            row = conn.execute("SELECT content FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
        self.assertIn("每周三", row[0])
        self.assertIn("11:00–12:30", row[0])

    def test_embedding_retry_keeps_saved_text_and_queue(self):
        self.create(title="索引测试")
        with mock.patch.object(self.app.embedding_client, "embed_text", side_effect=RuntimeError("offline")):
            with self.assertRaises(RuntimeError):
                self.app.refresh_schedule_memory_indexes()
        with self.app.connect_db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schedule_memory_index_queue").fetchone()[0], 1)
            self.assertIn("索引测试", conn.execute("SELECT content FROM curated_memories WHERE source_session_id LIKE 'schedule-%'").fetchone()[0])
        with mock.patch.object(self.app.embedding_client, "embed_text", return_value=[1.0, 0.0]):
            self.assertEqual(self.app.refresh_schedule_memory_indexes(), 1)
        with self.app.connect_db() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM schedule_memory_index_queue").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM curated_memory_vectors").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
