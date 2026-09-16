"""Remote-only tests with isolated database and synthetic users."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wangcai_app.memberships import normalize_card, next_month, daily_hint
from wangcai_app.membership_memory import card_memory_text


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {'WANGCAI_WEB_DB': self.temp.name + '/test.db', 'WANGCAI_AUTH_CONFIG': self.temp.name + '/auth.json', 'WANGCAI_IDLE_AGENT_ENABLED': '0'})
        self.env.start();sys.modules.pop('app', None)
        self.app = importlib.import_module('app');self.app.init_db();self.app.schedule_store().initialize()
        self.store = self.app.membership_store();self.store.initialize()
        self.client = TestClient(self.app.app)
        self.ns = self.app.manage_membership_message.__globals__
        for user in ('alpha', 'bravo'):
            self.app.upsert_user_memory_binding('device:membership_test_'+user, user, share_chat_history=True)

    def tearDown(self):
        self.client.close();self.env.stop();self.temp.cleanup();sys.modules.pop('app', None)

    def create(self, name='测试会员卡', owner='alpha', **fields):
        return self.store.apply(owner, [{'action': 'create', 'card': {'name': name, **fields}}], 'create-'+name, name)['changes'][0]['card']

    def edit(self, card, patch, owner='alpha', request='edit-card'):
        return self.store.apply(owner, [{'action': 'update', 'id': card['id'], 'revision': card['revision'], 'card': patch}], request, 'edit')

    def memory(self, card):
        with self.app.connect_db() as conn:
            return dict(conn.execute('SELECT m.* FROM curated_memories m JOIN membership_memory_links l ON l.memory_id=m.id WHERE l.card_id=?', (card['id'],)).fetchone())

    def test_unknown_balances_and_decimal_precision(self):
        card = normalize_card({'name': '冰激凌', 'balance_note': '几元'})
        self.assertEqual(card['balance'], '')
        self.assertEqual(normalize_card({'name': '次卡', 'balance': '8000', 'remaining_uses': '5'})['balance'], '8000.00')
        for patch in [{'balance':'NaN'}, {'balance':'-1'}, {'balance':'1.001'}, {'balance':4}, {'remaining_uses':'1.5'}, {'reminder_enabled':'yes'}, {'expires_on':'2026-02-30'}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):normalize_card({'name':'卡', **patch})

    def test_api_binding_and_owner_isolation(self):
        self.create(balance='300')
        self.assertEqual(self.client.get('/api/memberships').status_code, 409)
        a = self.client.get('/api/memberships',headers={'X-Wangcai-Device-Id':'membership_test_alpha'}).json()
        b = self.client.get('/api/memberships',headers={'X-Wangcai-Device-Id':'membership_test_bravo'}).json()
        self.assertEqual(len(a['cards']),1);self.assertEqual(b['cards'],[])
        with self.assertRaises(LookupError):self.edit(a['cards'][0],{'balance':'0'},owner='bravo')

    def test_transactional_memory_update_delete_and_queue(self):
        card=self.create(balance='8000',remaining_uses='5',status='issue',notes='归属地似乎有问题')
        memory=self.memory(card)
        self.assertIn('8000.00元',memory['content']);self.assertIn('5次',memory['content'])
        updated=self.edit(card,{'balance':'6000','remaining_uses':'4'})['changes'][0]['card']
        self.assertEqual(self.memory(updated)['id'],memory['id']);self.assertIn('6000.00元',self.memory(updated)['content'])
        with self.app.connect_db() as conn:
            self.assertIn('6000.00',conn.execute('SELECT content FROM schedule_memory_index_queue WHERE memory_id=?',(memory['id'],)).fetchone()[0])
        self.store.apply('alpha',[{'action':'delete','id':card['id'],'revision':updated['revision']}],'delete-card','delete')
        with self.app.connect_db() as conn:
            self.assertIsNone(conn.execute('SELECT 1 FROM curated_memories WHERE id=?',(memory['id'],)).fetchone())
            self.assertIsNone(conn.execute('SELECT 1 FROM schedule_memory_index_queue WHERE memory_id=?',(memory['id'],)).fetchone())

    def test_retry_dedup_and_stale_revision(self):
        card=self.create()
        first=self.edit(card,{'balance':'20'})
        self.assertEqual(first,self.edit(card,{'balance':'20'}))
        with self.assertRaises(ValueError):self.edit(card,{'balance':'30'},request='stale-retry')
        self.assertEqual(len(self.store.list('alpha')),1)
        with self.assertRaises(ValueError):self.store.apply('alpha',[{'action':'create','card':{'name':'测试会员卡'}}],'duplicate-mention','duplicate')

    def test_sync_failure_rolls_back_everything(self):
        card=self.create(balance='20')
        with mock.patch.object(self.store.synchronizer,'apply',side_effect=OSError('fail')):
            with self.assertRaises(OSError):self.edit(card,{'balance':'0'})
        self.assertEqual(self.store.list('alpha')[0]['balance'],'20.00')
        self.assertIsNone(self.store.cached('alpha','edit-card'))

    def test_daily_rotation_and_pause_filters(self):
        cards=[self.create(name=name) for name in ('A','B','C')]
        first=daily_hint(cards,'2026-09-16',{})
        self.assertEqual(first,daily_hint(list(reversed(cards)),'2026-09-16',{}))
        self.assertNotEqual(first['card_id'],daily_hint(cards,'2026-09-17',{})['card_id'])
        self.assertIsNone(daily_hint(cards,'2026-09-16',{'snooze_until':'2026-10-16'}))
        for card in cards:card['status']='used_up'
        self.assertIsNone(daily_hint(cards,'2026-09-16',{}))
        cards[0]['status']='active';cards[0]['reminder_enabled']=False
        self.assertIsNone(daily_hint(cards,'2026-09-16',{}))
        self.assertEqual(next_month('2026-01-31'),'2026-02-28');self.assertEqual(next_month('2026-12-31'),'2027-01-31')

    def test_issue_and_expiration_do_not_nudge_spending(self):
        card=self.create(status='issue',notes='归属地需要确认')
        self.assertIn('先确认使用问题',daily_hint([card],'2026-09-16',{})['text'])
        card.update(status='active',expires_on='2026-09-15')
        self.assertIn('先核实是否仍可用',daily_hint([card],'2026-09-16',{})['text'])

    def test_preference_persistence_and_cross_device(self):
        self.app.upsert_user_memory_binding('device:membership_test_alternate','alpha',share_chat_history=True)
        headers={'X-Wangcai-Device-Id':'membership_test_alpha'}
        self.assertEqual(self.client.post('/api/memberships/preferences',headers=headers,json={'action':'collapse'}).status_code,200)
        data=self.client.post('/api/memberships/preferences',headers=headers,json={'action':'snooze'}).json()
        other=self.client.get('/api/memberships',headers={'X-Wangcai-Device-Id':'membership_test_alternate'}).json()
        self.assertTrue(other['preferences']['collapsed']);self.assertEqual(data['preferences'],other['preferences'])
        self.assertEqual(self.client.post('/api/memberships/preferences',headers=headers,json={'action':'invalid'}).status_code,400)

    def test_dismiss_today_persists_across_devices_and_expires_next_day(self):
        self.create(); self.create(owner='bravo')
        self.app.upsert_user_memory_binding('device:membership_test_alternate','alpha',share_chat_history=True)
        headers={'X-Wangcai-Device-Id':'membership_test_alpha'}
        ns=self.app.membership_snapshot.__globals__
        with mock.patch.dict(ns, {'schedule_today': lambda: '2026-12-31'}):
            response=self.client.post('/api/memberships/preferences',headers=headers,json={'action':'dismiss_today'})
            self.assertEqual(response.status_code,200)
            self.assertIsNone(response.json()['hint'])
            for device in ('alpha','alternate'):
                result=self.client.get('/api/memberships',headers={'X-Wangcai-Device-Id':'membership_test_'+device}).json()
                self.assertIsNone(result['hint'])
            other=self.client.get('/api/memberships',headers={'X-Wangcai-Device-Id':'membership_test_bravo'}).json()
            self.assertIsNotNone(other['hint'])
        with mock.patch.dict(ns, {'schedule_today': lambda: '2027-01-01'}):
            self.assertIsNotNone(self.client.get('/api/memberships',headers=headers).json()['hint'])

    def test_daily_dismiss_does_not_shorten_month_pause_and_resume_clears_both(self):
        self.create()
        headers={'X-Wangcai-Device-Id':'membership_test_alpha'}
        ns=self.app.membership_snapshot.__globals__
        with mock.patch.dict(ns, {'schedule_today': lambda: '2026-12-31'}):
            self.client.post('/api/memberships/preferences',headers=headers,json={'action':'snooze'})
            self.client.post('/api/memberships/preferences',headers=headers,json={'action':'dismiss_today'})
        with mock.patch.dict(ns, {'schedule_today': lambda: '2027-01-01'}):
            self.assertIsNone(self.client.get('/api/memberships',headers=headers).json()['hint'])
            restored=self.client.post('/api/memberships/preferences',headers=headers,json={'action':'resume'}).json()
            self.assertIsNotNone(restored['hint'])
            self.assertEqual(restored['preferences']['dismissed_on'],'')

    def test_main_chat_and_memory_editor_use_same_card(self):
        card=self.create(balance='20')
        decision={'reply':'已更新','operations':[{'action':'update','id':card['id'],'revision':card['revision'],'card':{'balance':'10'}}]}
        with mock.patch.dict(self.ns,{'membership_agent_decision':lambda ctx:decision}):
            context=self.app.membership_context_for_chat('alpha','会员卡余额变成10元','chat-update',[],lambda:False)
        self.assertIn('10.00',context)
        card=self.store.list('alpha')[0];memory=self.memory(card)
        decision['operations'][0]['card']={'balance':'8'}
        with mock.patch.dict(self.ns,{'membership_agent_decision':lambda ctx:decision}):
            self.assertTrue(self.app.update_admin_memory(memory['id'],'用户会员卡余额8元','other'))
        self.assertEqual(self.store.list('alpha')[0]['balance'],'8.00')
        self.assertTrue(self.app.delete_admin_memory(memory['id']));self.assertEqual(self.store.list('alpha'),[])

    def test_unrelated_chat_does_not_invoke_model(self):
        self.create()
        with mock.patch.dict(self.ns,{'membership_agent_decision':mock.Mock(side_effect=AssertionError('must not call'))}):
            result=self.app.membership_context_for_chat('alpha','帮我看看这段代码','unrelated',[],lambda:False)
        self.assertIn('不主动',result)


if __name__=='__main__':unittest.main()
