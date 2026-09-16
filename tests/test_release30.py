"""Remote-only release policy and owner-isolation regression tests."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from fastapi.testclient import TestClient
from wangcai_app.model_runtime import (GuardedCompletions, ModelCallError, normalize_parameters,
                                       check_response, request_timeout, validate_slot, friendly_error)
from wangcai_app.release_features import FEATURES


class RuntimePolicies(unittest.TestCase):
    def response(self, text='hello', finish='stop'):
        return NS(choices=[NS(finish_reason=finish, message=NS(content=text, refusal=None, tool_calls=None))])

    def test_provider_matrix_preserves_compatible_requests(self):
        params={'max_tokens':512,'temperature':0.3,'top_p':0.9,'messages':[]}
        for provider,model in [('local','qwen3.8-27b'),('deepseek','deepseek-flash'),('dashscope','qwen3.7-max'),('zhipu','glm-5.2'),('doubao','doubao-seed-2-0-pro'),('custom','custom')]:
            self.assertEqual(normalize_parameters({'provider':provider,'model':model},params),params)
        for model in ('gpt-5.5','gpt-5','o3','o4-mini'):
            result=normalize_parameters({'provider':'openai','model':model},params)
            self.assertEqual(result['max_completion_tokens'],512)
            self.assertNotIn('temperature',result);self.assertNotIn('top_p',result)
        self.assertEqual(params['max_tokens'],512)

    def test_timeout_rollback_and_configuration(self):
        self.assertEqual(request_timeout(1200,False),1200)
        timeout=request_timeout(1200,True)
        self.assertEqual(timeout.connect,8);self.assertEqual(timeout.read,120)
        self.assertEqual(request_timeout(3,True).read,3)
        for provider in ('deepseek','openai','zhipu','dashscope','doubao'):
            with self.assertRaises(ModelCallError):validate_slot({'provider':provider,'base_url':'https://example.test','model':'x','api_key':''})
        validate_slot({'provider':'local','base_url':'http://localhost','model':'x'})
        validate_slot({'provider':'custom','base_url':'http://localhost','model':'x'})

    def test_structured_validation_and_rollback(self):
        for text,finish in [('', 'stop'),('{"x":1}', 'length'),('not JSON','stop')]:
            with self.assertRaises(ModelCallError):check_response(self.response(text,finish),True)
        check_response(self.response('```json\n{"x":1}\n```'),True)
        response=self.response('', 'length');create=Mock(return_value=response)
        wrapper=GuardedCompletions(create,{}, {'structured_guard':False},'chat',None)
        self.assertIs(wrapper.create(messages=[]),response)
        wrapper.flags['structured_guard']=True
        with self.assertRaises(ModelCallError):wrapper.create(messages=[])

    def test_clear_errors_can_rollback_and_do_not_expose_secrets(self):
        error=RuntimeError('secret credential https://user:password@example.test')
        create=Mock(side_effect=error)
        wrapper=GuardedCompletions(create,{}, {'clear_errors':True},'chat',None)
        with self.assertRaises(ModelCallError) as raised:wrapper.create(messages=[])
        self.assertNotIn('password',str(raised.exception))
        wrapper.flags['clear_errors']=False
        with self.assertRaises(RuntimeError) as raised:wrapper.create(messages=[])
        self.assertIs(raised.exception,error)
        self.assertEqual(friendly_error(httpx.ReadTimeout('x')).code,'timeout')

    def test_stream_error_closes_connection_and_records_no_message_content(self):
        stream=Mock();stream.__iter__=Mock(return_value=iter([NS(choices=[NS(delta=NS(content='private'),finish_reason='length')])]))
        records=[];wrapper=GuardedCompletions(Mock(return_value=stream),{'model':'x'},dict.fromkeys(FEATURES,True),'chat',records.append)
        with self.assertRaises(ModelCallError):list(wrapper.create(stream=True,messages=[]))
        stream.close.assert_called_once()
        self.assertNotIn('private',json.dumps(records))
        self.assertEqual(records[-1]['status'],'truncated')

    def test_empty_stream_fails_unless_policy_rolled_back(self):
        def stream():
            return iter([NS(choices=[NS(delta=NS(content=None), finish_reason='stop')])])
        wrapper=GuardedCompletions(stream, {}, {'structured_guard': True}, 'chat', None)
        wrapper._create=lambda **kwargs: stream()
        with self.assertRaises(ModelCallError): list(wrapper.create(stream=True))
        wrapper.flags['structured_guard']=False
        self.assertEqual(len(list(wrapper.create(stream=True))),1)

    def test_backend_compat_rollback_changes_only_parameter_policy(self):
        create=Mock(return_value=self.response());flags={'backend_compat':False}
        wrapper=GuardedCompletions(create,{'provider':'openai','model':'gpt-5.5'},flags,'chat',None)
        wrapper.create(max_tokens=512,temperature=0.5)
        self.assertIn('max_tokens',create.call_args.kwargs)
        flags['backend_compat']=True;wrapper.create(max_tokens=512,temperature=0.5)
        self.assertIn('max_completion_tokens',create.call_args.kwargs)


class ReleaseIsolation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'WANGCAI_WEB_DB':self.temp.name+'/test.db','WANGCAI_AUTH_CONFIG':self.temp.name+'/auth.json','WANGCAI_IDLE_AGENT_ENABLED':'0'})
        self.env.start();sys.modules.pop('app',None)
        self.app=importlib.import_module('app');self.app.init_db()
        self.client=TestClient(self.app.app)
        self.app.upsert_user_memory_binding('device:release_alpha_device','alpha',share_chat_history=True)
        self.app.upsert_user_memory_binding('device:release_bravo_device','bravo',share_chat_history=True)
        self.headers={'X-Wangcai-Device-Id':'release_alpha_device'}

    def tearDown(self):
        self.client.close();self.env.stop();self.temp.cleanup();sys.modules.pop('app',None)

    def test_every_feature_rolls_back_independently_and_can_restore_inheritance(self):
        for key in FEATURES:
            response=self.client.put('/api/release-features',headers=self.headers,json={'expected_owner':'alpha','changes':{key:False}})
            self.assertEqual(response.status_code,200,response.text)
            flags={x['id']:x['enabled'] for x in response.json()['features']}
            self.assertFalse(flags[key]);self.assertTrue(all(v for k,v in flags.items() if k!=key))
            other=self.client.get('/api/release-features',headers={'X-Wangcai-Device-Id':'release_bravo_device'}).json()
            self.assertTrue(all(x['enabled'] for x in other['features']))
            self.client.put('/api/release-features',headers=self.headers,json={'expected_owner':'alpha','changes':{key:None}})
        self.assertTrue(all(x['inherited'] for x in self.app.release_feature_store().public('alpha')['features']))

    def test_system_controls_require_admin_and_stale_owner_is_rejected(self):
        self.assertEqual(self.client.get('/api/release-features?scope=system',headers=self.headers).status_code,401)
        self.assertEqual(self.client.put('/api/release-features',headers=self.headers,json={'expected_owner':'bravo','changes':{'fast_fail':False}}).status_code,409)
        self.assertEqual(self.client.put('/api/release-features',headers=self.headers,json={'expected_owner':'alpha','changes':{'unknown':False}}).status_code,422)
        self.assertEqual(self.client.put('/api/release-features',headers=self.headers,json={'expected_owner':'alpha','changes':{'fast_fail':'false'}}).status_code,422)

    def test_diagnostics_only_use_saved_settings_and_respect_rollback(self):
        bad=self.client.post('/api/model-settings/probe',headers=self.headers,json={'slot':'chat','expected_owner':'alpha','api_key':'untrusted'})
        self.assertEqual(bad.status_code,422)
        self.app.release_feature_store().save('alpha',{'model_probe':False})
        self.assertEqual(self.client.post('/api/model-settings/probe',headers=self.headers,json={'slot':'chat','expected_owner':'alpha'}).status_code,409)

    def test_single_pass_drawing_preserves_context_and_uses_one_call(self):
        client=Mock();http_client=Mock()
        answer={"prompt_mode":"revision","optimized_prompt":"A sleeping orange cat on a red cushion beside a wooden window, golden afternoon sunlight and detailed fur.","aspect_ratio":"1:1"}
        client.chat.completions.create.return_value=NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps(answer)))])
        factory=Mock(return_value=(client,http_client,{'provider':'custom','model':'fixture'}))
        context='Previous image result:\n- optimized_prompt: Orange cat on a blue cushion by a window\n- negative_prompt: blurry\n- aspect_ratio: 16:9'
        with patch.dict(self.app.optimize_draw_prompt.__globals__,{'openai_client_for_slot':factory}):
            result=self.app.optimize_draw_prompt('把垫子改红色',context=context)
        self.assertEqual(client.chat.completions.create.call_count,1)
        self.assertIn('red cushion',result['optimized_prompt']);self.assertEqual(result['aspect_ratio'],'16:9')
        self.assertIn('blue cushion',client.chat.completions.create.call_args.kwargs['messages'][-1]['content'])
        http_client.close.assert_called_once()

    def test_single_pass_drawing_rejects_missing_mode_or_context(self):
        for answer in ({'optimized_prompt':'an image'}, {'prompt_mode':'revision','optimized_prompt':'a revised image'}):
            client=Mock();http_client=Mock()
            client.chat.completions.create.return_value=NS(choices=[NS(finish_reason='stop',message=NS(content=json.dumps(answer)))])
            with patch.dict(self.app.optimize_draw_prompt.__globals__,{'openai_client_for_slot':lambda *a,**k:(client,http_client,{'provider':'custom','model':'fixture'})}):
                with self.assertRaisesRegex(RuntimeError,'已停止画图'):self.app.optimize_draw_prompt('画一只猫')
            http_client.close.assert_called_once()

    def test_gpu_fallback_flag_can_restore_legacy_behavior(self):
        namespace=self.app.background_gpu_role_indices.__globals__
        with patch.dict(namespace, {'background_detect_gpu_role_indices':lambda:{}}), patch.dict(os.environ,{},clear=True):
            self.assertEqual(len(self.app.background_gpu_role_indices()),4)
            self.app.release_feature_store().save('',{'gpu_role_detection':False})
            self.assertLess(len(self.app.background_gpu_role_indices()),4)
