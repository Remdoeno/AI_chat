"""Chinese public holiday feed, persistent cache, and date annotations."""
import json
from datetime import date, datetime, timedelta
from urllib.parse import urlparse
import httpx
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
PROVIDER = "https://github.com/NateScarlet/holiday-cn"
FEEDS = (
    "https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json",
    "https://cdn.jsdelivr.net/gh/NateScarlet/holiday-cn@master/{year}.json",
)


def validate_holidays(payload, year):
    if not isinstance(payload, dict) or payload.get("year") != year:
        raise ValueError("holiday year mismatch")
    papers, days = payload.get("papers"), payload.get("days")
    if not isinstance(papers, list) or not isinstance(days, list) or len(days) > 400 or len(papers) > 30:
        raise ValueError("invalid holiday feed")
    for link in papers:
        if not isinstance(link, str):
            raise ValueError("invalid official source")
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not (parsed.hostname == "gov.cn" or (parsed.hostname or "").endswith(".gov.cn")):
            raise ValueError("holiday source is not a government publication")
    if days and not papers:
        raise ValueError("missing official source")
    normalized, seen = [], set()
    for item in days:
        if not isinstance(item, dict) or type(item.get("isOffDay")) is not bool:
            raise ValueError("invalid holiday flag")
        value, name = item.get("date"), item.get("name")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or parsed.year not in {year - 1, year, year + 1} or value in seen:
            raise ValueError("invalid or duplicate holiday date")
        if not isinstance(name, str) or not name.strip() or len(name) > 40:
            raise ValueError("invalid holiday name")
        seen.add(value)
        normalized.append({"date": value, "name": name.strip(), "isOffDay": item["isOffDay"]})
    return {"year": year, "papers": papers, "days": sorted(normalized, key=lambda item: item["date"])}


def fetch_holidays(year, proxy=None):
    last_error = None
    for template in FEEDS:
        url = template.format(year=year)
        try:
            with httpx.Client(proxy=proxy, trust_env=False, timeout=12, follow_redirects=True,
                              headers={"User-Agent": "Wangcai-HolidaySync/2.6.2", "Cache-Control": "no-cache"}) as client:
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 256000:
                            raise ValueError("oversized holiday feed")
            return validate_holidays(json.loads(body), year), url
        except Exception as exc:
            last_error = exc
    raise RuntimeError("holiday sources unavailable: " + type(last_error).__name__)


def sync_due(row, now):
    if not row or not row.get("last_attempt_at"):
        return True
    previous = datetime.fromisoformat(row["last_attempt_at"]).astimezone(SHANGHAI)
    if row.get("last_error") or not row.get("last_success_at"):
        return (now - previous).total_seconds() >= 3600
    scheduled = now.replace(hour=6, minute=15, second=0, microsecond=0)
    return now >= scheduled and previous < scheduled


class HolidayCalendar:
    def __init__(self, connect, fetch=fetch_holidays):
        self.connect, self.fetch = connect, fetch

    def initialize(self):
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS holiday_year_cache (
                year INTEGER PRIMARY KEY, payload_json TEXT NOT NULL DEFAULT '{}',
                source_url TEXT NOT NULL DEFAULT '', last_success_at TEXT NOT NULL DEFAULT '',
                last_attempt_at TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '')""")

    def records(self):
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='holiday_year_cache'").fetchone():
                return {}
            return {row["year"]: dict(row) for row in conn.execute("SELECT * FROM holiday_year_cache")}

    def sync(self, now=None, force=False):
        now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
        records = self.records()
        results = []
        # The next year's notice may also change late December of the current year.
        for year in (now.year, now.year + 1):
            row = records.get(year)
            if not force and not sync_due(row, now):
                continue
            stamp = now.isoformat(timespec="seconds")
            with self.connect() as conn:
                conn.execute("INSERT INTO holiday_year_cache(year,last_attempt_at) VALUES (?,?) ON CONFLICT(year) DO UPDATE SET last_attempt_at=excluded.last_attempt_at", (year, stamp))
            try:
                payload, source = self.fetch(year)
                payload = validate_holidays(payload, year)
                old = json.loads(row["payload_json"]) if row else {}
                if old.get("days") and len(payload["days"]) < len(old["days"]) // 2 + 1:
                    raise ValueError("incomplete replacement holiday feed")
                serialized = json.dumps(payload, ensure_ascii=False)
                with self.connect() as conn:
                    conn.execute("UPDATE holiday_year_cache SET payload_json=?,source_url=?,last_success_at=?,last_error='' WHERE year=?",
                                 (serialized, source, stamp, year))
                results.append({"year": year, "ok": True, "changed": old != payload, "published": bool(payload["papers"] and payload["days"])})
            except Exception as exc:
                with self.connect() as conn:
                    conn.execute("UPDATE holiday_year_cache SET last_error=? WHERE year=?", (type(exc).__name__, year))
                results.append({"year": year, "ok": False, "changed": False})
        return results

    def window(self, today, length=14):
        start = date.fromisoformat(today)
        end = start + timedelta(days=length - 1)
        records = self.records()
        annotations, years, papers = {}, [], []
        for year in range(start.year, end.year + 2):
            row = records.get(year, {})
            payload = json.loads(row.get("payload_json") or "{}")
            published = bool(payload.get("papers") and payload.get("days"))
            state = "published" if published else "pending" if row.get("last_success_at") else "unavailable"
            checked = row.get("last_success_at", "")
            stale = bool(row.get("last_error")) or (bool(checked) and (datetime.now(SHANGHAI) - datetime.fromisoformat(checked)).total_seconds() > 172800)
            years.append({"year": year, "state": state, "stale": stale, "checked_at": checked, "last_attempt_at": row.get("last_attempt_at", "")})
            for paper in payload.get("papers", []):
                if paper not in papers:
                    papers.append(paper)
            for item in payload.get("days", []):
                # A later notice takes precedence for cross-year overlaps.
                annotations[item["date"]] = {"date": item["date"], "name": item["name"],
                    "kind": "holiday" if item["isOffDay"] else "makeup", "is_off_day": item["isOffDay"],
                    "label": "放假" if item["isOffDay"] else "调休补班", "stale": stale}
        days = []
        for offset in range(length):
            current = start + timedelta(days=offset)
            key = current.isoformat()
            if key in annotations:
                days.append(annotations[key])
                continue
            state = next((row for row in years if row["year"] == current.year), {})
            known = state.get("state") == "published"
            weekend = current.weekday() >= 5
            days.append({"date": key, "name": "", "kind": "weekend" if weekend else "workday" if known else "unknown",
                "label": ("周末" if known else "周末·调休待核对") if weekend else "" if known else "安排待发布/收录",
                "is_off_day": weekend if known else None, "stale": state.get("stale", False)})
        return {"days": days, "years": years, "papers": papers, "provider": PROVIDER,
                "sync_schedule": "每天北京时间06:15检查；失败一小时后重试", "scope": "全国放假调休安排；个人课程、单位安排另行确认"}
