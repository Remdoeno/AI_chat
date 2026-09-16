"""Member card facts and passive daily home hints, isolated by bound user."""
import json
import uuid
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

CARD_FIELDS = {"name", "balance", "balance_note", "remaining_uses", "location", "expires_on", "status", "notes", "reminder_enabled"}


def normalize_card(data):
    if not isinstance(data, dict) or set(data) - CARD_FIELDS:
        raise ValueError("会员卡字段不正确")
    card = {key: data.get(key, "") for key in CARD_FIELDS - {"reminder_enabled"}}
    for key, value in card.items():
        if not isinstance(value, str):
            raise ValueError("会员卡内容需为文字；余额不明时留空")
        card[key] = value.strip()
    if not card["name"] or len(card["name"]) > 120:
        raise ValueError("会员卡名称需为1–120字")
    if any(len(card[key]) > limit for key, limit in [("balance_note", 120), ("location", 200), ("notes", 2000)]):
        raise ValueError("会员卡备注过长")
    if card["balance"]:
        try:
            amount = Decimal(card["balance"])
            if not amount.is_finite() or amount < 0 or amount > Decimal("999999999") or amount != amount.quantize(Decimal("0.01")):
                raise ValueError("余额应为非负金额，最多两位小数")
            card["balance"] = format(amount.quantize(Decimal("0.01")), "f")
        except InvalidOperation:
            raise ValueError("余额应为有效金额") from None
    if card["remaining_uses"]:
        if not card["remaining_uses"].isascii() or not card["remaining_uses"].isdigit() or int(card["remaining_uses"]) > 100000:
            raise ValueError("剩余次数应为非负整数")
        card["remaining_uses"] = str(int(card["remaining_uses"]))
    if card["expires_on"] and date.fromisoformat(card["expires_on"]).isoformat() != card["expires_on"]:
        raise ValueError("有效期格式应为YYYY-MM-DD")
    card["status"] = card["status"] or "active"
    if card["status"] not in {"active", "issue", "used_up"}:
        raise ValueError("未知会员卡状态")
    card["reminder_enabled"] = data.get("reminder_enabled", True)
    if type(card["reminder_enabled"]) is not bool:
        raise ValueError("提醒开关必须为布尔值")
    return card


def next_month(today):
    value = date.fromisoformat(today)
    year, month = (value.year + 1, 1) if value.month == 12 else (value.year, value.month + 1)
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1])).isoformat()


def daily_hint(cards, today, preferences):
    if preferences.get("snooze_until", "") > today or preferences.get("dismissed_on") == today:
        return None
    eligible = sorted((card for card in cards if card["status"] != "used_up" and card["reminder_enabled"]), key=lambda c: c["id"])
    if not eligible:
        return None
    # Server-provided Shanghai date keeps selection stable across devices.
    day = (date.fromisoformat(today) - date(2026, 9, 14)).days
    card = eligible[day % len(eligible)]
    balance = (card["balance"] + "元") if card["balance"] else card["balance_note"] or "余额待核实"
    if card["remaining_uses"]:
        balance += " · " + card["remaining_uses"] + "次"
    if card["status"] == "issue":
        text = f"{card['name']}：{balance}。先确认使用问题：{card['notes'] or '适用门店或使用规则待核实'}"
    elif card["expires_on"] and card["expires_on"] < today:
        text = f"{card['name']}：记录的有效期已过，先核实是否仍可用。"
    else:
        text = f"{card['name']}：{balance}。下次有需要时，可以先用这张卡。"
        if card["expires_on"]:
            text += " 记录有效期至" + card["expires_on"] + "。"
    return {"card_id": card["id"], "text": text, "date": today}


