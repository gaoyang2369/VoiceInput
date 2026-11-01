"""Check the cleanup request contract and multiline transport, without network."""
import unittest
from unittest.mock import Mock

from core import cleanup


class FormattingTests(unittest.TestCase):
    def test_structured_plain_text_roundtrip(self):
        expected = '我有两个要求：\n\n第一点：缩小图标。\n第二点：添加动画。\n\n另外，保持右 Alt。'
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {
            'choices': [{'finish_reason': 'stop', 'message': {'content': '\n' + expected + '\n'}}]}
        original = '我有两个要求第一缩小图标第二添加动画另外保持右Alt'
        self.assertEqual(cleanup(original, 'test-key', session=session), expected)
        payload = session.post.call_args.kwargs['json']
        self.assertEqual(payload['messages'][1], {'role': 'user', 'content': original})
        self.assertEqual(payload['messages'][0]['role'], 'system')
        self.assertFalse(payload['stream'])

    def test_service_failure_still_preserves_raw_text_in_error(self):
        session = Mock()
        session.post.return_value.status_code = 429
        with self.assertRaisesRegex(RuntimeError, '原文已保留'):
            cleanup('原文', 'test-key', session=session)


if __name__ == '__main__':
    unittest.main()
