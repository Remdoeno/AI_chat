"""Transactional member-card projection into the existing memory index queue."""
import hashlib
from datetime import datetime, timezone


def card_memory_text(card):
    status = {"active": "有余额或次数待使用", "issue": "使用问题待处理", "used_up": "已用完"}[card["status"]]
    parts = [f"用户会员卡【{status}】：{card['name']}",
             "余额：" + (card["balance"] + "元" if card["balance"] else card["balance_note"] or "待核实"),
             "剩余次数：" + (card["remaining_uses"] + "次" if card["remaining_uses"] else "待核实"),
             "适用地点：" + (card["location"] or "待补充"), "有效期：" + (card["expires_on"] or "未知"),
             "首页提示：" + ("开启" if card["reminder_enabled"] else "暂停")]
    if card["notes"]:
        parts.append("备注：" + card["notes"])
    return "；".join(parts) + "。余额和次数是用户提供的记录，不代表已向商家实时核验。"


class MembershipMemoryBridge:
    def __init__(self, cache_key=None):
        self.cache_key = cache_key

    def initialize(self, conn):
        conn.executescript("""CREATE TABLE IF NOT EXISTS membership_memory_links (
            card_id TEXT PRIMARY KEY, memory_id INTEGER NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS schedule_memory_index_queue (
                memory_id INTEGER PRIMARY KEY,content TEXT NOT NULL,updated_at TEXT NOT NULL);""")

    def apply(self, conn, owner, changes):
        devices = [row[0] for row in conn.execute("SELECT device_id FROM shared_user_bindings WHERE shared_user_id=? ORDER BY is_host DESC,updated_at DESC", (owner,))]
        if not devices:
            raise ValueError("请先绑定用户，才能保存会员卡和记忆")
        now = datetime.now(timezone.utc).isoformat()
        for change in changes:
            card = change["card"]
            link = conn.execute("SELECT memory_id FROM membership_memory_links WHERE card_id=?", (card["id"],)).fetchone()
            memory_id = link[0] if link else None
            if memory_id:
                row = conn.execute("SELECT visitor_ip FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
                if row and row["visitor_ip"] not in devices:
                    raise ValueError("关联记忆不属于当前用户")
                if not row:
                    conn.execute("DELETE FROM membership_memory_links WHERE card_id=?", (card["id"],))
                    memory_id = None
            if change["action"] == "delete":
                if memory_id:
                    conn.execute("DELETE FROM curated_memory_vectors WHERE memory_id=?", (memory_id,))
                    conn.execute("DELETE FROM schedule_memory_index_queue WHERE memory_id=?", (memory_id,))
                    conn.execute("DELETE FROM curated_memories WHERE id=?", (memory_id,))
                conn.execute("DELETE FROM membership_memory_links WHERE card_id=?", (card["id"],))
                continue
            content = card_memory_text(card)
            digest = hashlib.sha256((owner + ':membership:' + card['id']).encode()).hexdigest()
            if memory_id:
                conn.execute("""UPDATE curated_memories SET content=?,importance_label='other',timeline_at=NULL,
                    timeline_start_at=NULL,timeline_end_at=NULL,timeline_kind='point',updated_at=?,
                    source_session_id=?,source_hash=?,refine_status='membership_managed' WHERE id=?""",
                    (content, now, 'membership-' + card['id'], digest, memory_id))
            else:
                cursor = conn.execute("""INSERT INTO curated_memories
                    (content,importance_label,updated_at,source_session_id,start_message_id,end_message_id,
                     source_hash,visitor_ip,created_at,confidence,refine_status)
                    VALUES (?,'other',?,?,0,0,?,?,?,1.0,'membership_managed')""",
                    (content, now, 'membership-' + card['id'], digest, devices[0], now))
                memory_id = cursor.lastrowid
                conn.execute("INSERT INTO membership_memory_links VALUES (?,?)", (card['id'], memory_id))
            conn.execute("DELETE FROM curated_memory_vectors WHERE memory_id=?", (memory_id,))
            conn.execute("INSERT INTO schedule_memory_index_queue VALUES (?,?,?) ON CONFLICT(memory_id) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at", (memory_id, content, now))
        if self.cache_key:
            for device in devices:
                conn.execute("DELETE FROM app_settings WHERE key=?", (self.cache_key(device),))
