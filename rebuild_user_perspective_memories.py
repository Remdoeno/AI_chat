#!/usr/bin/env python3
import argparse
import json
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import httpx
from openai import OpenAI

import app
import embedding_client
import vector_memory


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "data" / "chat_history.sqlite3"

USER_MEMORY_AUDIT_SYSTEM_PROMPT = (
    "你是长期记忆审计器。你的任务是根据用户原话审计一条已有长期记忆。"
    "只能把用户原话明确表达、明确更正或明确要求的内容保存为记忆。"
    "assistant 的回答、玩笑、推测、补充设定、上一次记忆内容本身都不是证据。"
    "如果用户原话只是提问、问候、让助手猜测、或没有直接陈述事实，应删除该记忆。"
    "如果已有记忆夹杂了 assistant 编出的细节，改写为用户原话能支持的最小事实。"
    "输出 JSON：{\"action\":\"keep|rewrite|delete\","
    "\"memory\":\"用户视角的简短记忆或空字符串\","
    "\"label\":\"preference|identity|rule|persona|risk|other\","
    "\"confidence\":0到1,\"reason\":\"一句话说明\"}。"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_audit_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS curated_memory_user_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            memory_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            old_content TEXT NOT NULL,
            new_content TEXT NOT NULL,
            old_label TEXT NOT NULL,
            new_label TEXT NOT NULL,
            confidence REAL,
            reason TEXT NOT NULL,
            user_source TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


def load_chat_curated_memories(conn: sqlite3.Connection, limit: Optional[int] = None) -> List[sqlite3.Row]:
    sql = """
        SELECT id, source_session_id, start_message_id, end_message_id,
               content, importance_label, confidence
        FROM curated_memories
        WHERE source_session_id NOT LIKE 'admin-%'
          AND source_session_id NOT LIKE 'artifact-%'
        ORDER BY id ASC
    """
    params: List[object] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    return conn.execute(sql, params).fetchall()


def load_user_source_for_memory(conn: sqlite3.Connection, row: sqlite3.Row) -> str:
    rows = conn.execute(
        """
        SELECT id, content
        FROM messages
        WHERE session_id = ?
          AND role = 'user'
          AND status = 'completed'
          AND id BETWEEN ? AND ?
          AND length(trim(content)) > 0
        ORDER BY id ASC
        """,
        (
            str(row["source_session_id"]),
            int(row["start_message_id"]),
            int(row["end_message_id"]),
        ),
    ).fetchall()
    return "\n".join(f"[user #{item['id']}] {str(item['content']).strip()}" for item in rows)


def build_audit_messages(row: sqlite3.Row, user_source: str) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": USER_MEMORY_AUDIT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "已有记忆：\n"
                f"ID: {int(row['id'])}\n"
                f"label: {row['importance_label']}\n"
                f"content: {row['content']}\n\n"
                "用户原话证据：\n"
                f"{user_source or '[无用户原话]'}"
            ),
        },
    ]


def parse_audit_response(text: str) -> Dict[str, object]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        import re

        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    import re

    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if match:
        cleaned = match.group(0)
    payload = json.loads(cleaned)
    action = str(payload.get("action", "")).strip().lower()
    if action not in {"keep", "rewrite", "delete"}:
        action = "delete"
    memory = str(payload.get("memory", "")).strip()
    label = str(payload.get("label", "other")).strip() or "other"
    if label not in {"preference", "identity", "rule", "persona", "risk", "other"}:
        label = "other"
    try:
        confidence = float(payload.get("confidence", 0.7))
    except Exception:
        confidence = 0.7
    return {
        "action": action,
        "memory": memory,
        "label": label,
        "confidence": min(1.0, max(0.0, confidence)),
        "reason": str(payload.get("reason", "")).strip()[:300],
    }


def call_audit_model(row: sqlite3.Row, user_source: str) -> Dict[str, object]:
    if not user_source.strip():
        return {
            "action": "delete",
            "memory": "",
            "label": str(row["importance_label"] or "other"),
            "confidence": 0.0,
            "reason": "no user-source evidence",
        }
    http_client = httpx.Client(trust_env=False, timeout=app.REQUEST_TIMEOUT)
    client = OpenAI(api_key="EMPTY", base_url=app.BASE_URL, http_client=http_client)
    try:
        resp = client.chat.completions.create(
            model=app.MODEL_NAME,
            messages=build_audit_messages(row, user_source),
            temperature=0.05,
            top_p=0.8,
            max_tokens=360,
            extra_body=app.build_extra_body(),
        )
        content = resp.choices[0].message.content or ""
        _, answer = app.split_think_text(content)
        decision = parse_audit_response(answer)
        if decision["action"] != "delete" and not str(decision["memory"]).strip():
            decision["action"] = "delete"
            decision["reason"] = "empty audited memory"
        return decision
    finally:
        http_client.close()


