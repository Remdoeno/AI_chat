import unittest
import test_schedule as base
from wangcai_app.schedule import normalize_event

class OrderTests(unittest.TestCase):
    setUp = base.ScheduleTests.setUp
    tearDown = base.ScheduleTests.tearDown
    create = base.ScheduleTests.create

    def project(self, stages):
        return self.create(title='排序项目', kind='project', date='', time='', milestones=stages)

    def test_dates_times_intervals_and_independent_tracks(self):
        e=self.project([
            {'id':'report','title':'报告','date':'2026-09-26','track':'测试'},
            {'id':'pm','title':'下午测试','date':'2026-09-22','time':'13:00','track':'测试'},
            {'id':'other','title':'另一条路线','date':'2026-09-01','track':'演示'},
            {'id':'am','title':'上午测试','date':'2026-09-22','time':'09:00','track':'测试'},
            {'id':'range','title':'准备','start_date':'2026-09-20','date':'2026-09-25','track':'测试'}])
        self.assertEqual([s['id'] for s in e['milestones']],['range','am','pm','report','other'])

    def test_update_reorders_and_syncs_memory(self):
        e=self.project([{'id':'a','title':'早节点','date':'2026-09-22'}, {'id':'b','title':'晚节点','date':'2026-09-26'}])
        stages=[{**s,'date':'2026-09-28'} if s['id']=='a' else s for s in e['milestones']]
        result=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'milestones':stages}}],'reorder','')
        self.assertEqual([s['id'] for s in result['changes'][0]['event']['milestones']],['b','a'])
        with self.app.connect_db() as c:
            text=c.execute('SELECT content FROM curated_memories WHERE id=(SELECT memory_id FROM schedule_memory_links WHERE event_id=?)',(e['id'],)).fetchone()[0]
        self.assertLess(text.index('晚节点'),text.index('早节点'))

    def test_dependencies_win_without_fabricating_dates(self):
        e=self.project([{'id':'report','title':'报告','date':'2026-09-22','depends_on':['test']},
                        {'id':'test','title':'测试'}])
        self.assertEqual([s['id'] for s in e['milestones']],['test','report'])
        self.assertEqual(e['milestones'][0]['date'],'')
        with self.app.connect_db() as c:
            text=c.execute('SELECT content FROM curated_memories WHERE id=(SELECT memory_id FROM schedule_memory_links WHERE event_id=?)',(e['id'],)).fetchone()[0]
        self.assertIn('前置阶段：测试',text)

    def test_dependency_preserved_on_manual_edit_and_removed_with_predecessor(self):
        e=self.project([{'id':'a','title':'测试'},{'id':'b','title':'报告','depends_on':['a']}])
        stages=[{k:v for k,v in s.items() if k!='depends_on'} for s in e['milestones']]
        stages[0]['done']=True
        e=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'milestones':stages}}],'preserve','')['changes'][0]['event']
        self.assertEqual(e['milestones'][1]['depends_on'],['a'])
        e=self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':2,'event':{'milestones':[stages[1]]}}],'remove','')['changes'][0]['event']
        self.assertEqual(e['milestones'][0]['depends_on'],[])

    def test_invalid_dependencies_are_atomic(self):
        e=self.project([{'id':'a','title':'A'},{'id':'b','title':'B'}])
        invalid=[['missing'],['a'],['b','b'],'b', [2]]
        for dep in invalid:
            stages=[{**s,'depends_on':dep} if s['id']=='a' else s for s in e['milestones']]
            with self.assertRaises(ValueError):
                self.store.apply('schedule-a',[{'action':'update','id':e['id'],'revision':1,'event':{'milestones':stages}}],'bad','')
        self.assertEqual(self.store.list('schedule-a')[0]['revision'],1)
        for stages in [[{'id':'a','title':'A','depends_on':['b']},{'id':'b','title':'B','depends_on':['a']}],
                       [{'id':'a','title':'A','track':'一'},{'id':'b','title':'B','track':'二','depends_on':['a']}]]:
            with self.assertRaises(ValueError):normalize_event({'title':'项目','kind':'project','milestones':stages})

    def test_undated_and_equal_time_stable(self):
        stages=[{'id':i,'title':i} for i in ['c','a','b']]
        self.assertEqual([s['id'] for s in self.project(stages)['milestones']],['c','a','b'])
