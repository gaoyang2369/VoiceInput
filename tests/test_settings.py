import tempfile
import unittest
from pathlib import Path

from app import load_settings
from core import DEFAULT_MODEL


class SettingsTests(unittest.TestCase):
    def test_invalid_or_missing_settings_use_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            self.assertEqual(load_settings(path)['model'], DEFAULT_MODEL)
            for contents in ('not json', '[]', 'null', '{"polish":"false","auto_paste":4,"model":[],"microphone":0}'):
                path.write_text(contents, encoding='utf-8')
                settings = load_settings(path)
                self.assertTrue(settings['polish'])
                self.assertTrue(settings['auto_paste'])
                self.assertEqual(settings['model'], DEFAULT_MODEL)

    def test_explicit_options_survive_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{"polish":false,"auto_paste":false,"model":" custom-model ","microphone":"mic"}',
                            encoding='utf-8')
            self.assertEqual(load_settings(path), {
                'polish': False, 'auto_paste': False, 'model': 'custom-model', 'microphone': 'mic',
                'vocabulary': []})

    def test_vocabulary_loads_with_invalid_entries_filtered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{"vocabulary":[" 接口 ",null,"VoiceInput","接口"]}', encoding='utf-8')
            self.assertEqual(load_settings(path)['vocabulary'], ['接口', 'VoiceInput'])