class MembershipStore:
    def __init__(self, connect, synchronizer=None):
        self.connect = connect
        self.synchronizer = synchronizer

    def initialize(self):
        with self.connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS membership_cards (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, data TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS membership_owner ON membership_cards(owner);
                CREATE TABLE IF NOT EXISTS membership_turns (
                    owner TEXT NOT NULL, request_id TEXT NOT NULL, message TEXT NOT NULL,
                    result TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(owner, request_id));
            """)
            if self.synchronizer:
                self.synchronizer.initialize(conn)

    @staticmethod
    def card(row):
        return {**json.loads(row["data"]), "id": row["id"], "revision": row["revision"], "updated_at": row["updated_at"]}

    def list(self, owner):
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='membership_cards'").fetchone():
                return []
            return [self.card(row) for row in conn.execute(
                "SELECT * FROM membership_cards WHERE owner=? ORDER BY updated_at DESC", (owner,))]

    def history(self, owner):
        with self.connect() as conn:
            rows = conn.execute("SELECT message,result FROM membership_turns WHERE owner=? ORDER BY created_at DESC,rowid DESC LIMIT 8", (owner,)).fetchall()
        return [{"user": row["message"], "result": json.loads(row["result"])} for row in reversed(rows)]

    def cached(self, owner, request_id):
        with self.connect() as conn:
            row = conn.execute("SELECT result FROM membership_turns WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()
            return json.loads(row["result"]) if row else None

    def apply(self, owner, operations, request_id, message, reply="", cancelled=lambda: False):
        if not owner or not request_id:
            raise ValueError("缺少用户或请求标识")
        if not isinstance(operations, list) or len(operations) > 30:
            raise ValueError("一次最多管理 30 条会员卡")
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cached = conn.execute("SELECT result FROM membership_turns WHERE owner=? AND request_id=?", (owner, request_id)).fetchone()
            if cached:
                return json.loads(cached["result"])
            changed = []
            for operation in operations:
                if not isinstance(operation, dict):
                    raise ValueError("会员卡操作格式不正确")
                action = operation.get("action")
                if action not in {"create", "update", "delete"}:
                    raise ValueError("未知的会员卡操作")
                card_id = operation.get("id")
                current = None
                if action != "create":
                    row = conn.execute("SELECT * FROM membership_cards WHERE id=? AND owner=?", (card_id, owner)).fetchone()
                    if not row:
                        raise LookupError("找不到这条会员卡")
                    current = self.card(row)
                    if operation.get("revision") != current["revision"]:
                        raise ValueError("这条会员卡刚刚发生变化，请刷新后再试")
                stamp = datetime.now(timezone.utc).isoformat()
                if action == "delete":
                    conn.execute("DELETE FROM membership_cards WHERE id=? AND owner=?", (card_id, owner))
                    changed.append({"action": "delete", "card": current})
                    continue
                patch = operation.get("card", {})
                if not isinstance(patch, dict):
                    raise ValueError("会员卡内容格式不正确")
                data = normalize_card({**({key: current[key] for key in CARD_FIELDS} if current else {}), **patch})
                if current:
                    conn.execute("UPDATE membership_cards SET data=?,revision=revision+1,updated_at=? WHERE id=? AND owner=?",
                                 (json.dumps(data, ensure_ascii=False), stamp, card_id, owner))
                else:
                    # Repeated mention of the same card and branch must not duplicate it.
                    duplicate = next((self.card(row) for row in conn.execute("SELECT * FROM membership_cards WHERE owner=?", (owner,))
                                      if all(json.loads(row["data"]).get(key) == data[key] for key in ("name", "location"))), None)
                    if duplicate:
                        if all(duplicate.get(key) == data[key] for key in CARD_FIELDS):
                            continue
                        raise ValueError("已有同名同门店会员卡，请修改原会员卡")
                    card_id = uuid.uuid4().hex
                    conn.execute("INSERT INTO membership_cards VALUES (?,?,?,1,?)", (card_id, owner, json.dumps(data, ensure_ascii=False), stamp))
                changed.append({"action": action, "card": {**data, "id": card_id, "revision": current["revision"] + 1 if current else 1, "updated_at": stamp}})
            if cancelled():
                raise ValueError("本次会员卡操作已停止，未保存")
            if self.synchronizer and changed:
                self.synchronizer.apply(conn, owner, changed)
            result = {"reply": reply, "changes": changed}
            conn.execute("INSERT INTO membership_turns VALUES (?,?,?,?,?)", (owner, request_id, message, json.dumps(result, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
            return result

