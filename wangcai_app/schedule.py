"""User-owned calendar storage; no dependency on the application namespace or models."""
import json
import uuid
from datetime import date, datetime, timedelta, timezone


CATEGORIES = {
    "meal": ("同学约饭", "#b86d26"), "date": ("约会", "#c4517c"),
    "meeting": ("会议", "#4679c2"), "research": ("组会", "#8660c1"),
    "club": ("社团活动", "#258878"), "interview": ("面试", "#c45d46"),
    "talk": ("宣讲", "#468694"), "course": ("课程", "#9b783a"), "other": ("其他", "#77818e"),
}
FIELDS = {"title", "date", "time", "end_date", "end_time", "category", "status", "location", "notes", "repeat"}


def normalize_event(data):
    if not isinstance(data, dict) or set(data) - FIELDS:
        raise ValueError("日程字段不正确")
    event = {key: data.get(key, "") for key in FIELDS}
    for key in FIELDS:
        if not isinstance(event[key], str):
            raise ValueError("日程字段必须是文字")
        event[key] = event[key].strip()
    if not event["title"] or len(event["title"]) > 120:
        raise ValueError("标题需为 1–120 字")
    if len(event["location"]) > 200 or len(event["notes"]) > 2000:
        raise ValueError("地点或备注过长")
    event["category"] = event["category"] or "other"
    event["status"] = event["status"] or "tentative"
    event["repeat"] = event["repeat"] or "none"
    if event["repeat"] not in {"none", "weekly"}:
        raise ValueError("重复规则只能为不重复或每周")
    if event["category"] not in CATEGORIES or event["status"] not in {"tentative", "confirmed", "cancelled"}:
        raise ValueError("未知的分类或状态")
    for key in ("date", "end_date"):
        if event[key] and date.fromisoformat(event[key]).isoformat() != event[key]:
            raise ValueError("日期格式应为 YYYY-MM-DD")
    for key in ("time", "end_time"):
        if event[key] and datetime.strptime(event[key], "%H:%M").strftime("%H:%M") != event[key]:
            raise ValueError("时间格式应为 HH:MM")
    if not event["date"] and any(event[key] for key in ("time", "end_date", "end_time")):
        raise ValueError("请先确定日期，未定的时间可写在备注里")
    if event["end_time"] and not event["time"]:
        raise ValueError("填写结束时间时也需要开始时间")
    if event["end_date"] and event["end_date"] < event["date"]:
        raise ValueError("结束日期不能早于开始日期")
    if event["end_time"] and (event["end_date"] or event["date"]) == event["date"] and event["end_time"] <= event["time"]:
        raise ValueError("结束时间必须晚于开始时间；跨天事项请填写结束日期")
    if event["repeat"] == "weekly" and (not event["date"] or (event["end_date"] and event["end_date"] != event["date"])):
        raise ValueError("每周事项需要首次日期，且须在同一天结束")
    return event


