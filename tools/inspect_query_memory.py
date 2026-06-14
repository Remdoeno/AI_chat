import hashlib
import sys

import app
import embedding_client
import vector_memory


query = sys.argv[1] if len(sys.argv) > 1 else "abc"
session_id = app.create_session("debug", "memory-debug")
prompt = app.build_system_prompt(session_id, query, "debug")
print("query", repr(query))
print(
    "prompt_len",
    len(prompt),
    "hash",
    hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12],
    "has_history",
    "历史记忆" in prompt,
)
print("prompt_preview")
print(prompt[:2500].replace("\n", "\\n"))

query_vector = embedding_client.embed_text(query)
with app.connect_db() as conn:
    rows = vector_memory.retrieve_similar_segments(conn, query_vector, limit=10)

for index, row in enumerate(rows, 1):
    content = str(row["content"])
    print()
    print(
        "SEG",
        index,
        "id",
        row["id"],
        "score",
        round(float(row["score"]), 4),
        "hash",
        hashlib.sha256(content.encode("utf-8")).hexdigest()[:12],
    )
    print(content.replace("\n", " ")[:700])
