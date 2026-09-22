import json
import re
from typing import Dict, Tuple


def split_think_text(text: str) -> Tuple[str, str]:
    if not isinstance(text, str):
        return "", ""

    matches = list(re.finditer(r"<think>(.*?)</think>", text, flags=re.S))
    if not matches:
        return "", text.strip()

    reasoning = "\n\n".join(match.group(1).strip() for match in matches if match.group(1).strip())
    answer = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return reasoning, answer


def longest_suffix_prefix(text: str, marker: str) -> int:
    max_len = min(len(text), len(marker) - 1)
    for length in range(max_len, 0, -1):
        if marker.startswith(text[-length:]):
            return length
    return 0


class _TagStripper:
    def __init__(self) -> None:
        self.in_think = False
        self.buffer = ""

    def feed(self, text: str) -> str:
        if not text:
            return ""

        data = self.buffer + text
        self.buffer = ""
        output = []
        i = 0

        while i < len(data):
            if self.in_think:
                close_index = data.find("</think>", i)
                if close_index == -1:
                    keep = longest_suffix_prefix(data[i:], "</think>")
                    self.buffer = data[len(data) - keep :] if keep else ""
                    return "".join(output)
                i = close_index + len("</think>")
                self.in_think = False
                continue

            open_index = data.find("<think>", i)
            if open_index == -1:
                keep = longest_suffix_prefix(data[i:], "<think>")
                visible_end = len(data) - keep if keep else len(data)
                output.append(data[i:visible_end])
                self.buffer = data[visible_end:] if keep else ""
                return "".join(output)

            output.append(data[i:open_index])
            i = open_index + len("<think>")
            self.in_think = True

        return "".join(output)

    def flush(self) -> str:
        if self.in_think:
            self.buffer = ""
            return ""
        remaining = self.buffer
        self.buffer = ""
        return remaining


class ReplyGuard:
    """Quarantine an initial prefix before exposing untagged model self-analysis."""
    def __init__(self):
        self.pending = ""
        self.started = False

    def feed(self, text):
        if self.started:
            return text
        self.pending += text
        if len(self.pending) < 192:
            return ""
        return self.flush()

    def flush(self):
        text, self.pending = self.pending, ""
        prefix = text[:700]
        internal = "this_turn_result" in prefix or "我作为助手" in prefix or "系统提示的结构" in prefix
        deliberation = bool(re.search(r"我需要|我应该|我无法|我倾向|我认为|只能输出|工具调用能力|上一轮|规则说", prefix))
        if internal and deliberation:
            raise ValueError("模型返回了内部分析而非正式回答，已阻止显示；请重试。")
        self.started = True
        return text


class ThinkStripper:
    def __init__(self):
        self.tags = _TagStripper()
        self.guard = ReplyGuard()

    def feed(self, text):
        return self.guard.feed(self.tags.feed(text))

    def flush(self):
        return self.guard.feed(self.tags.flush()) + self.guard.flush()


def format_sse(event: str, payload: Dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
