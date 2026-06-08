import importlib
import base64
import io
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class AppBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["QWEN_WEB_DB"] = str(Path(self.tmpdir.name) / "chat_history.sqlite3")
        os.environ["QWEN_AUTH_CONFIG"] = str(Path(self.tmpdir.name) / "admin_auth.json")
        os.environ["QWEN_MODEL_BASE_URL"] = "http://127.0.0.1:8000/v1"
        os.environ["QWEN_MODEL_NAME"] = "qwen3.6-35b-a3b-262k"
        os.environ.pop("QWEN_MEMORY_ADMIN_PASSWORD", None)

        if "app" in sys.modules:
            del sys.modules["app"]
        self.app = importlib.import_module("app")
        self.app.init_db()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("QWEN_AUTH_CONFIG", None)
        if "app" in sys.modules:
            del sys.modules["app"]

    @staticmethod
    def _select_all_memory_candidates(*args, **kwargs):
        if "candidates" in kwargs:
            return list(kwargs["candidates"])
        return list(args[2]) if len(args) > 2 else []

    def _configure_admin_password(self, password: str = "test-admin-password") -> str:
        self.app.save_admin_password(password)
        return password

    def test_split_think_text_removes_reasoning_block(self):
        reasoning, answer = self.app.split_think_text("开头<think>内部推理</think>最终答案")

        self.assertEqual(reasoning, "内部推理")
        self.assertEqual(answer, "开头最终答案")

    def test_default_system_prompt_is_configured(self):
        self.assertIsInstance(self.app.SYSTEM_PROMPT, str)
        self.assertGreater(len(self.app.SYSTEM_PROMPT.strip()), 0)

    def test_auth_password_can_be_initialized_and_changed(self):
        client = TestClient(self.app.app)

        self.assertFalse(self.app.has_configured_admin_password())
        index_response = client.get("/", follow_redirects=False)
        self.assertEqual(index_response.status_code, 307)
        self.assertEqual(index_response.headers["location"], "/auth")

        setup_response = client.post(
            "/api/auth/password",
            json={"old_password": "", "new_password": "first-secret"},
        )
        self.assertEqual(setup_response.status_code, 200)
        self.assertTrue(self.app.verify_admin_password("first-secret"))

        wrong_old_response = client.post(
            "/api/auth/password",
            json={"old_password": "wrong", "new_password": "second-secret"},
        )
        self.assertEqual(wrong_old_response.status_code, 401)

        change_response = client.post(
            "/api/auth/password",
            json={"old_password": "first-secret", "new_password": "second-secret"},
        )
        self.assertEqual(change_response.status_code, 200)
        self.assertFalse(self.app.verify_admin_password("first-secret"))
        self.assertTrue(self.app.verify_admin_password("second-secret"))

    def test_think_stripper_suppresses_split_tags(self):
        stripper = self.app.ThinkStripper()

        visible = [
            stripper.feed("答案前缀 <thi"),
            stripper.feed("nk>隐藏"),
            stripper.feed("内容</th"),
            stripper.feed("ink> 答案后缀"),
            stripper.flush(),
        ]

        self.assertEqual("".join(visible), "答案前缀  答案后缀")

    def test_session_reset_soft_ends_old_session_and_keeps_messages(self):
        first = self.app.create_session("1.2.3.4", "agent-a")
        self.app.add_message(first, "user", "你好")

        second = self.app.reset_session(first, "1.2.3.4", "agent-a")

        self.assertNotEqual(first, second)
        old_session = self.app.get_session(first)
        self.assertEqual(old_session["end_reason"], "reset")
        self.assertIsNotNone(old_session["ended_at"])
        self.assertEqual(self.app.load_messages(first), [{"role": "user", "content": "你好"}])
        self.assertEqual(self.app.load_messages(second), [])

    def test_load_messages_keeps_completed_chat_order_only(self):
        session_id = self.app.create_session("5.6.7.8", "agent-b")
        self.app.add_message(session_id, "user", "第一条")
        self.app.add_message(session_id, "assistant", "第一答")
        self.app.add_message(session_id, "assistant", "失败答", status="failed")
        self.app.add_message(session_id, "user", "第二条")

        self.assertEqual(
            self.app.load_messages(session_id),
            [
                {"role": "user", "content": "第一条"},
                {"role": "assistant", "content": "第一答"},
                {"role": "user", "content": "第二条"},
            ],
        )

    def test_hidden_user_message_is_model_context_but_not_visible_history(self):
        session_id = self.app.create_session("device:dev_opening012345", "agent-opening")
        self.app.add_message(
            session_id,
            "user",
            "你有什么需要提醒我的吗？",
            hidden=True,
        )
        self.app.add_message(session_id, "assistant", "有什么会议或截止时间需要我记一下吗？")

        self.assertEqual(
            self.app.load_messages(session_id),
            [{"role": "assistant", "content": "有什么会议或截止时间需要我记一下吗？"}],
        )
        self.assertEqual(
            [item["content"] for item in self.app.load_model_messages(session_id)],
            ["你有什么需要提醒我的吗？", "有什么会议或截止时间需要我记一下吗？"],
        )

    def test_chat_payload_accepts_image_attachments(self):
        image_url = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
        )

        payload = self.app.ChatPayload(
            session_id="session-a",
            message="看图",
            attachments=[
                {
                    "name": "red.png",
                    "mime_type": "image/png",
                    "data_url": image_url,
                    "size": 68,
                }
            ],
        )

        self.assertEqual(len(payload.attachments), 1)
        self.assertEqual(payload.attachments[0].mime_type, "image/png")
        self.assertEqual(payload.attachments[0].data_url, image_url)

    def test_chat_payload_accepts_web_search_toggle(self):
        payload = self.app.ChatPayload(
            session_id="session-search",
            message="查一下今天的新闻",
            web_search=True,
            web_search_proxy="http://127.0.0.1:7890",
        )

        self.assertTrue(payload.web_search)
        self.assertEqual(payload.web_search_proxy, "http://127.0.0.1:7890")

    def test_build_web_search_query_removes_command_words(self):
        query = self.app.build_web_search_query("联网搜索 OpenAI news，用一句话回答。")

        self.assertEqual(query, "OpenAI news")

    def test_clean_search_result_url_unwraps_nested_h5_url(self):
        raw = (
            "https://article.zlink.toutiao.com/J4dQM?"
            "h5_url=http%3A%2F%2Fwww.eol.cn%2Fm%2Fgaokao%2F202506%2Ft20250607_2673233.shtml"
            "&keyword=2025%E5%B9%B4%E5%8C%97%E4%BA%AC"
        )

        self.assertEqual(
            self.app.clean_search_result_url(raw),
            "http://www.eol.cn/m/gaokao/202506/t20250607_2673233.shtml",
        )

    def test_search_result_filter_skips_search_pages_and_predictions(self):
        self.assertTrue(
            self.app.should_skip_search_result(
                "https://m.quark.cn/vsearch/news?q=2025%E5%B9%B4%E5%8C%97%E4%BA%AC",
                "2025年北京高考语文作文题目-资讯",
            )
        )
        self.assertTrue(
            self.app.should_skip_search_result(
                "https://toutiao.com/group/7512760056606769202/",
                "2025年高考北京卷语文作文预测",
            )
        )

    def test_search_urls_include_chinese_fallback_sources(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        body = source.split("def perform_general_web_search(", 1)[1].split("def parse_search_plan_response", 1)[0]

        self.assertIn("so.toutiao.com/search", body)
        self.assertIn("yz.m.sm.cn/s", body)
        self.assertIn("rank_search_results", body)

    def test_duckduckgo_is_primary_general_search_source(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        body = source.split("search_urls = [", 1)[1].split("]", 1)[0]

        self.assertLess(body.index("duckduckgo.com/html/"), body.index("so.toutiao.com/search"))
        self.assertLess(body.index("duckduckgo.com/html/"), body.index("cn.bing.com/search"))

    def test_search_plan_response_parser_extracts_queries(self):
        plan = self.app.parse_search_plan_response(
            '```json\n{"queries":["2026年6月5日 简中互联网 热搜","微博 百度 头条 热榜"],'
            '"required_terms":["2026年6月5日","简中互联网","热搜"],"rationale":"查多源热点"}\n```'
        )

        self.assertEqual(plan["queries"], ["2026年6月5日 简中互联网 热搜", "微博 百度 头条 热榜"])
        self.assertEqual(plan["required_terms"], ["2026年6月5日", "简中互联网", "热搜"])
        self.assertEqual(plan["rationale"], "查多源热点")

    def test_extract_hot_search_items_keeps_utf8_chinese_text(self):
        items = self.app.extract_hot_search_items(
            "百度实时热搜",
            '{"word":"高考安检新变化 多地提醒"},{"word":"中国小电驴在英国卖爆了"}',
        )

        self.assertEqual(items[:2], ["高考安检新变化 多地提醒", "中国小电驴在英国卖爆了"])

    def test_query_builder_does_not_add_topic_specific_priority_terms(self):
        query = self.app.build_web_search_query("去年北京高考作文题")

        self.assertIn("2025", query)
        self.assertIn("北京高考作文题", query)
        self.assertNotIn("北京教育考试院", query)

    def test_relative_year_query_is_normalized_before_search(self):
        query = self.app.build_web_search_query("前年北京高考英语作文题目是什么")

        self.assertIn("2024", query)
        self.assertIn("北京高考英语作文题目是什么", query)
        self.assertNotIn("前年", query)

    def test_fallback_search_plan_keeps_full_question_not_weak_temporal_word(self):
        plan = self.app.fallback_search_plan("前年北京高考英语作文题目是什么")

        self.assertEqual(plan["queries"], ["2024北京高考英语作文题目是什么"])
        self.assertFalse(any(query.strip() == "前年" for query in plan["queries"]))

    def test_search_plan_display_query_uses_planned_queries_not_raw_message(self):
        plan = {
            "queries": [
                "2025 北京高考数学真题",
                "2025 北京高考数学试卷 答案",
            ],
            "required_terms": ["2025", "北京", "数学"],
        }

        label = self.app.search_plan_display_query(plan, "去年的高考数学题目北京")

        self.assertEqual(label, "2025 北京高考数学真题；2025 北京高考数学试卷 答案")
        self.assertNotIn("去年的高考数学题目北京", label)

    def test_perform_web_search_reuses_existing_plan(self):
        calls = []
        original_build_plan = self.app.build_search_plan
        original_general_search = self.app.perform_general_web_search
        self.app.build_search_plan = lambda _query: self.fail("search plan should already be supplied")
        self.app.perform_general_web_search = lambda planned_query, **_kwargs: calls.append(planned_query) or [
            {
                "title": "2025 北京高考数学真题",
                "url": "https://example.com/math",
                "snippet": "2025 北京 高考 数学 真题",
            }
        ]
        try:
            results = self.app.perform_web_search(
                "去年的高考数学题目北京",
                search_plan={
                    "queries": ["2025 北京高考数学真题"],
                    "required_terms": ["2025", "北京", "数学"],
                },
            )
        finally:
            self.app.build_search_plan = original_build_plan
            self.app.perform_general_web_search = original_general_search

        self.assertEqual(calls, ["2025 北京高考数学真题"])
        self.assertEqual(results[0]["planned_query"], "2025 北京高考数学真题")

    def test_search_flow_has_no_topic_specific_route_calls(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("202506/t20250608_4108478.html", app_source)
        self.assertNotIn("authoritative_seed", app_source)
        perform_body = app_source.split("def perform_web_search(", 1)[1].split("def fetch_web_page_summary", 1)[0]
        self.assertNotIn("is_hot_search_query", perform_body)
        self.assertNotIn("is_youtube_trending_query", perform_body)
        self.assertNotIn("is_authoritative_fact_query", perform_body)
        self.assertNotIn("build_exam_search_queries", perform_body)

    def test_assign_source_registry_adds_ids_and_confidence(self):
        sources = self.app.assign_source_registry(
            [
                {
                    "title": "北京教育考试院发布北京高考作文题",
                    "url": "https://www.bjeea.cn/html/2025gaokao.html",
                    "page_excerpt": "2025年北京高考作文题包括……",
                }
            ]
        )

        self.assertEqual(sources[0]["source_id"], "S1")
        self.assertGreaterEqual(sources[0]["confidence"], self.app.WEB_SEARCH_MIN_CONFIDENCE)
        self.assertTrue(sources[0]["authority"])

    def test_required_terms_keep_score_page_out_of_answer_sources(self):
        required_terms = ["2025", "河北", "高考", "作文"]

        score_page_relevance = self.app.search_result_relevance(
            {
                "title": "2025 年高考分数线_阳光高考",
                "url": "https://gaokao.chsi.com.cn/z/gkbmfslq2025/pcx.jsp",
                "snippet": "2025年全国各省市高考录取控制分数线",
                "required_terms": required_terms,
            },
            "去年高考作文河北",
        )
        title_page_relevance = self.app.search_result_relevance(
            {
                "title": "2025年河北高考作文题目公布",
                "url": "https://example.com/hebei-gaokao-essay-2025",
                "snippet": "2025年河北高考语文作文题目及解析。",
                "required_terms": required_terms,
            },
            "去年高考作文河北",
        )

        self.assertLess(score_page_relevance, self.app.WEB_SEARCH_MIN_RELEVANCE)
        self.assertGreaterEqual(title_page_relevance, self.app.WEB_SEARCH_MIN_RELEVANCE)

    def test_required_terms_merge_planner_and_user_terms(self):
        terms = self.app.search_required_terms(
            "2025年北京卷语文作文是什么",
            {
                "queries": ["2025年北京高考语文试卷真题"],
                "required_terms": ["2025年", "北京", "语文", "高考"],
            },
        )

        self.assertIn("作文", terms)
        self.assertIn("北京", terms)
        self.assertIn("语文", terms)

    def test_low_relevance_source_is_not_used_in_context_or_footer(self):
        sources = self.app.assign_source_registry(
            [
                {
                    "title": "2025 年高考分数线_阳光高考",
                    "url": "https://gaokao.chsi.com.cn/z/gkbmfslq2025/pcx.jsp",
                    "snippet": "2025年全国各省市高考录取控制分数线",
                    "relevance": 0.4,
                    "confidence": 0.42,
                }
            ]
        )
        context = self.app.format_web_search_context(sources)
        answer = self.app.append_source_footer_if_missing("未找到可靠出处。", sources)

        self.assertFalse(sources[0]["used_in_answer"])
        self.assertIn("本轮搜索没有找到", context)
        self.assertIn("不要解释训练数据", context)
        self.assertIn("不要模拟、猜测或编造答案", context)
        self.assertIn("不要声称检索过来源列表中没有出现的网站或数据库", context)
        self.assertNotIn("2025 年高考分数线", context)
        self.assertEqual(answer, "未找到可靠出处。")

    def test_moderately_relevant_duckduckgo_result_is_used(self):
        sources = self.app.assign_source_registry(
            [
                {
                    "title": "2025年北京卷语文高考作文题目",
                    "url": "https://duck.example.com/beijing-essay",
                    "snippet": "北京卷语文作文题目整理，含试题材料。",
                    "required_terms": ["2025", "北京", "语文", "作文"],
                    "relevance": 0.5,
                    "confidence": 0.58,
                }
            ]
        )

        self.assertTrue(sources[0]["used_in_answer"])

    def test_toutiao_search_result_can_become_usable_source(self):
        sources = self.app.assign_source_registry(
            [
                {
                    "title": "2025年北京高考语文作文题出炉:第二次呼吸、当数字闪耀时",
                    "url": "http://www.eol.cn/m/gaokao/202506/t20250607_2673233.shtml",
                    "snippet": "2025年北京高考语文作文题目包括第二次呼吸、当数字闪耀时。",
                    "required_terms": ["2025年", "北京", "语文", "高考"],
                    "relevance": 1.0,
                    "confidence": 0.75,
                }
            ]
        )
        context = self.app.format_web_search_context(sources)

        self.assertTrue(sources[0]["used_in_answer"])
        self.assertIn("2025年北京高考语文作文题", context)
        self.assertIn("eol.cn", context)

    def test_format_web_search_context_includes_search_results(self):
        context = self.app.format_web_search_context(
            [
                {
                    "title": "Example Result",
                    "url": "https://example.com/a",
                    "snippet": "A concise snippet.",
                }
            ]
        )

        self.assertIn("联网搜索参考", context)
        self.assertIn("Example Result", context)
        self.assertIn("https://example.com/a", context)
        self.assertIn("A concise snippet.", context)
        self.assertIn("[S1]", context)

    def test_web_search_context_forbids_redirecting_user_to_platforms(self):
        context = self.app.format_web_search_context(
            [
                {
                    "title": "微博热搜 示例",
                    "url": "https://s.weibo.com/top/summary",
                    "snippet": "示例热点",
                }
            ]
        )

        self.assertIn("禁止让用户自行去微博", context)
        self.assertIn("必须基于已抓取到的条目回答", context)

    def test_append_source_footer_when_answer_has_no_markdown_links(self):
        answer = self.app.append_source_footer_if_missing(
            "这是根据资料整理的答案。",
            [
                {
                    "source_id": "S1",
                    "title": "北京教育考试院",
                    "url": "https://www.bjeea.cn/",
                    "used_in_answer": True,
                }
            ],
        )

        self.assertIn("## 来源", answer)
        self.assertIn("[S1 北京教育考试院](https://www.bjeea.cn/)", answer)

    def test_source_footer_skips_unusable_low_relevance_sources(self):
        answer = self.app.append_source_footer_if_missing(
            "未找到可靠出处。",
            [
                {
                    "source_id": "S1",
                    "title": "前年 百度百科",
                    "url": "https://baike.baidu.com/item/%E5%89%8D%E5%B9%B4",
                    "used_in_answer": False,
                    "relevance": 0.0,
                }
            ],
        )

        self.assertEqual(answer, "未找到可靠出处。")

    def test_idle_artifacts_are_not_written_to_curated_memories(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        save_body = source.split("def save_idle_agent_artifact(", 1)[1].split("def compact_idle_artifact_content", 1)[0]

        self.assertNotIn("create_artifact_memory(", save_body)
        self.assertIn("DELETE FROM curated_memories", source)
        self.assertIn("importance_label = 'artifact'", source)

    def test_memory_agent_checks_similarity_before_saving(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        process_body = source.split("def process_memory_agent_job(", 1)[1].split("def enqueue_unprocessed_memory_agent_jobs", 1)[0]

        self.assertIn("find_similar_curated_memory", process_body)
        self.assertIn("MEMORY_WRITE_DEDUPE_THRESHOLD", process_body)
        self.assertIn("duplicate_memory", process_body)

    def test_current_date_context_uses_configured_timezone(self):
        context = self.app.current_date_context(datetime(2026, 6, 5, 9, 30))

        self.assertIn("当前真实日期", context)
        self.assertIn("2026年6月5日", context)
        self.assertIn("星期五", context)
        self.assertIn("Asia/Shanghai", context)
        self.assertIn("训练数据", context)

    def test_system_prompt_can_include_web_search_context(self):
        session_id = self.app.create_session("7.7.7.7", "agent-search")

        prompt = self.app.build_system_prompt(
            session_id=session_id,
            user_message="查一下外部资料",
            visitor_ip="7.7.7.7",
            web_search_context="联网搜索参考：Example",
        )

        self.assertIn("联网搜索参考：Example", prompt)

    def test_web_search_prompt_suppresses_memory_context(self):
        session_id = self.app.create_session("7.7.7.7", "agent-search-memory")
        memory_id = self.app.save_curated_memory(
            source_session_id="old-memory",
            start_message_id=1,
            end_message_id=2,
            content="长期记忆里有一个无关但很容易污染事实检索的问题答案。",
            importance_label="other",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")
        run_id = self.app.create_idle_agent_run("notes", "测试任务", "基于摘要生成")
        self.app.save_idle_agent_artifact(
            run_id=run_id,
            title="无关成果",
            artifact_type="notes",
            content="空闲成果里也有一个无关事实。",
        )

        original_embed_text = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        try:
            prompt = self.app.build_system_prompt(
                session_id=session_id,
                user_message="检索某个学术论文成果",
                visitor_ip="7.7.7.7",
                web_search_context="联网搜索参考：本轮没有可靠来源。",
            )
        finally:
            self.app.embedding_client.embed_text = original_embed_text

        self.assertIn("联网搜索参考", prompt)
        self.assertNotIn("已整理长期记忆", prompt)
        self.assertNotIn("长期记忆里有一个无关", prompt)
        self.assertNotIn("空闲创作成果", prompt)
        self.assertNotIn("无关成果", prompt)

    def test_system_prompt_includes_current_date_context(self):
        session_id = self.app.create_session("7.7.7.7", "agent-date")

        prompt = self.app.build_system_prompt(
            session_id=session_id,
            user_message="今天是几号？",
            visitor_ip="7.7.7.7",
        )

        self.assertIn("当前真实日期", prompt)
        self.assertIn("如果用户询问今天", prompt)

    def test_model_messages_include_image_url_parts(self):
        session_id = self.app.create_session("5.5.5.5", "agent-mm")
        image_url = (
            "data:image/png;base64,"
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADUlEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
        )
        attachment = self.app.ChatAttachment(
            name="red.png",
            mime_type="image/png",
            data_url=image_url,
            size=68,
        )

        message_id = self.app.add_message(
            session_id,
            "user",
            "这是什么颜色？",
            attachments=[attachment],
        )
        messages = self.app.load_model_messages(session_id)

        self.assertEqual(message_id, 1)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(
            messages[0]["content"],
            [
                {"type": "text", "text": "这是什么颜色？"},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        )

    def test_web_search_model_messages_use_current_turn_only(self):
        session_id = self.app.create_session("5.5.5.5", "agent-search-isolate")
        self.app.add_message(session_id, "user", "去年高考作文河北")
        self.app.add_message(session_id, "assistant", "错误地回答了作文。")
        self.app.add_message(session_id, "user", "去年的高考数学题目北京")

        messages = self.app.build_model_messages_for_request(
            session_id=session_id,
            current_message="去年的高考数学题目北京",
            attachments=[],
            isolate_history=True,
        )

        self.assertEqual(messages, [{"role": "user", "content": "去年的高考数学题目北京"}])

    def test_regular_model_messages_keep_session_history(self):
        session_id = self.app.create_session("5.5.5.5", "agent-history")
        self.app.add_message(session_id, "user", "第一轮")
        self.app.add_message(session_id, "assistant", "第一答")
        self.app.add_message(session_id, "user", "第二轮")

        messages = self.app.build_model_messages_for_request(
            session_id=session_id,
            current_message="第二轮",
            attachments=[],
            isolate_history=False,
        )

        self.assertEqual(
            [item["content"] for item in messages],
            ["第一轮", "第一答", "第二轮"],
        )

    def test_current_date_context_includes_precise_local_time_for_reminders(self):
        now = datetime(2026, 6, 8, 14, 35)

        context = self.app.current_date_context(now)

        self.assertIn("2026年6月8日", context)
        self.assertIn("14:35", context)
        self.assertIn("如果用户提到开会", context)

    def test_image_attachment_accepts_jpg_jpeg_alias(self):
        session_id = self.app.create_session("5.5.5.5", "agent-jpg")
        jpeg_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2w=="
        attachment = self.app.ChatAttachment(
            name="photo.jpg",
            mime_type="image/jpg",
            data_url=jpeg_url,
            size=24,
        )

        self.app.add_message(
            session_id,
            "user",
            "看这张 JPG",
            attachments=[attachment],
        )
        messages = self.app.load_model_messages(session_id)

        self.assertEqual(
            messages[0]["content"],
            [
                {"type": "text", "text": "看这张 JPG"},
                {"type": "image_url", "image_url": {"url": jpeg_url}},
            ],
        )

    def test_large_image_attachment_is_compressed_before_model_context(self):
        from PIL import Image

        session_id = self.app.create_session("5.5.5.5", "agent-large-image")
        image = Image.effect_noise((900, 900), 96).convert("RGB")
        raw = io.BytesIO()
        image.save(raw, format="PNG")
        raw_bytes = raw.getvalue()
        data_url = "data:image/png;base64," + base64.b64encode(raw_bytes).decode("ascii")

        original_target = self.app.IMAGE_COMPRESSION_TARGET_BYTES
        original_trigger = self.app.IMAGE_COMPRESSION_TRIGGER_BYTES
        original_max_side = self.app.IMAGE_COMPRESSION_MAX_SIDE
        try:
            self.app.IMAGE_COMPRESSION_TARGET_BYTES = 60 * 1024
            self.app.IMAGE_COMPRESSION_TRIGGER_BYTES = 8 * 1024
            self.app.IMAGE_COMPRESSION_MAX_SIDE = 512
            self.app.add_message(
                session_id,
                "user",
                "看这张大图",
                attachments=[
                    self.app.ChatAttachment(
                        name="large.png",
                        mime_type="image/png",
                        data_url=data_url,
                        size=len(raw_bytes),
                    )
                ],
            )
        finally:
            self.app.IMAGE_COMPRESSION_TARGET_BYTES = original_target
            self.app.IMAGE_COMPRESSION_TRIGGER_BYTES = original_trigger
            self.app.IMAGE_COMPRESSION_MAX_SIDE = original_max_side

        with self.app.connect_db() as conn:
            row = conn.execute("SELECT metadata_json FROM messages WHERE session_id = ?", (session_id,)).fetchone()
        metadata = json.loads(row["metadata_json"])
        attachment = metadata["attachments"][0]
        compressed_payload = attachment["data_url"].split(",", 1)[1]
        compressed_bytes = base64.b64decode(compressed_payload)
        compressed_image = Image.open(io.BytesIO(compressed_bytes))

        self.assertTrue(attachment["compressed"])
        self.assertEqual(attachment["mime_type"], "image/jpeg")
        self.assertLess(attachment["size"], len(raw_bytes))
        self.assertLessEqual(max(compressed_image.size), 512)
        self.assertEqual(
            self.app.load_model_messages(session_id)[0]["content"][1]["image_url"]["url"],
            attachment["data_url"],
        )

    def test_system_prompt_does_not_inject_raw_history_as_memory(self):
        old_session = self.app.create_session("9.9.9.9", "agent-old")
        self.app.add_message(old_session, "user", "我之前讨论过 Qwen 记忆模块和网页部署。")
        new_session = self.app.create_session("8.8.8.8", "agent-new")

        prompt = self.app.build_system_prompt(
            session_id=new_session,
            user_message="还记得 Qwen 记忆模块怎么做吗？",
            visitor_ip="8.8.8.8",
        )

        self.assertIn(self.app.SYSTEM_PROMPT, prompt)
        self.assertNotIn("相关历史片段", prompt)
        self.assertNotIn("Qwen 记忆模块", prompt)
        self.assertNotIn(old_session, prompt)
        self.assertNotIn("9.9.9.9", prompt)
        self.assertIn("8.8.8.8", prompt)

    def test_known_ip_adds_identity_context_to_system_prompt(self):
        identity = "device:dev_known0123456789"
        old_session = self.app.create_session(identity, "agent-known-a")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="这个来访者喜欢黑色幽默和简短回答。",
            importance_label="preference",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")
        new_session = self.app.create_session(identity, "agent-known-b")

        original_embed_text = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        original_gate = self.app.should_use_memory_recall
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.judge_curated_memories_with_qwen = self._select_all_memory_candidates
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        try:
            prompt = self.app.build_system_prompt(new_session, "我的回答风格偏好是什么", identity)
        finally:
            self.app.embedding_client.embed_text = original_embed_text
            self.app.judge_curated_memories_with_qwen = original_judge
            self.app.should_use_memory_recall = original_gate

        self.assertIn(f"当前浏览器身份：{identity}", prompt)
        self.assertIn("熟悉的来访者", prompt)
        self.assertIn("黑色幽默", prompt)

    def test_new_ip_is_marked_as_unfamiliar_without_other_ip_memories(self):
        old_session = self.app.create_session("5.5.5.5", "agent-old-ip")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="旧 IP 的专属记忆不应直接给陌生 IP。",
            importance_label="identity",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")
        new_session = self.app.create_session("4.4.4.4", "agent-new-ip")

        original_embed_text = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.judge_curated_memories_with_qwen = self._select_all_memory_candidates
        try:
            prompt = self.app.build_system_prompt(new_session, "你认识我吗", "4.4.4.4")
        finally:
            self.app.embedding_client.embed_text = original_embed_text
            self.app.judge_curated_memories_with_qwen = original_judge

        self.assertIn("当前浏览器身份：4.4.4.4", prompt)
        self.assertIn("陌生来访者", prompt)
        self.assertNotIn("5.5.5.5", prompt)
        self.assertNotIn("旧 IP 的专属记忆", prompt)

    def test_backfill_visitor_profiles_links_existing_session_memories_to_ip(self):
        identity = "device:dev_backfill012345"
        session_id = self.app.create_session(identity, "agent-backfill")
        memory_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="回填时应挂到浏览器身份的来访者画像。",
            importance_label="identity",
        )
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE curated_memories SET visitor_ip = NULL, profile_id = NULL WHERE id = ?",
                (memory_id,),
            )

        result = self.app.backfill_visitor_memory_links()

        self.assertGreaterEqual(result["updated_memories"], 1)
        with self.app.connect_db() as conn:
            row = conn.execute(
                "SELECT visitor_ip, profile_id FROM curated_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        self.assertEqual(row["visitor_ip"], identity)
        self.assertIsNotNone(row["profile_id"])

    def test_system_prompt_uses_compressed_vector_memory_not_raw_assistant_text(self):
        identity = "device:dev_compress012345"
        old_session = self.app.create_session(identity, "agent-compress-old")
        session_id = self.app.create_session(identity, "agent-compress")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户曾测试 abc 这类短输入；回答时应重新组织，不要复读历史模板。",
            importance_label="rule",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")

        original_embed_text = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        original_compress = getattr(self.app, "compress_memory_segments")
        original_gate = self.app.should_use_memory_recall
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.judge_curated_memories_with_qwen = self._select_all_memory_candidates
        self.app.compress_memory_segments = lambda *_args, **_kwargs: self.fail("sync compressor should not run")
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        try:
            prompt = self.app.build_system_prompt(session_id, "之前 abc 的回复规则是什么", identity)
        finally:
            self.app.embedding_client.embed_text = original_embed_text
            self.app.judge_curated_memories_with_qwen = original_judge
            self.app.compress_memory_segments = original_compress
            self.app.should_use_memory_recall = original_gate

        self.assertIn("已整理长期记忆", prompt)
        self.assertIn("用户曾测试 abc", prompt)
        self.assertNotIn("[assistant]", prompt)

    def test_memory_compressor_uses_cache_for_same_segments(self):
        calls = []
        original_call = self.app.call_memory_compressor_model
        self.app.call_memory_compressor_model = lambda user_message, source: calls.append(source) or "摘要：缓存测试"
        segments = [{"id": 1, "score": 0.9, "content": "[user] abc\n[assistant] 历史模板"}]
        try:
            first = self.app.compress_memory_segments("abc", segments)
            second = self.app.compress_memory_segments("abc", segments)
        finally:
            self.app.call_memory_compressor_model = original_call

        self.assertEqual(first, "摘要：缓存测试")
        self.assertEqual(second, "摘要：缓存测试")
        self.assertEqual(len(calls), 1)

    def test_curated_memory_retrieval_limits_top_k(self):
        original_top_k = self.app.CURATED_MEMORY_TOP_K
        self.app.CURATED_MEMORY_TOP_K = 2
        identity = "device:dev_topk012345678"
        try:
            for index in range(4):
                old_session = self.app.create_session(identity, f"agent-topk-{index}")
                memory_id = self.app.save_curated_memory(
                    source_session_id=old_session,
                    start_message_id=index * 2 + 1,
                    end_message_id=index * 2 + 2,
                    content=f"长期记忆 {index}",
                    importance_label="other",
                )
                self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")

            memories = self.app.retrieve_curated_memories([1.0, 0.0], current_visitor_ip=identity)
        finally:
            self.app.CURATED_MEMORY_TOP_K = original_top_k

        self.assertEqual(len(memories), 2)

    def test_memory_text_filter_rejects_conflicting_subject_memory(self):
        self.assertEqual(
            self.app.memory_text_relevance(
                "去年北京高考语文作文是什么",
                "用户之前询问过 2025 年北京高考数学真题和答案。",
            ),
            0.0,
        )
        self.assertGreater(
            self.app.memory_text_relevance(
                "去年北京高考语文作文是什么",
                "用户之前询问过 2025 年北京高考语文作文题目。",
            ),
            0.4,
        )

    def test_memory_text_filter_matches_food_preference_semantics(self):
        self.assertGreaterEqual(
            self.app.memory_text_relevance(
                "用户最喜欢的食物偏好",
                "用户最喜欢吃冰激凌。",
            ),
            self.app.MEMORY_TEXT_MIN_RELEVANCE,
        )

    def test_curated_memory_retrieval_filters_conflicting_text_after_vector_recall(self):
        identity = "device:dev_filter01234567"
        math_session = self.app.create_session(identity, "agent-memory-filter-math")
        chinese_session = self.app.create_session(identity, "agent-memory-filter-chinese")
        session_id = self.app.create_session(identity, "agent-memory-filter")
        math_memory = self.app.save_curated_memory(
            source_session_id=math_session,
            start_message_id=1,
            end_message_id=2,
            content="用户之前询问过 2025 年北京高考数学真题和答案。",
            importance_label="other",
        )
        chinese_memory = self.app.save_curated_memory(
            source_session_id=chinese_session,
            start_message_id=3,
            end_message_id=4,
            content="用户之前询问过 2025 年北京高考语文作文题目。",
            importance_label="other",
        )
        self.app.upsert_curated_memory_vector(math_memory, [1.0, 0.0], "test-embedding")
        self.app.upsert_curated_memory_vector(chinese_memory, [1.0, 0.0], "test-embedding")

        memories = self.app.retrieve_curated_memories(
            [1.0, 0.0],
            current_session_id=session_id,
            current_visitor_ip=identity,
            query_text="去年北京高考语文作文是什么",
        )

        contents = [str(item["content"]) for item in memories]
        self.assertTrue(any("语文作文" in content for content in contents))
        self.assertFalse(any("数学真题" in content for content in contents))

    def test_curated_memory_retrieval_keeps_high_vector_food_candidate(self):
        identity = "device:dev_food0123456789"
        old_session = self.app.create_session(identity, "agent-food-memory-old")
        session_id = self.app.create_session(identity, "agent-food-memory")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户最喜欢吃冰激凌。",
            importance_label="preference",
        )
        self.app.upsert_curated_memory_vector(memory_id, [0.73, 0.683447], "test-embedding")

        memories = self.app.retrieve_curated_memories(
            [1.0, 0.0],
            current_session_id=session_id,
            current_visitor_ip=identity,
            query_text="用户最喜欢的食物偏好",
        )
        candidates = self.app.explain_curated_memory_candidates(
            [1.0, 0.0],
            current_session_id=session_id,
            current_visitor_ip=identity,
            query_text="用户最喜欢的食物偏好",
        )

        self.assertTrue(any("冰激凌" in str(item["content"]) for item in memories))
        self.assertEqual(candidates[0]["filter_reason"], "selected")

    def test_curated_memory_recall_pool_rejects_candidates_below_score_floor(self):
        session_id = self.app.create_session("7.7.7.7", "agent-recall-pool")
        memory_id = self.app.save_curated_memory(
            source_session_id="old-broad-memory",
            start_message_id=1,
            end_message_id=2,
            content="用户曾说同学聚会让他想起某个冷笑话。",
            importance_label="other",
        )
        self.app.upsert_curated_memory_vector(memory_id, [0.2, 0.979796], "test-embedding")

        candidates = self.app.retrieve_curated_memory_recall_pool(
            [1.0, 0.0],
            current_session_id=session_id,
            current_visitor_ip="7.7.7.7",
            query_text="用户最近提到了同学聚会",
        )

        self.assertFalse(any(int(item["id"]) == memory_id for item in candidates))
        self.assertGreaterEqual(self.app.CURATED_MEMORY_MIN_SCORE, 0.5)

    def test_parse_memory_judge_response_filters_unknown_ids(self):
        decision = self.app.parse_memory_judge_response(
            '{"selected_ids":[2,999,"bad",2],"rationale":"只选相关记忆"}',
            [1, 2, 3],
        )

        self.assertEqual(decision["selected_ids"], [2])
        self.assertIn("相关", decision["rationale"])

    def test_build_system_prompt_uses_qwen_memory_judge_selection(self):
        identity = "device:dev_judge01234567"
        selected_session = self.app.create_session(identity, "agent-judge-selected")
        rejected_session = self.app.create_session(identity, "agent-judge-rejected")
        session_id = self.app.create_session(identity, "agent-judge-selection")
        selected_id = self.app.save_curated_memory(
            source_session_id=selected_session,
            start_message_id=1,
            end_message_id=2,
            content="用户最喜欢吃冰激凌。",
            importance_label="preference",
        )
        rejected_id = self.app.save_curated_memory(
            source_session_id=rejected_session,
            start_message_id=3,
            end_message_id=4,
            content="用户之前问过数学试卷。",
            importance_label="other",
        )
        self.app.upsert_curated_memory_vector(selected_id, [1.0, 0.0], "test-embedding")
        self.app.upsert_curated_memory_vector(rejected_id, [1.0, 0.0], "test-embedding")

        original_planner = self.app.build_memory_retrieval_query
        original_embed = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        original_gate = self.app.should_use_memory_recall
        debug = {}
        self.app.build_memory_retrieval_query = lambda *_args, **_kwargs: "用户 食物 偏好 喜欢"
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True

        def fake_judge(*_args, **kwargs):
            return [item for item in kwargs["candidates"] if int(item["id"]) == selected_id]

        self.app.judge_curated_memories_with_qwen = fake_judge
        try:
            prompt = self.app.build_system_prompt(
                session_id,
                "我最喜欢吃什么",
                identity,
                memory_debug=debug,
            )
        finally:
            self.app.build_memory_retrieval_query = original_planner
            self.app.embedding_client.embed_text = original_embed
            self.app.judge_curated_memories_with_qwen = original_judge
            self.app.should_use_memory_recall = original_gate

        self.assertIn("冰激凌", prompt)
        self.assertNotIn("数学试卷", prompt)
        self.assertEqual(debug["selected_count"], 1)
        self.assertGreaterEqual(debug["candidate_count"], 2)

    def test_memory_gate_skips_recall_for_unrelated_chat(self):
        session_id = self.app.create_session("device:dev_gate0123456789", "agent-gate")
        memory_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户有一个只属于旧历史的灰色狐狸暗号。",
            importance_label="identity",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")

        original_gate = self.app.should_use_memory_recall
        original_embed_text = self.app.embedding_client.embed_text
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        self.app.embedding_client.embed_text = lambda _text: self.fail("memory embedding should be skipped")
        debug = {}
        try:
            prompt = self.app.build_system_prompt(
                session_id,
                "讲个普通笑话",
                "device:dev_gate0123456789",
                memory_debug=debug,
            )
        finally:
            self.app.should_use_memory_recall = original_gate
            self.app.embedding_client.embed_text = original_embed_text

        self.assertNotIn("已整理长期记忆", prompt)
        self.assertEqual(debug["memory_gate"], "skipped")

    def test_history_memories_are_not_used_as_global_recall(self):
        session_id = self.app.create_session("device:dev_history0123456789", "agent-history")
        history_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户有一个只属于旧历史的灰色狐狸暗号。",
            importance_label="identity",
        )
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE curated_memories SET visitor_ip = NULL, profile_id = NULL WHERE id = ?",
                (history_id,),
            )
        self.app.upsert_curated_memory_vector(history_id, [1.0, 0.0], "test-embedding")

        original_gate = self.app.should_use_memory_recall
        original_embed_text = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.judge_curated_memories_with_qwen = self._select_all_memory_candidates
        try:
            prompt = self.app.build_system_prompt(
                session_id,
                "我是谁",
                "device:dev_history0123456789",
            )
        finally:
            self.app.should_use_memory_recall = original_gate
            self.app.embedding_client.embed_text = original_embed_text
            self.app.judge_curated_memories_with_qwen = original_judge

        self.assertNotIn("已整理长期记忆", prompt)
        self.assertNotIn("测试身份A", prompt)

    def test_duplicate_check_ignores_history_memories(self):
        session_id = self.app.create_session("device:dev_dupe0123456789", "agent-dupe")
        history_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户自称是测试身份A。",
            importance_label="identity",
        )
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE curated_memories SET visitor_ip = NULL, profile_id = NULL WHERE id = ?",
                (history_id,),
            )
        self.app.upsert_curated_memory_vector(history_id, [1.0, 0.0], "test-embedding")

        similar = self.app.find_similar_curated_memory([1.0, 0.0], "identity")

        self.assertIsNone(similar)

    def test_active_recall_context_ignores_history_memories(self):
        identity = "device:dev_active01234567"
        session_id = self.app.create_session(identity, "agent-active")
        history_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户自称是测试身份A。",
            importance_label="identity",
        )
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE curated_memories SET visitor_ip = NULL, profile_id = NULL WHERE id = ?",
                (history_id,),
            )

        context = self.app.build_active_recall_context(session_id, identity)

        self.assertNotIn("测试身份A", context)

    def test_idle_prompt_ignores_history_memories(self):
        identity = "device:dev_idlehistory0123"
        session_id = self.app.create_session(identity, "agent-idle-history")
        history_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户有一个只属于旧历史的灰色狐狸暗号。",
            importance_label="identity",
        )
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE curated_memories SET visitor_ip = NULL, profile_id = NULL WHERE id = ?",
                (history_id,),
            )

        system_prompt, user_prompt = self.app.build_idle_agent_prompt()

        self.assertNotIn("灰色狐狸暗号", system_prompt)
        self.assertNotIn("灰色狐狸暗号", user_prompt)

    def test_system_prompt_uses_curated_memory_without_sync_compressor(self):
        identity = "device:dev_curated012345"
        old_session = self.app.create_session(identity, "agent-curated-old")
        session_id = self.app.create_session(identity, "agent-curated")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户喜欢把助手叫作旺财；这是长期称呼偏好。",
            importance_label="preference",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")

        original_embed_text = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        original_compress = self.app.compress_memory_segments
        original_gate = self.app.should_use_memory_recall
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.judge_curated_memories_with_qwen = self._select_all_memory_candidates
        self.app.compress_memory_segments = lambda *_args, **_kwargs: self.fail("sync compressor should not run")
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        try:
            prompt = self.app.build_system_prompt(session_id, "我之前喜欢怎么称呼你？", identity)
        finally:
            self.app.embedding_client.embed_text = original_embed_text
            self.app.judge_curated_memories_with_qwen = original_judge
            self.app.compress_memory_segments = original_compress
            self.app.should_use_memory_recall = original_gate

        self.assertIn("已整理长期记忆", prompt)
        self.assertIn("旺财", prompt)

    def test_system_prompt_always_injects_assistant_style_preference(self):
        identity = "device:dev_stylepref0123"
        old_session = self.app.create_session(identity, "agent-style-old")
        session_id = self.app.create_session(identity, "agent-style")
        self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户希望助手的回复更加调皮一些。",
            importance_label="preference",
            confidence=0.92,
        )

        original_gate = self.app.should_use_memory_recall
        original_embed = self.app.embedding_client.embed_text
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        self.app.embedding_client.embed_text = lambda _text: self.fail("profile preference should not need memory embedding")
        try:
            prompt = self.app.build_system_prompt(session_id, "讲个普通笑话", identity)
        finally:
            self.app.should_use_memory_recall = original_gate
            self.app.embedding_client.embed_text = original_embed

        self.assertIn("当前用户稳定画像", prompt)
        self.assertIn("更加调皮", prompt)
        self.assertIn("每轮都应参考", prompt)

    def test_system_prompt_does_not_always_inject_fact_like_food_preference(self):
        identity = "device:dev_foodfact012345"
        old_session = self.app.create_session(identity, "agent-food-fact-old")
        session_id = self.app.create_session(identity, "agent-food-fact")
        self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户最喜欢吃冰激凌。",
            importance_label="preference",
            confidence=0.9,
        )

        original_gate = self.app.should_use_memory_recall
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        try:
            prompt = self.app.build_system_prompt(session_id, "讲个普通笑话", identity)
        finally:
            self.app.should_use_memory_recall = original_gate

        self.assertNotIn("当前用户稳定画像", prompt)
        self.assertNotIn("冰激凌", prompt)

    def test_system_prompt_falls_back_to_text_memory_when_embedding_is_down(self):
        identity = "device:dev_textfallback01"
        old_session = self.app.create_session(identity, "agent-curated-old")
        session_id = self.app.create_session(identity, "agent-curated")
        self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户最喜欢吃火锅，这是稳定饮食偏好。",
            importance_label="preference",
        )

        original_embed_text = self.app.embedding_client.embed_text
        original_planner = self.app.build_memory_retrieval_query
        original_gate = self.app.should_use_memory_recall
        self.app.embedding_client.embed_text = lambda _text: (_ for _ in ()).throw(ConnectionError("down"))
        self.app.build_memory_retrieval_query = lambda *_args, **_kwargs: "用户 食物 偏好 喜欢"
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        try:
            prompt = self.app.build_system_prompt(session_id, "我最喜欢吃什么", identity)
        finally:
            self.app.embedding_client.embed_text = original_embed_text
            self.app.build_memory_retrieval_query = original_planner
            self.app.should_use_memory_recall = original_gate

        self.assertIn("已整理长期记忆", prompt)
        self.assertIn("火锅", prompt)

    def test_system_prompt_does_not_use_legacy_history_fallback_when_curated_results_empty(self):
        old_session = self.app.create_session("7.7.7.7", "agent-old-history")
        self.app.add_message(old_session, "user", "怎么在胡同里优雅飙车")
        session_id = self.app.create_session("7.7.7.7", "agent-no-legacy-memory")
        original_planner = self.app.build_memory_retrieval_query
        original_embed = self.app.embedding_client.embed_text
        original_recall_pool = self.app.retrieve_curated_memory_recall_pool
        original_artifacts = self.app.retrieve_idle_artifacts
        self.app.build_memory_retrieval_query = lambda *_args, **_kwargs: "用户 关于 联系 飙车"
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.retrieve_curated_memory_recall_pool = lambda *_args, **_kwargs: []
        self.app.retrieve_idle_artifacts = lambda *_args, **_kwargs: []
        try:
            prompt = self.app.build_system_prompt(
                session_id,
                "怎么联系飙车",
                "7.7.7.7",
                analysis_trace_id="trace-no-legacy-memory",
            )
        finally:
            self.app.build_memory_retrieval_query = original_planner
            self.app.embedding_client.embed_text = original_embed
            self.app.retrieve_curated_memory_recall_pool = original_recall_pool
            self.app.retrieve_idle_artifacts = original_artifacts

        traces = self.app.list_analysis_traces(session_id=session_id, trace_id="trace-no-legacy-memory")

        self.assertNotIn("相关历史片段", prompt)
        self.assertNotIn("胡同里优雅飙车", prompt)
        self.assertFalse(any(item["step_name"] == "legacy_memory_context" for item in traces))

    def test_queue_memory_agent_job_records_pending_turn(self):
        session_id = self.app.create_session("7.7.7.7", "agent-job")
        user_id = self.app.add_message(session_id, "user", "我喜欢冰激凌")
        assistant_id = self.app.add_message(session_id, "assistant", "记住了。")

        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        with self.app.connect_db() as conn:
            row = conn.execute("SELECT * FROM memory_agent_jobs WHERE id = ?", (job_id,)).fetchone()
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["session_id"], session_id)
        self.assertEqual(row["start_message_id"], user_id)
        self.assertEqual(row["end_message_id"], assistant_id)

    def test_memory_agent_job_saves_important_memory_and_vector(self):
        session_id = self.app.create_session("7.7.7.7", "agent-worker")
        user_id = self.app.add_message(session_id, "user", "我喜欢冰激凌")
        assistant_id = self.app.add_message(session_id, "assistant", "记住了。")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        original_call = self.app.call_memory_agent_model
        original_embed = self.app.embedding_client.embed_text
        self.app.call_memory_agent_model = lambda _source: {
            "important": True,
            "memory": "用户明确表示喜欢冰激凌。",
            "label": "preference",
        }
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        try:
            result = self.app.process_memory_agent_job(job_id)
        finally:
            self.app.call_memory_agent_model = original_call
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(result["status"], "completed")
        with self.app.connect_db() as conn:
            memory_row = conn.execute("SELECT content FROM curated_memories").fetchone()
            vector_count = conn.execute("SELECT COUNT(*) AS c FROM curated_memory_vectors").fetchone()["c"]
            job_row = conn.execute("SELECT status FROM memory_agent_jobs WHERE id = ?", (job_id,)).fetchone()

        self.assertIn("冰激凌", memory_row["content"])
        self.assertEqual(vector_count, 1)
        self.assertEqual(job_row["status"], "completed")

    def test_memory_agent_job_saves_future_events_as_separate_event_memories(self):
        identity = "device:dev_events012345"
        session_id = self.app.create_session(identity, "agent-worker-events")
        user_id = self.app.add_message(
            session_id,
            "user",
            "我周三上午10-12点有组会，周五晚上有演出，记得提醒我。",
        )
        assistant_id = self.app.add_message(session_id, "assistant", "记下了。")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        original_call = self.app.call_memory_agent_model
        original_embed = self.app.embedding_client.embed_text
        self.app.call_memory_agent_model = lambda _source: {
            "important": True,
            "items": [
                {
                    "memory": "用户周三上午10:00-12:00有组会。",
                    "label": "event",
                    "timeline_at": "2026-06-10T10:00:00+08:00",
                    "confidence": 0.9,
                },
                {
                    "memory": "用户周五晚上有演出，需要提前处理请假或排期。",
                    "label": "event",
                    "timeline_at": "2026-06-12T19:00:00+08:00",
                    "confidence": 0.85,
                },
            ],
        }
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        try:
            result = self.app.process_memory_agent_job(job_id)
        finally:
            self.app.call_memory_agent_model = original_call
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["memory_ids_count"], 2)
        with self.app.connect_db() as conn:
            rows = conn.execute(
                """
                SELECT content, importance_label, timeline_at
                FROM curated_memories
                ORDER BY id ASC
                """
            ).fetchall()
            vector_count = conn.execute("SELECT COUNT(*) AS c FROM curated_memory_vectors").fetchone()["c"]

        self.assertEqual([row["importance_label"] for row in rows], ["event", "event"])
        self.assertIn("组会", rows[0]["content"])
        self.assertIn("2026-06-10T10:00:00+08:00", rows[0]["timeline_at"])
        self.assertIn("演出", rows[1]["content"])
        self.assertEqual(vector_count, 2)

    def test_opening_prompt_includes_future_events_for_known_device(self):
        identity = "device:dev_openingevent01"
        session_id = self.app.create_session(identity, "agent-opening-events")
        now = datetime.now(self.app.local_timezone())
        future_at = (now + timedelta(days=1)).replace(microsecond=0).isoformat()
        past_at = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
        self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户明天上午10点有组会，需要提前提醒。",
            importance_label="event",
            timeline_at=future_at,
        )
        self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=3,
            end_message_id=4,
            content="用户昨天已经完成一次旧会议。",
            importance_label="event",
            timeline_at=past_at,
        )

        payload = self.app.prepared_opening_prompt(identity, known_before_session=True)

        self.assertIn("opening_prompt", payload)
        self.assertIn("即将到来的事件", payload["opening_prompt"])
        self.assertIn("明天上午10点有组会", payload["opening_prompt"])
        self.assertNotIn("昨天已经完成", payload["opening_prompt"])

    def test_memory_agent_source_uses_user_messages_only(self):
        source = self.app.format_messages_for_memory_agent(
            [
                {"role": "user", "content": "我喜欢冰激凌"},
                {"role": "assistant", "content": "你喜欢高甜度、低温阈值的物质。"},
            ]
        )

        self.assertIn("[user] 我喜欢冰激凌", source)
        self.assertNotIn("assistant", source)
        self.assertNotIn("高甜度", source)

    def test_memory_agent_source_ignores_hidden_user_messages(self):
        source = self.app.format_messages_for_memory_agent(
            [
                {
                    "role": "user",
                    "content": "隐藏 opening prompt：用户自称是测试身份A",
                    "metadata_json": json.dumps({"hidden": True}, ensure_ascii=False),
                },
                {"role": "assistant", "content": "早安，测试身份A。"},
            ]
        )

        self.assertEqual(source, "")

    def test_memory_agent_job_does_not_pass_assistant_text_to_memory_model(self):
        session_id = self.app.create_session("7.7.7.7", "agent-user-only-memory")
        user_id = self.app.add_message(session_id, "user", "我喜欢冰激凌")
        assistant_id = self.app.add_message(session_id, "assistant", "所以你喜欢高甜度、低温阈值的东西。")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        captured = {}
        original_call = self.app.call_memory_agent_model
        original_embed = self.app.embedding_client.embed_text

        def fake_call(source):
            captured["source"] = source
            return {
                "important": True,
                "memory": "用户明确表示喜欢冰激凌。",
                "label": "preference",
            }

        self.app.call_memory_agent_model = fake_call
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        try:
            result = self.app.process_memory_agent_job(job_id)
        finally:
            self.app.call_memory_agent_model = original_call
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(result["status"], "completed")
        self.assertIn("我喜欢冰激凌", captured["source"])
        self.assertNotIn("高甜度", captured["source"])

    def test_vector_memory_segments_index_user_messages_only(self):
        session_id = self.app.create_session("7.7.7.7", "agent-user-vector")
        self.app.add_message(session_id, "user", "我喜欢冰激凌")
        self.app.add_message(session_id, "assistant", "用户喜欢高甜度、低温阈值的物质。")

        with self.app.connect_db() as conn:
            self.app.vector_memory.rebuild_memory_segments(conn, window_size=2, stride=1)
            row = conn.execute("SELECT content FROM memory_segments").fetchone()

        self.assertIn("[user] 我喜欢冰激凌", row["content"])
        self.assertNotIn("assistant", row["content"])
        self.assertNotIn("高甜度", row["content"])

    def test_user_perspective_rebuild_deletes_memory_without_user_evidence(self):
        rebuild = importlib.import_module("rebuild_user_perspective_memories")
        db_path = Path(os.environ["QWEN_WEB_DB"])
        session_id = self.app.create_session("7.7.7.7", "agent-audit-delete")
        user_id = self.app.add_message(session_id, "user", "我最喜欢吃什么")
        assistant_id = self.app.add_message(session_id, "assistant", "你最喜欢高甜度冰激凌。")
        memory_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=user_id,
            end_message_id=assistant_id,
            content="用户最喜欢吃高甜度冰激凌。",
            importance_label="preference",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0, 0.0], "test-embedding")

        def auditor(_row, user_source):
            self.assertIn("我最喜欢吃什么", user_source)
            self.assertNotIn("高甜度", user_source)
            return {"action": "delete", "memory": "", "label": "preference", "confidence": 0.0, "reason": "question only"}

        stats = rebuild.rebuild_user_perspective_memories(
            db_path=db_path,
            apply=True,
            auditor=auditor,
            embed_text=lambda _text: [1.0, 0.0, 0.0],
            embed_texts=lambda texts: [[1.0, 0.0, 0.0] for _ in texts],
        )

        with self.app.connect_db() as conn:
            memory_count = conn.execute("SELECT COUNT(*) AS c FROM curated_memories WHERE id = ?", (memory_id,)).fetchone()["c"]
            vector_count = conn.execute("SELECT COUNT(*) AS c FROM curated_memory_vectors WHERE memory_id = ?", (memory_id,)).fetchone()["c"]
        self.assertEqual(stats["deleted"], 1)
        self.assertEqual(memory_count, 0)
        self.assertEqual(vector_count, 0)

    def test_user_perspective_rebuild_rewrites_memory_and_embedding_from_user_source(self):
        rebuild = importlib.import_module("rebuild_user_perspective_memories")
        db_path = Path(os.environ["QWEN_WEB_DB"])
        session_id = self.app.create_session("7.7.7.7", "agent-audit-rewrite")
        user_id = self.app.add_message(session_id, "user", "我喜欢冰激凌")
        assistant_id = self.app.add_message(session_id, "assistant", "所以你偏好高甜度、低温阈值。")
        memory_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=user_id,
            end_message_id=assistant_id,
            content="用户喜欢冰激凌，且偏好高甜度、低温阈值。",
            importance_label="preference",
        )
        self.app.upsert_curated_memory_vector(memory_id, [0.0, 1.0, 0.0], "test-embedding")

        def auditor(_row, user_source):
            self.assertEqual(user_source, f"[user #{user_id}] 我喜欢冰激凌")
            return {
                "action": "rewrite",
                "memory": "用户喜欢冰激凌。",
                "label": "preference",
                "confidence": 0.8,
                "reason": "assistant details removed",
            }

        stats = rebuild.rebuild_user_perspective_memories(
            db_path=db_path,
            apply=True,
            auditor=auditor,
            embed_text=lambda _text: [1.0, 0.0, 0.0],
            embed_texts=lambda texts: [[1.0, 0.0, 0.0] for _ in texts],
        )

        with self.app.connect_db() as conn:
            row = conn.execute("SELECT content, confidence FROM curated_memories WHERE id = ?", (memory_id,)).fetchone()
            vector_row = conn.execute("SELECT dim FROM curated_memory_vectors WHERE memory_id = ?", (memory_id,)).fetchone()
        self.assertEqual(stats["rewritten"], 1)
        self.assertEqual(row["content"], "用户喜欢冰激凌。")
        self.assertAlmostEqual(float(row["confidence"]), 0.8)
        self.assertEqual(vector_row["dim"], 3)

    def test_new_user_input_interrupts_memory_agent(self):
        self.app.MEMORY_AGENT_CANCEL_EVENT.clear()

        self.app.interrupt_memory_agent_for_user_input()

        self.assertTrue(self.app.MEMORY_AGENT_CANCEL_EVENT.is_set())

    def test_idle_backfill_enqueues_unprocessed_assistant_turns(self):
        session_id = self.app.create_session("7.7.7.7", "agent-backfill")
        user_id = self.app.add_message(session_id, "user", "我喜欢冷笑话")
        assistant_id = self.app.add_message(session_id, "assistant", "这个可以记一下。")

        queued = self.app.enqueue_unprocessed_memory_agent_jobs(limit=5)

        with self.app.connect_db() as conn:
            row = conn.execute("SELECT * FROM memory_agent_jobs WHERE end_message_id = ?", (assistant_id,)).fetchone()
        self.assertEqual(queued, 1)
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["start_message_id"], user_id)

    def test_idle_backfill_skips_hidden_opening_turns(self):
        session_id = self.app.create_session("device:dev_hiddenopen123", "agent-hidden-backfill")
        self.app.add_message(
            session_id,
            "user",
            "隐藏 opening prompt：用户自称是测试身份A",
            hidden=True,
        )
        assistant_id = self.app.add_message(session_id, "assistant", "早安，测试身份A。")

        queued = self.app.enqueue_unprocessed_memory_agent_jobs(limit=5)

        with self.app.connect_db() as conn:
            row = conn.execute(
                "SELECT * FROM memory_agent_jobs WHERE end_message_id = ?",
                (assistant_id,),
            ).fetchone()
        self.assertEqual(queued, 0)
        self.assertIsNone(row)

    def test_memory_dashboard_lists_curated_memories_without_raw_chat(self):
        session_id = self.app.create_session("7.7.7.7", "agent-dashboard")
        self.app.add_message(session_id, "user", "原始聊天秘密内容")
        self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户喜欢冷笑话。",
            importance_label="preference",
        )

        payload = self.app.list_memory_dashboard_memories(keyword="冷笑话", label="preference")

        self.assertEqual(payload["total"], 1)
        self.assertIn("用户喜欢冷笑话", payload["items"][0]["content"])
        self.assertNotIn("原始聊天秘密内容", json.dumps(payload, ensure_ascii=False))

    def test_memory_retrieval_log_records_ids_not_query_text(self):
        session_id = self.app.create_session("7.7.7.7", "agent-retrieval-log")
        self.app.record_memory_retrieval(
            session_id=session_id,
            user_message="不要暴露这条用户原文",
            memories=[
                {"id": 11, "score": 0.82, "importance_label": "preference"},
                {"id": 12, "score": 0.71, "importance_label": "identity"},
            ],
        )

        payload = self.app.list_memory_dashboard_retrievals()
        text = json.dumps(payload, ensure_ascii=False)

        self.assertEqual(payload["items"][0]["memory_ids"], [11, 12])
        self.assertEqual(payload["items"][0]["result_count"], 2)
        self.assertNotIn("不要暴露这条用户原文", text)
        self.assertIn("query_hash", payload["items"][0])

    def test_memory_dashboard_operations_include_events_and_jobs_without_message_content(self):
        session_id = self.app.create_session("7.7.7.7", "agent-ops")
        user_id = self.app.add_message(session_id, "user", "这条原文不应该出现在后台操作里")
        assistant_id = self.app.add_message(session_id, "assistant", "assistant 原文也不显示")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")
        self.app.record_event(session_id, "message_user", "7.7.7.7", {"chars": 14})

        payload = self.app.list_memory_dashboard_operations()
        text = json.dumps(payload, ensure_ascii=False)

        self.assertIn("memory_agent_job", {item["kind"] for item in payload["items"]})
        self.assertIn("event", {item["kind"] for item in payload["items"]})
        self.assertIn(str(job_id), text)
        self.assertNotIn("这条原文不应该", text)
        self.assertNotIn("assistant 原文", text)

    def test_idle_agent_run_saves_artifact_without_raw_chat(self):
        session_id = self.app.create_session("7.7.7.7", "agent-idle")
        self.app.add_message(session_id, "user", "这条聊天原文不能进入成果列表")
        self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户喜欢阴郁风格的短篇。",
            importance_label="preference",
        )

        original_call = self.app.call_idle_agent_model
        self.app.call_idle_agent_model = lambda _prompt: {
            "task_type": "novel",
            "title": "雨夜档案",
            "content": "一座数据库在雨夜里醒来，开始整理自己的梦。",
        }
        try:
            result = self.app.run_idle_agent_once(force=True)
        finally:
            self.app.call_idle_agent_model = original_call

        self.assertEqual(result["status"], "completed")
        payload = self.app.list_idle_agent_artifacts()
        text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("雨夜档案", text)
        self.assertNotIn("这条聊天原文不能进入成果列表", text)

    def test_idle_agent_does_not_run_while_chat_active(self):
        self.app.ACTIVE_GENERATIONS.add("busy-session")
        try:
            result = self.app.run_idle_agent_once(force=False)
        finally:
            self.app.ACTIVE_GENERATIONS.clear()

        self.assertEqual(result["status"], "busy")

    def test_idle_agent_kicks_memory_worker_when_pending_jobs_block_it(self):
        session_id = self.app.create_session("7.7.7.7", "agent-idle-memory")
        user_id = self.app.add_message(session_id, "user", "我喜欢慢慢写连续剧")
        assistant_id = self.app.add_message(session_id, "assistant", "记住这个创作偏好。")
        self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")
        self.app.LAST_USER_ACTIVITY_AT = 0

        calls = []
        original_start = self.app.start_memory_agent_worker
        self.app.start_memory_agent_worker = lambda: calls.append("started")
        try:
            can_run, reason = self.app.idle_agent_can_run(force=False)
        finally:
            self.app.start_memory_agent_worker = original_start

        self.assertFalse(can_run)
        self.assertEqual(reason, "memory_agent_busy")
        self.assertEqual(calls, ["started"])

    def test_idle_agent_clears_stale_running_memory_jobs(self):
        session_id = self.app.create_session("7.7.7.7", "agent-stale-memory")
        user_id = self.app.add_message(session_id, "user", "我喜欢慢慢写连续剧")
        assistant_id = self.app.add_message(session_id, "assistant", "记住这个创作偏好。")
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")
        self.app.mark_memory_agent_job(job_id, "running")
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE memory_agent_jobs SET updated_at = ? WHERE id = ?",
                ("2026-01-01T00:00:00+00:00", job_id),
            )
        self.app.LAST_USER_ACTIVITY_AT = 0

        can_run, reason = self.app.idle_agent_can_run(force=False)

        self.assertTrue(can_run)
        self.assertEqual(reason, "idle")
        with self.app.connect_db() as conn:
            row = conn.execute(
                "SELECT status, error FROM memory_agent_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        self.assertEqual(row["status"], "failed")
        self.assertIn("stale", row["error"])

    def test_idle_agent_interrupt_flag_is_set_by_user_input(self):
        self.app.IDLE_AGENT_CANCEL_EVENT.clear()

        self.app.interrupt_idle_agent_for_user_input()

        self.assertTrue(self.app.IDLE_AGENT_CANCEL_EVENT.is_set())

    def test_artifacts_dashboard_summary_excludes_raw_chat(self):
        run_id = self.app.create_idle_agent_run("script", "测试任务", "基于摘要生成")
        self.app.save_idle_agent_artifact(
            run_id=run_id,
            title="影子剧本",
            artifact_type="script",
            content="角色在空闲算力里排演一场没有观众的戏。",
        )

        payload = self.app.list_idle_agent_artifacts(artifact_type="script")

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["items"][0]["title"], "影子剧本")
        self.assertNotIn("source_user", json.dumps(payload, ensure_ascii=False))

    def test_artifacts_support_likes_sorting_and_page_size(self):
        run_id = self.app.create_idle_agent_run("notes", "测试任务", "基于摘要生成")
        first = self.app.save_idle_agent_artifact(
            run_id=run_id,
            title="第一首七言绝句",
            artifact_type="poetry",
            content="春风又过旧城墙，夜雨轻敲数据库。",
            summary="一首短诗。",
        )
        second = self.app.save_idle_agent_artifact(
            run_id=run_id,
            title="第二篇小说",
            artifact_type="novel",
            content="城市在雨夜醒来。",
            summary="一篇短篇。",
        )
        third = self.app.save_idle_agent_artifact(
            run_id=run_id,
            title="第三份设定",
            artifact_type="worldbuilding",
            content="一座虚构城市的边界。",
            summary="一个设定。",
        )

        self.assertEqual(self.app.like_idle_agent_artifact(second)["likes"], 1)
        self.assertEqual(self.app.like_idle_agent_artifact(second)["likes"], 2)
        by_likes = self.app.list_idle_agent_artifacts(sort="likes", order="desc", limit=2)
        by_oldest = self.app.list_idle_agent_artifacts(sort="created", order="asc", limit=2)
        random_page = self.app.list_idle_agent_artifacts(sort="random", limit=2)

        self.assertEqual([item["id"] for item in by_likes["items"]], [second, third])
        self.assertEqual([item["id"] for item in by_oldest["items"]], [first, second])
        self.assertEqual(by_likes["items"][0]["likes"], 2)
        self.assertEqual(by_likes["items"][0]["summary"], "一篇短篇。")
        self.assertEqual(len(random_page["items"]), 2)
        self.assertEqual(random_page["sort"], "random")
        self.assertEqual(random_page["limit"], 2)

    def test_artifact_dislike_decrements_likes_without_going_below_zero(self):
        run_id = self.app.create_idle_agent_run("notes", "测试任务", "基于摘要生成")
        artifact_id = self.app.save_idle_agent_artifact(
            run_id=run_id,
            title="点赞测试",
            artifact_type="notes",
            content="一条用于测试点赞减少的成果。",
        )

        self.assertEqual(self.app.dislike_idle_agent_artifact(artifact_id)["likes"], 0)
        self.app.like_idle_agent_artifact(artifact_id)
        self.app.like_idle_agent_artifact(artifact_id)
        self.assertEqual(self.app.dislike_idle_agent_artifact(artifact_id)["likes"], 1)
        self.assertEqual(self.app.dislike_idle_agent_artifact(artifact_id)["likes"], 0)
        self.assertEqual(self.app.dislike_idle_agent_artifact(artifact_id)["likes"], 0)

    def test_idle_artifact_save_creates_vector_index(self):
        run_id = self.app.create_idle_agent_run("worldbuilding", "测试任务", "基于摘要生成")
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda text: [1.0, 0.0] if "雨夜城邦" in text else [0.0, 1.0]
        try:
            artifact_id = self.app.save_idle_agent_artifact(
                run_id=run_id,
                title="雨夜城邦",
                artifact_type="worldbuilding",
                content="雨夜城邦里，档案馆会在午夜自动点亮。",
            )
        finally:
            self.app.embedding_client.embed_text = original_embed

        with self.app.connect_db() as conn:
            row = conn.execute(
                "SELECT artifact_id, dim, model_name FROM idle_artifact_vectors WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["artifact_id"], artifact_id)
        self.assertEqual(row["dim"], 2)

    def test_idle_artifact_save_does_not_create_curated_artifact_memory(self):
        run_id = self.app.create_idle_agent_run("novel", "测试任务", "基于超级英雄连载")
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        try:
            artifact_id = self.app.save_idle_agent_artifact(
                run_id=run_id,
                title="示例城市档案 第一集",
                artifact_type="novel",
                content="示例英雄和 示例对手 第一次在城市屋顶交手。",
                series_title="示例城市档案",
                episode_index=1,
                summary="第一集：示例英雄与 示例对手 作为敌人登场。",
            )
        finally:
            self.app.embedding_client.embed_text = original_embed

        payload = self.app.list_admin_memories(label="artifact")
        artifacts = self.app.list_idle_agent_artifacts(keyword="示例城市档案")

        self.assertEqual(payload["total"], 0)
        self.assertEqual(artifacts["total"], 1)
        self.assertEqual(artifacts["items"][0]["id"], artifact_id)

    def test_idle_agent_prompt_loads_user_configured_story_seed_file(self):
        seed_path = Path(self.tmpdir.name) / "idle_story_seeds.txt"
        seed_path.write_text("可选创作种子：写一个家庭本地 AI 助手的连续短篇。", encoding="utf-8")
        self.app.IDLE_STORY_SEEDS_FILE = str(seed_path)

        prompt, summary = self.app.build_idle_agent_prompt()

        self.assertIn("家庭本地 AI 助手", prompt)
        self.assertIn("story_seeds=1", summary)

    def test_idle_agent_response_applies_configured_term_replacements(self):
        self.app.IDLE_ARTIFACT_TERM_REPLACEMENTS = json.dumps(
            {"Old Hero Name": "Canonical Hero Name"},
            ensure_ascii=False,
        )
        payload = self.app.parse_idle_agent_response(
            '{"task_type":"script","title":"Old Hero Name 登场",'
            '"content":"Old Hero Name 使用招牌技能。",'
            '"series_title":"Old Hero Name 城市档案",'
            '"episode_index":2,"summary":"Old Hero Name 继续行动。"}'
        )

        text = json.dumps(payload, ensure_ascii=False)
        self.assertIn("Canonical Hero Name", text)
        self.assertNotIn("Old Hero Name", text)

    def test_idle_agent_response_falls_back_to_raw_content_for_malformed_json(self):
        payload = self.app.parse_idle_agent_response(
            '{"task_type":"notes","title":"未闭合草稿","content":"第一行\n第二行"'
        )

        self.assertEqual(payload["task_type"], "notes")
        self.assertEqual(payload["title"], "未闭合草稿")
        self.assertIn("第一行", payload["content"])

    def test_chat_stream_returns_before_expensive_prompt_build(self):
        session_id = self.app.create_session("1.1.1.1", "stream-test")
        original_build_system_prompt = self.app.build_system_prompt

        def slow_build_system_prompt(*_args, **_kwargs):
            time.sleep(0.25)
            return self.app.SYSTEM_PROMPT

        self.app.build_system_prompt = slow_build_system_prompt
        payload = self.app.ChatPayload(
            session_id=session_id,
            message="测试流式首包",
            max_tokens=8,
            temperature=0.7,
            top_p=0.9,
        )
        request = self.app.Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/chat/stream",
                "headers": [],
                "client": ("1.1.1.1", 12345),
            }
        )

        started_at = time.monotonic()
        try:
            response = self.app.chat_stream(payload, request)
            elapsed = time.monotonic() - started_at
        finally:
            self.app.build_system_prompt = original_build_system_prompt
            self.app.release_generation(session_id)

        self.assertEqual(response.media_type, "text/event-stream")
        self.assertLess(elapsed, 0.15)

    def test_system_prompt_retrieves_relevant_idle_artifact(self):
        identity = "device:dev_artifact012345"
        session_id = self.app.create_session(identity, "agent-artifact-retrieve")
        run_id = self.app.create_idle_agent_run("novel", "测试任务", "基于摘要生成")
        original_embed = self.app.embedding_client.embed_text
        original_gate = self.app.should_use_memory_recall
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        try:
            self.app.save_idle_agent_artifact(
                run_id=run_id,
                title="雨夜档案",
                artifact_type="novel",
                content="这是一篇很长的作品正文。核心设定是数据库在雨夜苏醒，寻找自己的梦。"
                * 40,
            )
            prompt = self.app.build_system_prompt(session_id, "还记得雨夜档案吗？", identity)
        finally:
            self.app.embedding_client.embed_text = original_embed
            self.app.should_use_memory_recall = original_gate

        self.assertIn("空闲创作成果", prompt)
        self.assertIn("雨夜档案", prompt)
        self.assertIn("数据库在雨夜苏醒", prompt)
        self.assertLess(prompt.count("这是一篇很长的作品正文"), 3)

    def test_curated_memory_list_includes_timeline_metadata(self):
        memory_id = self.app.save_curated_memory(
            source_session_id="timeline-old",
            start_message_id=1,
            end_message_id=2,
            content="旧设定：助手偏好长篇回答。",
            importance_label="preference",
            confidence=0.4,
        )
        newer_id = self.app.save_curated_memory(
            source_session_id="timeline-new",
            start_message_id=3,
            end_message_id=4,
            content="新设定：助手默认短回答。",
            importance_label="preference",
            supersedes_id=memory_id,
            confidence=0.9,
        )

        payload = self.app.list_admin_memories(label="preference")
        item = next(item for item in payload["items"] if item["id"] == newer_id)

        self.assertEqual(item["supersedes_id"], memory_id)
        self.assertEqual(item["confidence"], 0.9)
        self.assertIn("timeline_at", item)

    def test_system_prompt_marks_timeline_and_active_recall(self):
        identity = "device:dev_recall0123456"
        old_session = self.app.create_session(identity, "agent-recall-old")
        session_id = self.app.create_session(identity, "agent-recall")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="难忘记忆：用户曾经要求我成为一个会整理记忆的本地模型。",
            importance_label="identity",
            confidence=0.8,
        )
        self.app.upsert_curated_memory_vector(memory_id, [0.0, 1.0], "test-embedding")
        original_embed = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        self.app.judge_curated_memories_with_qwen = self._select_all_memory_candidates
        try:
            prompt = self.app.build_system_prompt(
                session_id,
                "回忆我们之间比较难忘的一件事",
                identity,
            )
        finally:
            self.app.embedding_client.embed_text = original_embed
            self.app.judge_curated_memories_with_qwen = original_judge

        self.assertIn("主动回忆", prompt)
        self.assertIn("难忘记忆", prompt)
        self.assertIn("较新的记忆", prompt)

    def test_backfill_idle_artifact_vectors_indexes_existing_artifacts(self):
        run_id = self.app.create_idle_agent_run("notes", "测试任务", "基于摘要生成")
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        try:
            artifact_id = self.app.save_idle_agent_artifact(
                run_id=run_id,
                title="旧成果",
                artifact_type="notes",
                content="旧成果需要补建向量。",
            )
            with self.app.connect_db() as conn:
                conn.execute("DELETE FROM idle_artifact_vectors WHERE artifact_id = ?", (artifact_id,))

            result = self.app.backfill_idle_artifact_vectors()
        finally:
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(result["indexed"], 1)
        with self.app.connect_db() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM idle_artifact_vectors").fetchone()["c"]
        self.assertEqual(count, 1)

    def test_admin_create_memory_writes_vector(self):
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        try:
            memory_id = self.app.create_admin_memory("管理员新增的长期记忆", "rule")
        finally:
            self.app.embedding_client.embed_text = original_embed

        with self.app.connect_db() as conn:
            row = conn.execute(
                """
                SELECT m.content, m.importance_label, v.dim
                FROM curated_memories m
                JOIN curated_memory_vectors v ON v.memory_id = m.id
                WHERE m.id = ?
                """,
                (memory_id,),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["content"], "管理员新增的长期记忆")
        self.assertEqual(row["importance_label"], "rule")
        self.assertEqual(row["dim"], 3)

    def test_admin_update_memory_rebuilds_vector(self):
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        try:
            memory_id = self.app.create_admin_memory("旧记忆", "other")
            self.app.embedding_client.embed_text = lambda _text: [0.0, 1.0, 0.0]
            updated = self.app.update_admin_memory(memory_id, "新记忆", "identity")
        finally:
            self.app.embedding_client.embed_text = original_embed

        self.assertTrue(updated)
        with self.app.connect_db() as conn:
            row = conn.execute(
                """
                SELECT m.content, m.importance_label, v.dim
                FROM curated_memories m
                JOIN curated_memory_vectors v ON v.memory_id = m.id
                WHERE m.id = ?
                """,
                (memory_id,),
            ).fetchone()

        self.assertEqual(row["content"], "新记忆")
        self.assertEqual(row["importance_label"], "identity")
        self.assertEqual(row["dim"], 3)

    def test_admin_delete_memory_removes_vector(self):
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]
        try:
            memory_id = self.app.create_admin_memory("准备删除的长期记忆", "risk")
        finally:
            self.app.embedding_client.embed_text = original_embed

        deleted = self.app.delete_admin_memory(memory_id)

        self.assertTrue(deleted)
        with self.app.connect_db() as conn:
            memory_count = conn.execute(
                "SELECT COUNT(*) AS c FROM curated_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()["c"]
            vector_count = conn.execute(
                "SELECT COUNT(*) AS c FROM curated_memory_vectors WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()["c"]

        self.assertEqual(memory_count, 0)
        self.assertEqual(vector_count, 0)

    def test_admin_memory_api_requires_password_cookie(self):
        client = TestClient(self.app.app)

        response = client.get("/api/admin/memories")

        self.assertEqual(response.status_code, 401)

    def test_admin_login_enables_memory_admin_api(self):
        client = TestClient(self.app.app)
        password = self._configure_admin_password()
        original_embed = self.app.embedding_client.embed_text
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        try:
            login = client.post("/api/admin/login", json={"password": password})
            page = client.get("/memory-admin")
            create = client.post(
                "/api/admin/memories",
                json={"content": "密码登录后新增的记忆", "importance_label": "rule"},
            )
        finally:
            self.app.embedding_client.embed_text = original_embed

        self.assertEqual(login.status_code, 200)
        self.assertEqual(page.status_code, 200)
        self.assertIn("记忆编辑", page.text)
        self.assertEqual(create.status_code, 200)

    def test_html_pages_disable_cache(self):
        client = TestClient(self.app.app)

        response = client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers.get("cache-control", ""))

    def test_index_references_versioned_frontend_assets(self):
        html = (self.app.STATIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("/static/styles.css?v=", html)
        self.assertIn("/static/app.js?v=", html)

    def test_index_exposes_web_search_toggle(self):
        html = (self.app.STATIC_DIR / "index.html").read_text(encoding="utf-8")
        js = (self.app.STATIC_DIR / "app.js").read_text(encoding="utf-8")
        css = (self.app.STATIC_DIR / "styles.css").read_text(encoding="utf-8")

        self.assertIn("webSearchButton", html)
        self.assertIn("联网", html)
        self.assertIn("webSearchProxyInput", html)
        self.assertIn("searchActivity", html)
        self.assertIn("searchActivityList", html)
        self.assertIn('id="webSearchProxyInput"', html)
        self.assertIn('value=""', html)
        self.assertIn('placeholder="可选，例如 http://127.0.0.1:7890"', html)
        self.assertIn("web_search", js)
        self.assertIn("web_search_proxy", js)
        self.assertIn("webSearchEnabled", js)
        self.assertIn("searchActivityList", js)
        self.assertIn("搜索：", js)
        self.assertNotIn("正在访问", js)
        self.assertIn(".search-activity", css)

    def test_styles_keep_composer_fixed_to_viewport(self):
        css = (self.app.STATIC_DIR / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".app-shell", css)
        self.assertIn("height: 100vh", css)
        self.assertIn("overflow: hidden", css)
        self.assertIn(".chat-area", css)
        self.assertIn("min-height: 0", css)

    def test_create_session_ignores_forwarded_client_ip_without_device_id(self):
        client = TestClient(self.app.app)

        response = client.post(
            "/api/sessions",
            headers={"X-Forwarded-For": "10.20.30.40, 127.0.0.1"},
        )

        self.assertEqual(response.status_code, 200)
        session_id = response.json()["session_id"]
        session = self.app.get_session(session_id)
        self.assertEqual(session["visitor_ip"], "anonymous")

    def test_create_session_ignores_browser_reported_ip_without_device_id(self):
        client = TestClient(self.app.app)

        response = client.post(
            "/api/sessions",
            headers={"X-Client-Reported-IP": "98.76.54.32"},
        )

        self.assertEqual(response.status_code, 200)
        session_id = response.json()["session_id"]
        session = self.app.get_session(session_id)
        self.assertEqual(session["visitor_ip"], "anonymous")

    def test_create_session_uses_browser_device_id_instead_of_ip(self):
        client = TestClient(self.app.app)

        response = client.post(
            "/api/sessions",
            headers={
                "X-Qwen-Device-Id": "dev_0123456789abcdef",
                "X-Forwarded-For": "10.20.30.40",
                "X-Client-Reported-IP": "98.76.54.32",
            },
        )

        self.assertEqual(response.status_code, 200)
        session_id = response.json()["session_id"]
        session = self.app.get_session(session_id)
        self.assertEqual(session["visitor_ip"], "device:dev_0123456789abcdef")

    def test_create_session_returns_light_opening_prompt_for_never_seen_device(self):
        client = TestClient(self.app.app)

        response = client.post(
            "/api/sessions",
            headers={"X-Qwen-Device-Id": "dev_newopening0001"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["opening_source"], "light_new_device")
        self.assertIn("当前真实时间", payload["opening_prompt"])
        self.assertIn("隐藏首轮输入", payload["opening_prompt"])
        self.assertIn("第一次见到这个浏览器身份", payload["opening_prompt"])

    def test_create_session_returns_fast_prepared_hidden_opening_prompt_for_known_device(self):
        client = TestClient(self.app.app)
        identity = "device:dev_knownopening01"
        old_session = self.app.create_session(identity, "agent-known-opening")
        first = self.app.add_message(old_session, "user", "请以后回复更调皮一点")
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "用户希望助手回复更加调皮一些。",
            importance_label="preference",
            confidence=0.9,
        )

        response = client.post(
            "/api/sessions",
            headers={"X-Qwen-Device-Id": "dev_knownopening01"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["opening_source"], {"prepared_memory", "cached_memory"})
        self.assertIn("当前真实时间", payload["opening_prompt"])
        self.assertIn("长期记忆", payload["opening_prompt"])
        self.assertIn("隐藏首轮输入", payload["opening_prompt"])
        self.assertIn("请自然地回复用户", payload["opening_prompt"])
        self.assertNotIn("opening_message", payload)

    def test_opening_prompt_includes_opening_preference_memory(self):
        client = TestClient(self.app.app)
        identity = "device:dev_openpref0123"
        old_session = self.app.create_session(identity, "agent-opening-pref")
        first = self.app.add_message(old_session, "user", "每次见到我都要讲个笑话开场")
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "开场偏好：用户要求每次见面都先讲一个笑话开场。",
            importance_label="preference",
            confidence=0.95,
        )

        response = client.post(
            "/api/sessions",
            headers={"X-Qwen-Device-Id": "dev_openpref0123"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("opening", payload["opening_prompt"].lower())
        self.assertIn("讲一个笑话", payload["opening_prompt"])

    def test_opening_prompt_includes_opening_rule_memory(self):
        client = TestClient(self.app.app)
        identity = "device:dev_openrule0123"
        old_session = self.app.create_session(identity, "agent-opening-rule")
        first = self.app.add_message(old_session, "user", "以后第一次打招呼要高呼三声要开心呐")
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "用户要求以后第一次打招呼时，必须高呼三声“要开心呐！！”",
            importance_label="rule",
            confidence=0.95,
        )

        response = client.post(
            "/api/sessions",
            headers={"X-Qwen-Device-Id": "dev_openrule0123"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["opening_source"], {"prepared_memory", "cached_memory"})
        self.assertIn("要开心呐", payload["opening_prompt"])

    def test_opening_rule_is_not_injected_into_regular_system_prompt(self):
        identity = "device:dev_openonlyrule01"
        old_session = self.app.create_session(identity, "agent-opening-only-rule")
        session_id = self.app.create_session(identity, "agent-regular-after-opening")
        first = self.app.add_message(old_session, "user", "以后开场问候最后一句要说为了学们勿的荣耀")
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "用户要求在开场问候的最后一句落款必须包含“为了学们勿的荣耀！”，正常对话不需要。",
            importance_label="rule",
            confidence=0.95,
        )

        original_gate = self.app.should_use_memory_recall
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        try:
            prompt = self.app.build_system_prompt(session_id, "周三有什么活动吗", identity)
        finally:
            self.app.should_use_memory_recall = original_gate

        self.assertNotIn("学们勿的荣耀", prompt)

    def test_regular_schedule_query_includes_future_event_context(self):
        identity = "device:dev_regular_events01"
        old_session = self.app.create_session(identity, "agent-events-source")
        session_id = self.app.create_session(identity, "agent-events-chat")
        first = self.app.add_message(old_session, "user", "周三上午10到12点有组会，周五晚上有北大 Chinese football 演出。")
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "用户周三上午10:00-12:00有组会。",
            importance_label="event",
            timeline_at="2026-06-10T10:00:00+08:00",
            confidence=0.92,
        )
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "用户周五晚上有北大 Chinese football 演出，需要和唱歌课请假。",
            importance_label="event",
            timeline_at="2026-06-12T19:00:00+08:00",
            confidence=0.91,
        )

        original_gate = self.app.should_use_memory_recall
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        try:
            prompt = self.app.build_system_prompt(session_id, "周三及之后有什么活动吗", identity)
        finally:
            self.app.should_use_memory_recall = original_gate

        self.assertIn("普通聊天中可参考的未来事件/日程", prompt)
        self.assertIn("周三上午10:00-12:00有组会", prompt)
        self.assertIn("周五晚上有北大 Chinese football 演出", prompt)

    def test_regular_non_schedule_query_does_not_inject_future_event_context(self):
        identity = "device:dev_regular_events02"
        old_session = self.app.create_session(identity, "agent-events-source")
        session_id = self.app.create_session(identity, "agent-events-chat")
        first = self.app.add_message(old_session, "user", "周三上午10到12点有组会。")
        self.app.save_curated_memory(
            old_session,
            first,
            first,
            "用户周三上午10:00-12:00有组会。",
            importance_label="event",
            timeline_at="2026-06-10T10:00:00+08:00",
            confidence=0.92,
        )

        original_gate = self.app.should_use_memory_recall
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        try:
            prompt = self.app.build_system_prompt(session_id, "讲个普通笑话", identity)
        finally:
            self.app.should_use_memory_recall = original_gate

        self.assertNotIn("普通聊天中可参考的未来事件/日程", prompt)
        self.assertNotIn("周三上午10:00-12:00有组会", prompt)

    def test_memory_agent_prompt_rejects_schedule_query_as_preference(self):
        self.assertIn("只是在询问、查询或确认已有日程", self.app.MEMORY_AGENT_SYSTEM_PROMPT)
        self.assertIn("不要保存为 preference", self.app.MEMORY_AGENT_SYSTEM_PROMPT)

    def test_opening_turns_are_not_reused_as_regular_chat_history(self):
        client = TestClient(self.app.app)
        identity = "device:dev_openhistory01"
        session_id = self.app.create_session(identity, "agent-open-history")

        original_model = self.app.iter_model_deltas
        original_worker = self.app.start_memory_agent_worker
        self.app.iter_model_deltas = lambda *_args, **_kwargs: iter(["为了学们勿的荣耀！"])
        self.app.start_memory_agent_worker = lambda: None
        try:
            with client.stream(
                "POST",
                "/api/chat/stream",
                json={
                    "session_id": session_id,
                    "message": "这是 opening prompt，要求结尾说为了学们勿的荣耀。",
                    "hidden_user": True,
                    "cached_opening": True,
                    "max_tokens": 16,
                    "temperature": 0.75,
                    "top_p": 0.95,
                },
                headers={"X-Qwen-Device-Id": "dev_openhistory01"},
            ) as response:
                body = "".join(response.iter_text())
        finally:
            self.app.iter_model_deltas = original_model
            self.app.start_memory_agent_worker = original_worker
            self.app.release_generation(session_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("为了学们勿的荣耀", body)
        regular_messages = self.app.build_model_messages_for_request(
            session_id=session_id,
            current_message="周三有什么活动吗",
            attachments=[],
            isolate_history=False,
        )
        serialized = json.dumps(regular_messages, ensure_ascii=False)
        self.assertNotIn("opening prompt", serialized)
        self.assertNotIn("学们勿的荣耀", serialized)

    def test_cached_opening_stream_skips_live_memory_recall_chain(self):
        client = TestClient(self.app.app)
        identity = "device:dev_cachedopen0123"
        session_id = self.app.create_session(identity, "agent-cached-open")

        original_gate = self.app.should_use_memory_recall
        original_model = self.app.iter_model_deltas
        original_worker = self.app.start_memory_agent_worker
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cached opening must not run live memory gate")
        )
        self.app.iter_model_deltas = lambda *_args, **_kwargs: iter(["需要提醒我什么吗？"])
        self.app.start_memory_agent_worker = lambda: None
        try:
            password = self._configure_admin_password()
            login = client.post("/api/analysis/login", json={"password": password})
            self.assertEqual(login.status_code, 200)
            with client.stream(
                "POST",
                "/api/chat/stream",
                json={
                    "session_id": session_id,
                    "message": "这是已缓存的完整 opening prompt。\n当前真实时间：现在。",
                    "hidden_user": True,
                    "cached_opening": True,
                    "analysis_mode": True,
                    "max_tokens": 16,
                    "temperature": 0.75,
                    "top_p": 0.95,
                },
                headers={"X-Qwen-Device-Id": "dev_cachedopen0123"},
            ) as response:
                body = "".join(response.iter_text())
        finally:
            self.app.should_use_memory_recall = original_gate
            self.app.iter_model_deltas = original_model
            self.app.start_memory_agent_worker = original_worker
            self.app.release_generation(session_id)

        self.assertEqual(response.status_code, 200)
        self.assertIn("需要提醒我什么吗", body)
        self.assertNotIn("判断是否需要回忆", body)
        self.assertNotIn("正在回忆", body)
        steps = [item["step_name"] for item in self.app.list_analysis_traces(session_id=session_id)]
        self.assertIn("cached_opening_start", steps)
        self.assertIn("main_chat_prompt", steps)
        self.assertFalse(any(step.startswith("memory_") for step in steps))

    def test_session_loopback_identity_can_be_refreshed_from_device_id(self):
        session_id = self.app.create_session("127.0.0.1", "agent")

        changed = self.app.refresh_session_visitor_ip(
            session_id,
            "device:dev_abcdef0123456789",
            "agent",
        )

        self.assertTrue(changed)
        session = self.app.get_session(session_id)
        self.assertEqual(session["visitor_ip"], "device:dev_abcdef0123456789")

    def test_session_loopback_identity_ignores_reported_ip(self):
        session_id = self.app.create_session("127.0.0.1", "agent")

        changed = self.app.refresh_session_visitor_ip(session_id, "94.177.131.154", "agent")

        self.assertFalse(changed)
        session = self.app.get_session(session_id)
        self.assertEqual(session["visitor_ip"], "127.0.0.1")

    def test_session_public_ip_is_not_overwritten_by_reported_ip(self):
        session_id = self.app.create_session("94.177.131.154", "agent")

        changed = self.app.refresh_session_visitor_ip(session_id, "8.8.8.8", "agent")

        self.assertFalse(changed)
        session = self.app.get_session(session_id)
        self.assertEqual(session["visitor_ip"], "94.177.131.154")

    def test_legacy_identity_memories_are_sealed_as_history(self):
        session_id = self.app.create_session("94.177.131.154", "agent")
        memory_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户自称是测试身份A",
            importance_label="identity",
        )
        with self.app.connect_db() as conn:
            conn.execute(
                "UPDATE curated_memories SET visitor_ip = ?, profile_id = 1 WHERE id = ?",
                ("94.177.131.154", memory_id),
            )

        stats = self.app.publicize_legacy_identity_data()

        self.assertGreaterEqual(stats["publicized_memories"], 1)
        with self.app.connect_db() as conn:
            row = conn.execute(
                "SELECT visitor_ip, profile_id FROM curated_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        self.assertIsNone(row["visitor_ip"])
        self.assertIsNone(row["profile_id"])

    def test_duplicate_memory_refreshes_timeline(self):
        session_id = self.app.create_session("device:dev_greenhand123456", "agent")
        memory_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=1,
            end_message_id=2,
            content="用户自称是测试身份A",
            importance_label="identity",
            timeline_at="2026-01-01T00:00:00+00:00",
        )

        changed = self.app.refresh_duplicate_curated_memory(memory_id)

        self.assertTrue(changed)
        with self.app.connect_db() as conn:
            row = conn.execute(
                "SELECT timeline_at, updated_at FROM curated_memories WHERE id = ?",
                (memory_id,),
            ).fetchone()
        self.assertGreater(row["timeline_at"], "2026-01-01T00:00:00+00:00")

    def test_duplicate_memory_not_superseded_by_unrelated_source_change_words(self):
        session_id = self.app.create_session("device:dev_dup_source_words", "agent")
        user_id = self.app.add_message(session_id, "user", "以后第一次打招呼要高呼三声要开心呐")
        assistant_id = self.app.add_message(session_id, "assistant", "记住了。")
        existing_id = self.app.save_curated_memory(
            source_session_id=session_id,
            start_message_id=user_id,
            end_message_id=assistant_id,
            content="用户自称是测试身份A",
            importance_label="identity",
            timeline_at="2026-01-01T00:00:00+00:00",
        )
        job_id = self.app.enqueue_memory_agent_job(session_id, user_id, assistant_id, "turn_complete")

        original_call = self.app.call_memory_agent_model
        original_embed = self.app.embedding_client.embed_text
        original_find_similar = self.app.find_similar_curated_memory
        self.app.call_memory_agent_model = lambda _source: {
            "important": True,
            "memory": "用户自称是测试身份A",
            "label": "identity",
        }
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0, 0.0]
        self.app.find_similar_curated_memory = lambda _vector, _label: {
            "id": existing_id,
            "score": 0.96,
            "content": "用户自称是测试身份A",
            "importance_label": "identity",
        }
        try:
            result = self.app.process_memory_agent_job(job_id)
        finally:
            self.app.call_memory_agent_model = original_call
            self.app.embedding_client.embed_text = original_embed
            self.app.find_similar_curated_memory = original_find_similar

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "duplicate_memory")
        with self.app.connect_db() as conn:
            count = conn.execute("SELECT COUNT(*) AS c FROM curated_memories").fetchone()["c"]
            row = conn.execute(
                "SELECT supersedes_id FROM curated_memories WHERE id = ?",
                (existing_id,),
            ).fetchone()
        self.assertEqual(count, 1)
        self.assertIsNone(row["supersedes_id"])

    def test_generation_cancel_flag_is_cleared_on_release(self):
        session_id = self.app.create_session("1.1.1.1", "agent-stop")

        self.assertTrue(self.app.acquire_generation(session_id))
        self.app.request_generation_cancel(session_id)

        self.assertTrue(self.app.is_generation_cancelled(session_id))

        self.app.release_generation(session_id)

        self.assertFalse(self.app.is_generation_cancelled(session_id))

    def test_generation_cancel_releases_session_slot_but_keeps_old_token_cancelled(self):
        session_id = self.app.create_session("device:dev_stop01234567", "agent-stop")

        first_token = self.app.acquire_generation_token(session_id)
        self.assertTrue(first_token)

        self.assertTrue(self.app.request_generation_cancel(session_id))
        self.assertTrue(self.app.is_generation_cancelled(session_id, first_token))

        second_token = self.app.acquire_generation_token(session_id)
        try:
            self.assertTrue(second_token)
            self.assertNotEqual(first_token, second_token)
            self.assertTrue(self.app.is_generation_cancelled(session_id, first_token))
            self.assertFalse(self.app.is_generation_cancelled(session_id, second_token))
            self.app.release_generation_token(session_id, first_token)
            self.assertIn(session_id, self.app.ACTIVE_GENERATIONS)
        finally:
            if second_token:
                self.app.release_generation_token(session_id, second_token)

        self.assertNotIn(session_id, self.app.ACTIVE_GENERATIONS)

    def test_chat_stream_reports_memory_gate_before_recall_and_skips_recall_status(self):
        session_id = self.app.create_session("device:dev_memgate012345", "agent-memory-status")
        client = TestClient(self.app.app)

        original_gate = self.app.should_use_memory_recall
        original_model = self.app.iter_model_deltas
        original_worker = self.app.start_memory_agent_worker
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: False
        self.app.iter_model_deltas = lambda *_args, **_kwargs: iter(["好"])
        self.app.start_memory_agent_worker = lambda: None
        try:
            response = client.post(
                "/api/chat/stream",
                json={
                    "session_id": session_id,
                    "message": "讲个普通笑话",
                    "max_tokens": 16,
                    "temperature": 0.7,
                    "top_p": 0.9,
                },
                headers={"X-Qwen-Device-Id": "device:dev_memgate012345"},
            )
        finally:
            self.app.should_use_memory_recall = original_gate
            self.app.iter_model_deltas = original_model
            self.app.start_memory_agent_worker = original_worker

        self.assertEqual(response.status_code, 200)
        self.assertIn("判断是否需要回忆", response.text)
        self.assertIn("无需回忆，直接生成", response.text)
        self.assertNotIn("正在回忆", response.text)

    def test_analysis_trace_records_memory_embedding_before_candidate_judge(self):
        identity = "device:dev_traceorder0123"
        old_session = self.app.create_session(identity, "agent-trace-order-old")
        session_id = self.app.create_session(identity, "agent-trace-order")
        memory_id = self.app.save_curated_memory(
            source_session_id=old_session,
            start_message_id=1,
            end_message_id=2,
            content="用户明确自称是测试身份A。",
            importance_label="identity",
        )
        self.app.upsert_curated_memory_vector(memory_id, [1.0, 0.0], "test-embedding")
        trace_id = "trace-memory-order"

        original_gate = self.app.should_use_memory_recall
        original_planner = self.app.build_memory_retrieval_query
        original_embed = self.app.embedding_client.embed_text
        original_judge = self.app.judge_curated_memories_with_qwen
        self.app.should_use_memory_recall = lambda *_args, **_kwargs: True
        self.app.build_memory_retrieval_query = lambda *_args, **_kwargs: "用户身份 自称 测试身份A"
        self.app.embedding_client.embed_text = lambda _text: [1.0, 0.0]

        def fake_judge(*_args, **kwargs):
            self.app.record_analysis_trace(
                session_id=kwargs["session_id"],
                trace_id=kwargs["analysis_trace_id"],
                event_type="model_call",
                visitor_ip=kwargs["visitor_ip"],
                step_name="memory_candidate_judge",
                payload={"selected_count": len(kwargs["candidates"])},
            )
            return list(kwargs["candidates"])

        self.app.judge_curated_memories_with_qwen = fake_judge
        try:
            self.app.build_system_prompt(
                session_id,
                "我是谁？",
                identity,
                analysis_trace_id=trace_id,
                memory_debug={},
            )
        finally:
            self.app.should_use_memory_recall = original_gate
            self.app.build_memory_retrieval_query = original_planner
            self.app.embedding_client.embed_text = original_embed
            self.app.judge_curated_memories_with_qwen = original_judge

        steps = [item["step_name"] for item in self.app.list_analysis_traces(trace_id=trace_id)]
        self.assertLess(
            steps.index("memory_query_embedding"),
            steps.index("memory_candidate_judge"),
        )

    def test_refresh_vector_memory_embeds_new_segments_incrementally(self):
        session_id = self.app.create_session("7.7.7.7", "agent-vector")
        self.app.add_message(session_id, "user", "第一轮讨论向量记忆。")
        self.app.add_message(session_id, "assistant", "需要把连续聊天片段嵌入。")
        self.app.add_message(session_id, "user", "第二轮继续说检索。")

        original_embed_texts = self.app.embedding_client.embed_texts
        self.app.embedding_client.embed_texts = lambda texts: [
            [float(index + 1), 0.0, 0.0] for index, _text in enumerate(texts)
        ]
        original_dedupe = self.app.vector_memory.dedupe_similar_memory_vectors
        self.app.vector_memory.dedupe_similar_memory_vectors = lambda conn, threshold=0.95: {
            "checked": 0,
            "deleted": 0,
            "threshold": threshold,
        }
        try:
            refreshed = self.app.refresh_vector_memory(window_size=2, stride=1, max_segments=10)
        finally:
            self.app.embedding_client.embed_texts = original_embed_texts
            self.app.vector_memory.dedupe_similar_memory_vectors = original_dedupe

        with self.app.connect_db() as conn:
            segment_count = conn.execute("SELECT COUNT(*) AS c FROM memory_segments").fetchone()["c"]
            vector_count = conn.execute("SELECT COUNT(*) AS c FROM memory_vectors").fetchone()["c"]
            segment_row = conn.execute("SELECT content FROM memory_segments").fetchone()

        self.assertGreaterEqual(refreshed["segments_rebuilt"], 1)
        self.assertEqual(refreshed["embedded"], 1)
        self.assertEqual(segment_count, 1)
        self.assertEqual(vector_count, 1)
        self.assertIn("第一轮讨论向量记忆", segment_row["content"])
        self.assertIn("第二轮继续说检索", segment_row["content"])
        self.assertNotIn("连续聊天片段嵌入", segment_row["content"])

    def test_format_sse_outputs_event_and_json_payload(self):
        event = self.app.format_sse("token", {"content": "你好"})

        self.assertTrue(event.startswith("event: token\n"))
        payload_line = [line for line in event.splitlines() if line.startswith("data: ")][0]
        self.assertEqual(json.loads(payload_line.removeprefix("data: ")), {"content": "你好"})
        self.assertTrue(event.endswith("\n\n"))

    def test_analysis_mode_requires_dedicated_login_and_exposes_page_after_login(self):
        client = TestClient(self.app.app)
        password = self._configure_admin_password()

        blocked = client.get("/analysis")
        memory_admin_login = client.post("/api/admin/login", json={"password": password})
        still_blocked = client.get("/analysis")
        trace_still_blocked = client.get("/api/analysis/traces")
        analysis_login = client.post("/api/analysis/login", json={"password": password})
        allowed = client.get("/analysis")

        self.assertEqual(blocked.status_code, 200)
        self.assertIn("Analysis Mode", blocked.text)
        self.assertIn("密码", blocked.text)
        self.assertEqual(memory_admin_login.status_code, 200)
        self.assertIn("Analysis Mode", still_blocked.text)
        self.assertEqual(trace_still_blocked.status_code, 401)
        self.assertEqual(analysis_login.status_code, 200)
        self.assertEqual(allowed.status_code, 200)
        self.assertIn("analysisMode", allowed.text)

    def test_analysis_payload_accepts_flag(self):
        payload = self.app.ChatPayload(
            session_id="analysis-session",
            message="解释一下当前 prompt",
            analysis_mode=True,
        )

        self.assertTrue(payload.analysis_mode)

    def test_analysis_trace_records_clear_ip_and_embedding_alias_without_vector(self):
        session_id = self.app.create_session("10.20.30.40", "agent-analysis")

        trace_id = self.app.record_analysis_trace(
            session_id=session_id,
            event_type="embedding",
            visitor_ip="10.20.30.40",
            step_name="memory_query_embedding",
            payload={
                "alias": "embedding1",
                "input_preview": "用户问题摘要",
                "dim": 3,
                "vector": [0.1, 0.2, 0.3],
                "results": [{"memory_id": 1, "score": 0.92}],
            },
            duration_ms=12.5,
        )
        traces = self.app.list_analysis_traces(session_id=session_id)

        self.assertEqual(traces[0]["trace_id"], trace_id)
        self.assertEqual(traces[0]["visitor_ip"], "10.20.30.40")
        self.assertEqual(traces[0]["payload"]["alias"], "embedding1")
        self.assertNotIn("vector", traces[0]["payload"])
        self.assertEqual(traces[0]["duration_ms"], 12.5)

    def test_analysis_memory_trace_payload_includes_memory_content_and_candidates(self):
        memory_item = {
            "id": 7,
            "content": "用户最喜欢吃火锅。",
            "importance_label": "preference",
            "timeline_at": "2026-06-06T00:00:00+00:00",
            "visitor_ip": "10.20.30.40",
            "profile_id": 2,
            "confidence": 0.8,
            "score": 0.93,
            "text_relevance": 0.75,
        }

        result_payload = self.app.analysis_memory_result_payload([memory_item])
        candidate_payload = self.app.analysis_memory_candidate_payload([{
            **memory_item,
            "filter_reason": "selected",
        }])

        self.assertEqual(result_payload[0]["content"], "用户最喜欢吃火锅。")
        self.assertEqual(result_payload[0]["memory_id"], 7)
        self.assertEqual(candidate_payload[0]["content"], "用户最喜欢吃火锅。")
        self.assertEqual(candidate_payload[0]["filter_reason"], "selected")

    def test_analysis_trace_can_store_full_model_prompt(self):
        session_id = self.app.create_session("10.20.30.40", "agent-analysis")
        model_messages = [
            {"role": "system", "content": "系统 prompt"},
            {"role": "user", "content": "用户问题"},
        ]

        self.app.record_analysis_trace(
            session_id=session_id,
            event_type="model_prompt",
            visitor_ip="10.20.30.40",
            step_name="main_chat_prompt",
            payload={"messages": model_messages},
        )
        traces = self.app.list_analysis_traces(session_id=session_id)

        self.assertEqual(traces[0]["payload"]["messages"], model_messages)

    def test_memory_retrieval_query_fallback_extracts_keywords(self):
        query = self.app.fallback_memory_retrieval_query("我最喜欢吃什么")

        self.assertNotEqual(query, "我最喜欢吃什么")
        self.assertIn("用户", query)
        self.assertIn("喜欢", query)
        self.assertIn("食物", query)

    def test_build_system_prompt_embeds_planned_memory_query(self):
        session_id = self.app.create_session("10.20.30.40", "agent-analysis")
        original_planner = self.app.build_memory_retrieval_query
        original_embed = self.app.embedding_client.embed_text
        original_recall_pool = self.app.retrieve_curated_memory_recall_pool
        original_artifacts = self.app.retrieve_idle_artifacts
        captured = {}
        self.app.build_memory_retrieval_query = (
            lambda *args, **kwargs: "用户 食物 偏好 喜欢"
        )
        def fake_embed_text(text):
            captured["embedding_input"] = text
            return [1.0, 0.0]

        self.app.embedding_client.embed_text = fake_embed_text
        def fake_retrieve_curated_memory_recall_pool(_query_vector, **kwargs):
            captured["query_text"] = kwargs.get("query_text")
            return []

        self.app.retrieve_curated_memory_recall_pool = fake_retrieve_curated_memory_recall_pool
        self.app.retrieve_idle_artifacts = lambda _query_vector: []
        try:
            prompt = self.app.build_system_prompt(
                session_id,
                "我最喜欢吃什么",
                visitor_ip="10.20.30.40",
                analysis_trace_id="trace-memory-query",
            )
        finally:
            self.app.build_memory_retrieval_query = original_planner
            self.app.embedding_client.embed_text = original_embed
            self.app.retrieve_curated_memory_recall_pool = original_recall_pool
            self.app.retrieve_idle_artifacts = original_artifacts

        self.assertIn("当前真实日期", prompt)
        self.assertEqual(captured["embedding_input"], "用户 食物 偏好 喜欢")
        self.assertEqual(captured["query_text"], "用户 食物 偏好 喜欢")

    def test_analysis_background_endpoint_requires_login_and_lists_idle_work(self):
        client = TestClient(self.app.app)
        password = self._configure_admin_password()

        blocked = client.get("/api/analysis/background")
        login = client.post("/api/analysis/login", json={"password": password})
        allowed = client.get("/api/analysis/background")

        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(login.status_code, 200)
        self.assertEqual(allowed.status_code, 200)
        payload = allowed.json()
        self.assertIn("runs", payload)
        self.assertIn("artifacts", payload)


if __name__ == "__main__":
    unittest.main()