class ScheduleStore:
    def __init__(self, connect, synchronizer=None):
        self.connect = connect
        self.synchronizer = synchronizer

    def initialize(self):
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS schedule_events (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS schedule_owner ON schedule_events(owner);
                CREATE TABLE IF NOT EXISTS schedule_turns (
                    owner TEXT NOT NULL, request_id TEXT NOT NULL, message TEXT NOT NULL,
                    result TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(owner, request_id));
            """)
            if self.synchronizer:
                self.synchronizer.initialize(conn)

    @staticmethod
    def event(row):
        return {"repeat": "none", **json.loads(row["data"]), "id": row["id"], "revision": row["revision"], "updated_at": row["updated_at"]}

    def list(self, owner):
        with self.connect() as conn:
            return [self.event(row) for row in conn.execute(
                "SELECT * FROM schedule_events WHERE owner=? ORDER BY updated_at DESC", (owner,))]

    def history(self, owner):
        with self.connect() as conn:
            rows = conn.execute("SELECT message,result FROM schedule_turns WHERE owner=? ORDER BY created_at DESC,rowid DESC LIMIT 12", (owner,)).fetchall()
        return [{"user": row["message"], "result": json.loads(row["result"])} for row in reversed(rows)]

    def cached(self, owner, request_id):
        with self.connect() as conn:
            row = conn.execute("SELECT result FROM schedule_turns WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()
            return json.loads(row["result"]) if row else None

    def apply(self, owner, operations, request_id, message, reply="", cancelled=lambda: False):
        if not owner or not request_id:
            raise ValueError("缺少用户或请求标识")
        if not isinstance(operations, list) or len(operations) > 30:
            raise ValueError("一次最多管理 30 条事项")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cached = conn.execute("SELECT result FROM schedule_turns WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()
            if cached:
                return json.loads(cached["result"])
            changed = []
            for operation in operations:
                if not isinstance(operation, dict):
                    raise ValueError("日程操作格式不正确")
                action = operation.get("action")
                if action not in {"create", "update", "delete"}:
                    raise ValueError("未知的日程操作")
                event_id = operation.get("id")
                current = None
                if action != "create":
                    row = conn.execute("SELECT * FROM schedule_events WHERE id=? AND owner=?", (event_id, owner)).fetchone()
                    if not row:
                        raise LookupError("找不到这条日程")
                    current = self.event(row)
                    if operation.get("revision") != current["revision"]:
                        raise ValueError("这条日程刚刚发生变化，请刷新后再试")
                stamp = datetime.now(timezone.utc).isoformat()
                if action == "delete":
                    conn.execute("DELETE FROM schedule_events WHERE id=? AND owner=?", (event_id, owner))
                    changed.append({"action": "delete", "event": current})
                    continue
                patch = operation.get("event", {})
                if not isinstance(patch, dict):
                    raise ValueError("日程内容格式不正确")
                data = normalize_event({**({key: current[key] for key in FIELDS} if current else {}), **patch})
                if current:
                    conn.execute("UPDATE schedule_events SET data=?,revision=revision+1,updated_at=? WHERE id=? AND owner=?",
                                 (json.dumps(data, ensure_ascii=False), stamp, event_id, owner))
                else:
                    # Repeated mention of the same occurrence must not duplicate a calendar card.
                    duplicate = next((self.event(row) for row in conn.execute("SELECT * FROM schedule_events WHERE owner=?", (owner,))
                                      if all(json.loads(row["data"]).get(key) == data[key] for key in ("title", "date", "time"))), None)
                    if duplicate:
                        if all(duplicate.get(key, "none" if key == "repeat" else "") == data[key] for key in FIELDS):
                            continue
                        raise ValueError("已有同名同时间事项，请修改原事项")
                    event_id = uuid.uuid4().hex
                    conn.execute("INSERT INTO schedule_events VALUES (?,?,?,1,?)", (event_id, owner, json.dumps(data, ensure_ascii=False), stamp))
                changed.append({"action": action, "event": {**data, "id": event_id, "revision": current["revision"] + 1 if current else 1, "updated_at": stamp}})
            if cancelled():
                raise ValueError("本次日程操作已停止，未保存")
            if self.synchronizer and changed:
                self.synchronizer.apply(conn, owner, changed)
            result = {"reply": reply, "changes": changed}
            conn.execute("INSERT INTO schedule_turns VALUES (?,?,?,?,?)", (owner, request_id, message, json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
            return result


def calendar_window(events, today):
    end = (date.fromisoformat(today) + timedelta(days=13)).isoformat()
    active = [event for event in events if event["status"] != "cancelled"]
    items = []
    for event in active:
        if event.get("repeat") == "weekly" and event["date"]:
            anchor = date.fromisoformat(event["date"])
            start = date.fromisoformat(today)
            first = anchor + timedelta(days=max(0, ((start - anchor).days + 6) // 7) * 7)
            while first.isoformat() <= end:
                items.append({**event, "series_date": event["date"], "date": first.isoformat(), "end_date": first.isoformat() if event["end_date"] else ""})
                first += timedelta(days=7)
        elif not event["date"] or (event["date"] <= end and (event["end_date"] or event["date"]) >= today):
            items.append(event)
    return {"today": today, "end": end, "timezone": "Asia/Shanghai", "items": items}
