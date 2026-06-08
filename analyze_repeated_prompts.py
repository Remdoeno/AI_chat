import collections
import hashlib
import sqlite3


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


conn = sqlite3.connect("data/chat_history.sqlite3")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT id, session_id, role, content, created_at
    FROM messages
    WHERE status = 'completed' AND role IN ('user', 'assistant')
    ORDER BY id ASC
    """
).fetchall()

by_session = collections.defaultdict(list)
for row in rows:
    by_session[row["session_id"]].append(row)

pairs = []
for session_id, messages in by_session.items():
    for index, row in enumerate(messages[:-1]):
        next_row = messages[index + 1]
        if row["role"] == "user" and next_row["role"] == "assistant":
            pairs.append(
                (
                    session_id,
                    int(row["id"]),
                    row["content"].strip(),
                    next_row["content"].strip(),
                    int(next_row["id"]),
                )
            )

by_prompt = collections.defaultdict(list)
for pair in pairs:
    by_prompt[pair[2]].append(pair)

print("repeated_prompts")
for prompt, prompt_pairs in sorted(by_prompt.items(), key=lambda item: len(item[1]), reverse=True)[:30]:
    if len(prompt_pairs) < 2:
        continue
    answers = [pair[3] for pair in prompt_pairs]
    print()
    print(
        "PROMPT",
        repr(prompt[:120]),
        "count",
        len(prompt_pairs),
        "unique_answers",
        len(set(answers)),
        "answer_hashes",
        [short_hash(answer) for answer in answers[:12]],
    )
    for session_id, user_id, _prompt, answer, assistant_id in prompt_pairs[-8:]:
        print(
            " ",
            user_id,
            "->",
            assistant_id,
            "sid",
            session_id[:8],
            short_hash(answer),
            answer.replace("\n", " ")[:220],
        )

