"""Bounded retention of diagnostic heartbeats, separate from business events."""
from contextlib import closing
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

# Explicit whitelist: never expire business records or failure diagnostics by default.
HEARTBEATS = ('idle_worker_tick', 'idle_worker_tick_done')
RETENTION_DAYS = 7
LOGGER = logging.getLogger(__name__)


def compact_batch(db_path, now=None, batch_size=1000):
    """Atomically preserve daily counts and remove only the selected old heartbeats."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=RETENTION_DAYS)).isoformat(timespec='seconds')
    with closing(sqlite3.connect(str(db_path), timeout=0.25)) as conn, conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('''CREATE TABLE IF NOT EXISTS event_daily_summaries (
            day TEXT NOT NULL, event_type TEXT NOT NULL, event_count INTEGER NOT NULL,
            first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
            PRIMARY KEY(day, event_type))''')
        rows = conn.execute('''SELECT id, event_type, created_at FROM events
            WHERE event_type IN (?, ?) AND created_at < ?
            ORDER BY id LIMIT ?''', (*HEARTBEATS, cutoff, max(1, min(batch_size, 2000)))).fetchall()
        groups = {}
        for _, kind, created in rows:
            key = (created[:10], kind)
            count, first, last = groups.get(key, (0, created, created))
            groups[key] = (count + 1, min(first, created), max(last, created))
        for (day, kind), (count, first, last) in groups.items():
            conn.execute('''INSERT INTO event_daily_summaries VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(day, event_type) DO UPDATE SET
                event_count=event_count+excluded.event_count,
                first_seen_at=min(first_seen_at, excluded.first_seen_at),
                last_seen_at=max(last_seen_at, excluded.last_seen_at)''',
                (day, kind, count, first, last))
        conn.executemany('DELETE FROM events WHERE id=?', [(r[0],) for r in rows])
    return len(rows)


def run_maintenance(db_path, stop):
    """Start after the web service, yield between batches, retry locks later."""
    delay = 60
    while not stop.wait(delay):
        total = 0
        try:
            for _ in range(600):
                count = compact_batch(db_path)
                total += count
                if not count or stop.wait(0.1):
                    break
            if total:
                LOGGER.info('Event retention: compacted %s old heartbeats into daily counts', total)
            delay = 86400
        except sqlite3.Error:
            LOGGER.exception('Event retention postponed; committed batches remain consistent')
            delay = 3600
