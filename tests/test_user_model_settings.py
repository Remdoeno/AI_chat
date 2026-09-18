"""Remote-only model ownership, credential isolation, and execution context tests."""
import asyncio
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
import httpx
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wangcai_app.model_context import current_model_owner, model_owner_scope, bind_model_context


class UserModelSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=mock.patch.dict(os.environ,{'WANGCAI_WEB_DB':self.temp.name+'/test.db','WANGCAI_AUTH_CONFIG':self.temp.name+'/auth.json','WANGCAI_IDLE_AGENT_ENABLED':'0'})
        self.env.start();sys.modules.pop('app',None)
        self.app=importlib.import_module('app');self.app.init_db();self.app.release_feature_store().save('', {'draw_single_pass':False});self.app.schedule_store().initialize();self.app.membership_store().initialize()
        self.ns=self.app.load_model_settings.__globals__;self.store=self.app.user_model_settings_store()
        for device,user in [('alpha_one','alpha'),('alpha_two','alpha'),('bravo_one','bravo')]:
            self.app.upsert_user_memory_binding('device:model_test_'+device,user,share_chat_history=True)
        slots={name:self.slot('global-'+name,'SYSTEM-'+name) for name in ('chat','background','image')}
        self.app.save_model_settings(slots)
        self.client=TestClient(self.app.app)

    def tearDown(self):
        self.client.close();self.env.stop();self.temp.cleanup();sys.modules.pop('app',None)
        self.assertEqual(current_model_owner(),'')

    @staticmethod
    def slot(model,key='private-key'):
        return {'provider':'custom','base_url':'https://example.test/v1','model':model,'display_name':model,'api_key':key,'use_proxy':False,'proxy_url':''}

    @staticmethod
    def headers(device='alpha_one'):
        return {'X-Wangcai-Device-Id':'model_test_'+device}

    def put(self,payload,device='alpha_one',scope='user'):
        return self.client.put('/api/model-settings?scope='+scope,headers=self.headers(device),json=payload)

    def test_deepseek_flash_images_use_selected_model(self):
        messages=[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,fixture'}}]}]
        for model in ('deepseek-flash','deepseek-v4-flash','deepseek-v4-flash-vision-exp'):
            with self.subTest(model=model):
                slot={**self.slot(model),'provider':'deepseek','base_url':'https://api.deepseek.com/v1'}
                self.store.save('alpha',{'chat':slot})
                with model_owner_scope('alpha'):
                    candidates=self.app.chat_model_candidate_slots(messages)
                    self.assertEqual(len(candidates),1)
                    self.assertEqual(candidates[0][1]['model'],model)
                    self.assertEqual(candidates[0][1]['provider'],'deepseek')
                    self.assertEqual(self.app.draw_reference_image_analysis_slots()[0][1]['model'],model)
                    self.assertEqual(len(self.app.draw_reference_image_analysis_slots()),1)

    def test_native_vision_error_does_not_silently_call_another_model(self):
        self.store.save('alpha',{'chat':{**self.slot('deepseek-flash'),'provider':'deepseek','base_url':'https://api.deepseek.com/v1'}})
        client=mock.Mock()
        client.chat.completions.create.side_effect=ValueError('invalid_request_error: image_url')
        http_client=mock.Mock()
        with model_owner_scope('alpha'):
            slot=self.app.model_slot_config('chat')
            factory=mock.Mock(return_value=(client,http_client,slot))
            with mock.patch.dict(self.ns,{'openai_client_for_model_slot_config':factory}):
                messages=[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,fixture'}}]}]
                with self.assertRaisesRegex(ValueError,'image_url'):
                    list(self.app.iter_model_deltas(messages,128,0.1,0.95))
            self.assertEqual(factory.call_count,1)
            self.assertEqual(client.chat.completions.create.call_count,1)
            http_client.close.assert_called_once()

    def test_deepseek_text_models_keep_image_fallback(self):
        for model in ('deepseek-v4-pro','deepseek-chat','deepseek-reasoner'):
            self.assertFalse(self.app.model_slot_likely_accepts_image_messages({'provider':'deepseek','model':model}))
        self.store.save('alpha',{'chat':{**self.slot('deepseek-v4-pro'),'provider':'deepseek','base_url':'https://api.deepseek.com/v1'}})
        with model_owner_scope('alpha'):
            messages=[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,fixture'}}]}]
            self.assertNotEqual(self.app.chat_model_candidate_slots(messages)[0][1]['model'],'deepseek-v4-pro')
            self.assertEqual(self.app.chat_model_candidate_slots([{'role':'user','content':'你好'}])[0][1]['model'],'deepseek-v4-pro')

    def test_draw_preparation_deepseek_uses_json_without_consuming_budget_on_reasoning(self):
        self.store.save('alpha',{'background':{**self.slot('deepseek-flash'),'provider':'deepseek'}})
        client=mock.Mock();http_client=mock.Mock()
        answers=[{'translated_prompt':'Draw a dancing person'}, {'mode':'natural'}, {'optimized_prompt':'A dancing person in a warmly lit ballroom, flowing clothes, graceful full-body pose and soft cinematic lighting'}]
        client.chat.completions.create.side_effect=[mock.Mock(choices=[mock.Mock(finish_reason='stop',message=mock.Mock(content=json.dumps(x)))]) for x in answers]
        with model_owner_scope('alpha'):
            slot=self.app.model_slot_config('background')
            with mock.patch.dict(self.ns,{'openai_client_for_slot':lambda *a,**k:(client,http_client,slot)}):
                result=self.app.optimize_draw_prompt('画一个跳舞的人')
            self.assertIn('ballroom',result['optimized_prompt'])
            self.assertEqual(client.chat.completions.create.call_count,3)
            for call in client.chat.completions.create.call_args_list:
                self.assertEqual(call.kwargs['extra_body']['thinking']['type'],'disabled')
                self.assertEqual(call.kwargs['response_format'],{'type':'json_object'})
            self.assertEqual(self.app.model_completion_kwargs(slot)['extra_body']['thinking']['type'],'disabled')
        local={'provider':'local','model':'local-fixture'}
        self.assertEqual(self.app.draw_prompt_completion_kwargs(local),self.app.model_completion_kwargs(local))

    def test_draw_prompt_truncation_stops_generation_even_with_parseable_json(self):
        client=mock.Mock();http_client=mock.Mock()
        client.chat.completions.create.return_value=mock.Mock(choices=[mock.Mock(finish_reason='length',message=mock.Mock(content='{"optimized_prompt":"An incomplete but parseable prompt"}'))])
        with mock.patch.dict(self.ns,{'classify_draw_prompt_mode':lambda *a,**k:{'mode':'natural'},'openai_client_for_slot':lambda *a,**k:(client,http_client,{'provider':'custom','model':'test'})}):
            with self.assertRaisesRegex(RuntimeError,'已停止画图'):
                self.app.optimize_draw_prompt('Draw a dancing person')
        http_client.close.assert_called_once()

    def test_draw_prompt_missing_background_key_fails_before_any_model_call(self):
        self.store.save('alpha',{'background':{**self.slot('deepseek-flash',''),'provider':'deepseek','base_url':'https://api.deepseek.com/v1'}})
        factory=mock.Mock(side_effect=AssertionError('should fail before network'))
        with model_owner_scope('alpha'), mock.patch.dict(self.ns,{'openai_client_for_slot':factory}):
            with self.assertRaisesRegex(ValueError,'API Key'):
                self.app.optimize_draw_prompt('画一个安静的卧室')
        factory.assert_not_called()

    def test_draw_prompt_invalid_or_unchanged_result_is_not_silent_fallback(self):
        for content in ('{}','not json','{"optimized_prompt":"A quiet bedroom"}'):
            with self.subTest(content=content):
                client=mock.Mock();http_client=mock.Mock()
                client.chat.completions.create.return_value=mock.Mock(choices=[mock.Mock(message=mock.Mock(content=content))])
                with mock.patch.dict(self.ns,{
                    'translate_draw_text_to_english':lambda *a,**k:'A quiet bedroom',
                    'translate_draw_context_to_english':lambda *a:'',
                    'classify_draw_prompt_mode':lambda *a,**k:{'mode':'natural'},
                    'openai_client_for_slot':lambda *a,**k:(client,http_client,{'provider':'custom','model':'test'}),
                }):
                    with self.assertRaisesRegex(RuntimeError,'已停止画图'):
                        self.app.optimize_draw_prompt('画一个安静的卧室')
                http_client.close.assert_called_once()

    def test_draw_prompt_preserves_professional_english_and_uses_successful_optimization(self):
        with mock.patch.dict(self.ns,{'classify_draw_prompt_mode':lambda *a,**k:{'mode':'professional'}}):
            result=self.app.optimize_draw_prompt('A quiet bedroom, warm light, wide composition, oil painting')
            self.assertIn('warm light',result['optimized_prompt'])
        client=mock.Mock();http_client=mock.Mock()
        client.chat.completions.create.return_value=mock.Mock(choices=[mock.Mock(message=mock.Mock(content='{"optimized_prompt":"A peaceful bedroom bathed in warm moonlight, gentle shadows and detailed linen textures","aspect_ratio":"16:9"}'))])
        with mock.patch.dict(self.ns,{'classify_draw_prompt_mode':lambda *a,**k:{'mode':'natural'},'openai_client_for_slot':lambda *a,**k:(client,http_client,{'provider':'custom','model':'test'})}):
            result=self.app.optimize_draw_prompt('A quiet bedroom')
            self.assertIn('moonlight',result['optimized_prompt']);self.assertEqual(result['aspect_ratio'],'16:9')

    def test_flash_thinking_disabled_for_every_slot_and_alias(self):
        for model in ('deepseek-flash','deepseek-v4-flash','deepseek-v4-flash-vision-exp','deepseek/deepseek-flash'):
            for provider in ('deepseek','custom'):
                slot={**self.slot(model),'provider':provider}
                self.assertEqual(self.app.model_completion_kwargs(slot)['extra_body'],{'thinking':{'type':'disabled'}})
        for model in ('deepseek-reasoner','other-model'):
            self.assertNotIn('extra_body',self.app.model_completion_kwargs(self.slot(model)))

    def test_streaming_and_nonstreaming_flash_send_disabled_thinking(self):
        slot={**self.slot('deepseek-flash'),'provider':'deepseek'}
        client=mock.Mock();http_client=mock.Mock()
        client.chat.completions.create.side_effect=[
            [mock.Mock(choices=[mock.Mock(delta=mock.Mock(content='hello'))])],
            mock.Mock(choices=[mock.Mock(message=mock.Mock(content='hello'))]),
        ]
        with mock.patch.dict(self.ns,{'chat_model_candidate_slots':lambda *a:[('chat',slot,'')],'openai_client_for_model_slot_config':lambda *a,**k:(client,http_client,slot)}):
            self.assertEqual(''.join(self.app.iter_model_deltas([],512,0.6,0.9)),'hello')
            self.assertEqual(self.app.call_chat_completion_once([],512,0.6,0.9),'hello')
        for call in client.chat.completions.create.call_args_list:
            self.assertEqual(call.kwargs['extra_body'],{'thinking':{'type':'disabled'}})
            self.assertEqual(call.kwargs['max_tokens'],512)

    def test_thinking_setting_roundtrip_per_user_and_per_slot(self):
        flash={**self.slot('deepseek-flash'),'provider':'deepseek'}
        response=self.put({'chat':{**flash,'thinking_enabled':True},'background':{**flash,'thinking_enabled':False}})
        self.assertEqual(response.status_code,200,response.text)
        same=self.client.get('/api/model-settings',headers=self.headers('alpha_two')).json()
        self.assertTrue(same['chat']['thinking_enabled']);self.assertFalse(same['background']['thinking_enabled'])
        self.assertTrue(same['chat']['thinking_supported'])
        other=self.client.get('/api/model-settings',headers=self.headers('bravo_one')).json()
        self.assertFalse(other['chat']['thinking_enabled'])
        with model_owner_scope('alpha'):
            slot=self.app.model_slot_config('chat')
            self.assertEqual(self.app.model_completion_kwargs(slot)['extra_body']['thinking']['type'],'enabled')
            self.assertEqual(self.app.model_output_token_limit(slot,512),8704)
            self.assertEqual(self.app.model_output_token_limit(slot,18000),26192)
            self.assertEqual(self.app.model_output_token_limit(slot,64000),64000)
            self.assertEqual(self.app.model_output_token_limit(self.app.model_slot_config('background'),512),512)
        self.assertEqual(self.put({'chat':{'thinking_enabled':'false'}}).status_code,422)
        self.assertEqual(self.put({'chat':{'thinking_enabled':False}}).status_code,200)
        self.assertFalse(self.store.public('alpha')['chat']['thinking_enabled'])

    def test_local_thinking_disabled_and_system_schema_preserves_option(self):
        response=self.put({'chat':{'provider':'local','thinking_enabled':True}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertFalse(response.json()['chat']['thinking_enabled'])
        self.assertFalse(response.json()['chat']['thinking_supported'])
        payload=self.app.ModelSettingsPayload(chat={'provider':'deepseek','thinking_enabled':True},background={'provider':'deepseek','thinking_enabled':False})
        data=payload.model_dump() if hasattr(payload,'model_dump') else payload.dict()
        self.app.save_model_settings(data)
        system=self.app.public_model_settings(self.app.load_system_model_settings())
        self.assertTrue(system['chat']['thinking_enabled']);self.assertFalse(system['background']['thinking_enabled'])
        self.assertEqual(system['chat']['model'],'deepseek-flash')
        self.assertTrue(self.store.public('bravo')['chat']['thinking_enabled'])

    def test_empty_opening_returns_error_and_failed_trace_instead_of_success(self):
        session=self.app.create_session('device:model_test_alpha_one','test')
        with mock.patch.dict(self.ns,{
            'iter_model_deltas':lambda *a,**k:iter([]),
            'call_chat_completion_once':lambda *a,**k:'',
            'require_analysis_user':lambda *a:'alpha',
            'cached_opening_system_prompt':lambda *a:'Give a short greeting.',
        }):
            response=self.client.post('/api/chat/stream',headers=self.headers(),json={'session_id':session,'message':'hello','cached_opening':True,'hidden_user':True,'analysis_mode':True,'max_tokens':512})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('event: error',response.text)
        self.assertIn('开场白生成失败',response.text)
        self.assertNotIn('event: done',response.text)
        with self.app.connect_db() as c:
            rows=c.execute("SELECT event_type,payload_json FROM analysis_trace_events WHERE session_id=? AND step_name='main_chat_stream'",(session,)).fetchall()
        self.assertTrue(rows)
        self.assertEqual(rows[-1][0],'model_call_error')
        self.assertEqual(json.loads(rows[-1][1])['status'],'empty_failed')

    def test_personal_three_slots_and_same_user_devices(self):
        payload={name:self.slot('alpha-'+name) for name in ('chat','background','image')}
        response=self.put(payload);self.assertEqual(response.status_code,200,response.text)
        a=self.client.get('/api/model-settings',headers=self.headers('alpha_two')).json()
        b=self.client.get('/api/model-settings',headers=self.headers('bravo_one')).json()
        for name in payload:self.assertEqual(a[name]['model'],'alpha-'+name);self.assertFalse(a[name]['inherit']);self.assertTrue(b[name]['inherit'])
        self.assertEqual(self.app.load_system_model_settings()['chat']['model'],'global-chat')

    def test_inherited_key_never_copied_or_exposed_to_custom_endpoint(self):
        before=self.client.get('/api/model-settings',headers=self.headers()).json()
        self.assertNotIn('SYSTEM-',json.dumps(before));self.assertEqual(before['chat']['base_url'],'')
        payload=self.slot('mine');payload.pop('api_key')
        self.assertEqual(self.put({'chat':payload}).status_code,200)
        saved=self.store.load('alpha');self.assertEqual(saved['slots']['chat']['api_key'],'')
        with model_owner_scope('alpha'):
            self.assertEqual(self.app.model_slot_config('chat')['api_key'],'')
            self.assertEqual(self.app.model_slot_config('background')['api_key'],'SYSTEM-background')
        self.assertNotIn('SYSTEM-',json.dumps(saved))

    def test_own_secret_is_preserved_and_not_returned(self):
        self.put({'chat':self.slot('mine','ALPHA-SECRET')})
        response=self.put({'chat':{'model':'mine-v2'}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['chat']['has_api_key']);self.assertNotIn('ALPHA-SECRET',response.text)
        own=self.store.load('alpha')['slots']['chat'];self.assertEqual(own['api_key'],'ALPHA-SECRET');self.assertEqual(own['base_url'],'https://example.test/v1')
        self.assertNotIn('ALPHA-SECRET',self.client.get('/api/model-settings',headers=self.headers('bravo_one')).text)

    def test_inheritance_preserves_personal_configuration_and_key(self):
        own={**self.slot('my-model','PRIVATE-KEY'),'thinking_enabled':True}
        self.put({'chat':own})
        response=self.put({'chat':None})
        self.assertTrue(response.json()['chat']['inherit'])
        self.assertEqual(response.json()['saved_slots']['chat']['model'],'my-model')
        self.assertNotIn('PRIVATE-KEY',response.text)
        self.assertNotIn('saved_slots',self.store.effective('alpha'))
        response=self.put({'chat':{'provider':'custom','inherit':False}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.store.effective('alpha')['chat']['api_key'],'PRIVATE-KEY')
        self.assertEqual(self.store.effective('alpha')['chat']['model'],'my-model')

    def test_save_draft_while_inherited_and_restore_after_provider_switch(self):
        own={**self.slot('private-model','PRIVATE-KEY'),'inherit':True}
        response=self.put({'chat':own})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['chat']['inherit'])
        self.assertNotEqual(self.store.effective('alpha')['chat']['model'],'private-model')
        self.put({'chat':{'provider':'local'}})
        response=self.put({'chat':{'provider':'custom'}})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.store.effective('alpha')['chat']['api_key'],'PRIVATE-KEY')
        self.assertEqual(self.store.effective('alpha')['chat']['model'],'private-model')
        self.assertNotIn('PRIVATE-KEY',response.text)
        self.assertNotIn('private-model',self.client.get('/api/model-settings',headers=self.headers('bravo_one')).text)
        self.put({'chat':{'provider':'custom','base_url':'https://different.test/v1'}})
        self.assertEqual(self.store.effective('alpha')['chat']['api_key'],'')

    def test_inherit_reset_tracks_default_without_replacing_other_slots(self):
        self.put({'chat':self.slot('mine'), 'background':self.slot('mine-bg')})
        self.put({'chat':None})
        self.app.save_model_settings({'chat':self.slot('global-new','SYSTEM-NEW')})
        with model_owner_scope('alpha'):
            settings=self.app.load_model_settings();self.assertEqual(settings['chat']['model'],'global-new');self.assertEqual(settings['background']['model'],'mine-bg')
        self.assertEqual(self.app.load_system_model_settings()['image']['model'],'global-image')

    def test_scope_authorization_and_stale_binding(self):
        self.assertEqual(self.client.get('/api/model-settings?scope=user').status_code,409)
        self.assertEqual(self.put({'chat':None},scope='system').status_code,401)
        self.assertEqual(self.client.get('/api/model-settings?scope=system',headers=self.headers()).status_code,401)
        self.assertEqual(self.put({'expected_owner':'bravo','chat':self.slot('x')}).status_code,422)
        self.assertEqual(self.put({'owner':'bravo','chat':self.slot('x')}).status_code,422)
        self.assertEqual(self.store.load('bravo')['slots'],{})

    def test_bad_slot_rolls_back_entire_patch(self):
        response=self.put({'chat':self.slot('mine'),'image':{'provider':'custom','base_url':'javascript:bad','model':'x'}})
        self.assertEqual(response.status_code,422);self.assertEqual(self.store.load('alpha')['slots'],{})
        self.assertEqual(self.put({'chat':{'provider':'none'}}).status_code,422)

    def test_http_clients_use_effective_owner_key_and_endpoint(self):
        for owner in ('alpha','bravo'):
            self.store.save(owner,{name:self.slot(owner+'-'+name,owner+'-key') for name in ('chat','background','image')})
        for owner in ('alpha','bravo'):
            with model_owner_scope(owner):
                for name in ('chat','background'):
                    client,http_client,slot=self.app.openai_client_for_slot(name,timeout=1)
                    try:self.assertEqual(client.api_key,owner+'-key');self.assertEqual(slot['model'],owner+'-'+name)
                    finally:http_client.close()
                self.assertEqual(self.app.image_slot_config()['model'],owner+'-image')

    def test_parallel_stream_requests_keep_owner_after_endpoint_returns(self):
        for owner in ('alpha','bravo'):self.store.save(owner,{'chat':self.slot(owner)})
        app=self.app
        @app.app.get('/_test/model-stream')
        def endpoint():
            def stream():
                for _ in range(4):yield json.dumps({'owner':current_model_owner(),'model':app.model_slot_config('chat')['model']})+'\n'
            return StreamingResponse(stream(),media_type='text/plain')
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app),base_url='http://test') as client:
                return await asyncio.gather(*(client.get('/_test/model-stream',headers=self.headers(device)) for device in ('alpha_one','bravo_one')))
        responses=asyncio.run(run())
        for owner,response in zip(('alpha','bravo'),responses):
            self.assertEqual(response.status_code,200)
            for line in response.text.splitlines():self.assertEqual(json.loads(line),{'owner':owner,'model':owner})

    def test_detached_threads_copy_and_reset_context_on_failure(self):
        seen=[]
        def work():seen.append(current_model_owner())
        with model_owner_scope('alpha'):target=bind_model_context(work)
        with model_owner_scope('bravo'):
            thread=threading.Thread(target=target);thread.start();thread.join()
            self.assertEqual(current_model_owner(),'bravo')
        self.assertEqual(seen,['alpha'])
        with self.assertRaises(ValueError):
            with model_owner_scope('alpha'):raise ValueError('test')
        self.assertEqual(current_model_owner(),'')

    def test_memory_job_uses_session_owner_instead_of_ambient_user(self):
        session=self.app.create_session('device:model_test_alpha_one','test')
        message=self.app.add_message(session,'user','我喜欢测试',hidden=False)
        job=self.app.enqueue_memory_agent_job(session,message,message,'test')
        observed=[]
        def source(*args):observed.append(current_model_owner());return []
        with model_owner_scope('bravo'),mock.patch.dict(self.ns,{'load_memory_agent_source_messages':source}):
            self.app.process_memory_agent_job(job);self.assertEqual(current_model_owner(),'bravo')
        self.assertEqual(observed,['alpha'])

    def test_idle_writer_uses_artifact_owner(self):
        seen=[]
        def can_run(**kwargs):seen.append(current_model_owner());return False,'idle_disabled'
        with model_owner_scope('bravo'),mock.patch.dict(self.ns,{'idle_writer_owner_shared_user_id':lambda:'alpha','idle_agent_can_run':can_run}):
            self.app.run_idle_agent_once();self.assertEqual(current_model_owner(),'bravo')
        self.assertEqual(seen,['alpha'])

    def test_memory_dedupe_is_grouped_by_user(self):
        pairs=[{'visitor_ip':'device:model_test_alpha_one'}, {'visitor_ip':'device:model_test_bravo_one'}];seen=[]
        def decide(items):seen.append((current_model_owner(),len(items)));return {'actions':[]}
        with mock.patch.dict(self.ns,{'memory_dedupe_agent_can_run':lambda **kwargs:(True,'idle'), 'load_memory_dedupe_candidate_pairs':lambda:pairs,
                                     'call_memory_dedupe_agent_model':decide,'mark_memory_dedupe_agent_run':lambda:None}):
            self.app.run_memory_dedupe_agent_once(force=True)
        self.assertEqual(seen,[('alpha',1),('bravo',1)])

    def test_owned_schedule_and_card_adapters_override_ambient_scope(self):
        seen=[]
        def decide(context):seen.append(current_model_owner());return {'operations':[],'reply':'没有改动'}
        with model_owner_scope('bravo'),mock.patch.dict(self.ns,{'schedule_agent_decision':decide,'membership_agent_decision':decide}):
            self.app.manage_schedule_message('alpha','查询','scope-schedule')
            self.app.manage_membership_message('alpha','查询','scope-member')
            self.assertEqual(current_model_owner(),'bravo')
        self.assertEqual(seen,['alpha','alpha'])

    def test_user_can_disable_images_without_local_detection(self):
        self.store.save('alpha',{'image':{'provider':'none'}})
        with model_owner_scope('alpha'),mock.patch.dict(self.ns,{'detect_local_image_generation_service':mock.Mock(side_effect=AssertionError('must not detect'))}):
            self.assertEqual(self.app.image_generation_status()['reason'],'disabled')

    def test_user_network_proxy_does_not_change_system_or_other_user(self):
        self.put({'web_search_proxy':'http://proxy.test:7890'})
        with model_owner_scope('alpha'):self.assertEqual(self.app.normalize_web_search_proxy(),'http://proxy.test:7890')
        with model_owner_scope('bravo'):self.assertNotEqual(self.app.load_model_settings()['web_search_proxy'],'http://proxy.test:7890')


if __name__=='__main__':unittest.main()
