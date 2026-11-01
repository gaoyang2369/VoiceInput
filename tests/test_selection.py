import unittest
import base64
import subprocess
from unittest.mock import patch

from selection import capture_selection, UIA_SCRIPT, nearest_selection_rect, SelectionSnapshot


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.patches = [patch('selection.user32.GetForegroundWindow', return_value=123),
                        patch('selection.user32.GetAsyncKeyState', return_value=0)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_uia_selection_does_not_touch_clipboard(self):
        with patch('selection.read_uia_selection', return_value={'supported': True, 'text': '选中的材料'}), \
             patch('selection.keyboard.Controller') as keyboard:
            self.assertEqual(capture_selection(123), '选中的材料')
            keyboard.assert_not_called()

    def test_snapshot_keeps_bounds_near_original_cursor(self):
        with patch('selection.read_uia_selection', return_value={
                'supported': True, 'text': '选中的材料', 'bounds': [[100, 100, 300, 120], [100, 120, 220, 140]]}), \
             patch('selection.cursor_anchor', return_value=(210, 135, 210, 135)):
            selected = capture_selection(123, with_location=True)
        self.assertEqual(selected, SelectionSnapshot('选中的材料', (100, 120, 220, 140)))

    def test_invalid_or_unavailable_bounds_fall_back_to_trigger_point(self):
        fallback = (20, 30, 20, 30)
        self.assertEqual(nearest_selection_rect([[1, 1, 1, 1], [0, float('inf'), 20, 30]], fallback), fallback)
        self.assertEqual(nearest_selection_rect([], fallback), fallback)

    def test_empty_supported_selection_never_uses_old_clipboard(self):
        with patch('selection.read_uia_selection', return_value={'supported': True, 'text': ''}), \
             patch('selection.pyperclip.paste') as paste:
            with self.assertRaisesRegex(RuntimeError, '未读取到选中文本'):
                capture_selection(123)
            paste.assert_not_called()

    def test_window_change_aborts_before_copying(self):
        with patch('selection.user32.GetForegroundWindow', side_effect=[123, 456]), \
             patch('selection.read_uia_selection', return_value={}), \
             patch('selection.keyboard.Controller') as keyboard:
            with self.assertRaisesRegex(RuntimeError, '窗口已切换'):
                capture_selection(123)
            keyboard.assert_not_called()

    def test_fresh_copy_fallback(self):
        with patch('selection.read_uia_selection', return_value={}), \
             patch('selection.user32.GetClipboardSequenceNumber', side_effect=[10, 11]), \
             patch('selection.user32.GetClipboardOwner', return_value=0), \
             patch('selection.keyboard.Controller') as keyboard, \
             patch('selection.pyperclip.paste', return_value='新复制的文本'):
            self.assertEqual(capture_selection(123), '新复制的文本')
            keyboard.return_value.press.assert_called_once_with('c')

    def test_unchanged_clipboard_is_rejected(self):
        with patch('selection.read_uia_selection', return_value={}), \
             patch('selection.user32.GetClipboardSequenceNumber', return_value=10), \
             patch('selection.time.monotonic', side_effect=[0, 0, 2]), \
             patch('selection.keyboard.Controller'), \
             patch('selection.pyperclip.paste') as paste:
            with self.assertRaisesRegex(RuntimeError, '未能复制'):
                capture_selection(123)
            paste.assert_not_called()

    def test_oversized_selection_is_not_silently_truncated(self):
        with patch('selection.read_uia_selection', return_value={'supported': True, 'text': '字' * 20001}):
            with self.assertRaisesRegex(RuntimeError, '20000'):
                capture_selection(123)

    def test_protected_field_has_no_copy_fallback(self):
        with patch('selection.read_uia_selection', return_value={'protected': True}), \
             patch('selection.keyboard.Controller') as keyboard:
            with self.assertRaisesRegex(RuntimeError, '受保护'):
                capture_selection(123)
            keyboard.assert_not_called()

    def test_uia_script_parses_and_windows_assemblies_load(self):
        # Validate the actual helper dependencies without reading any user's UI.
        source = base64.b64encode(UIA_SCRIPT.encode('utf-16-le')).decode('ascii')
        script = ("$ErrorActionPreference='Stop'; Add-Type -AssemblyName UIAutomationClient; "
                  "Add-Type -AssemblyName UIAutomationTypes; $tokens=$null; $errors=$null; "
                  "$source=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + source + "')); "
                  "[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors) | Out-Null; "
                  "if ($errors.Count) { throw 'Invalid UIA helper syntax' }; Write-Output 'uia-ready'")
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-STA', '-EncodedCommand', encoded],
                                capture_output=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        self.assertIn(b'uia-ready', result.stdout)


if __name__ == '__main__':
    unittest.main()
