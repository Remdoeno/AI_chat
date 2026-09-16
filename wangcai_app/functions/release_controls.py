"""Legacy app bridge for reversible release policies and model diagnostics."""
from wangcai_app.release_features import ReleaseFeatureStore


def release_feature_store():
    return ReleaseFeatureStore(connect_db)


def release_feature_values():
    return release_feature_store().values(current_model_owner())


def release_feature_enabled(name):
    return release_feature_values().get(name, False)


from wangcai_app.model_runtime import GuardedClient, validate_slot, request_timeout, friendly_error


def configured_model_client(slot, timeout, task='chat'):
    flags = release_feature_values()
    if flags['fast_fail']:
        validate_slot(slot)
    http_client = model_http_client(slot, request_timeout(timeout, flags['bounded_waits']))
    retries = 0 if flags['bounded_waits'] or slot.get('provider') == 'local' else 2
    client = OpenAI(api_key=model_api_key(slot), base_url=str(slot.get('base_url') or BASE_URL).rstrip('/'),
                    http_client=http_client, max_retries=retries)
    def record(payload):
        try:
            record_event(None, 'model_runtime_call', 'local', payload)
        except Exception:
            pass
    return GuardedClient(client, slot, flags, task, record), http_client, slot
