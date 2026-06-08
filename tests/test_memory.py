import importlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = sqlite3.connect(str(Path(self.tmpdir.name) / "memory.sqlite3"))
        self.conn.row_factory = sqlite3.Row
        if "memory" in sys.modules:
            del sys.modules["memory"]
        self.memory = importlib.import_module("memory")
        self.memory.init_memory_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()
        if "memory" in sys.modules:
            del sys.modules["memory"]

    def test_retrieves_relevant_history_from_other_sessions(self):
        self.memory.index_message(
            self.conn,
            message_id=1,
            session_id="old-session",
            role="user",
            content="我之前在聊 Qwen 网页部署和黑色幽默风格。",
            created_at="2026-05-27T01:00:00+00:00",
        )
        self.memory.index_message(
            self.conn,
            message_id=2,
            session_id="current-session",
            role="user",
            content="当前 session 的内容不应该作为长期记忆返回。",
            created_at="2026-05-27T02:00:00+00:00",
        )

        results = self.memory.retrieve_relevant_history(
            self.conn,
            query="还记得 Qwen 部署和黑色幽默吗？",
            current_session_id="current-session",
            limit=3,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["session_id"], "old-session")
        self.assertIn("Qwen 网页部署", results[0]["content"])

    def test_build_memory_context_anonymizes_identifiers(self):
        self.memory.index_message(
            self.conn,
            message_id=3,
            session_id="secret-session-id",
            role="assistant",
            content="你之前问过模型记忆模块应该如何接入。",
            created_at="2026-05-27T03:00:00+00:00",
        )

        context = self.memory.build_memory_context(
            self.conn,
            current_session_id="new-session",
            user_message="记忆模块怎么接入？",
            visitor_ip="1.2.3.4",
        )

        self.assertIn("相关历史片段", context)
        self.assertIn("模型记忆模块", context)
        self.assertNotIn("secret-session-id", context)
        self.assertNotIn("1.2.3.4", context)

    def test_memory_items_are_included_when_relevant(self):
        self.memory.add_memory_item(
            self.conn,
            content="长期设定：助手应该保持阴郁、腹黑、黑色幽默的男助手风格。",
            memory_type="persona",
            source_session_id="source-session",
        )

        context = self.memory.build_memory_context(
            self.conn,
            current_session_id="current-session",
            user_message="你的人设风格是什么？",
        )

        self.assertIn("长期记忆", context)
        self.assertIn("阴郁、腹黑、黑色幽默", context)
        self.assertNotIn("source-session", context)

    def test_init_memory_tables_backfills_existing_messages(self):
        self.conn.executescript(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                created_at TEXT NOT NULL
            );
            INSERT INTO messages (id, session_id, role, content, status, created_at)
            VALUES (10, 'past-session', 'user', '历史里有 C160 测试板和 Qwen 记忆。', 'completed', '2026-05-27T05:00:00+00:00');
            INSERT INTO messages (id, session_id, role, content, status, created_at)
            VALUES (11, 'past-session', 'assistant', '失败消息不该进入索引。', 'failed', '2026-05-27T05:01:00+00:00');
            """
        )

        self.memory.init_memory_tables(self.conn)

        results = self.memory.retrieve_relevant_history(
            self.conn,
            query="C160 测试板记忆",
            current_session_id="new-session",
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], 10)

    def test_empty_context_when_nothing_is_relevant(self):
        self.memory.index_message(
            self.conn,
            message_id=4,
            session_id="old-session",
            role="user",
            content="只是在讨论天气。",
            created_at="2026-05-27T04:00:00+00:00",
        )

        context = self.memory.build_memory_context(
            self.conn,
            current_session_id="current-session",
            user_message="矩阵乘法怎么优化？",
        )

        self.assertEqual(context, "")


if __name__ == "__main__":
    unittest.main()
