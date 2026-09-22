import unittest
from wangcai_app.reply_recovery import recover_reply_stream

LEAK='用户说修改组会，我需要判断 this_turn_result 是否属于上一轮。'

class RecoveryTests(unittest.TestCase):
    def test_normal_answer_uses_one_call(self):
        calls=[]
        def first(): calls.append(1); return iter(['正常回复'])
        def unused(): self.fail('Unnecessary retry')
        self.assertEqual(''.join(recover_reply_stream([first,unused,unused])),'正常回复')
        self.assertEqual(calls,[1])

    def test_retry_hides_reasoning_and_closes_rejected_stream(self):
        closed=[];records=[]
        def first():
            try: yield LEAK
            finally: closed.append(True)
        self.assertEqual(''.join(recover_reply_stream([first,lambda:iter(['已核对日程。'])],lambda *r:records.append(r))),'已核对日程。')
        self.assertEqual(closed,[True]);self.assertEqual(len(records),1)
        self.assertNotIn(LEAK,str(records))

    def test_second_leak_uses_local_once(self):
        calls=[]
        def local(): calls.append('local');return iter(['本地回复'])
        self.assertEqual(''.join(recover_reply_stream([lambda:iter([LEAK]),lambda:iter([LEAK]),local])),'本地回复')
        self.assertEqual(calls,['local'])

    def test_failed_retry_also_falls_back(self):
        def failed(): raise TimeoutError()
        self.assertEqual(''.join(recover_reply_stream([lambda:iter([LEAK]),failed,lambda:iter(['本地回复'])])),'本地回复')

    def test_exhaustion_is_bounded_and_hides_detection_message(self):
        with self.assertRaisesRegex(RuntimeError,'暂时未能生成回复'):
            list(recover_reply_stream([lambda:iter([LEAK])]*3))

    def test_primary_network_error_is_not_retried_by_this_policy(self):
        def failed(): raise TimeoutError('network')
        with self.assertRaises(TimeoutError): list(recover_reply_stream([failed,lambda:self.fail('retry')]))

    def test_disconnect_closes_active_stream_without_retry(self):
        closed=[]
        def stream():
            try:
                yield '正常回答'*60
                yield '后续'
            finally: closed.append(True)
        reply=recover_reply_stream([stream,lambda:self.fail('retry')]);next(reply);reply.close()
        self.assertEqual(closed,[True])


import test_schedule as base
from unittest import mock
from types import SimpleNamespace as NS

class RecoveryIntegrationTests(unittest.TestCase):
    setUp=base.ScheduleTests.setUp
    tearDown=base.ScheduleTests.tearDown

    def test_stream_and_completion_route_to_local_without_replaying_actions(self):
        for streaming in (True,False):
            calls=[];closed=[]
            def client(slot, **unused):
                def create(**kwargs):
                    calls.append((slot.copy(),kwargs))
                    text='本地正式回复' if slot['provider']=='local' else LEAK
                    if streaming:
                        return iter([NS(choices=[NS(delta=NS(content=text))])])
                    return NS(choices=[NS(message=NS(content=text))])
                return NS(chat=NS(completions=NS(create=create))), NS(close=lambda:closed.append(True)), None
            remote={'provider':'deepseek','model':'remote','thinking_enabled':True}
            local={'provider':'local','model':'local'}
            messages=[{'role':'system','content':'original'},{'role':'user','content':'问题'}]
            replacements={'chat_model_candidate_slots':lambda m:[('remote',remote,'')],
                'default_model_slot':lambda _:local,'openai_client_for_model_slot_config':client,
                'model_completion_kwargs':lambda slot:{'model':slot['model']},
                'record_event':lambda *a,**k:None}
            with mock.patch.dict(self.ns,replacements):
                if streaming: answer=''.join(self.app.iter_model_deltas(messages,300,.5,.9))
                else: answer=self.app.call_chat_completion_once(messages,300,.5,.9)
            self.assertEqual(answer,'本地正式回复')
            self.assertEqual([s['provider'] for s,k in calls],['deepseek','deepseek','local'])
            self.assertFalse(calls[1][0]['thinking_enabled'])
            self.assertEqual(len(closed),3)
            self.assertEqual(messages[0]['content'],'original')
            self.assertEqual(calls[-1][1]['messages'][-1]['role'],'user')
