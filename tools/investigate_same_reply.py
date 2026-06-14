import hashlib

import httpx
from openai import OpenAI

import app
import embedding_client
import vector_memory


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def compact(text: str, limit: int = 260) -> str:
    return text.replace("\n", " ")[:limit]


def call_model(client, messages, temperature, top_p, label):
    print(f"\n{label}")
    outputs = []
    for index in range(3):
        resp = client.chat.completions.create(
            model=app.MODEL_NAME,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=96,
            extra_body=app.build_extra_body(),
        )
        text = (resp.choices[0].message.content or "").strip()
        outputs.append(text)
        print(index, digest(text), compact(text))
    print("unique_outputs", len(set(outputs)))


def main():
    query = "你是什么模型"
    client = OpenAI(
        api_key="EMPTY",
        base_url=app.BASE_URL,
        http_client=httpx.Client(trust_env=False, timeout=1200),
    )

    base_messages = [
        {"role": "system", "content": app.SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    print("query", query)
    print("system_prompt", app.SYSTEM_PROMPT)
    print("frontend_effective_temperature", 0.6)
    print("frontend_effective_top_p", 0.95)
    print("backend_default_temperature", app.ChatPayload.model_fields["temperature"].default)
    print("backend_default_top_p", app.ChatPayload.model_fields["top_p"].default)

    call_model(client, base_messages, 0.6, 0.95, "DIRECT_MODEL_NO_MEMORY_TEMP_0_6")
    call_model(client, base_messages, 1.2, 0.95, "DIRECT_MODEL_NO_MEMORY_TEMP_1_2")

    session = app.create_session("debug", "same-reply-debug")
    prompt = app.build_system_prompt(session, query, "debug")
    print("\nAPP_MEMORY_PROMPT")
    print("prompt_len", len(prompt))
    print("prompt_hash", digest(prompt))
    print("has_memory", "历史记忆" in prompt)
    print("preview", prompt[:1400].replace("\n", "\\n"))

    qv = embedding_client.embed_text(query)
    with app.connect_db() as conn:
        results = vector_memory.retrieve_similar_segments(conn, qv, limit=10)
    print("\nTOP_MEMORY_SEGMENTS")
    for row in results[:10]:
        content = str(row["content"])
        print(
            {
                "id": row["id"],
                "score": round(float(row["score"]), 4),
                "message_count": row["message_count"],
                "hash": digest(content),
                "preview": compact(content),
            }
        )

    memory_messages = [{"role": "system", "content": prompt}, {"role": "user", "content": query}]
    call_model(client, memory_messages, 0.6, 0.95, "DIRECT_MODEL_WITH_APP_MEMORY_TEMP_0_6")


if __name__ == "__main__":
    main()
