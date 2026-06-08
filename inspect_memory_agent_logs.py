import sqlite3
from pathlib import Path

DB = Path('/base/home/lizhzh/Project3/qwen_web/data/chat_history.sqlite3')
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

print('DB =', DB)
print('\n== table counts ==')
for table in ['messages', 'memory_agent_jobs', 'curated_memories', 'curated_memory_vectors', 'events']:
    try:
        row = conn.execute(f'SELECT COUNT(*) AS c FROM {table}').fetchone()
        print(f'{table}:', row['c'])
    except Exception as exc:
        print(f'{table}: ERROR {exc}')

print('\n== memory_agent_jobs by status ==')
for row in conn.execute('SELECT status, COUNT(*) AS c FROM memory_agent_jobs GROUP BY status ORDER BY status'):
    print(dict(row))

print('\n== recent memory_agent_jobs ==')
for row in conn.execute('''
    SELECT id, session_id, start_message_id, end_message_id, status, reason, error, created_at, updated_at
    FROM memory_agent_jobs
    ORDER BY id DESC
    LIMIT 12
'''):
    print(dict(row))

print('\n== recent curated_memories with source turn ==')
rows = conn.execute('''
    SELECT m.id, m.importance_label, m.content, m.source_session_id,
           m.start_message_id, m.end_message_id, m.created_at,
           v.dim, v.model_name,
           u.content AS user_text,
           a.content AS assistant_text
    FROM curated_memories m
    LEFT JOIN curated_memory_vectors v ON v.memory_id = m.id
    LEFT JOIN messages u ON u.id = m.start_message_id
    LEFT JOIN messages a ON a.id = m.end_message_id
    ORDER BY m.id DESC
    LIMIT 10
''').fetchall()
if not rows:
    print('[no curated memories yet]')
for row in rows:
    print('\n-- curated_memory', row['id'], '--')
    print('label:', row['importance_label'], 'created_at:', row['created_at'])
    print('vector:', {'dim': row['dim'], 'model_name': row['model_name']})
    print('memory:', row['content'])
    print('source_user:', (row['user_text'] or '')[:260])
    print('source_assistant:', (row['assistant_text'] or '')[:260])

print('\n== recent memory-agent events ==')
for row in conn.execute('''
    SELECT id, event_type, session_id, created_at, metadata_json
    FROM events
    WHERE event_type LIKE 'memory_agent%'
    ORDER BY id DESC
    LIMIT 12
'''):
    print(dict(row))
