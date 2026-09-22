import unittest
from unittest import mock
import test_schedule as base
from wangcai_app.schedule_receipts import align_weekly_updates, saved_reply
from wangcai_app.schedule import calendar_window

class ReceiptTests(unittest.TestCase):
    setUp=base.ScheduleTests.setUp
    tearDown=base.ScheduleTests.tearDown
    create=base.ScheduleTests.create

    def test_actual_reported_bug_updates_weekday_and_memory(self):
        e=self.create(title='算法组组会', date='2026-09-17', repeat='weekly', time='10:00', end_time='11:30', notes='每周四上午固定组会。2026-09-17 当天未参加。')
        decision={'reply':'已改周三', 'operations':[{'action':'update','id':e['id'],'revision':e['revision'],'event':{'time':'15:00','end_time':'17:00'}}]}
        with mock.patch.dict(self.ns, {'schedule_agent_decision':lambda _:decision,'schedule_today':lambda:'2026-09-22'}):
            result=self.app.manage_schedule_message('schedule-a','每周的算法组组会又改回周三3~5点了，调整一下日程','regression-weekday')
        saved=self.store.list('schedule-a')[0]
        self.assertEqual(saved['date'],'2026-09-23')
        self.assertIn('每周三',result['reply']);self.assertIn('15:00–17:00',result['reply'])
        self.assertNotIn('每周四',saved['notes']);self.assertIn('2026-09-17 当天未参加',saved['notes'])
        self.assertEqual([x['date'] for x in calendar_window([saved],'2026-09-22')['items']],['2026-09-23','2026-09-30'])
        with self.app.connect_db() as c:
            text=c.execute('SELECT content FROM curated_memories WHERE id=(SELECT memory_id FROM schedule_memory_links WHERE event_id=?)',(saved['id'],)).fetchone()[0]
        self.assertIn('2026-09-23',text);self.assertNotIn('每周四',text)

    def test_receipt_uses_saved_fields_not_model_claim(self):
        e=self.create(title='算法组组会',date='2026-09-17',repeat='weekly')
        result=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'time':'15:00'}}],'fact-receipt','改时间','已改周三')
        self.assertIn('每周四',result['reply']);self.assertNotIn('周三',result['reply'])
        self.assertIn('没有保存',saved_reply([], '已调整好日程'))

    def test_context_has_direct_verified_receipt(self):
        e=self.create(title='算法组组会',date='2026-09-17',repeat='weekly')
        result=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'time':'15:00'}}],'direct-receipt','改时间','随便说成功')
        with mock.patch.dict(self.ns, {'manage_schedule_message':lambda *a,**k:result}):
            context=self.app.schedule_context_for_chat('schedule-a','修改组会','context-call',[],lambda:False)
        self.assertEqual(context.reply,result['reply']);self.assertIn('current_request_id',context)

    def test_only_explicit_single_series_target_is_aligned(self):
        e={'id':'x','repeat':'weekly','date':'2026-09-17','notes':''}
        ops=[{'action':'update','id':'x','event':{'time':'15:00'}}]
        self.assertEqual(align_weekly_updates(ops,[e],'周三组会吗？','2026-09-22'),ops)
        with self.assertRaises(ValueError):
            align_weekly_updates(ops,[e],'只这次改到周三','2026-09-22')
