"""Bounded text-only recovery before any rejected prefix reaches the browser."""
from streaming_utils import ThinkStripper, ReasoningLeakError


def recover_reply_stream(factories, record=lambda *_: None):
    recovering = False
    for index, factory in enumerate(factories):
        stream = None
        visible = False
        guard = ThinkStripper()
        try:
            stream = iter(factory())
            for chunk in stream:
                text = guard.feed(chunk)
                if text:
                    visible = True
                    yield text
            tail = guard.flush()
            if tail:
                visible = True
                yield tail
            if recovering and not visible:
                raise RuntimeError('empty_recovery')
            return
        except ReasoningLeakError:
            if visible:
                raise RuntimeError('暂时未能生成完整回复，请稍后再试。') from None
            recovering = True
            record(index + 1, 'reasoning_content_rejected')
        except Exception as exc:
            if not recovering or visible:
                raise
            record(index + 1, type(exc).__name__)
        finally:
            if stream is not None:
                close = getattr(stream, 'close', None)
                if close:
                    close()
    raise RuntimeError('暂时未能生成回复，请稍后再试。') from None
