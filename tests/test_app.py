"""Recording workflow checks with fake audio/ASR/cleanup; no external requests."""
import time
import tkinter as tk
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from app import App


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch('app.Tray'), patch('app.GlobalShortcut'),
            patch('app.keyring.get_password', return_value=''),
            patch('app.model_ready', return_value=True),
            patch('app.sd.query_devices', return_value=[]),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root)
        self.root.withdraw()
        self.addCleanup(self.app.close)

    def start_recording(self):
        with patch('app.sd.query_devices', return_value={'default_samplerate': 16000}), \
             patch('app.sd.InputStream') as factory:
            self.app.toggle(via_hotkey=True)
            self.stream = factory.return_value
        self.assertTrue(self.app.recording)
        self.assertEqual(self.app.popup.mode, 'recording')

    def test_cancel_discards_audio_and_never_transcribes(self):
        self.start_recording()
        self.app.frames = [np.ones((8000, 1), dtype=np.float32)]
        with patch('app.Transcriber') as transcriber:
            self.app.events.put(('cancel', None))
            self.app.drain()
            transcriber.assert_not_called()
        self.stream.stop.assert_called_once()
        self.stream.close.assert_called_once()
        self.assertFalse(self.app.recording)
        self.assertEqual(self.app.frames, [])
        self.assertFalse(self.app.busy)

    def test_finish_processes_audio_and_updates_result(self):
        self.start_recording()
        self.app.frames = [np.ones((8000, 1), dtype=np.float32) * 0.1]
        self.app.should_paste = False
        self.app.engine = MagicMock()
        self.app.engine.transcribe.return_value = '测试原文'
        final = '我有两个要求：\n\n第一点：缩小图标。\n第二点：添加动画。\n\n另外，保留快捷键。'
        with patch('app.cleanup', return_value=final) as cleanup:
            self.app.events.put(('finish', None))
            self.app.drain()
            deadline = time.monotonic() + 3
            while self.app.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
            self.assertFalse(self.app.busy)
            cleanup.assert_called_once()
        self.assertEqual(self.app.raw.get('1.0', 'end-1c'), '测试原文')
        self.assertEqual(self.app.result.get('1.0', 'end-1c'), final)
        self.assertEqual(self.app.popup.mode, 'complete')
        self.assertFalse(self.app.recording)
        self.assertIsNotNone(self.app.popup.timer)

    def test_paste_preserves_list_and_paragraph_breaks(self):
        final = '第一点：缩小图标。\n第二点：添加动画。\n\n另外，保留快捷键。'
        with patch('app.user32.GetForegroundWindow', return_value=123), \
             patch('app.user32.GetAsyncKeyState', return_value=0), \
             patch('app.pyperclip.copy') as copy, \
             patch('app.keyboard.Controller'):
            self.app.paste(final, 123)
        copy.assert_called_once_with(final)
        self.assertEqual(self.app.popup.mode, 'complete')

    def test_microphone_failure_is_visible(self):
        with patch('app.sd.query_devices', side_effect=RuntimeError('unavailable')):
            self.app.toggle(via_hotkey=True)
        self.assertFalse(self.app.recording)
        self.assertIn('无法打开麦克风', self.app.status.get())
        self.assertIsNotNone(self.app.popup.timer)

    def test_cleanup_error_stops_loading_and_preserves_transcript(self):
        self.start_recording()
        self.app.frames = [np.ones((8000, 1), dtype=np.float32) * 0.1]
        self.app.engine = MagicMock()
        self.app.engine.transcribe.return_value = '原文仍然保留'
        with patch('app.cleanup', side_effect=RuntimeError('网络失败，原文已保留。')):
            self.app.stop()
            deadline = time.monotonic() + 3
            while self.app.busy and time.monotonic() < deadline:
                self.root.update()
                time.sleep(0.01)
        self.assertFalse(self.app.busy)
        self.assertEqual(self.app.raw.get('1.0', 'end-1c'), '原文仍然保留')
        self.assertEqual(self.app.popup.mode, 'message')
        self.assertIsNone(self.app.popup.animation_timer)
        self.assertIn('网络失败', self.app.status.get())


if __name__ == '__main__':
    unittest.main()
