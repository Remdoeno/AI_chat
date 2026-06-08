import hashlib
import os
import sqlite3
import time
from pathlib import Path

import app
import embedding_client
import vector_memory

DB = Path('data/chat_history.sqlite3')
LIMIT = int(os.environ.get('QWEN_INSPECT_LIMIT', '5'))
REPEAT = int(os.environ.get('QWEN_INSPECT_REPEAT', '1'))

def compact(text, n=900):
    text = text.strip()
    if len(text) <= n:
        return text
    return text[:n] + '\n...[truncated]'

with sqlite3.connect(DB) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, session_id, content, created_at
        FROM messages
        WHERE role = 'user' AND status = 'completed' AND length(trim(content)) > 0
        ORDER BY id DESC
        LIMIT ?
        """,
        (LIMIT,),
    ).fetchall()

print('recent_user_messages', len(rows), 'repeat=', REPEAT)
for repeat_index in range(1, REPEAT + 1):
    print('\n' + '#' * 100)
    print('repeat', repeat_index)
    for row in rows:
        user_message = row['content'].strip()
        session_id = row['session_id']
        print('\n' + '=' * 100)
        print('message_id=', row['id'], 'session=', session_id[:8], 'created_at=', row['created_at'])
        print('user=', repr(user_message[:160]))

        t0 = time.perf_counter()
        qv = embedding_client.embed_text(user_message)
        t1 = time.perf_counter()
        with app.connect_db() as conn:
            segments = [
                seg for seg in vector_memory.retrieve_similar_segments(
                    conn,
                    query_vector=qv,
                    limit=10,
                    current_session_id=session_id,
                    current_user_message=user_message,
                )
                if float(seg['score']) >= 0.2
            ]
        t2 = time.perf_counter()
        limited_segments = segments[:app.MEMORY_COMPRESS_SEGMENT_LIMIT]
        summary = app.compress_memory_segments(user_message, limited_segments) if limited_segments else ''
        t3 = time.perf_counter()
        memory_context = app.format_compressed_memory_context(summary) if summary else ''

        print(
            'segments=',
            len(segments),
            'compressed_segments=',
            len(limited_segments),
            'scores=',
            [round(float(s['score']), 3) for s in segments[:5]],
        )
        print('timing_ms=', {
            'embedding': round((t1 - t0) * 1000, 1),
            'retrieval': round((t2 - t1) * 1000, 1),
            'compressor': round((t3 - t2) * 1000, 1),
            'total_memory': round((t3 - t0) * 1000, 1),
        })
        print('summary_hash=', hashlib.sha256(summary.encode()).hexdigest()[:12], 'summary_chars=', len(summary))
        print('memory_prompt_preview:')
        print(compact(memory_context))
