import copy
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from wangcai_app.holidays import HolidayCalendar, SHANGHAI, sync_due, validate_holidays


class HolidayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / 'holidays.sqlite3')
        self.now = datetime(2026, 9, 16, 8, tzinfo=SHANGHAI)
        self.payload = {'year': 2026, 'papers': ['https://www.gov.cn/example.htm'], 'days': [
            {'date': '2026-09-20', 'name': '国庆节', 'isOffDay': False},
            {'date': '2026-09-25', 'name': '中秋节', 'isOffDay': True},
            {'date': '2026-09-26', 'name': '中秋节', 'isOffDay': True},
            {'date': '2026-09-27', 'name': '中秋节', 'isOffDay': True}]}
        self.next_payload = {'year': 2027, 'papers': [], 'days': []}
        self.calls = []
        self.failure = False
        self.calendar = HolidayCalendar(self.connect, self.fetch)
        self.calendar.initialize()

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def fetch(self, year):
        self.calls.append(year)
        if self.failure:
            raise OSError('offline')
        return copy.deepcopy(self.payload if year == 2026 else self.next_payload), 'https://example.test/feed'

    def test_actual_days_and_pending_year(self):
        self.calendar.sync(self.now)
        data = self.calendar.window('2026-09-16')
        days = {day['date']: day for day in data['days']}
        self.assertEqual(days['2026-09-20']['kind'], 'makeup')
        self.assertFalse(days['2026-09-20']['is_off_day'])
        self.assertEqual(days['2026-09-25']['kind'], 'holiday')
        self.assertEqual(days['2026-09-19']['kind'], 'weekend')
        self.assertEqual(data['years'][1]['state'], 'pending')
        pending = self.calendar.window('2027-01-01')['days']
        self.assertTrue(all(day['is_off_day'] is None for day in pending))

    def test_daily_schedule_persists_across_restart(self):
        self.calendar.sync(self.now)
        restored = HolidayCalendar(self.connect, self.fetch)
        self.assertEqual(restored.sync(self.now + timedelta(hours=1)), [])
        self.assertEqual(restored.sync(self.now.replace(day=17, hour=6, minute=14)), [])
        self.assertEqual(len(restored.sync(self.now.replace(day=17, hour=6, minute=15))), 2)
        self.assertEqual(self.calls, [2026, 2027, 2026, 2027])

    def test_failure_keeps_cache_and_retries_after_hour(self):
        self.calendar.sync(self.now)
        original = self.calendar.records()[2026]['payload_json']
        self.failure = True
        retry = self.now + timedelta(days=1)
        self.calendar.sync(retry)
        self.assertEqual(self.calendar.records()[2026]['payload_json'], original)
        self.assertTrue(self.calendar.window('2026-09-16')['days'][4]['stale'])
        self.assertEqual(self.calendar.sync(retry + timedelta(minutes=59)), [])
        self.failure = False
        self.assertEqual(len(self.calendar.sync(retry + timedelta(hours=1))), 2)
        self.assertEqual(self.calendar.records()[2026]['last_error'], '')

    def test_cross_year_notice_wins_and_revisions_replace_old_dates(self):
        self.payload['days'].append({'date': '2026-12-31', 'name': '元旦', 'isOffDay': False})
        self.next_payload = {'year': 2027, 'papers': ['https://www.gov.cn/next.htm'],
                             'days': [{'date': '2026-12-31', 'name': '元旦', 'isOffDay': True}]}
        self.calendar.sync(self.now)
        self.assertEqual(self.calendar.window('2026-12-31')['days'][0]['kind'], 'holiday')
        self.payload['days'][0]['date'] = '2026-09-19'
        self.calendar.sync(self.now, force=True)
        days = self.calendar.window('2026-09-19')['days']
        self.assertEqual(days[0]['kind'], 'makeup')
        self.assertEqual(days[1]['kind'], 'weekend')

    def test_empty_response_cannot_erase_published_calendar(self):
        self.calendar.sync(self.now)
        self.payload['days'] = []
        results = self.calendar.sync(self.now, force=True)
        self.assertFalse(results[0]['ok'])
        self.assertEqual(self.calendar.window('2026-09-20')['days'][0]['kind'], 'makeup')

    def test_validation_rejects_untrusted_and_malformed_sources(self):
        for mutate in [lambda p: p.update(year=2025), lambda p: p.update(papers=[]),
                       lambda p: p.update(papers=['https://gov.cn.evil.test/a']),
                       lambda p: p['days'][0].update(isOffDay='false'),
                       lambda p: p['days'][0].update(date='2026-02-30'),
                       lambda p: p['days'].append(p['days'][0])]:
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.assertRaises(ValueError):
                validate_holidays(payload, 2026)

    def test_missing_table_and_interrupted_first_attempt(self):
        with self.connect() as conn:
            conn.execute('DROP TABLE holiday_year_cache')
        self.assertEqual(self.calendar.window('2026-09-16')['years'][0]['state'], 'unavailable')
        row = {'last_attempt_at': self.now.isoformat(), 'last_success_at': '', 'last_error': ''}
        self.assertFalse(sync_due(row, self.now + timedelta(minutes=20)))
        self.assertTrue(sync_due(row, self.now + timedelta(hours=1)))


if __name__ == '__main__':
    unittest.main()
