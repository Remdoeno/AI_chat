"""Run remotely: progress persistence, validation, ownership and memory projection."""
import unittest
from unittest import mock
import test_schedule as base
from wangcai_app.schedule import normalize_event, calendar_window


class ProgressTests(unittest.TestCase):
    setUp = base.ScheduleTests.setUp
    tearDown = base.ScheduleTests.tearDown
    create = base.ScheduleTests.create

    def project(self):
        return self.create(title='旅行', kind='project', category='travel', date='2026-09-01', end_date='2026-10-10',
                           milestones=[{'title':'买票','date':'2026-09-25'}, {'title':'出行','date':'2026-10-10'}])

    def test_progress_updates_memory_and_preserves_stages_on_partial_edit(self):
        event = self.project()
        stages = event['milestones']
        stages[0]['done'] = True
        self.store.apply('schedule-a', [{'action':'update','id':event['id'],'revision':1,'event':{'milestones':stages}}], 'done-stage', '买好票了')
        self.store.apply('schedule-a', [{'action':'update','id':event['id'],'revision':2,'event':{'notes':'携带相机'}}], 'note-stage', '备注')
        current = self.store.list('schedule-a')[0]
        self.assertTrue(current['milestones'][0]['done'])
        self.assertEqual(current['milestones'][1]['id'], stages[1]['id'])
        with self.app.connect_db() as c:
            memory = c.execute('SELECT content FROM curated_memories WHERE id=(SELECT memory_id FROM schedule_memory_links WHERE event_id=?)', (event['id'],)).fetchone()[0]
        self.assertIn('1/2阶段完成', memory)
        self.assertIn('2026-09-25', memory)
        self.assertIn('携带相机', memory)

    def test_calendar_range_and_cancel(self):
        event = self.project()
        self.assertEqual(calendar_window([event], '2026-09-21')['items'][0]['milestones'], event['milestones'])
        self.assertEqual(calendar_window([event], '2026-10-11')['items'], [])
        self.assertEqual(calendar_window([{**event,'status':'cancelled'}], '2026-09-21')['items'], [])

    def test_reject_invalid_stage_and_roll_back_entire_edit(self):
        event = self.project()
        for stage in [{'title':'X','date':'2026-12-01'}, {'title':'X','done':'false'}, {'title':'X','time':'10:00'}, {'title':''}]:
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                self.store.apply('schedule-a', [{'action':'update','id':event['id'],'revision':1,'event':{'milestones':[stage]}}], 'invalid-stage', '')
        self.assertEqual(self.store.list('schedule-a')[0]['revision'], 1)

    def test_request_retry_and_cross_user_protection(self):
        event = self.project()
        op={'action':'update','id':event['id'],'revision':1,'event':{'notes':'first'}}
        first=self.store.apply('schedule-a',[op],'stable-id','')
        self.assertEqual(first,self.store.apply('schedule-a',[op],'stable-id',''))
        with self.assertRaises(LookupError):self.store.apply('schedule-b',[op],'wrong-id','')
        with self.assertRaises(ValueError):self.store.apply('schedule-a',[op],'stale-id','')

    def test_old_events_and_draft_stages(self):
        self.assertEqual(normalize_event({'title':'普通'})['milestones'], [])
        draft=normalize_event({'title':'项目','kind':'project','milestones':[{'title':'写初稿'}]})
        self.assertEqual(draft['milestones'][0]['date'],'')
        with self.assertRaises(ValueError):normalize_event({'title':'项目','kind':'project','date':'2026-09-21'})
        with self.assertRaises(ValueError):normalize_event({'title':'项目','kind':'project','repeat':'weekly','date':'2026-09-21','end_date':'2026-09-21'})

    def test_calendar_chat_can_save_project_stages(self):
        decision={'reply':'已保存旅行阶段','operations':[{'action':'create','event':{'title':'旅行','kind':'project','category':'travel','date':'2026-09-21','end_date':'2026-10-01','milestones':[{'title':'买票','date':'2026-09-22'}]}}]}
        with mock.patch.dict(self.ns, {'schedule_agent_decision':lambda context:decision}):
            r=self.client.post('/api/schedule/chat',headers={'X-Wangcai-Device-Id':self.device_a},json={'message':'建一个旅行计划','request_id':'project-chat'})
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['changes'][0]['event']['kind'],'project')
