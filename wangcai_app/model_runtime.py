"""Composable runtime policies for OpenAI-compatible providers; no persistent state."""
import json
import re
import time
from types import SimpleNamespace
import httpx


class ModelCallError(RuntimeError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def validate_slot(slot):
    if not str(slot.get('base_url') or '').strip() or not str(slot.get('model') or '').strip():
        raise ModelCallError('configuration', '模型接口或型号未配置，请打开模型设置补齐。')
    if slot.get('provider') in {'openai', 'deepseek', 'zhipu', 'dashscope', 'doubao'} and not str(slot.get('api_key') or '').strip():
        raise ModelCallError('credentials', '当前模型没有配置 API Key。台前与后台的密钥分别保存，请检查对应设置。')


def request_timeout(seconds, enabled):
    if not enabled:
        return seconds
    # This is an inactivity timeout: long streams continue while making progress.
    limit = min(float(seconds), 120.0)
    return httpx.Timeout(limit, connect=min(limit, 8.0), pool=min(limit, 8.0), write=min(limit, 30.0))


def normalize_parameters(slot, kwargs):
    params = dict(kwargs)
    model = str(slot.get('model') or '').lower()
    if slot.get('provider') == 'openai' and (model.startswith('gpt-5') or re.match(r'^o[134](?:-|$)', model)):
        if 'max_tokens' in params:
            params['max_completion_tokens'] = params.pop('max_tokens')
        # Reasoning families do not uniformly accept custom sampling controls.
        params.pop('temperature', None)
        params.pop('top_p', None)
    return params


def friendly_error(exc):
    if isinstance(exc, ModelCallError):
        return exc
    status = getattr(exc, 'status_code', None)
    name = type(exc).__name__.lower()
    if status in (401, 403):
        return ModelCallError('authentication', '模型认证失败：请检查此模型的 API Key 和访问权限。')
    if status == 429:
        return ModelCallError('rate_limit', '模型服务限流或额度不足，请稍后重试并检查账户额度。')
    if status == 404:
        return ModelCallError('model_not_found', '模型接口或型号不存在，请检查 Base URL 和模型名称。')
    if status in (400, 422):
        return ModelCallError('request', '模型不接受本次请求，请检查型号、图片支持情况和请求长度。')
    if status and status >= 500:
        return ModelCallError('upstream', '模型服务暂时不可用，请稍后重试。')
    if 'timeout' in name or isinstance(exc, httpx.TimeoutException):
        return ModelCallError('timeout', '模型等待超时，已结束本次等待。请检查代理或网络，或更换模型后重试。')
    if 'connection' in name or isinstance(exc, httpx.NetworkError):
        return ModelCallError('connection', '无法连接模型服务，请检查服务是否运行，以及代理和网络设置。')
    return ModelCallError('model_error', '模型调用失败，请检查模型配置或稍后重试。')


def needs_json(params, task):
    if params.get('response_format', {}).get('type') == 'json_object':
        return True
    if task != 'background':
        return False
    system = '\n'.join(str(m.get('content') or '') for m in params.get('messages', []) if m.get('role') == 'system')
    return bool(re.search(r'(只输出|只返回|输出严格|只生成)[^\n。]{0,25}JSON|strict JSON|only.*JSON', system, re.I))


def check_response(response, json_expected=False):
    choices = getattr(response, 'choices', None)
    if not choices:
        raise ModelCallError('empty', '模型没有返回结果，本次操作未完成，请重试。')
    choice = choices[0]
    if choice.finish_reason == 'length':
        raise ModelCallError('truncated', '模型输出达到上限，结果不完整。本次操作未完成，请增加额度或简化请求。')
    message = choice.message
    text = getattr(message, 'content', '') or getattr(message, 'refusal', '') or ''
    if not text and not getattr(message, 'tool_calls', None):
        raise ModelCallError('empty', '模型没有返回正文，本次操作未完成，请重试。')
    if json_expected:
        value = re.sub(r'^```(?:json)?\s*|\s*```$', '', str(text).strip())
        # Local models may put a reasoning block before their JSON answer.
        value = re.sub(r'^<think>.*?</think>\s*', '', value, flags=re.S)
        try:
            json.loads(value)
        except (ValueError, TypeError):
            raise ModelCallError('invalid_json', '模型返回的结构化结果不完整，本次操作未完成，请重试。') from None


class GuardedCompletions:
    def __init__(self, create, slot, flags, task, record):
        self._create, self.slot, self.flags, self.task, self.record = create, slot, flags, task, record

    def create(self, **kwargs):
        params = normalize_parameters(self.slot, kwargs) if self.flags.get('backend_compat') else dict(kwargs)
        json_expected = needs_json(params, self.task)
        started = time.monotonic()
        try:
            response = self._create(**params)
            if params.get('stream'):
                return self._stream(response, started)
            if self.flags.get('structured_guard'):
                check_response(response, json_expected)
            self._record('completed', started)
            return response
        except Exception as exc:
            self._record(getattr(exc, 'code', 'failed'), started)
            if self.flags.get('clear_errors'):
                raise friendly_error(exc) from exc
            raise

    def _record(self, status, started, **extra):
        if self.flags.get('model_probe') and self.record:
            self.record({'provider': self.slot.get('provider'), 'model': self.slot.get('model'),
                         'status': status, 'duration_ms': round((time.monotonic() - started) * 1000), **extra})

    def _stream(self, stream, started):
        first_text = None
        finish = None
        has_tool_or_refusal = False
        try:
            for chunk in stream:
                if getattr(chunk, 'choices', None):
                    choice = chunk.choices[0]
                    finish = choice.finish_reason or finish
                    has_tool_or_refusal = has_tool_or_refusal or bool(getattr(choice.delta, "tool_calls", None) or getattr(choice.delta, "refusal", None))
                    if getattr(choice.delta, 'content', None) and first_text is None:
                        first_text = round((time.monotonic() - started) * 1000)
                yield chunk
            if self.flags.get('structured_guard') and finish == 'length':
                raise ModelCallError('truncated', '模型回复达到输出上限，内容未完成，请增加额度或简化请求。')
            if self.flags.get('structured_guard') and first_text is None and not has_tool_or_refusal:
                raise ModelCallError('empty', '模型未返回正文，本次回复未完成，请重试。')
            self._record('completed' if first_text is not None or has_tool_or_refusal else 'empty', started, first_text_ms=first_text)
        except GeneratorExit:
            self._record('cancelled', started, first_text_ms=first_text)
            raise
        except Exception as exc:
            self._record(getattr(exc, 'code', 'failed'), started, first_text_ms=first_text)
            if self.flags.get('clear_errors'):
                raise friendly_error(exc) from exc
            raise
        finally:
            close = getattr(stream, 'close', None)
            if close:
                close()


class GuardedClient:
    def __init__(self, client, slot, flags, task, record=None):
        self._client, self._slot, self._flags, self._task, self._record = client, slot, flags, task, record
        self.chat = SimpleNamespace(completions=GuardedCompletions(client.chat.completions.create, slot, flags, task, record))

    def with_options(self, **kwargs):
        return GuardedClient(self._client.with_options(**kwargs), self._slot, self._flags, self._task, self._record)

    def __getattr__(self, name):
        return getattr(self._client, name)
