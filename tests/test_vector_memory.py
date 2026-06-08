import importlib
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class VectorMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.conn = sqlite3.connect(str(Path(self.tmpdir.name) / "vector.sqlite3"))
        self.conn.row_factory = sqlite3.Row
        self._create_messages()
        if "vector_memory" in sys.modules:
            del sys.modules["vector_memory"]
        self.vector_memory = importlib.import_module("vector_memory")
        self.vector_memory.init_vector_memory_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmpdir.cleanup()
        if "vector_memory" in sys.modules:
            del sys.modules["vector_memory"]

    def _create_messages(self):
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
            """
        )
        rows = [
            ("s1", "user", "我们在讨论 Qwen 向量记忆。"),
            ("s1", "assistant", "可以把聊天切成连续窗口。"),
            ("s1", "user", "每段十条左右，然后 embedding。"),
            ("s1", "assistant", "检索时用余弦相似度。"),
            ("s1", "user", "命中后加载连续聊天记录。"),
            ("s2", "user", "今天午饭吃面。"),
            ("s2", "assistant", "听起来不错。"),
        ]
        for index, (session_id, role, content) in enumerate(rows, start=1):
            self.conn.execute(
                """
                INSERT INTO messages (id, session_id, role, content, status, created_at)
            VALUES (?, ?, ?, ?, 'completed', ?)
            """,
                (index, session_id, role, content, f"2026-05-28T00:00:{index:02d}+00:00"),
            )
        self.conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, status, created_at)
            VALUES (?, ?, ?, ?, 'completed', ?)
            """,
            (8, "s3", "user", "Qwen 向量记忆是什么意思？", "2026-05-28T00:00:08+00:00"),
        )
        self.conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, status, created_at)
            VALUES (?, ?, ?, ?, 'completed', ?)
            """,
            (9, "s3", "assistant", "这是一个历史模板回答。", "2026-05-28T00:00:09+00:00"),
        )
        self.conn.commit()

    def test_build_memory_segments_uses_sliding_windows_per_session(self):
        created = self.vector_memory.rebuild_memory_segments(self.conn, window_size=3, stride=2)

        self.assertEqual(created, 4)
        rows = self.conn.execute(
            """
            SELECT session_id, start_message_id, end_message_id, message_count, content
            FROM memory_segments
            ORDER BY id
            """
        ).fetchall()
        self.assertEqual(
            [(row["session_id"], row["start_message_id"], row["end_message_id"], row["message_count"]) for row in rows],
            [("s1", 1, 3, 3), ("s1", 3, 5, 3), ("s2", 6, 7, 2), ("s3", 8, 9, 2)],
        )
        self.assertIn("[user] 我们在讨论 Qwen 向量记忆。", rows[0]["content"])

    def test_vector_roundtrip_and_cosine_retrieval(self):
        self.vector_memory.rebuild_memory_segments(self.conn, window_size=3, stride=2)
        rows = self.conn.execute("SELECT id, content FROM memory_segments ORDER BY id").fetchall()
        for row in rows:
            vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            if "午饭" in row["content"]:
                vector = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            self.vector_memory.upsert_memory_vector(
                self.conn,
                segment_id=row["id"],
                vector=vector,
                model_name="fake-embedding",
            )

        results = self.vector_memory.retrieve_similar_segments(
            self.conn,
            query_vector=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            limit=2,
        )

        self.assertEqual(len(results), 2)
        self.assertGreaterEqual(results[0]["score"], 0.99)
        self.assertIn("Qwen 向量记忆", results[0]["content"])
        self.assertNotIn("session_id", self.vector_memory.format_vector_memory_context(results))

    def test_retrieval_can_exclude_exact_current_user_prompt_segments(self):
        self.vector_memory.rebuild_memory_segments(self.conn, window_size=3, stride=2)
        rows = self.conn.execute("SELECT id, content FROM memory_segments ORDER BY id").fetchall()
        for row in rows:
            vector = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            self.vector_memory.upsert_memory_vector(
                self.conn,
                segment_id=row["id"],
                vector=vector,
                model_name="fake-embedding",
            )

        results = self.vector_memory.retrieve_similar_segments(
            self.conn,
            query_vector=np.array([1.0, 0.0, 0.0], dtype=np.float32),
            limit=10,
            current_session_id="s1",
            current_user_message="Qwen 向量记忆",
        )

        self.assertTrue(results)
        self.assertTrue(all(row["session_id"] != "s1" for row in results))
        self.assertTrue(all("Qwen 向量记忆" not in row["content"] for row in results))

    def test_missing_vector_segments_are_returned_in_order(self):
        self.vector_memory.rebuild_memory_segments(self.conn, window_size=3, stride=2)
        first_id = self.conn.execute("SELECT id FROM memory_segments ORDER BY id LIMIT 1").fetchone()["id"]
        self.vector_memory.upsert_memory_vector(
            self.conn,
            segment_id=first_id,
            vector=np.array([1.0, 0.0], dtype=np.float32),
            model_name="fake-embedding",
        )

        missing = self.vector_memory.get_segments_missing_vectors(self.conn, limit=10)

        self.assertEqual(len(missing), 3)
        self.assertNotEqual(missing[0]["id"], first_id)

    def test_build_vector_memory_context_returns_empty_without_vectors(self):
        self.vector_memory.rebuild_memory_segments(self.conn, window_size=3, stride=2)

        context = self.vector_memory.build_vector_memory_context(
            self.conn,
            query_vector=np.array([1.0, 0.0, 0.0], dtype=np.float32),
        )

        self.assertEqual(context, "")

    def test_memory_context_warns_against_copying_history_answers(self):
        context = self.vector_memory.format_vector_memory_context(
            [{"content": "[user] abc\n[assistant] 历史回答模板", "score": 0.98}]
        )

        self.assertIn("仅供参考", context)
        self.assertIn("不要复制", context)
        self.assertIn("不要把历史 assistant 回复当作当前答案模板", context)

    def test_dedupe_removes_older_similar_vector_index_but_keeps_messages(self):
        self.vector_memory.rebuild_memory_segments(self.conn, window_size=2, stride=2)
        rows = self.conn.execute("SELECT id FROM memory_segments ORDER BY id LIMIT 2").fetchall()
        old_id = rows[0]["id"]
        new_id = rows[1]["id"]
        self.vector_memory.upsert_memory_vector(
            self.conn,
            segment_id=old_id,
            vector=np.array([1.0, 0.0], dtype=np.float32),
            model_name="fake-embedding",
        )
        self.vector_memory.upsert_memory_vector(
            self.conn,
            segment_id=new_id,
            vector=np.array([0.97, 0.03], dtype=np.float32),
            model_name="fake-embedding",
        )
        before_messages = self.conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]

        stats = self.vector_memory.dedupe_similar_memory_vectors(self.conn, threshold=0.95)

        self.assertEqual(stats["deleted"], 1)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM memory_segments WHERE id = ?", (old_id,)).fetchone())
        self.assertIsNotNone(self.conn.execute("SELECT 1 FROM memory_segments WHERE id = ?", (new_id,)).fetchone())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"], before_messages)
        tombstone = self.conn.execute("SELECT segment_id FROM memory_segment_tombstones").fetchone()
        self.assertEqual(tombstone["segment_id"], old_id)


if __name__ == "__main__":
    unittest.main()
