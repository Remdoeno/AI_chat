"""Transactional projection of calendar entries into the user's long-term memory."""
import hashlib
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def memory_projection(event, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    event_date = event["date"]
    repeat = event.get("repeat", "none")
    when = event_date or "日期待定"
    if repeat == "weekly":
        anchor = date.fromisoformat(event_date)
        weekday = "一二三四五六日"[anchor.weekday()]
        when = f"每周{weekday}（自{event_date}起）"
        delta = (date.fromisoformat(today) - anchor).days
        event_date = (anchor + timedelta(days=max(0, (delta + 6) // 7) * 7)).isoformat()
    clock = event["time"] or "时间待定"
    if event["end_time"]:
        clock += "–" + event["end_time"]
    if event["end_date"] and event["end_date"] != event["date"]:
        when += "至" + event["end_date"]
    status = {"tentative": "待确认", "confirmed": "已确定", "cancelled": "已取消"}[event["status"]]
    text = f"用户日程【{status}】：{event['title']}；{when} {clock}（北京时间）。"
    if event["location"]:
        text += f"地点：{event['location']}。"
    if event["notes"]:
        text += f"备注：{event['notes']}"
    if event.get("kind") == "project":
        stages = event.get("milestones", [])
        text += f" 长期事项进度：{sum(stage['done'] for stage in stages)}/{len(stages)}阶段完成。"
        for stage in stages:
            if stage.get("track"):
                text += f" 子任务路线【{stage['track']}】。"
            text += f" 阶段【{'已完成' if stage['done'] else '未完成'}】{stage['title']}；DDL：{stage['date'] or '待定'} {stage['time']}。"
            if stage.get('start_date'):
                text += f"执行区间：{stage['start_date']}至{stage['date']}。"
            if stage.get('tentative'):
                text += '日期为待定窗口，尚未最终确定。'
            if stage.get('important'):
                text += '这是重要节点。'
            if stage['notes']:
                text += f"阶段备注：{stage['notes']}。"
    active = event["status"] != "cancelled"
    start = f"{event_date}T{event['time'] or '00:00'}:00+08:00" if event_date and active else None
    end_date = event_date if repeat == "weekly" else event["end_date"] or event_date
    end = f"{end_date}T{event['end_time'] or event['time'] or '23:59'}:00+08:00" if end_date and active else None
    return {"content": text, "label": "event" if active else "diary", "start": start, "end": end,
            "kind": "range" if end and end != start else "point"}


class ScheduleMemoryBridge:
    def __init__(self, cache_key=None):
        self.cache_key = cache_key

    def initialize(self, conn):
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS schedule_memory_links (
                event_id TEXT PRIMARY KEY, memory_id INTEGER NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS schedule_memory_index_queue (
                memory_id INTEGER PRIMARY KEY, content TEXT NOT NULL, updated_at TEXT NOT NULL);
        """)

    def apply(self, conn, owner, changes):
        devices = [row[0] for row in conn.execute(
            "SELECT device_id FROM shared_user_bindings WHERE shared_user_id=? ORDER BY is_host DESC,updated_at DESC", (owner,))]
        if not devices:
            raise ValueError("用户未绑定，无法同步日程记忆")
        now = datetime.now(timezone.utc).isoformat()
        for change in changes:
            event = change["event"]
            link = conn.execute("SELECT memory_id FROM schedule_memory_links WHERE event_id=?", (event["id"],)).fetchone()
            memory_id = link[0] if link else None
            if memory_id:
                row = conn.execute("SELECT visitor_ip,content FROM curated_memories WHERE id=?", (memory_id,)).fetchone()
                if row and row["visitor_ip"] not in devices:
                    raise ValueError("关联记忆不属于当前用户")
                if not row:
                    conn.execute("DELETE FROM schedule_memory_links WHERE event_id=?", (event["id"],))
                    memory_id = None
            if change["action"] == "delete":
                if memory_id:
                    conn.execute("DELETE FROM curated_memory_vectors WHERE memory_id=?", (memory_id,))
                    conn.execute("DELETE FROM schedule_memory_index_queue WHERE memory_id=?", (memory_id,))
                    conn.execute("DELETE FROM schedule_memory_links WHERE event_id=?", (event["id"],))
                    conn.execute("DELETE FROM curated_memories WHERE id=?", (memory_id,))
                continue
            projection = memory_projection(event)
            digest = hashlib.sha256((owner + ":schedule:" + event["id"]).encode()).hexdigest()
            values = (projection["content"], projection["label"], projection["start"], projection["start"], projection["end"], projection["kind"], now)
            if memory_id:
                conn.execute("""UPDATE curated_memories SET content=?,importance_label=?,timeline_at=?,timeline_start_at=?,timeline_end_at=?,timeline_kind=?,updated_at=?,
                    source_session_id=?,source_hash=?,refine_status='schedule_managed' WHERE id=?""", (*values, "schedule-" + event["id"], digest, memory_id))
            else:
                cursor = conn.execute("""INSERT INTO curated_memories
                    (content,importance_label,timeline_at,timeline_start_at,timeline_end_at,timeline_kind,updated_at,
                     source_session_id,start_message_id,end_message_id,source_hash,visitor_ip,created_at,confidence,refine_status)
                    VALUES (?,?,?,?,?,?,?,?,0,0,?,?,?,1.0,'schedule_managed')""",
                    (*values, "schedule-" + event["id"], digest, devices[0], now))
                memory_id = cursor.lastrowid
                conn.execute("INSERT INTO schedule_memory_links VALUES (?,?)", (event["id"], memory_id))
            # Never leave an old text embedding attached to newly edited facts.
            conn.execute("DELETE FROM curated_memory_vectors WHERE memory_id=?", (memory_id,))
            conn.execute("INSERT INTO schedule_memory_index_queue VALUES (?,?,?) ON CONFLICT(memory_id) DO UPDATE SET content=excluded.content,updated_at=excluded.updated_at",
                         (memory_id, projection["content"], now))
        if self.cache_key:
            for device in devices:
                conn.execute("DELETE FROM app_settings WHERE key=?", (self.cache_key(device),))
