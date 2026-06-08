#!/usr/bin/env python3
import argparse
import sqlite3
from pathlib import Path
from typing import Optional

import embedding_client
import vector_memory


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = APP_DIR / "data" / "chat_history.sqlite3"


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def rebuild(
    db_path: Path = DEFAULT_DB_PATH,
    window_size: int = vector_memory.DEFAULT_WINDOW_SIZE,
    stride: int = vector_memory.DEFAULT_STRIDE,
    batch_size: int = 8,
    limit: Optional[int] = None,
    dedupe_threshold: float = vector_memory.DEFAULT_DEDUPE_THRESHOLD,
) -> dict:
    with connect_db(db_path) as conn:
        vector_memory.init_vector_memory_tables(conn)
        segments = vector_memory.rebuild_memory_segments(conn, window_size=window_size, stride=stride)
        embedded = 0

        while True:
            missing = vector_memory.get_segments_missing_vectors(conn, limit=batch_size)
            if limit is not None:
                remaining = limit - embedded
                if remaining <= 0:
                    break
                missing = missing[:remaining]
            if not missing:
                break

            vectors = embedding_client.embed_texts([str(item["content"]) for item in missing])
            for item, vector in zip(missing, vectors):
                vector_memory.upsert_memory_vector(
                    conn,
                    segment_id=int(item["id"]),
                    vector=vector,
                    model_name=embedding_client.EMBEDDING_MODEL,
                )
                embedded += 1
            conn.commit()
            print(f"embedded={embedded}", flush=True)

        dedupe = vector_memory.dedupe_similar_memory_vectors(conn, threshold=dedupe_threshold)
        total_segments = conn.execute("SELECT count(*) FROM memory_segments").fetchone()[0]
        total_vectors = conn.execute("SELECT count(*) FROM memory_vectors").fetchone()[0]
        return {
            "segments_created_or_updated": segments,
            "embedded": embedded,
            "deduped": dedupe["deleted"],
            "total_segments": total_segments,
            "total_vectors": total_vectors,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild qwen_web embedding vector memory.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--window-size", type=int, default=vector_memory.DEFAULT_WINDOW_SIZE)
    parser.add_argument("--stride", type=int, default=vector_memory.DEFAULT_STRIDE)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dedupe-threshold", type=float, default=vector_memory.DEFAULT_DEDUPE_THRESHOLD)
    args = parser.parse_args()

    result = rebuild(
        db_path=Path(args.db),
        window_size=args.window_size,
        stride=args.stride,
        batch_size=args.batch_size,
        limit=args.limit,
        dedupe_threshold=args.dedupe_threshold,
    )
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
