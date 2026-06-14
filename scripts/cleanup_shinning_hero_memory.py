import json
import pathlib
import sys


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app


HERO_SEED_MEMORY_ID = 230
HERO_SEED_CONTENT = (
    "作品计划：可以不定期连载《闪光超人城市档案》。"
    "闪光超人的英文名固定为 Shinning Hero，禁止使用任何其他英文误译；"
    "他的招牌大招是动感光波，战斗时应经常使用。"
    "主要人物包括 Shinning Hero、BenMan、绿手侠、Mr.H、Cora、Discoman。"
    "BenMan 是吸收巨龙之力穿越回现代的沉默肌肉男，最初是反派，后来亦敌亦友；"
    "绿手侠右手被生化武器感染成绿色，可发射辐射物质，力量和速度很强；"
    "Mr.H 是头盔科技达人，Cora 是机器人助手；"
    "Discoman 使用光碟和巨大音响。这个系列可在空闲时偶尔续写，不要强制每次都写。"
)


def clean(value):
    return app.normalize_hero_terms(value or "")


def main():
    app.init_db()
    artifact_ids = set()
    memory_ids = set()

    with app.connect_db() as conn:
        artifacts = conn.execute(
            """
            SELECT id, title, content, series_title, summary
            FROM idle_agent_artifacts
            """
        ).fetchall()
        for row in artifacts:
            title = clean(row["title"])
            content = clean(row["content"])
            series_title = clean(row["series_title"])
            summary = clean(row["summary"])
            if (
                title != (row["title"] or "")
                or content != (row["content"] or "")
                or series_title != (row["series_title"] or "")
                or summary != (row["summary"] or "")
            ):
                conn.execute(
                    """
                    UPDATE idle_agent_artifacts
                    SET title = ?, content = ?, series_title = ?, summary = ?
                    WHERE id = ?
                    """,
                    (
                        title,
                        content,
                        series_title or None,
                        summary or None,
                        int(row["id"]),
                    ),
                )
                artifact_ids.add(int(row["id"]))

        memories = conn.execute("SELECT id, content FROM curated_memories").fetchall()
        for row in memories:
            content = clean(row["content"])
            if content != (row["content"] or ""):
                conn.execute(
                    """
                    UPDATE curated_memories
                    SET content = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (content, app.utc_now(), int(row["id"])),
                )
                memory_ids.add(int(row["id"]))

        seed = conn.execute(
            "SELECT id, content FROM curated_memories WHERE id = ?",
            (HERO_SEED_MEMORY_ID,),
        ).fetchone()
        if seed is not None and seed["content"] != HERO_SEED_CONTENT:
            conn.execute(
                """
                UPDATE curated_memories
                SET content = ?, importance_label = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    HERO_SEED_CONTENT,
                    "artifact",
                    app.utc_now(),
                    HERO_SEED_MEMORY_ID,
                ),
            )
            memory_ids.add(HERO_SEED_MEMORY_ID)

    artifact_reindexed = 0
    for artifact_id in sorted(artifact_ids):
        app.index_idle_agent_artifact(artifact_id)
        artifact_reindexed += 1

    memory_reindexed = 0
    for memory_id in sorted(memory_ids):
        with app.connect_db() as conn:
            row = conn.execute(
                "SELECT content FROM curated_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        if row is None:
            continue
        vector = app.embedding_client.embed_text(row["content"])
        app.upsert_curated_memory_vector(
            memory_id,
            vector,
            app.embedding_client.EMBEDDING_MODEL,
        )
        memory_reindexed += 1

    with app.connect_db() as conn:
        remaining_memories = conn.execute(
            """
            SELECT COUNT(*) AS c FROM curated_memories
            WHERE content LIKE '%Flash Superman%' OR content LIKE '%Falsh Superman%'
            """
        ).fetchone()["c"]
        remaining_artifacts = conn.execute(
            """
            SELECT COUNT(*) AS c FROM idle_agent_artifacts
            WHERE title LIKE '%Flash Superman%'
               OR content LIKE '%Flash Superman%'
               OR series_title LIKE '%Flash Superman%'
               OR summary LIKE '%Flash Superman%'
               OR title LIKE '%Falsh Superman%'
               OR content LIKE '%Falsh Superman%'
               OR series_title LIKE '%Falsh Superman%'
               OR summary LIKE '%Falsh Superman%'
            """
        ).fetchone()["c"]
        remaining_vectors = conn.execute(
            """
            SELECT COUNT(*) AS c FROM idle_artifact_vectors
            WHERE index_text LIKE '%Flash Superman%' OR index_text LIKE '%Falsh Superman%'
            """
        ).fetchone()["c"]

    print(
        json.dumps(
            {
                "artifact_rows_cleaned": len(artifact_ids),
                "artifact_vectors_reindexed": artifact_reindexed,
                "memory_rows_cleaned": len(memory_ids),
                "memory_vectors_reindexed": memory_reindexed,
                "remaining": {
                    "curated_memories": remaining_memories,
                    "idle_agent_artifacts": remaining_artifacts,
                    "idle_artifact_vectors": remaining_vectors,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
