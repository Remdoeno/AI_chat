import importlib.util
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "data" / "view_chat_history.py"


class ViewChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "chat_history.sqlite3"
        self._create_db()

        spec = importlib.util.spec_from_file_location("view_chat_history", SCRIPT)
        self.viewer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.viewer)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                visitor_ip TEXT NOT NULL,
                user_agent TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                end_reason TEXT
            );
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
        conn.execute(
            """
            INSERT INTO sessions
            (id, visitor_ip, user_agent, started_at, ended_at, end_reason)
            VALUES ('s1', '1.2.3.4', 'ua-one', '2026-05-27T01:00:00+00:00', NULL, NULL)
            """
        )
        conn.execute(
            """
            INSERT INTO sessions
            (id, visitor_ip, user_agent, started_at, ended_at, end_reason)
            VALUES ('s2', '5.6.7.8', 'ua-two', '2026-05-27T02:00:00+00:00', '2026-05-27T02:05:00+00:00', 'reset')
            """
        )
        conn.execute(
            """
            INSERT INTO messages (session_id, role, content, status, created_at)
            VALUES ('s1', 'user', '你好', 'completed', '2026-05-27T01:01:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO messages (session_id, role, content, status, created_at)
            VALUES ('s1', 'assistant', '你好，我在。', 'completed', '2026-05-27T01:01:05+00:00')
            """
        )
        conn.commit()
        conn.close()

    def test_list_sessions_returns_newest_first(self):
        sessions = self.viewer.list_sessions(self.db_path)

        self.assertEqual([session["id"] for session in sessions], ["s2", "s1"])
        self.assertEqual(sessions[0]["visitor_ip"], "5.6.7.8")

    def test_get_messages_for_session_returns_ordered_messages(self):
        messages = self.viewer.get_messages_for_session("s1", self.db_path)

        self.assertEqual(
            [(message["role"], message["content"]) for message in messages],
            [("user", "你好"), ("assistant", "你好，我在。")],
        )

    def test_print_all_chats_outputs_sessions_and_messages(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.viewer.print_all_chats(self.db_path)

        text = output.getvalue()
        self.assertIn("Session: s1", text)
        self.assertIn("IP: 1.2.3.4", text)
        self.assertIn("[user]", text)
        self.assertIn("你好，我在。", text)


if __name__ == "__main__":
    unittest.main()
