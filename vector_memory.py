import hashlib
import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np


DEFAULT_WINDOW_SIZE = 10
DEFAULT_STRIDE = 5
DEFAULT_TOP_K = 10
DEFAULT_DEDUPE_THRESHOLD = 0.95
VECTOR_DTYPE = np.float32


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_dict(row: sqlite3.Row) -> Dict[str, object]:
    return {key: row[key] for key in row.keys()}


def init_vector_memory_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            start_message_id INTEGER NOT NULL,
            end_message_id INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS memory_vectors (
            segment_id INTEGER PRIMARY KEY,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            model_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(segment_id) REFERENCES memory_segments(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memory_segment_tombstones (
            content_hash TEXT PRIMARY KEY,
            segment_id INTEGER NOT NULL,
            duplicate_of_segment_id INTEGER,
            similarity REAL,
            reason TEXT NOT NULL,
            deleted_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memory_segments_session
            ON memory_segments(session_id, start_message_id, end_message_id);
        CREATE INDEX IF NOT EXISTS idx_memory_segments_updated
            ON memory_segments(updated_at);
        """
    )


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def normalize_vector(vector: np.ndarray) -> np.ndarray:
    arr = np.asarray(vector, dtype=VECTOR_DTYPE).reshape(-1)
    norm = float(np.linalg.norm(arr))
    if norm == 0.0:
        return arr
    return arr / norm


def vector_to_blob(vector: np.ndarray) -> bytes:
    return normalize_vector(vector).astype(VECTOR_DTYPE).tobytes()


def blob_to_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=VECTOR_DTYPE, count=dim)


def format_message(role: str, content: str) -> str:
    return f"[{role}] {content.strip()}"


def segment_contains_exact_user_message(content: str, user_message: str) -> bool:
    text = user_message.strip()
    if not text:
        return False
    if text in content:
        return True
    pattern = rf"(?m)^\[user\]\s+{re.escape(text)}\s*$"
    return re.search(pattern, content) is not None


def fetch_completed_messages(conn: sqlite3.Connection) -> Dict[str, List[sqlite3.Row]]:
    rows = conn.execute(
        """
        SELECT id, session_id, role, content, created_at
        FROM messages
        WHERE status = 'completed'
          AND role = 'user'
          AND length(trim(content)) > 0
        ORDER BY session_id ASC, id ASC
        """
    ).fetchall()

    by_session: Dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        by_session.setdefault(str(row["session_id"]), []).append(row)
    return by_session


def build_segment_content(messages: List[sqlite3.Row]) -> str:
    return "\n".join(format_message(str(row["role"]), str(row["content"])) for row in messages)


def upsert_memory_segment(conn: sqlite3.Connection, session_id: str, messages: List[sqlite3.Row]) -> int:
    text = build_segment_content(messages)
    digest = content_hash(text)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO memory_segments (
            session_id, start_message_id, end_message_id, message_count,
            content, content_hash, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(content_hash) DO UPDATE SET
            session_id = excluded.session_id,
            start_message_id = excluded.start_message_id,
            end_message_id = excluded.end_message_id,
            message_count = excluded.message_count,
            content = excluded.content,
            updated_at = excluded.updated_at
        """,
        (
            session_id,
            int(messages[0]["id"]),
            int(messages[-1]["id"]),
            len(messages),
            text,
            digest,
            now,
            now,
        ),
    )
    row = conn.execute("SELECT id FROM memory_segments WHERE content_hash = ?", (digest,)).fetchone()
    return int(row["id"])


def is_tombstoned_content(conn: sqlite3.Connection, digest: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM memory_segment_tombstones WHERE content_hash = ?",
        (digest,),
    ).fetchone()
    return row is not None


def rebuild_memory_segments(
    conn: sqlite3.Connection,
    window_size: int = DEFAULT_WINDOW_SIZE,
    stride: int = DEFAULT_STRIDE,
) -> int:
    init_vector_memory_tables(conn)
    if window_size <= 0 or stride <= 0:
        raise ValueError("window_size and stride must be positive")

    created_or_updated = 0
    for session_id, messages in fetch_completed_messages(conn).items():
        start = 0
        while start < len(messages):
            window = messages[start : start + window_size]
            if not window:
                break
            digest = content_hash(build_segment_content(window))
            if not is_tombstoned_content(conn, digest):
                upsert_memory_segment(conn, session_id, window)
                created_or_updated += 1
            if start + window_size >= len(messages):
                break
            start += stride

    return created_or_updated


def upsert_memory_vector(
    conn: sqlite3.Connection,
    segment_id: int,
    vector: np.ndarray,
    model_name: str,
) -> None:
    arr = normalize_vector(vector)
    conn.execute(
        """
        INSERT INTO memory_vectors (segment_id, dim, vector, model_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(segment_id) DO UPDATE SET
            dim = excluded.dim,
            vector = excluded.vector,
            model_name = excluded.model_name,
            created_at = excluded.created_at
        """,
        (segment_id, int(arr.shape[0]), arr.tobytes(), model_name, utc_now()),
    )


def get_segments_missing_vectors(conn: sqlite3.Connection, limit: Optional[int] = None) -> List[Dict[str, object]]:
    sql = """
        SELECT s.id, s.session_id, s.start_message_id, s.end_message_id, s.message_count, s.content
        FROM memory_segments s
        LEFT JOIN memory_vectors v ON v.segment_id = s.id
        WHERE v.segment_id IS NULL
        ORDER BY s.id ASC
    """
    params = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (int(limit),)
    rows = conn.execute(sql, params).fetchall()
    return [row_to_dict(row) for row in rows]


def retrieve_similar_segments(
    conn: sqlite3.Connection,
    query_vector: np.ndarray,
    limit: int = DEFAULT_TOP_K,
    current_session_id: Optional[str] = None,
    current_user_message: str = "",
) -> List[Dict[str, object]]:
    query = normalize_vector(query_vector)
    rows = conn.execute(
        """
        SELECT s.id, s.session_id, s.content, s.message_count, s.start_message_id, s.end_message_id,
               v.dim, v.vector, v.model_name
        FROM memory_segments s
        JOIN memory_vectors v ON v.segment_id = s.id
        ORDER BY s.id ASC
        """
    ).fetchall()
    if not rows:
        return []

    scored: List[Dict[str, object]] = []
    for row in rows:
        if current_session_id and str(row["session_id"]) == str(current_session_id):
            continue
        if segment_contains_exact_user_message(str(row["content"]), current_user_message):
            continue
        dim = int(row["dim"])
        vector = blob_to_vector(row["vector"], dim)
        if vector.shape != query.shape:
            continue
        score = float(np.dot(vector, query))
        item = row_to_dict(row)
        item.pop("vector", None)
        item["score"] = score
        scored.append(item)

    scored.sort(key=lambda item: (-float(item["score"]), int(item["id"])))
    return scored[:limit]


def dedupe_similar_memory_vectors(
    conn: sqlite3.Connection,
    threshold: float = DEFAULT_DEDUPE_THRESHOLD,
) -> Dict[str, object]:
    init_vector_memory_tables(conn)
    rows = conn.execute(
        """
        SELECT s.id, s.content_hash, v.dim, v.vector
        FROM memory_segments s
        JOIN memory_vectors v ON v.segment_id = s.id
        ORDER BY s.id ASC
        """
    ).fetchall()

    delete_plan: Dict[int, Dict[str, object]] = {}
    for i, old_row in enumerate(rows):
        old_id = int(old_row["id"])
        old_dim = int(old_row["dim"])
        old_vector = blob_to_vector(old_row["vector"], old_dim)
        for new_row in rows[i + 1 :]:
            new_dim = int(new_row["dim"])
            if new_dim != old_dim:
                continue
            new_vector = blob_to_vector(new_row["vector"], new_dim)
            score = float(np.dot(normalize_vector(old_vector), normalize_vector(new_vector)))
            if score <= threshold:
                continue
            previous = delete_plan.get(old_id)
            if previous is None or int(new_row["id"]) > int(previous["duplicate_of_segment_id"]):
                delete_plan[old_id] = {
                    "content_hash": str(old_row["content_hash"]),
                    "duplicate_of_segment_id": int(new_row["id"]),
                    "similarity": score,
                }

    now = utc_now()
    for segment_id, plan in delete_plan.items():
        conn.execute(
            """
            INSERT INTO memory_segment_tombstones (
                content_hash, segment_id, duplicate_of_segment_id,
                similarity, reason, deleted_at
            )
            VALUES (?, ?, ?, ?, 'dedupe_similarity', ?)
            ON CONFLICT(content_hash) DO UPDATE SET
                segment_id = excluded.segment_id,
                duplicate_of_segment_id = excluded.duplicate_of_segment_id,
                similarity = excluded.similarity,
                reason = excluded.reason,
                deleted_at = excluded.deleted_at
            """,
            (
                plan["content_hash"],
                segment_id,
                plan["duplicate_of_segment_id"],
                plan["similarity"],
                now,
            ),
        )
        conn.execute("DELETE FROM memory_vectors WHERE segment_id = ?", (segment_id,))
        conn.execute("DELETE FROM memory_segments WHERE id = ?", (segment_id,))

    return {"checked": len(rows), "deleted": len(delete_plan), "threshold": threshold}


def format_vector_memory_context(segments: List[Dict[str, object]]) -> str:
    if not segments:
        return ""

    lines = [
        "以下是你可参考的向量检索历史记忆片段。",
        "这些片段仅供参考，来自过往聊天，可能不完全相关；只在有帮助时提取事实、偏好或长期设定。",
        "不要复制、复述或延续历史 assistant 回复；不要把历史 assistant 回复当作当前答案模板。",
        "如果当前问题和历史问题相似，也必须基于当前用户输入重新组织回答。",
        "不要泄露或编造任何 session、IP、User-Agent 等身份信息。",
        "",
    ]
    for index, segment in enumerate(segments, start=1):
        score = float(segment.get("score", 0.0))
        lines.append(f"[历史记忆 {index}] score={score:.3f}")
        lines.append(str(segment["content"]).strip())
        lines.append("")
    return "\n".join(lines).strip()


def build_vector_memory_context(
    conn: sqlite3.Connection,
    query_vector: np.ndarray,
    limit: int = DEFAULT_TOP_K,
    min_score: float = 0.1,
    current_session_id: Optional[str] = None,
    current_user_message: str = "",
) -> str:
    segments = [
        segment
        for segment in retrieve_similar_segments(
            conn,
            query_vector,
            limit=limit,
            current_session_id=current_session_id,
            current_user_message=current_user_message,
        )
        if float(segment["score"]) >= min_score
    ]
    return format_vector_memory_context(segments)