def apply_audit_decision(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    user_source: str,
    decision: Dict[str, object],
    embed_text: Callable[[str], object] = embedding_client.embed_text,
) -> str:
    ensure_audit_log_table(conn)
    action = str(decision.get("action", "delete"))
    old_content = str(row["content"])
    old_label = str(row["importance_label"] or "other")
    new_content = str(decision.get("memory", "")).strip()
    new_label = str(decision.get("label", old_label) or old_label)
    confidence = float(decision.get("confidence", 0.7) or 0.7)
    reason = str(decision.get("reason", ""))
    now = utc_now()
    memory_id = int(row["id"])

    conn.execute(
        """
        INSERT INTO curated_memory_user_audit_log (
            memory_id, action, old_content, new_content, old_label, new_label,
            confidence, reason, user_source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            memory_id,
            action,
            old_content,
            new_content,
            old_label,
            new_label,
            confidence,
            reason,
            user_source,
            now,
        ),
    )

    if action == "delete":
        conn.execute("DELETE FROM curated_memory_vectors WHERE memory_id = ?", (memory_id,))
        conn.execute("DELETE FROM curated_memories WHERE id = ?", (memory_id,))
        return "deleted"

    if action == "keep":
        new_content = old_content
        new_label = old_label

    if new_content != old_content or new_label != old_label:
        conn.execute(
            """
            UPDATE curated_memories
            SET content = ?, importance_label = ?, confidence = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_content, new_label, confidence, now, memory_id),
        )

    vector = embed_text(new_content)
    arr = vector_memory.normalize_vector(vector)
    conn.execute(
        """
        INSERT INTO curated_memory_vectors (memory_id, dim, vector, model_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(memory_id) DO UPDATE SET
            dim = excluded.dim,
            vector = excluded.vector,
            model_name = excluded.model_name,
            created_at = excluded.created_at
        """,
        (memory_id, int(arr.shape[0]), arr.tobytes(), embedding_client.EMBEDDING_MODEL, now),
    )
    return "updated" if action == "rewrite" else "kept"


def reset_and_rebuild_user_segments(
    conn: sqlite3.Connection,
    embed_texts: Callable[[List[str]], List[object]] = embedding_client.embed_texts,
    batch_size: int = 8,
) -> Dict[str, int]:
    vector_memory.init_vector_memory_tables(conn)
    conn.execute("DELETE FROM memory_vectors")
    conn.execute("DELETE FROM memory_segments")
    rebuilt = vector_memory.rebuild_memory_segments(conn)
    embedded = 0
    while True:
        missing = vector_memory.get_segments_missing_vectors(conn, limit=batch_size)
        if not missing:
            break
        vectors = embed_texts([str(item["content"]) for item in missing])
        for item, vector in zip(missing, vectors):
            vector_memory.upsert_memory_vector(
                conn,
                segment_id=int(item["id"]),
                vector=vector,
                model_name=embedding_client.EMBEDDING_MODEL,
            )
            embedded += 1
    return {"segments_rebuilt": int(rebuilt), "vectors_embedded": int(embedded)}


def rebuild_user_perspective_memories(
    db_path: Path = DEFAULT_DB_PATH,
    apply: bool = False,
    backup: bool = False,
    limit: Optional[int] = None,
    auditor: Callable[[sqlite3.Row, str], Dict[str, object]] = call_audit_model,
    embed_text: Callable[[str], object] = embedding_client.embed_text,
    embed_texts: Callable[[List[str]], List[object]] = embedding_client.embed_texts,
) -> Dict[str, int]:
    if apply and backup:
        backup_path = db_path.with_name(
            f"{db_path.stem}.before_user_perspective_rebuild_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}"
        )
        shutil.copy2(db_path, backup_path)
        print(f"backup={backup_path}", flush=True)

    stats = {"checked": 0, "deleted": 0, "rewritten": 0, "kept": 0, "segments_rebuilt": 0, "vectors_embedded": 0}
    with connect_db(db_path) as conn:
        rows = load_chat_curated_memories(conn, limit=limit)
        for row in rows:
            stats["checked"] += 1
            user_source = load_user_source_for_memory(conn, row)
            decision = auditor(row, user_source)
            action = str(decision.get("action", "delete"))
            print(
                json.dumps(
                    {
                        "memory_id": int(row["id"]),
                        "action": action,
                        "old": str(row["content"])[:100],
                        "new": str(decision.get("memory", ""))[:100],
                        "reason": str(decision.get("reason", ""))[:160],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if not apply:
                if action == "delete":
                    stats["deleted"] += 1
                elif action == "rewrite":
                    stats["rewritten"] += 1
                else:
                    stats["kept"] += 1
                continue
            result = apply_audit_decision(conn, row, user_source, decision, embed_text=embed_text)
            if result == "deleted":
                stats["deleted"] += 1
            elif result == "updated":
                stats["rewritten"] += 1
            else:
                stats["kept"] += 1
            conn.commit()
            time.sleep(0.05)

        if apply:
            segment_stats = reset_and_rebuild_user_segments(conn, embed_texts=embed_texts)
            stats.update(segment_stats)
            conn.commit()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit curated memories against user-only source text and rebuild embeddings.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    stats = rebuild_user_perspective_memories(
        db_path=Path(args.db),
        apply=bool(args.apply),
        backup=bool(args.backup),
        limit=args.limit,
    )
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
