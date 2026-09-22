import unittest
import test_schedule as base
from wangcai_app.schedule import normalize_event

class TrackTests(unittest.TestCase):
    setUp=base.ScheduleTests.setUp
    tearDown=base.ScheduleTests.tearDown
    create=base.ScheduleTests.create

    def project(self):
        return self.create(title='脑计划',kind='project',date='2026-09-22',end_date='2026-09-26',milestones=[
            {'title':'测试大纲','date':'2026-09-26','track':'三方测试'},
            {'title':'申请服务器','track':'多模态演示'},
            {'title':'跑通网络','track':'多模态演示'},
            {'title':'联系老师','track':'动力学神经网络'}])

    def test_tracks_persist_and_sync_to_memory(self):
        e=self.project();saved=self.store.list('schedule-a')[0]
        self.assertEqual([s['track'] for s in saved['milestones']],['三方测试','多模态演示','多模态演示','动力学神经网络'])
        with self.app.connect_db() as c:
            text=c.execute('SELECT content FROM curated_memories WHERE id=(SELECT memory_id FROM schedule_memory_links WHERE event_id=?)',(e['id'],)).fetchone()[0]
        for track in ['三方测试','多模态演示','动力学神经网络']:self.assertIn(track,text)

    def test_omitted_group_is_preserved_but_explicit_empty_clears(self):
        e=self.project();stages=[{k:v for k,v in s.items() if k!='track'} for s in e['milestones']];stages[1]['done']=True
        r=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'milestones':stages}}],'keep-tracks','')['changes'][0]['event']
        self.assertEqual(r['milestones'][1]['track'],'多模态演示');self.assertTrue(r['milestones'][1]['done'])
        stages=r['milestones'];stages[1]['track']=''
        r=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':2,'event':{'milestones':stages}}],'clear-track','')['changes'][0]['event']
        self.assertEqual(r['milestones'][1]['track'],'')
        self.assertEqual(r['milestones'][2]['track'],'多模态演示')

    def test_invalid_group_is_rejected_atomically(self):
        e=self.project()
        for track in [7,{},'x'*81]:
            stages=[{**s,'track':track} for s in e['milestones']]
            with self.assertRaises(ValueError):
                self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'milestones':stages}}],'invalid-'+str(type(track)),'')
        self.assertEqual(self.store.list('schedule-a')[0]['revision'],1)

    def test_existing_ungrouped_projects_remain_compatible(self):
        e=normalize_event({'title':'旧项目','kind':'project','milestones':[{'title':'节点'}]})
        self.assertEqual(e['milestones'][0]['track'],'')
