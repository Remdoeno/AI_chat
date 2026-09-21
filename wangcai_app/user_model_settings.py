"""Store only personal overrides. Inherited credentials never enter user records."""
import json
from datetime import datetime, timezone
from urllib.parse import urlparse

SLOTS = ('chat', 'background', 'image')
FIELDS = {'provider', 'display_name', 'base_url', 'model', 'api_key', 'use_proxy', 'proxy_url', 'thinking_enabled'}


class UserModelSettingsStore:
    def __init__(self, connect, normalize_slot, load_system, public_slot):
        self.connect, self.normalize_slot = connect, normalize_slot
        self.load_system, self.public_slot = load_system, public_slot

    @staticmethod
    def key(owner):
        if not owner:
            raise ValueError('请先绑定用户')
        return 'user_model_settings_v1:' + owner

    def load(self, owner):
        with self.connect() as conn:
            row = conn.execute('SELECT value FROM app_settings WHERE key=?', (self.key(owner),)).fetchone()
        return json.loads(row[0]) if row else {'slots': {}}

    def save(self, owner, payload):
        if not isinstance(payload, dict) or set(payload) - {*SLOTS, 'web_search_proxy', 'expected_owner'}:
            raise ValueError('模型配置字段不正确')
        if payload.get('expected_owner', owner) != owner:
            raise ValueError('绑定用户已改变，请重新打开模型设置')
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT value FROM app_settings WHERE key=?', (self.key(owner),)).fetchone()
            record = json.loads(row[0]) if row else {'slots': {}}
            overrides = record['slots']
            saved = record.setdefault('saved_slots', {})
            profiles = record.setdefault('provider_profiles', {})
            for name in SLOTS:
                if name not in payload:
                    continue
                raw = payload[name]
                if raw is None:
                    if name in overrides:
                        saved[name] = dict(overrides[name])
                        profiles.setdefault(name, {})[overrides[name]['provider']] = dict(overrides[name])
                    overrides.pop(name, None)
                    continue
                if not isinstance(raw, dict) or set(raw) - (FIELDS | {'inherit'}):
                    raise ValueError('模型槽配置不正确')
                inherit = raw.get('inherit', False)
                if type(inherit) is not bool:
                    raise ValueError('继承开关必须为布尔值')
                raw = {k: v for k, v in raw.items() if k != 'inherit'}
                if any(not isinstance(value, str) and value is not None for key, value in raw.items() if key not in {'use_proxy', 'thinking_enabled'}):
                    raise ValueError('模型配置需为文字')
                if 'thinking_enabled' in raw and type(raw['thinking_enabled']) is not bool:
                    raise ValueError('思考开关必须为布尔值')
                if 'use_proxy' in raw and type(raw['use_proxy']) is not bool:
                    raise ValueError('代理开关必须为布尔值')
                if any(isinstance(value, str) and len(value) > 4096 for value in raw.values()):
                    raise ValueError('模型配置过长')
                old = overrides.get(name) or saved.get(name, {})
                if old:
                    profiles.setdefault(name, {})[old['provider']] = dict(old)
                provider = raw.get('provider') or old.get('provider') or ('none' if name == 'image' else 'local')
                allowed = {'none', 'hidream', 'qwen_image', 'custom'} if name == 'image' else {'local', 'openai', 'deepseek', 'zhipu', 'dashscope', 'doubao', 'custom'}
                if provider not in allowed:
                    raise ValueError('当前模型类型不支持所选服务')
                if provider != old.get('provider'):
                    old = profiles.get(name, {}).get(provider, {})
                same_provider = provider == old.get('provider')
                merged = {**(old if same_provider else {}), **raw, 'provider': provider}
                # Empty form submissions preserve only this user's own slot key.
                merged['api_key'] = raw.get('api_key') or (old.get('api_key', '') if same_provider else '')
                if raw.get('base_url') and raw['base_url'].rstrip('/') != str(old.get('base_url') or '').rstrip('/') and not raw.get('api_key'):
                    merged['api_key'] = ''
                slot = self.normalize_slot(merged, existing=old if same_provider else None)
                # Do not inherit environment/preset secrets, even for local services.
                slot['api_key'] = merged['api_key']
                for field in ('base_url', 'proxy_url'):
                    if not slot[field]:
                        continue
                    parsed = urlparse(slot[field])
                    schemes = {'http', 'https'} if field == 'base_url' else {'http', 'https', 'socks5', 'socks5h'}
                    if parsed.scheme not in schemes or not parsed.hostname or (field == 'base_url' and (parsed.username or parsed.password or parsed.query or parsed.fragment)):
                        raise ValueError('接口地址或代理地址格式不正确')
                if provider != 'none' and (not slot['base_url'] or not slot['model']):
                    raise ValueError('请填写接口地址和模型名')
                saved[name] = dict(slot)
                profiles.setdefault(name, {})[provider] = dict(slot)
                if inherit:
                    overrides.pop(name, None)
                else:
                    overrides[name] = slot
            if 'web_search_proxy' in payload:
                proxy = payload['web_search_proxy']
                if not isinstance(proxy, str) or len(proxy) > 4096:
                    raise ValueError('代理地址格式不正确')
                if proxy and (urlparse(proxy).scheme not in {'http','https','socks5','socks5h'} or not urlparse(proxy).hostname):
                    raise ValueError('代理地址格式不正确')
                record['web_search_proxy'] = proxy.strip()
            conn.execute('INSERT INTO app_settings VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
                         (self.key(owner), json.dumps(record, ensure_ascii=False), datetime.now(timezone.utc).isoformat()))
        return self.public(owner)

    def effective(self, owner):
        system = self.load_system()
        if not owner:
            return system
        record = self.load(owner)
        result = {**system, **{key: dict(value) for key, value in record['slots'].items()}}
        if 'web_search_proxy' in record:
            result['web_search_proxy'] = record['web_search_proxy']
        return result

    def public(self, owner):
        record, system = self.load(owner), self.load_system()
        result = {'scope': 'user', 'owner': owner, 'provider_api_keys': {}, 'web_search_proxy': record.get('web_search_proxy', '')}
        for name in SLOTS:
            if name in record['slots']:
                result[name] = {**self.public_slot(record['slots'][name]), 'inherit': False}
            else:
                slot = system[name]
                result[name] = {'inherit': True, 'provider': slot['provider'], 'display_name': slot['display_name'], 'model': slot['model'],
                                'base_url': '', 'proxy_url': '', 'has_api_key': False, 'use_proxy': False,
                                'thinking_enabled': self.public_slot(slot)['thinking_enabled'], 'thinking_supported': self.public_slot(slot)['thinking_supported']}
        result['saved_slots'] = {k: self.public_slot(v) for k, v in record.get('saved_slots', {}).items() if k in SLOTS}
        result['provider_profiles'] = {k: {provider: self.public_slot(v) for provider, v in values.items()} for k, values in record.get('provider_profiles', {}).items() if k in SLOTS}
        return result
