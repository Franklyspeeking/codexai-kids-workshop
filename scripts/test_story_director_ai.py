"""Checks for the optional server-side story continuation boundary."""

import json
import os
import unittest
from unittest.mock import patch

from scripts import story_director_ai as story


PAYLOAD = {
    'theme': 'adventure', 'act': 1, 'hero': '小安', 'buddy': '',
    'director': '小导演', 'persona': '勇敢',
    'history': [{'act': 0, 'choice': '寻找地图'}],
}


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return self.content


class StoryDirectorAI(unittest.TestCase):
    def test_disabled_without_server_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(story.configured())
            with self.assertRaises(story.StoryError) as caught:
                story.generate(PAYLOAD, 'disabled-test')
            self.assertEqual(caught.exception.status, 503)

    def test_choice_history_reaches_provider_and_response_is_checked(self):
        reply = {'title': '第2幕', 'text': '小安打开地图，找到了通往灯塔的小路。',
                 'choices': ['继续前进', '请伙伴帮忙']}
        envelope = {'choices': [{'message': {'content': json.dumps(reply, ensure_ascii=False)}}]}
        sent = []

        def fake_open(request, timeout):
            sent.append(json.loads(request.data))
            return FakeResponse(json.dumps(envelope, ensure_ascii=False).encode())

        with patch.dict(os.environ, {
            'CODEXAI_STORY_AI_URL': 'https://example.com/v1/chat/completions',
            'CODEXAI_STORY_AI_KEY': 'unit-test-key',
            'CODEXAI_STORY_AI_MODEL': 'unit-test-model',
        }), patch.object(story, 'urlopen', fake_open):
            result = story.generate(PAYLOAD, 'success-test')
        self.assertEqual(result, reply)
        self.assertIn('寻找地图', sent[0]['messages'][1]['content'])
        self.assertEqual(sent[0]['model'], 'unit-test-model')

    def test_bad_inputs_and_unsafe_output_are_rejected(self):
        with self.assertRaises(story.StoryError):
            story.validate({**PAYLOAD, 'history': [{'act': 0, 'choice': '自杀'}]})
        with self.assertRaises(story.StoryError):
            story._validate_result({'title': '第2幕', 'text': '血腥场景',
                                    'choices': ['继续', '返回']}, 1)


if __name__ == '__main__':
    unittest.main()
