"""Read the foreground selection, with a fresh-copy fallback for non-UIA apps."""
import base64
import ctypes
import json
import subprocess
import time

import pyperclip
from pynput import keyboard

user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetClipboardSequenceNumber.restype = ctypes.c_ulong
user32.GetClipboardOwner.restype = ctypes.c_void_p
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
MAX_SELECTION = 20000

# Fixed script: no selected text or question is interpolated into executable code.
UIA_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try {
    Add-Type -AssemblyName UIAutomationClient
    Add-Type -AssemblyName UIAutomationTypes
    $element = [System.Windows.Automation.AutomationElement]::FocusedElement
    $supported = $false
    $text = ''
    for ($i = 0; $i -lt 4 -and $null -ne $element; $i++) {
        if ($element.Current.IsPassword) { throw 'protected' }
        $pattern = $null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) {
            $supported = $true
            $parts = @($pattern.GetSelection() | ForEach-Object { $_.GetText(20001) })
            $text = $parts -join "`n"
            break
        }
        $element = [System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($element)
    }
    @{supported=$supported; text=$text; protected=$false} | ConvertTo-Json -Compress
} catch {
    @{supported=$false; text=''; protected=($_.Exception.Message -eq 'protected')} | ConvertTo-Json -Compress
}
'''


def read_uia_selection():
    encoded = base64.b64encode(UIA_SCRIPT.encode('utf-16-le')).decode('ascii')
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                                 '-STA', '-EncodedCommand', encoded],
                                capture_output=True, encoding='utf-8-sig', timeout=5,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}


def validate_selection(text):
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError('未读取到选中文本，请先选中文字再按右 Alt + 空格。')
    if len(text) > MAX_SELECTION:
        raise RuntimeError('选中文本超过 20000 字，请缩小选择范围。')
    return text.strip()


def capture_selection(target):
    """Never activate another window or mistake old clipboard text for a selection."""
    def check_target():
        if user32.GetForegroundWindow() != target:
            raise RuntimeError('获取选中文本时窗口已切换，请在原窗口重新选择并触发。')

    check_target()
    deadline = time.monotonic() + 3
    while any(user32.GetAsyncKeyState(k) & 0x8000 for k in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        check_target()
        if time.monotonic() >= deadline:
            raise RuntimeError('请松开快捷键后重试。')
        time.sleep(0.03)
    selected = read_uia_selection()
    check_target()
    if selected.get('protected'):
        raise RuntimeError('无法读取受保护输入框，请在普通文本区域选择内容。')
    if selected.get('supported'):
        return validate_selection(selected.get('text', ''))

    # Do not empty or insert a sentinel into the clipboard. A sequence change is
    # required, even when its existing text happens to match the current selection.
    previous = user32.GetClipboardSequenceNumber()
    controller = keyboard.Controller()
    with controller.pressed(keyboard.Key.ctrl):
        controller.press('c')
        controller.release('c')
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        check_target()
        if user32.GetClipboardSequenceNumber() != previous:
            owner = user32.GetClipboardOwner()
            if owner:
                source_pid = ctypes.c_ulong()
                owner_pid = ctypes.c_ulong()
                user32.GetWindowThreadProcessId(target, ctypes.byref(source_pid))
                user32.GetWindowThreadProcessId(owner, ctypes.byref(owner_pid))
                if source_pid.value != owner_pid.value:
                    raise RuntimeError('剪贴板被其他程序更新，请重新选择文本后重试。')
            try:
                return validate_selection(pyperclip.paste())
            except pyperclip.PyperclipException:
                pass
        time.sleep(0.03)
    raise RuntimeError('未能复制选中文本，请确认此应用支持 Ctrl+C 后重试。')
