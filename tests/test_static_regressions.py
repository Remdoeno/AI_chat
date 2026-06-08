import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StaticRegressionTests(unittest.TestCase):
    def test_backend_defines_current_date_context_and_injects_it(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("def current_date_context", app_py)
        self.assertIn("当前真实日期", app_py)
        self.assertIn("date_context = current_date_context()", app_py)
        self.assertIn("prompt_parts = [SYSTEM_PROMPT, date_context, visitor_context]", app_py)

    def test_backend_does_not_use_legacy_memory_context_in_prompt_builder(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")

        prompt_builder = app_py.split("def build_system_prompt(", 1)[1].split("def refresh_vector_memory", 1)[0]
        self.assertNotIn("memory.build_memory_context", prompt_builder)
        self.assertNotIn("legacy_memory_context", prompt_builder)
        self.assertIn('"0.5"', app_py)

    def test_backend_splits_schemas_and_streaming_helpers_out_of_app(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        schemas_py = (ROOT / "schemas.py").read_text(encoding="utf-8")
        streaming_py = (ROOT / "streaming_utils.py").read_text(encoding="utf-8")

        self.assertIn("from schemas import", app_py)
        self.assertIn("from streaming_utils import", app_py)
        self.assertNotIn("class ChatPayload(BaseModel)", app_py)
        self.assertNotIn("class ThinkStripper:", app_py)
        self.assertNotIn("def format_sse(", app_py)
        self.assertIn("class ChatPayload(BaseModel)", schemas_py)
        self.assertIn("class ThinkStripper:", streaming_py)
        self.assertIn("def format_sse(", streaming_py)

    def test_frontend_has_search_activity_region_and_handlers(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("searchActivity", html)
        self.assertIn("searchActivityList", html)
        self.assertIn("20260608_mobile_chrome_fix", html)
        self.assertIn("searchActivityList", js)
        self.assertIn("搜索：", js)
        self.assertNotIn("正在访问", js)
        self.assertIn("搜到候选网页", js)
        self.assertIn("浏览：", js)
        self.assertIn("已浏览", js)
        self.assertIn("memory: (payload)", js)
        self.assertIn("正在回忆", js)
        self.assertNotIn("正在读取", js)
        self.assertIn("function setSearchActivity", js)
        self.assertIn("startOpeningPrompt", js)
        self.assertIn("opening_prompt", js)
        self.assertIn("cached_opening", js)
        self.assertIn("hidden_user", js)
        self.assertIn("openingPlaceholder", js)
        self.assertIn("hasReceivedToken", js)
        self.assertIn("开场生成中", js)
        self.assertIn("isMessageComposing", js)
        self.assertIn("compositionstart", js)
        self.assertIn("compositionend", js)
        self.assertIn("isImeCompositionEvent(event)", js)
        self.assertIn("event.keyCode === 229", js)
        self.assertNotIn("OPENING_HIDDEN_PROMPT", js)
        self.assertNotIn("renderOpeningMessage", js)
        self.assertNotIn("searchActivityList.appendChild", js)
        self.assertIn("X-Qwen-Device-Id", js)
        self.assertIn("qwen_device_id", js)
        self.assertIn("crypto.randomUUID", js)
        self.assertNotIn("X-Client-Reported-IP", js)
        self.assertNotIn("api.ipify.org", js)
        self.assertNotIn("api64.ipify.org", js)
        self.assertNotIn("icanhazip.com", js)
        self.assertNotIn("ipinfo.io/ip", js)
        self.assertNotIn("isUsableClientIp", js)

    def test_large_image_upload_shows_compression_status(self):
        app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        analysis_js = (ROOT / "static" / "analysis.js").read_text(encoding="utf-8")
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("图片过大，狠狠压缩中...", app_js)
        self.assertIn("图片过大，狠狠压缩中...", analysis_js)
        self.assertIn("hasLargeAttachment", app_js)
        self.assertIn("hasLargeAttachment", analysis_js)
        self.assertNotIn("图片过大，单张最多 8MB", app_js)
        self.assertNotIn("图片过大：${file.name}", analysis_js)
        self.assertIn("compress_image_attachment", app_py)
        self.assertIn("IMAGE_COMPRESSION_TARGET_BYTES", app_py)

    def test_memory_admin_exposes_event_label(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        admin_html = (ROOT / "static" / "memory_admin.html").read_text(encoding="utf-8")
        admin_js = (ROOT / "static" / "memory_admin.js").read_text(encoding="utf-8")
        memory_html = (ROOT / "static" / "memory.html").read_text(encoding="utf-8")

        self.assertIn('"event"', app_py)
        self.assertIn("retrieve_future_event_memories", app_py)
        self.assertIn("format_future_events_context", app_py)
        self.assertIn('value="event"', admin_html)
        self.assertIn('"event"', admin_js)
        self.assertIn('value="event"', memory_html)
        self.assertIn("item.importance_label || item.label", admin_js)
        self.assertIn("20260608_auth_release", admin_html)

    def test_home_title_auth_page_and_release_docs_are_present(self):
        index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        auth_html = (ROOT / "static" / "auth.html").read_text(encoding="utf-8")
        auth_js = (ROOT / "static" / "auth.js").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("Ai助手聊天", index_html)
        self.assertNotIn("模型聊天", index_html)
        self.assertIn("旧管理员密码", auth_html)
        self.assertIn("/api/auth/password", auth_js)
        self.assertIn("@app.get(\"/auth\"", app_py)
        self.assertIn("has_configured_admin_password", app_py)
        self.assertIn("旺财1.0", readme)
        self.assertIn("家庭本地部署", readme)
        self.assertIn("QWEN_MODEL_BASE_URL", readme)
        self.assertIn("QWEN_IDLE_STORY_SEEDS_FILE", readme)
        self.assertIn("连续点击兔子 4 次", readme)
        self.assertIn("代理默认为空", readme)

    def test_release_removes_private_story_seeds_and_runtime_data_from_git(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("load_idle_story_seeds", app_py)
        self.assertIn("QWEN_IDLE_STORY_SEEDS_FILE", app_py)
        self.assertIn("data/", gitignore)
        self.assertIn("logs/", gitignore)
        self.assertIn("*.sqlite3", gitignore)
        self.assertIn("models/", gitignore)
        self.assertIn(".env", gitignore)

    def test_backend_reads_search_result_pages_for_context(self):
        app_py = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("WEB_SEARCH_MAX_CANDIDATES", app_py)
        self.assertIn("WEB_SEARCH_MAX_READ_PAGES", app_py)
        self.assertIn("WEB_SEARCH_MIN_CONFIDENCE", app_py)
        self.assertIn("def build_search_plan", app_py)
        self.assertIn("def parse_search_plan_response", app_py)
        self.assertIn("def assign_source_registry", app_py)
        self.assertIn("def append_source_footer_if_missing", app_py)
        self.assertIn("def fetch_web_page_summary", app_py)
        self.assertIn("page_excerpt", app_py)
        self.assertIn("status\": \"reading\"", app_py)
        self.assertIn("status\": \"candidates\"", app_py)
        self.assertIn("stage", app_py)
        self.assertIn("current_index", app_py)
        self.assertIn("max_pages", app_py)

    def test_markdown_renderer_keeps_ordered_lists_across_blank_lines(self):
        js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

        self.assertIn("blank lines inside lists should not reset ordered numbering", js)
        self.assertNotIn("if (!line.trim()) {\n      closeParagraph();\n      closeListsTo(-1);\n      continue;\n    }", js)

    def test_css_fixes_chat_composer_to_viewport(self):
        css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("height: 100vh", css)
        self.assertIn("overflow: hidden", css)
        self.assertIn(".search-activity", css)
        self.assertIn("min-height: 0", css)

    def test_user_message_label_is_on_right_side(self):
        css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

        self.assertIn(".message.user .message-label", css)
        self.assertIn("grid-column: 2", css)
        self.assertIn(".message.user .message-body", css)
        self.assertIn("grid-column: 1", css)
        self.assertIn("grid-template-columns: 72px minmax(0, 680px)", css)
        self.assertIn("grid-template-columns: minmax(0, 680px) 42px", css)

    def test_artifacts_page_exposes_idle_prompt_config(self):
        html = (ROOT / "static" / "artifacts.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "artifacts.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "artifacts.css").read_text(encoding="utf-8")

        self.assertIn("idlePromptInput", html)
        self.assertIn("savePromptButton", html)
        self.assertIn("/api/artifacts/prompt", js)
        self.assertIn("PUT", js)
        self.assertIn("20260608_artifact_delete", html)
        self.assertIn("function renderMarkdown", js)
        self.assertIn("setRenderedMarkdown(artifactDialogBody, item.content || \"\")", js)
        self.assertNotIn("body.textContent = item.content || \"\"", js)
        self.assertIn(".artifact-body strong", css)
        self.assertIn(".artifact-body ol", css)

    def test_artifacts_markdown_handles_deep_headings_and_list_boundaries(self):
        js = (ROOT / "static" / "artifacts.js").read_text(encoding="utf-8")

        self.assertIn("line.match(/^(#{1,6})\\s+(.+)$/)", js)
        self.assertIn("const level = Math.min(6, heading[1].length)", js)
        self.assertIn("function closeAllLists()", js)
        self.assertIn("closeAllLists();", js)
        self.assertIn("html.push(`<h${level}>", js)
        self.assertIn("closeListsTo(indent + 1);", js)

    def test_artifacts_page_supports_pagination(self):
        html = (ROOT / "static" / "artifacts.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "artifacts.js").read_text(encoding="utf-8")
        app = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn("loadMoreButton", html)
        self.assertIn("ARTIFACT_PAGE_SIZE", js)
        self.assertIn('params.set("offset", String(artifactOffset))', js)
        self.assertIn("renderArtifacts(await artifactsResp.json(), append)", js)
        self.assertIn("offset: int = Query", app)
        self.assertIn("OFFSET ?", app)

    def test_artifacts_page_is_card_grid_with_sort_like_and_detail_modal(self):
        html = (ROOT / "static" / "artifacts.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "artifacts.js").read_text(encoding="utf-8")
        css = (ROOT / "static" / "artifacts.css").read_text(encoding="utf-8")
        app = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('value="poetry"', html)
        self.assertIn("sortSelect", html)
        self.assertIn("orderSelect", html)
        self.assertIn("shuffleButton", html)
        self.assertIn("artifactDialog", html)
        self.assertIn("artifact-card", js)
        self.assertIn("renderArtifactCard", js)
        self.assertIn("openArtifactDialog", js)
        self.assertIn("likeArtifact", js)
        self.assertIn("dislikeArtifact", js)
        self.assertIn("renderDeleteButton", js)
        self.assertIn("deleteArtifact", js)
        self.assertIn("确认删除成果", js)
        self.assertIn("/api/artifacts/${artifactId}/like", js)
        self.assertIn("/api/artifacts/${artifactId}/like", js)
        self.assertIn("/api/artifacts/${artifactId}", js)
        self.assertIn("artifactDialogDelete", html)
        self.assertIn("event.detail >= 2", js)
        self.assertIn("ARTIFACT_PAGE_SIZE = 20", js)
        self.assertIn("grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))", css)
        self.assertIn("grid-template-columns: 1fr", css)
        self.assertIn("delete-artifact-button", css)
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn("position: static", css)
        self.assertIn('"likes", "INTEGER NOT NULL DEFAULT 0"', app)
        self.assertIn("@app.post(\"/api/artifacts/{artifact_id}/like\")", app)
        self.assertIn("@app.delete(\"/api/artifacts/{artifact_id}/like\")", app)
        self.assertIn("@app.delete(\"/api/artifacts/{artifact_id}\")", app)
        self.assertIn("position: sticky", css)
        self.assertNotIn("position: fixed", css)
        self.assertIn("opacity: 0.58", css)
        self.assertIn("event.target === artifactDialog", js)

    def test_chat_mobile_keeps_attachment_tools_visible(self):
        css = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn("20260608_mobile_chrome_fix", html)
        self.assertIn("height: 100dvh", css)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn("position: static", css)
        self.assertIn("grid-template-areas", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 76px", css)
        self.assertIn('"tools tools"', css)
        self.assertIn('"input send"', css)
        self.assertIn('"input send"', css)
        self.assertIn('"preview preview"', css)
        self.assertIn(".composer-tools", css)
        self.assertIn("grid-area: tools", css)

    def test_index_exposes_public_analysis_button(self):
        html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="/analysis"', html)
        self.assertIn("Analysis", html)

    def test_analysis_page_contract(self):
        html = (ROOT / "static" / "analysis.html").read_text(encoding="utf-8")
        js = (ROOT / "static" / "analysis.js").read_text(encoding="utf-8")

        self.assertIn("analysisMode", html)
        self.assertIn("tracePanel", html)
        self.assertIn("analysisImageInput", html)
        self.assertIn("analysisAttachmentPreview", html)
        self.assertIn("analysis_mode: true", js)
        self.assertIn("/api/analysis/traces", js)
        self.assertIn("embedding", js)
        self.assertIn("pendingAttachments", js)
        self.assertIn("image_url", js)
        self.assertIn("appendMessage(\"user\", text, attachmentsForMessage)", js)
        self.assertIn("openTraceKeys", js)
        self.assertIn("traceItemKey", js)
        self.assertIn("toggle", js)
        self.assertIn("openTraceKeys.add", js)
        self.assertIn("X-Qwen-Device-Id", js)
        self.assertIn("qwen_device_id", js)
        self.assertIn("crypto.randomUUID", js)
        self.assertNotIn("X-Client-Reported-IP", js)
        self.assertNotIn("api.ipify.org", js)
        self.assertNotIn("api64.ipify.org", js)
        self.assertNotIn("icanhazip.com", js)
        self.assertNotIn("ipinfo.io/ip", js)
        self.assertNotIn("isUsableClientIp", js)
        self.assertIn('value="0.75"', html)
        self.assertIn('value="0.95"', html)
        self.assertIn("backgroundPanel", html)
        self.assertIn("ANALYSIS_SAMPLING_STORAGE_KEY", js)
        self.assertIn("loadAnalysisSamplingSettings", js)
        self.assertIn("saveAnalysisSamplingSettings", js)
        self.assertIn("qwen_analysis_sampling_settings", js)
        self.assertIn("/api/analysis/background", js)
        self.assertIn('rel="icon"', html)
        self.assertIn("/static/favicon.svg", html)
        self.assertIn("backgroundItemKey", js)
        self.assertIn("openBackgroundKeys", js)
        self.assertIn("closedBackgroundKeys", js)
        self.assertIn("preserveScrollDuring", js)
        self.assertIn("tracePayloadScrollPositions", js)
        self.assertIn("backgroundPayloadScrollPositions", js)
        self.assertIn("collectPayloadScrollPositions", js)
        self.assertIn("restorePayloadScroll", js)
        self.assertIn("rememberPayloadScroll", js)
        self.assertIn("requestAnimationFrame", js)
        self.assertIn("20260608_ime_enter_fix", html)
        self.assertIn("refreshTraces", js)
        self.assertIn("sortTraceItemsNewestFirst", js)
        self.assertIn("sortTraceItemsNewestFirst(data.items).map(renderTraceItem)", js)
        self.assertIn("stopButton", html)
        self.assertIn("stopActiveGeneration", js)
        self.assertIn("/cancel", js)
        self.assertIn("activeController.abort", js)
        self.assertIn("startOpeningPrompt", js)
        self.assertIn("opening_prompt", js)
        self.assertIn("cached_opening", js)
        self.assertIn("hidden_user: hiddenUser", js)
        self.assertIn("isMessageComposing", js)
        self.assertIn("compositionstart", js)
        self.assertIn("compositionend", js)
        self.assertIn("isImeCompositionEvent(event)", js)
        self.assertIn("event.keyCode === 229", js)
        self.assertIn("hiddenUser: true", js)
        self.assertIn("showUser: false", js)
        self.assertIn("refreshBackground", js)
        self.assertIn('parsed.event === "memory"', js)
        self.assertIn("回忆中", js)
        self.assertIn("function renderMarkdown", js)
        self.assertIn("setRenderedMarkdown(assistantBody, assistantMarkdown)", js)
        self.assertIn("function renderArtifactItem", js)
        self.assertIn("background-markdown", js)
        self.assertIn("background-artifact-summary", js)
        self.assertIn(".background-markdown", css := (ROOT / "static" / "analysis.css").read_text(encoding="utf-8"))
        self.assertIn(".analysis-message.assistant .analysis-message-body", css)
        self.assertIn("analysis-back-button", html)
        self.assertIn(".analysis-back-button", css)
        self.assertNotIn("JSON.stringify(artifact, null, 2)", js)

    def test_identity_labels_use_device_instead_of_ip(self):
        admin_html = (ROOT / "static" / "memory_admin.html").read_text(encoding="utf-8")
        admin_js = (ROOT / "static" / "memory_admin.js").read_text(encoding="utf-8")
        analysis_login = (ROOT / "static" / "analysis_login.html").read_text(encoding="utf-8")

        self.assertIn("设备身份", admin_html)
        self.assertIn("关联设备身份", admin_html)
        self.assertIn("device ${item.visitor_ip}", admin_js)
        self.assertIn("设备身份", analysis_login)
        self.assertNotIn("<span>IP</span>", admin_html)
        self.assertNotIn("关联 IP", admin_html)
        self.assertNotIn("显示 IP", analysis_login)
        self.assertIn("20260608_analysis_markdown_artifacts", analysis_login)

    def test_analysis_login_uses_dedicated_endpoint(self):
        html = (ROOT / "static" / "analysis_login.html").read_text(encoding="utf-8")

        self.assertIn("/api/analysis/login", html)
        self.assertIn("/static/favicon.svg", html)
        self.assertNotIn("/api/admin/login", html)

    def test_favicon_asset_exists(self):
        favicon = ROOT / "static" / "favicon.svg"

        self.assertTrue(favicon.exists())
        self.assertIn("<svg", favicon.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
