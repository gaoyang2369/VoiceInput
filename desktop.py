"""Windows background integration; popup windows never activate the target app."""
import ctypes
from ctypes import wintypes as w
import threading
import math
import tkinter as tk
from PIL import Image, ImageDraw, ImageFont, ImageTk

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
user32 = ctypes.windll.user32
user32.GetParent.argtypes = [w.HWND]
user32.GetParent.restype = w.HWND
user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [ctypes.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.CallWindowProcW.restype = LRESULT

kernel32 = ctypes.windll.kernel32
user32.GetForegroundWindow.restype = w.HWND
user32.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
user32.CreateWindowExW.restype = w.HWND
user32.SetWindowTextW.argtypes = [w.HWND, w.LPCWSTR]
user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, w.UINT]
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
user32.DestroyWindow.argtypes = [w.HWND]
user32.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
user32.MonitorFromWindow.restype = w.HANDLE
user32.GetMonitorInfoW.argtypes = [w.HANDLE, w.LPVOID]


class MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', w.DWORD), ('rcMonitor', w.RECT), ('rcWork', w.RECT), ('dwFlags', w.DWORD)]


class StatusPopup:
    UI_SCALE = 0.75

    def __init__(self, root, events=None):
        self.root = root
        self.events = events
        self.timer = None
        self.animation_timer = None
        self.mode = 'message'
        self.phase = 0
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(bg='#010203')
        self.window.wm_attributes('-transparentcolor', '#010203')
        self.canvas = tk.Canvas(self.window, bg='#010203', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.window.update_idletasks()
        self.hwnd = user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        style = user32.GetWindowLongPtrW(self.hwnd, -20)
        user32.SetWindowLongPtrW(self.hwnd, -20, style | 0x08000088)
        # Keep native callback alive. Clicking the bar must not move the caret.
        def proc(hwnd, message, wp, lp):
            if message == 0x21:  # WM_MOUSEACTIVATE / MA_NOACTIVATE
                return 3
            return user32.CallWindowProcW(self.old_proc, hwnd, message, wp, lp)
        self.proc = WNDPROC(proc)
        self.old_proc = user32.SetWindowLongPtrW(self.hwnd, -4,
            ctypes.cast(self.proc, ctypes.c_void_p).value)
        self.canvas.bind('<ButtonRelease-1>', self.click)
        self.canvas.bind('<Motion>', self.hover)

    def click(self, event):
        x, y = event.x / self.UI_SCALE, event.y / self.UI_SCALE
        if self.mode == 'recording' and self.events is not None and 14 <= y <= 50:
            if 10 <= x <= 50:
                self.events.put(('cancel', None))
            elif 150 <= x <= 190:
                self.events.put(('finish', None))

    def hover(self, event):
        x, y = event.x / self.UI_SCALE, event.y / self.UI_SCALE
        button = self.mode == 'recording' and 14 <= y <= 50 and (10 <= x <= 50 or 150 <= x <= 190)
        self.canvas.configure(cursor='hand2' if button else '')

    def dimensions(self):
        compact = self.mode in ('recording', 'processing', 'complete')
        return round((200 if compact else 520) * self.UI_SCALE), round(64 * self.UI_SCALE)

    def render(self, text='', level=0):
        compact = self.mode in ('recording', 'processing', 'complete')
        width, height, scale = (200 if compact else 520), 64, 3
        im = Image.new('RGB', (width * scale, height * scale), '#010203')
        d = ImageDraw.Draw(im)
        def box(coords):
            return tuple(int(v * scale) for v in coords)
        def line(coords, fill='white', stroke=2):
            d.line(box(coords), fill=fill, width=stroke * scale)
        d.rounded_rectangle(box((3, 5, width - 3, 59)), radius=27 * scale,
                            fill='#090909', outline='#555555', width=scale)
        if self.mode == 'recording':
            d.ellipse(box((12, 14, 48, 50)), fill='#484848')
            d.ellipse(box((152, 14, 188, 50)), fill='white')
            line((23, 25, 37, 39)); line((37, 25, 23, 39))
            line((162, 32, 168, 38, 179, 26), '#111111', 3)
            for i in range(11):
                # Silent input stays low; movement is driven by actual microphone RMS.
                envelope = 0.4 + 0.6 * abs(math.sin(self.phase * 0.7 + i * 1.8))
                h = 4 + min(1, level) * 23 * envelope
                x = 67 + i * 6
                d.rounded_rectangle(box((x, 32 - h / 2, x + 3, 32 + h / 2)),
                                    radius=scale, fill='white')
        elif self.mode in ('processing', 'complete'):
            if self.mode == 'complete' and self.phase >= 14:
                line((90, 32, 97, 39, 111, 25), 'white', 3)
            else:
                # Indeterminate left-to-right sweep, not a fabricated percentage.
                d.rounded_rectangle(box((38, 29, 162, 35)), radius=3 * scale, fill='#333333')
                if self.mode == 'processing':
                    head = (self.phase % 42) / 41 * 156
                    left, right = max(0, head - 32), min(124, head)
                else:
                    left, right = 0, 124 * min(1, (self.phase + 1) / 14)
                if right > left:
                    d.rounded_rectangle(box((38 + left, 29, 38 + right, 35)),
                                        radius=3 * scale, fill='white')
        else:
            font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 16 * scale)
            # Preserve the full message in the settings window; fit the toast on screen.
            while text and d.textlength(text, font=font) > (width - 40) * scale:
                text = text[:-2].rstrip('…') + '…'
            d.text((width * scale / 2, 32 * scale), text, font=font,
                   fill='white', anchor='mm')
        return im.resize(self.dimensions(), Image.Resampling.LANCZOS)

    def stop_animation(self):
        if self.animation_timer is not None:
            self.root.after_cancel(self.animation_timer)
            self.animation_timer = None

    def animate(self):
        self.animation_timer = None
        if self.mode not in ('processing', 'complete'):
            return
        self.phase += 1
        self.paint()
        if self.mode == 'processing' or self.phase < 14:
            self.animation_timer = self.root.after(33, self.animate)

    def processing(self):
        # ASR -> text cleanup is one continuous animation, with no visual reset.
        if self.mode != 'processing':
            self.show('', mode='processing')

    def complete(self):
        self.show('', 1300, mode='complete')

    def paint(self, text='', level=0):
        self.photo = ImageTk.PhotoImage(self.render(text, level), master=self.window)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self.photo)

    def listen(self, level=0):
        if self.mode != 'recording':
            self.show('', mode='recording')
        self.phase += 1
        self.paint(level=level)

    def show(self, text, milliseconds=None, mode='message'):
        self.stop_animation()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.mode = mode
        self.phase = 0
        self.canvas.configure(cursor='')
        width, height = self.dimensions()
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        monitor = user32.MonitorFromWindow(user32.GetForegroundWindow(), 2)
        if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.rcWork
            x, y = (rect.left + rect.right - width) // 2, rect.bottom - height - 30
        else:
            x, y = 30, 30
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.canvas.configure(width=width, height=height)
        self.paint(text)
        self.window.update_idletasks()
        # SWP_NOACTIVATE | SHOWWINDOW. Neither keyboard focus nor caret is moved.
        user32.SetWindowPos(self.hwnd, w.HWND(-1), x, y, width, height, 0x0050)
        if mode in ('processing', 'complete'):
            self.animation_timer = self.root.after(33, self.animate)
        if milliseconds:
            self.timer = self.root.after(milliseconds, self.hide)

    def hide(self):
        self.stop_animation()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        user32.ShowWindow(self.hwnd, 0)
        self.timer = None
        self.mode = 'hidden'

    def close(self):
        self.stop_animation()
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        user32.SetWindowLongPtrW(self.hwnd, -4, self.old_proc)
        self.window.destroy()


