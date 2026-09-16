"""Build chronological schedule conversations independently of model transport."""
import json


def schedule_conversation_messages(prompt, context):
    facts = {key: value for key, value in context.items() if key not in {"history", "message"}}
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "以下是当前日程数据库与时间背景，仅作事实参考；本轮请求在对话末尾。\n" + json.dumps(facts, ensure_ascii=False)},
    ]
    turns = []
    for item in context.get("history") or []:
        if not isinstance(item, dict):
            continue
        if "user" in item:
            result = item.get("result") or {}
            turns.append({"role": "user", "content": str(item["user"])[:4000]})
            reply = str(result.get("reply") or "")[:3000]
            changes = result.get("changes") or []
            operations = []
            for change in changes:
                event = change["event"]
                action = change["action"]
                operation = {"action": action}
                if action != "create":
                    operation.update(id=event["id"], revision=max(1, event["revision"] - (action == "update")))
                if action != "delete":
                    operation["event"] = {key: value for key, value in event.items()
                                          if key not in {"id", "revision", "updated_at"}}
                operations.append(operation)
            if reply:
                turns.append({"role": "assistant", "content": json.dumps(
                    {"reply": reply, "operations": operations, "saved_changes": changes}, ensure_ascii=False)})
        elif item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
            content = item["content"][:4000]
            if item["role"] == "assistant":
                content = json.dumps({"reply": content, "operations": []}, ensure_ascii=False)
            turns.append({"role": item["role"], "content": content})
    current = context.get("message", "")
    if turns and turns[-1] == {"role": "user", "content": current}:
        turns.pop()
    messages.extend(turns[-24:])
    # Put the active exchange beside the current fragment, after older history.
    # This is only a reference: it must not carry facts into an explicit new topic.
    previous = next((item for item in reversed(context.get("history") or [])
                     if isinstance(item, dict) and "user" in item), None)
    if previous:
        result = previous.get("result") or {}
        ids = {change["event"]["id"] for change in result.get("changes", [])}
        focus = {"previous_user_message": previous["user"],
                 "previous_assistant_reply": result.get("reply", ""),
                 "previous_saved_events_current_state": [event for event in context.get("events", []) if event["id"] in ids]}
        content = json.dumps({"recent_exchange_for_followup": focus, "message": current}, ensure_ascii=False)
    else:
        content = current
    messages.append({"role": "user", "content": content})
    return messages
