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

    def test_phase_interval_and_uncertain_important_node(self):
        event=self.project()
        stages=[{'title':'改文字','start_date':'2026-09-28','date':'2026-09-30'},
                {'title':'投稿','start_date':'2026-09-30','date':'2026-10-01','important':True,'tentative':True}]
        result=self.store.apply('schedule-a',[{'action':'update','id':event['id'],'revision':1,'event':{'milestones':stages}}],'interval-save','')
        current=result['changes'][0]['event']
        self.assertEqual(current['milestones'][0]['start_date'],'2026-09-28')
        with self.app.connect_db() as c:
            text=c.execute('SELECT content FROM curated_memories WHERE id=(SELECT memory_id FROM schedule_memory_links WHERE event_id=?)',(event['id'],)).fetchone()[0]
        self.assertIn('2026-09-28至2026-09-30',text)
        self.assertIn('待定窗口',text)
        self.assertIn('重要节点',text)
        for stage in [{'title':'错','start_date':'2026-10-03','date':'2026-10-01'}, {'title':'错','start_date':'2026-09-01'}, {'title':'错','date':'2026-09-30','important':'true'}]:
            with self.assertRaises(ValueError):
                normalize_event({'title':'项目','kind':'project','milestones':[stage]})

    def test_split_project_shape_guard(self):
        from wangcai_app.schedule_project_shape import needs_project_repair
        split={'operations':[{'action':'create','event':{'title':t,'kind':'event'}} for t in ['Fire论文投稿','完成Fire论文图片','Fire论文文字调整']]}
        self.assertTrue(needs_project_repair('Fire论文先完成图片，然后改文字，最后投稿',split))
        self.assertFalse(needs_project_repair('明天与论文导师吃饭，然后去朋友生日会',{'operations':[{'action':'create','event':{'title':'吃饭'}},{'action':'create','event':{'title':'生日会'}}]}))
        self.assertFalse(needs_project_repair('项目分三个阶段',{'operations':[{'action':'create','event':{'kind':'project','milestones':[]}}]}))

    def test_merge_existing_entries_is_atomic_and_keeps_owner(self):
        parent=self.create(title='论文投稿',date='2026-09-30')
        child=self.create(title='论文图片',date='2026-09-27')
        ops=[{'action':'update','id':parent['id'],'revision':1,'event':{'kind':'project','date':'2026-09-27','end_date':'2026-10-01','milestones':[{'title':'图片','date':'2026-09-27'}]}},
             {'action':'delete','id':child['id'],'revision':99}]
        with self.assertRaises(ValueError):self.store.apply('schedule-a',ops,'merge-bad','')
        self.assertEqual(len(self.store.list('schedule-a')),2)
        self.assertEqual(next(e for e in self.store.list('schedule-a') if e['id']==parent['id'])['kind'],'event')
        ops[1]['revision']=1
        self.store.apply('schedule-a',ops,'merge-good','')
        self.assertEqual(len(self.store.list('schedule-a')),1)
        with self.app.connect_db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM schedule_memory_links').fetchone()[0],1)