class GlobalShortcut:
    def __init__(self, callback, error, ready=None):
        self.callback, self.error, self.ready = callback, error, ready
        self.thread_id = None
        self.thread = None
        self.stopping = threading.Event()
        self.down = False
        self.used = False
        self.forwarded = False
        self.held = set()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def key_event(self, vk, up):
        """Reserve a bare Right Alt tap; restore Right Alt for actual key chords."""
        if vk == 0xA5:
            if not up:
                if not self.down:
                    self.down = True
                    self.used = bool(self.held)
                    self.forwarded = self.used
                    return not self.forwarded
                return not self.forwarded  # ignore key auto-repeat
            if not self.down:
                return False
            fire, consume = not self.used, not self.forwarded
            self.down = False
            self.used = False
            self.forwarded = False
            if fire:
                self.callback()
            return consume
        if up:
            self.held.discard(vk)
        else:
            self.held.add(vk)
            if self.down:
                self.used = True
                if not self.forwarded:
                    self.forwarded = True
                    # Right Alt was withheld until we knew this was a chord.
                    user32.keybd_event(0xA5, 0x38, 0x1, 0)
        return False

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        class KeyboardData(ctypes.Structure):
            _fields_ = [('vkCode', w.DWORD), ('scanCode', w.DWORD),
                        ('flags', w.DWORD), ('time', w.DWORD),
                        ('dwExtraInfo', ctypes.c_size_t)]
        hook_type = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, hook_type, w.HINSTANCE, w.DWORD]
        user32.SetWindowsHookExW.restype = w.HANDLE
        user32.CallNextHookEx.argtypes = [w.HANDLE, ctypes.c_int, w.WPARAM, w.LPARAM]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [w.HANDLE]
        kernel32.GetModuleHandleW.argtypes = [w.LPCWSTR]
        kernel32.GetModuleHandleW.restype = w.HMODULE
        def handle(code, wp, lp):
            if code >= 0:
                data = ctypes.cast(lp, ctypes.POINTER(KeyboardData)).contents
                # Synthetic paste and our forwarded Alt must not retrigger dictation.
                if not data.flags & 0x10:
                    vk = data.vkCode
                    if vk == 0x12 and data.flags & 0x1:
                        vk = 0xA5
                    if self.key_event(vk, bool(data.flags & 0x80)):
                        return 1
            return user32.CallNextHookEx(None, code, wp, lp)
        self.proc = hook_type(handle)
        # Create the thread message queue before publishing readiness.
        msg = w.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        hook = user32.SetWindowsHookExW(13, self.proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            self.error('右 Alt 监听启动失败，请重启轻声输入；也可从托盘使用开始录音。')
            return
        if self.ready:
            self.ready()
        try:
            while not self.stopping.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            user32.UnhookWindowsHookEx(hook)
            if self.down and self.forwarded:
                user32.keybd_event(0xA5, 0x38, 0x3, 0)

    def stop(self):
        self.stopping.set()
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)


class Tray:
    def __init__(self, events):
        import pystray
        from PIL import Image, ImageDraw
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((3, 3, 61, 61), radius=16, fill='#176b66')
        draw.rounded_rectangle((26, 12, 38, 36), radius=6, fill='white')
        draw.arc((19, 20, 45, 45), 0, 180, fill='white', width=4)
        draw.line((32, 45, 32, 52), fill='white', width=4)
        draw.line((25, 52, 39, 52), fill='white', width=4)
        def send(action):
            return lambda icon, item: events.put((action, None))
        self.icon = pystray.Icon('LocalVoiceInput', image, '轻声输入 · 右 Alt 开始 / 结束',
            pystray.Menu(
                pystray.MenuItem('开始 / 结束录音（右 Alt）', send('hotkey')),
                pystray.MenuItem('打开设置 / 查看上次结果', send('settings'), default=True),
                pystray.MenuItem('复制上次结果', send('copy_last')),
                pystray.MenuItem('退出轻声输入', send('quit'))))

    def start(self):
        self.icon.run_detached()

    def stop(self):
        self.icon.stop()
