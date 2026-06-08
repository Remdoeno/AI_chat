#!/usr/bin/env python3
import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import vector_memory


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def has_explicit_change(text: str) -> bool:
    markers = ("改为", "更改", "变成", "不再", "以后", "从现在起", "纠正", "不是", "而是")
    return any(marker in (text or "") for marker in markers)


def compatible_scope(a: sqlite3.Row, b: sqlite3.Row) -> bool:
    if str(a["importance_label"]) != str(b["importance_label"]):
        return False
    a_ip = str(a["visitor_ip"] or "")
    b_ip = str(b["visitor_ip"] or "")
    a_profile = a["profile_id"]
    b_profile = b["profile_id"]
    if a_ip or b_ip:
        return a_ip == b_ip or (a_profile is not None and a_profile == b_profile)
    return True


def choose_keep(a: sqlite3.Row, b: sqlite3.Row) -> sqlite3.Row:
    a_conf = float(a["confidence"] if a["confidence"] is not None else 0.7)
    b_conf = float(b["confidence"] if b["confidence"] is not None else 0.7)
    if abs(a_conf - b_conf) >= 0.05:
        return a if a_conf > b_conf else b
    a_time = str(a["updated_at"] or a["created_at"] or "")
    b_time = str(b["updated_at"] or b["created_at"] or "")
    if a_time != b_time:
        return a if a_time > b_time else b
    return a if int(a["id"]) > int(b["id"]) else b


def load_rows(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT m.id, m.content, m.importance_label, m.visitor_ip, m.profile_id,
               m.timeline_at, m.supersedes_id, m.confidence, m.created_at, m.updated_at,
               v.dim, v.vector
        FROM curated_memories m
        JOIN curated_memory_vectors v ON v.memory_id = m.id
        WHERE m.importance_label != 'artifact'
        ORDER BY m.id ASC
        """
    ).fetchall()


def build_delete_plan(rows: List[sqlite3.Row], threshold: float) -> Dict[int, Dict[str, object]]:
    delete_plan: Dict[int, Dict[str, object]] = {}
    for i, left in enumerate(rows):
        if int(left["id"]) in delete_plan:
            continue
        left_vec = vector_memory.normalize_vector(vector_memory.blob_to_vector(left["vector"], int(left["dim"])))
        for right in rows[i + 1 :]:
            if int(right["id"]) in delete_plan:
                continue
            if int(left["dim"]) != int(right["dim"]):
                continue
            if not compatible_scope(left, right):
                continue
            if has_explicit_change(str(left["content"])) or has_explicit_change(str(right["content"])):
                continue
            right_vec = vector_memory.normalize_vector(vector_memory.blob_to_vector(right["vector"], int(right["dim"])))
            score = float(left_vec.dot(right_vec))
            if score < threshold:
                continue
            keep = choose_keep(left, right)
            delete = right if int(keep["id"]) == int(left["id"]) else left
            delete_plan[int(delete["id"])] = {
                "delete_id": int(delete["id"]),
                "keep_id": int(keep["id"]),
                "similarity": score,
                "label": str(delete["importance_label"]),
                "delete_content": str(delete["content"]),
                "keep_content": str(keep["content"]),
            }
            if int(delete["id"]) == int(left["id"]):
                break
    for item in delete_plan.values():
        keep_id = int(item["keep_id"])
        seen = {int(item["delete_id"])}
        while keep_id in delete_plan and keep_id not in seen:
            seen.add(keep_id)
            keep_id = int(delete_plan[keep_id]["keep_id"])
        item["keep_id"] = keep_id
    return delete_plan


def ensure_log_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS curated_memory_dedupe_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deleted_memory_id INTEGER NOT NULL,
            kept_memory_id INTEGER NOT NULL,
            similarity REAL NOT NULL,
            importance_label TEXT NOT NULL,
            deleted_content TEXT NOT NULL,
            kept_content TEXT NOT NULL,
            reason TEXT NOT NULL,
            deleted_at TEXT NOT NULL
        )
        """
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/chat_history.sqlite3")
    parser.add_argument("--threshold", type=float, default=0.88)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--preview", type=int, default=20)
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.apply and args.backup:
        backup_path = db_path.with_name(f"{db_path.stem}.before_curated_dedupe_{datetime.now().strftime('%Y%m%d_%H%M%S')}{db_path.suffix}")
        shutil.copy2(db_path, backup_path)
        print(f"backup={backup_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    rows = load_rows(conn)
    plan = build_delete_plan(rows, float(args.threshold))

    print(json.dumps({
        "checked": len(rows),
        "delete_count": len(plan),
        "threshold": float(args.threshold),
        "apply": bool(args.apply),
    }, ensure_ascii=False))
    for item in list(plan.values())[: max(0, int(args.preview))]:
        print(json.dumps({
            "delete_id": item["delete_id"],
            "keep_id": item["keep_id"],
            "similarity": round(float(item["similarity"]), 4),
            "label": item["label"],
            "delete_content": str(item["delete_content"])[:120],
            "keep_content": str(item["keep_content"])[:120],
        }, ensure_ascii=False))

    if not args.apply:
        conn.close()
        return

    ensure_log_table(conn)
    now = utc_now()
    with conn:
        for item in plan.values():
            conn.execute(
                """
                INSERT INTO curated_memory_dedupe_log (
                    deleted_memory_id, kept_memory_id, similarity, importance_label,
                    deleted_content, kept_content, reason, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'curated_similarity', ?)
                """,
                (
                    int(item["delete_id"]),
                    int(item["keep_id"]),
                    float(item["similarity"]),
                    str(item["label"]),
                    str(item["delete_content"]),
                    str(item["keep_content"]),
                    now,
                ),
            )
            conn.execute("DELETE FROM curated_memory_vectors WHERE memory_id = ?", (int(item["delete_id"]),))
            conn.execute("DELETE FROM curated_memories WHERE id = ?", (int(item["delete_id"]),))
    conn.close()


if __name__ == "__main__":
    main()
