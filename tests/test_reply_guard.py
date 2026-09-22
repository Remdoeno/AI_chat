import unittest
from streaming_utils import ThinkStripper

class ReplyGuardTests(unittest.TestCase):
    def test_leak_is_not_forwarded_even_token_by_token(self):
        raw='用户说组会改回周三，我需要更新日程。但 this_turn_result 是上一轮的历史结果。我应该怎么回应？'
        guard=ThinkStripper();visible=[]
        with self.assertRaises(ValueError):
            for char in raw: visible.append(guard.feed(char))
            visible.append(guard.flush())
        self.assertFalse(''.join(visible))

    def test_normal_reply_and_code_are_preserved(self):
        for raw in ['已保存：组会 · 每周三 15:00–17:00', '变量 this_turn_result 表示当轮结果。', '这是一段普通回答。'*80]:
            guard=ThinkStripper()
            self.assertEqual(''.join(guard.feed(c) for c in raw)+guard.flush(),raw)

    def test_tagged_reasoning_split_across_chunks(self):
        guard=ThinkStripper();raw='<think>我需要更新 this_turn_result。</think>已保存。'
        self.assertEqual(''.join(guard.feed(c) for c in raw)+guard.flush(),'已保存。')

    def test_unclosed_think_is_never_shown(self):
        guard=ThinkStripper()
        self.assertEqual(guard.feed('<think>secret')+guard.flush(),'')
