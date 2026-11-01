"""Windows integration checks; no microphone, network or real key presses."""
import ctypes
import queue
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from desktop import GlobalShortcut, StatusPopup, user32


class ShortcutTests(unittest.TestCase):
    def setUp(self):
        self.fired = []
        self.shortcut = GlobalShortcut(lambda: self.fired.append(True), self.fail)

    def test_tap_and_repeat(self):
        for _ in range(8):
            self.assertTrue(self.shortcut.key_event(0xA5, False))
        self.assertEqual(self.fired, [])
        self.assertTrue(self.shortcut.key_event(0xA5, True))
        self.assertEqual(len(self.fired), 1)
        self.shortcut.key_event(0xA5, True)
        self.assertEqual(len(self.fired), 1)

    def test_left_alt_and_other_keys_do_not_trigger(self):
        for key in (0xA4, 0x20, 0x11):
            self.assertFalse(self.shortcut.key_event(key, False))
            self.assertFalse(self.shortcut.key_event(key, True))
        self.assertEqual(self.fired, [])

    def test_existing_modifier_keeps_chord(self):
        self.shortcut.key_event(0xA2, False)
        self.assertFalse(self.shortcut.key_event(0xA5, False))
        self.assertFalse(self.shortcut.key_event(0xA5, True))
        self.shortcut.key_event(0xA2, True)
        self.assertEqual(self.fired, [])

    def test_alt_then_key_forwards_alt_once_and_does_not_trigger(self):
        with patch.object(user32, 'keybd_event') as forward:
            self.shortcut.key_event(0xA5, False)
            self.shortcut.key_event(0x41, False)
            self.shortcut.key_event(0x41, False)
            self.shortcut.key_event(0x41, True)
            self.assertFalse(self.shortcut.key_event(0xA5, True))
            forward.assert_called_once()
        self.assertEqual(self.fired, [])

    def test_native_hook_installs_and_stops(self):
        ready = threading.Event()
        errors = []
        shortcut = GlobalShortcut(lambda: None, errors.append, ready.set)
        shortcut.start()
        try:
            self.assertTrue(ready.wait(3), errors)
            self.assertEqual(errors, [])
        finally:
            shortcut.stop()
        self.assertFalse(shortcut.thread.is_alive())


class PopupTests(unittest.TestCase):
    def test_visible_noactivate_buttons_timer_and_render(self):
        root = tk.Tk()
        root.withdraw()
        events = queue.Queue()
        popup = StatusPopup(root, events)
        try:
            foreground = user32.GetForegroundWindow()
            popup.show('右 Alt 已就绪', 5000)
            root.update()
            self.assertTrue(user32.IsWindowVisible(popup.hwnd))
            self.assertEqual(foreground, user32.GetForegroundWindow())
            popup.listen(0.8)
            root.update()
            self.assertIsNone(popup.timer)
            self.assertEqual(popup.mode, 'recording')
            self.assertEqual(user32.SendMessageW(popup.hwnd, 0x21, 0, 0), 3)
            # Deliver clicks to the actual Tk canvas without global input injection.
            self.assertEqual(popup.dimensions(), (150, 48))
            for x, expected in ((22, 'cancel'), (128, 'finish')):
                popup.canvas.event_generate('<ButtonRelease-1>', x=x, y=24)
                root.update()
                self.assertEqual(events.get_nowait(), (expected, None))
                self.assertEqual(foreground, user32.GetForegroundWindow())
            popup.render(level=0.8).save('tests/recording-preview.png')
            popup.show('正在识别语音…')
            self.assertTrue(events.empty())
            popup.hide()
            self.assertFalse(user32.IsWindowVisible(popup.hwnd))
        finally:
            popup.close()
            root.destroy()

    def test_loading_completion_and_animation_cleanup(self):
        root = tk.Tk()
        root.withdraw()
        events = queue.Queue()
        popup = StatusPopup(root, events)
        try:
            popup.processing()
            first = popup.render().tobytes()
            timer = popup.animation_timer
            deadline = time.monotonic() + 0.2
            while time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertGreater(popup.phase, 0)
            self.assertNotEqual(first, popup.render().tobytes())
            # Switching ASR -> cleanup must preserve the current sweep.
            phase, timer = popup.phase, popup.animation_timer
            popup.processing()
            self.assertEqual(popup.phase, phase)
            self.assertEqual(popup.animation_timer, timer)
            popup.canvas.event_generate('<ButtonRelease-1>', x=22, y=24)
            self.assertTrue(events.empty())
            popup.complete()
            self.assertEqual(popup.mode, 'complete')
            self.assertIsNotNone(popup.timer)
            deadline = time.monotonic() + 1.1
            while popup.animation_timer is not None and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertGreaterEqual(popup.phase, 14)
            self.assertIsNone(popup.animation_timer)
            popup.processing()
            popup.show('网络错误', 2000)
            self.assertIsNone(popup.animation_timer)
            popup.processing()
            popup.hide()
            self.assertIsNone(popup.animation_timer)
            self.assertEqual(popup.mode, 'hidden')
        finally:
            popup.close()
            root.destroy()


if __name__ == '__main__':
    unittest.main()
