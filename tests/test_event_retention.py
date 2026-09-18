import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from wangcai_app.event_retention import compact_batch


class RetentionTests(unittest.TestCase):
    def test_preserves_business_errors_recent_and_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db'
            with sqlite3.connect(path) as c:
                c.execute('CREATE TABLE events(id INTEGER PRIMARY KEY,event_type TEXT,created_at TEXT)')
                c.executemany('INSERT INTO events(event_type,created_at) VALUES (?,?)', [
                    ('idle_worker_tick','2026-09-01T00:00:00+00:00'),
                    ('idle_worker_tick','2026-09-01T01:00:00+00:00'),
                    ('idle_worker_tick_done','2026-09-02T00:00:00+00:00'),
                    ('message_user','2026-01-01T00:00:00+00:00'),
                    ('idle_worker_error','2026-01-01T00:00:00+00:00'),
                    ('idle_worker_tick','2026-09-11T00:00:00+00:00')])
            now = datetime(2026,9,18,tzinfo=timezone.utc)
            self.assertEqual(compact_batch(path,now,1),1)
            self.assertEqual(compact_batch(path,now),2)
            self.assertEqual(compact_batch(path,now),0)
            with sqlite3.connect(path) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],3)
                self.assertEqual(c.execute('SELECT SUM(event_count) FROM event_daily_summaries').fetchone()[0],3)
                self.assertEqual(c.execute("SELECT event_count FROM event_daily_summaries WHERE day='2026-09-01'").fetchone()[0],2)

    def test_summary_and_deletion_rollback_together(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'db'
            with sqlite3.connect(path) as c:
                c.executescript("CREATE TABLE events(id INTEGER PRIMARY KEY,event_type TEXT,created_at TEXT); INSERT INTO events VALUES(1,'idle_worker_tick','2020-01-01'); CREATE TRIGGER deny BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'blocked'); END;")
            with self.assertRaises(sqlite3.IntegrityError):
                compact_batch(path)
            with sqlite3.connect(path) as c:
                self.assertEqual(c.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
                self.assertFalse(c.execute("SELECT name FROM sqlite_master WHERE name='event_daily_summaries'").fetchone())
