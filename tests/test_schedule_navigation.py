"""Remote-only isolated calendar-window regression checks."""
import unittest
from unittest import mock
import test_schedule as base

class NavigationTests(unittest.TestCase):
    setUp = base.ScheduleTests.setUp
    tearDown = base.ScheduleTests.tearDown
    create = base.ScheduleTests.create

    def request(self, start=None, device=None):
        return self.client.get('/api/schedule', params={} if start is None else {'start': start},
                               headers={'X-Wangcai-Device-Id': device or self.device_a})

    def test_window_uses_requested_dates_and_owner(self):
        self.create(title='老事项', date='2026-08-01')
        self.create(title='新事项', date='2026-10-15', end_date='2026-10-18')
        self.create(owner='schedule-b', title='别人的事项', date='2026-10-15')
        old=self.request('2026-08-01').json()
        future=self.request('2026-10-10').json()
        self.assertEqual([e['title'] for e in old['items']], ['老事项'])
        self.assertEqual([e['title'] for e in future['items']], ['新事项'])
        self.assertEqual(future['end'], '2026-10-23')
        self.assertEqual(future['actual_today'], self.app.schedule_today())
        self.assertEqual(future['holidays']['days'][0]['date'], '2026-10-10')

    def test_weekly_instances_expand_per_requested_window(self):
        self.create(title='周三组会', date='2026-09-02', repeat='weekly')
        result=self.request('2026-10-01').json()
        self.assertEqual([e['date'] for e in result['items']], ['2026-10-07', '2026-10-14'])
        self.assertFalse(self.request('2026-08-01').json()['items'])

    def test_bad_dates_rejected_and_binding_required(self):
        for value in ['oops','2026-02-30','20260921','9999-12-31']:
            self.assertEqual(self.request(value).status_code,422,value)
        self.assertEqual(self.request('2026-10-01','unbound-navigation-user').status_code,409)

    def test_default_window_and_scene_categories(self):
        data=self.request().json()
        self.assertEqual(data['today'],data['actual_today'])
        ids={x['id'] for x in data['categories']}
        self.assertTrue({'work','entertainment','health','growth','social','life'} <= ids)
        for category in ['work','entertainment','health','growth','social','life']:
            self.assertEqual(self.create(title=category,category=category)['category'],category)
