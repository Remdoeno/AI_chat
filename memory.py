import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init_memory_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL DEFAULT 'global',
            source_session_id TEXT,
            source_message_ids TEXT NOT NULL DEFAULT '[]',
            memory_type TEXT NOT NULL DEFAULT 'summary',
            content TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.8,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT,
            use_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS message_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL UNIQUE,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memory_items_updated
            ON memory_items(updated_at);
        CREATE INDEX IF NOT EXISTS idx_message_index_session
            ON message_index(session_id, id);
        CREATE INDEX IF NOT EXISTS idx_message_index_created
            ON message_index(created_at);
        """
    )

    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
            USING fts5(kind, ref_id UNINDEXED, content, tokenize='unicode61')
            """
        )
    except sqlite3.OperationalError:
        # Some SQLite builds omit FTS5. Retrieval still works via Python scoring.
        pass

    backfill_existing_messages(conn)


def row_to_dict(row: sqlite3.Row) -> Dict[str, object]:
    return {key: row[key] for key in row.keys()}


def has_fts(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'memory_fts'"
    ).fetchone()
    return row is not None


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def backfill_existing_messages(conn: sqlite3.Connection) -> int:
    if not table_exists(conn, "messages"):
        return 0

    rows = conn.execute(
        """
        SELECT id, session_id, role, content, created_at
        FROM messages
        WHERE status = 'completed'
          AND role IN ('user', 'assistant')
          AND id NOT IN (SELECT message_id FROM message_index)
        ORDER BY id ASC
        """
    ).fetchall()

    for row in rows:
        index_message(
            conn,
            message_id=int(row["id"]),
            session_id=str(row["session_id"]),
            role=str(row["role"]),
            content=str(row["content"]),
            created_at=str(row["created_at"]),
        )

    return len(rows)


def index_message(
    conn: sqlite3.Connection,
    message_id: int,
    session_id: str,
    role: str,
    content: str,
    created_at: str,
) -> None:
    if role not in {"user", "assistant"} or not content.strip():
        return

    conn.execute(
        """
        INSERT INTO message_index (message_id, session_id, role, content, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            session_id = excluded.session_id,
            role = excluded.role,
            content = excluded.content,
            created_at = excluded.created_at
        """,
        (message_id, session_id, role, content, created_at),
    )

    if has_fts(conn):
        ref_id = str(message_id)
        conn.execute("DELETE FROM memory_fts WHERE kind = 'message' AND ref_id = ?", (ref_id,))
        conn.execute(
            "INSERT INTO memory_fts (kind, ref_id, content) VALUES ('message', ?, ?)",
            (ref_id, content),
        )


def add_memory_item(
    conn: sqlite3.Connection,
    content: str,
    memory_type: str = "summary",
    scope: str = "global",
    source_session_id: Optional[str] = None,
    source_message_ids: Optional[Sequence[int]] = None,
    confidence: float = 0.8,
) -> int:
    now = utc_now()
    cur = conn.execute(
        """
        INSERT INTO memory_items (
            scope, source_session_id, source_message_ids, memory_type,
            content, confidence, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scope,
            source_session_id,
            json.dumps(list(source_message_ids or []), ensure_ascii=False),
            memory_type,
            content,
            confidence,
            now,
            now,
        ),
    )
    memory_id = int(cur.lastrowid)

    if has_fts(conn):
        conn.execute(
            "INSERT INTO memory_fts (kind, ref_id, content) VALUES ('memory', ?, ?)",
            (str(memory_id), content),
        )

    return memory_id
