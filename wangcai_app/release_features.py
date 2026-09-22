"""Independent, owner-scoped release switches; no model credentials or chat data."""
import json
from datetime import datetime, timezone

FEATURES = {
    'draw_single_pass': ('一次整理绘图提示词', '在一次调用内完成翻译、分类和优化，同时保留专业提示词与续改上下文。', '恢复原来的翻译、分类、优化三步流程。'),
    'gpu_role_detection': ('后台资源识别', '按实际进程识别模型用途，修正无检测结果时的默认部署显示。', '恢复原资源用途识别方式。'),
    'backend_compat': ('模型参数适配', '按模型整理输出额度和采样参数，减少接口不兼容。', '恢复 2.8.5 请求参数。'),
    'fast_fail': ('配置预检查', '缺少密钥或接口配置时立即说明原因。', '恢复由远端接口判断配置。'),
    'bounded_waits': ('等待与重试控制', '连接最多等待 8 秒，文本调用连续无响应最多等待 120 秒，不隐式重复请求。', '恢复原超时和 SDK 重试策略，可能等待较久。'),
    'structured_guard': ('后台结果完整性检查', '检查空结果、截断和 JSON，避免不完整结果进入后续流程。', '恢复各功能原有结果解析。'),
    'clear_errors': ('可读错误提示', '区分认证、限流、连接和服务故障，给出可执行的说明。', '恢复原接口错误文本。'),
    'model_probe': ('模型连接诊断', '可单独检查台前、后台模型是否返回正文及调用耗时。', '隐藏诊断入口，日常功能不受影响。'),
    'live_feedback': ('聊天等待反馈', '显示等待用时和恢复提示，改善移动端状态可读性。', '恢复原聊天状态显示。'),
}


class ReleaseFeatureStore:
    def __init__(self, connect):
        self.connect = connect

    @staticmethod
    def key(owner=''):
        return 'release_features_v3:' + (owner or '__system__')

    def overrides(self, owner=''):
        with self.connect() as conn:
            row = conn.execute('SELECT value FROM app_settings WHERE key=?', (self.key(owner),)).fetchone()
        if not row:
            return {}
        value = json.loads(row[0])
        return {k: v for k, v in value.items() if k in FEATURES and type(v) is bool}

    def values(self, owner=''):
        result = {key: True for key in FEATURES}
        result.update(self.overrides())
        if owner:
            result.update(self.overrides(owner))
        return result

    def public(self, owner=''):
        overrides = self.overrides(owner)
        values = self.values(owner)
        return {'version': '3.2.1', 'scope': 'user' if owner else 'system', 'owner': owner,
                'features': [{'id': key, 'title': text[0], 'description': text[1], 'rollback': text[2],
                              'enabled': values[key], 'inherited': bool(owner and key not in overrides)}
                             for key, text in FEATURES.items()]}

    def save(self, owner, changes):
        if not isinstance(changes, dict) or not changes or set(changes) - set(FEATURES):
            raise ValueError('请选择有效的更新项目')
        if any(type(v) is not bool and v is not None for v in changes.values()):
            raise ValueError('开关仅接受开启、关闭或恢复继承')
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT value FROM app_settings WHERE key=?', (self.key(owner),)).fetchone()
            data = json.loads(row[0]) if row else {}
            for key, value in changes.items():
                if value is None:
                    data.pop(key, None)
                else:
                    data[key] = value
            conn.execute('INSERT INTO app_settings VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',
                         (self.key(owner), json.dumps(data), datetime.now(timezone.utc).isoformat()))
        return self.public(owner)
