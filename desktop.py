"""Windows shortcut/tray integration, recording indicator and answer card."""
import ctypes
from ctypes import wintypes as w
import threading
import math
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont
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
user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, w.UINT]
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
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
        self.workflow = 'dictate'
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
            line((23, 25, 37, 39))
            line((37, 25, 23, 39))
            line((162, 32, 168, 38, 179, 26), '#111111', 3)
            special = getattr(self, 'workflow', 'dictate') != 'dictate'
            if special:
                badge = 'EN' if self.workflow == 'translate' else '?'
                font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 10 * scale)
                d.text((70 * scale, 32 * scale), badge, font=font, fill='#cccccc', anchor='mm')
            for i in range(8 if special else 11):
                # Silent input stays low; movement is driven by actual microphone RMS.
                envelope = 0.4 + 0.6 * abs(math.sin(self.phase * 0.7 + i * 1.8))
                h = 4 + min(1, level) * 23 * envelope
                x = (84 if special else 67) + i * 6
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
    def __init__(self, callback, error, ready=None, mode_callback=None):
        self.callback, self.error, self.ready = callback, error, ready
        self.mode_callback = mode_callback
        self.thread_id = None
        self.thread = None
        self.stopping = threading.Event()
        self.down = False
        self.forwarded = False
        self.held = set()
        self.consumed = set()
        self.action = None
        self.action_keys = set()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def key_event(self, vk, up):
        """Commit one exact shortcut only after all its keys are released."""
        if up:
            self.held.discard(vk)
            consume = vk in self.consumed
            self.consumed.discard(vk)
            if vk == 0xA5:
                self.down = False
                self.forwarded = False
            if self.action and not self.action_keys.intersection(self.held):
                action = self.action
                self.action = None
                self.action_keys = set()
                if action == 'dictate':
                    self.callback()
                elif self.mode_callback:
                    self.mode_callback(action)
            return consume
        if vk in self.held:
            return vk in self.consumed
        previous = self.held.copy()
        self.held.add(vk)
        if vk == 0xA5:
            self.down = True
            self.forwarded = bool(previous - {0xA1})
            if not previous or previous == {0xA1}:
                self.action = 'translate' if previous else 'dictate'
                self.action_keys = {0xA5, 0xA1} if previous else {0xA5}
                self.consumed.add(vk)
                return True
            return False
        if self.action == 'dictate' and previous == {0xA5} and vk in (0xA1, 0x20):
            self.action = 'translate' if vk == 0xA1 else 'ask'
            self.action_keys = {0xA5, vk}
            self.consumed.add(vk)
            return True
        if self.action:
            was_dictation = self.action == 'dictate'
            self.action = None
            self.action_keys = set()
            if was_dictation and self.down and not self.forwarded:
                self.forwarded = True
                self.consumed.discard(0xA5)
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
                    elif vk == 0x10:
                        vk = 0xA1 if data.scanCode == 0x36 else 0xA0
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


def enable_dpi_awareness():
    # UI Automation returns physical screen coordinates, so use the same space.
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def answer_geometry(anchor, size, work, gap=12):
    """Prefer below/above the selected line; keep the whole card in the work area."""
    left, top, right, bottom = work
    margin = min(12, max(0, (right - left) // 10), max(0, (bottom - top) // 10))
    width = min(size[0], right - left - margin * 2)
    height = min(size[1], bottom - top - margin * 2)
    ax, ay, ar, ab = anchor
    x = ax
    if ab + gap + height <= bottom - margin:
        y = ab + gap
    elif ay - gap - height >= top + margin:
        y = ay - gap - height
    elif right - ar >= width + gap + margin:
        x, y = ar + gap, ay
    elif ax - left >= width + gap + margin:
        x, y = ax - width - gap, ay
    else:
        y = ab + gap if bottom - ab >= ay - top else ay - gap - height
    return (round(max(left + margin, min(x, right - margin - width))),
            round(max(top + margin, min(y, bottom - margin - height))), round(width), round(height))


def anchor_work_area(anchor):
    rect = w.RECT(*anchor)
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(w.RECT), w.DWORD]
    user32.MonitorFromRect.restype = w.HANDLE
    monitor = user32.MonitorFromRect(ctypes.byref(rect), 2)
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        r = info.rcWork
        return (r.left, r.top, r.right, r.bottom)
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def wrapped_lines(text, font, width, limit):
    """Bounded measurement for short cards; long text stays in scrollable widgets."""
    lines, used, widths = 1, 0, {}
    for char in text:
        if char == '\n':
            lines, used = lines + 1, 0
        else:
            if char not in widths:
                widths[char] = font.measure(char)
            advance = widths[char]
            if used and used + advance > width:
                lines, used = lines + 1, 0
            used += advance
        if lines > limit:
            return limit + 1
    return lines


class AnswerWindow:
    """Answers appear separately so the original selected text stays intact."""
    def __init__(self, root):
        self.root = root
        self.window = None

    def show(self, question, answer, anchor=None):
        import pyperclip
        from selection import cursor_anchor
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()
        self.window = tk.Toplevel(self.root)
        self.window.withdraw()
        self.window.title('轻声输入 · 回答')
        self.window.overrideredirect(True)
        self.window.configure(bg='#dbe5df')
        self.window.bind('<Escape>', lambda event: self.close())
        anchor = anchor or cursor_anchor() or (80, 80, 80, 80)
        work = anchor_work_area(anchor)
        scale = max(1, self.window.winfo_fpixels('1i') / 96)
        pad = round(20 * scale)
        width = min(round(720 * scale), work[2] - work[0] - 24)
        body_width = width - pad * 2 - round(16 * scale)
        question_font = tkfont.Font(self.window, family='Microsoft YaHei UI', size=12)
        answer_font = tkfont.Font(self.window, family='Microsoft YaHei UI', size=13)
        self.question_font, self.answer_font = question_font, answer_font
        qlines = wrapped_lines(question, question_font, body_width, 5)
        alines = wrapped_lines(answer, answer_font, body_width, 14)
        # Real word wrapping may use slightly more lines than character measures.
        if len(answer) > 60 and alines <= 14:
            alines += 1
        max_height = min(round(660 * scale), round((work[3] - work[1]) * 0.7))
        chrome = round(136 * scale)
        qheight = min(qlines, 5) * (question_font.metrics('linespace') + 6)
        aheight = min(alines, 14) * (answer_font.metrics('linespace') + 6)
        height = min(max_height, max(round(200 * scale), chrome + qheight + aheight))
        x, y, width, height = answer_geometry(anchor, (width, height), work)
        self.window.geometry(f'{width}x{height}')
        panel = tk.Frame(self.window, bg='white', padx=pad, pady=round(12 * scale))
        panel.pack(fill='both', expand=True)
        panel.pack_configure(padx=1, pady=1)
        heading = tk.Frame(panel, bg='white')
        heading.pack(fill='x')
        tk.Label(heading, text='问题', bg='white', fg='#829088', font=('Microsoft YaHei UI', 10)).pack(side='left')
        tk.Button(heading, text='×', command=self.close, font=('Segoe UI', 17),
                  fg='#829088', bg='white', activebackground='#f1f5f3',
                  bd=0, highlightthickness=0, cursor='hand2', padx=4, pady=0).pack(side='right')
        question_body = tk.Frame(panel, bg='white', height=qheight)
        question_body.pack(fill='x', pady=(2, round(12 * scale)))
        question_body.pack_propagate(False)
        self.question_text = tk.Text(question_body, wrap='word', font=question_font, bg='white', fg='#52645a',
                                    bd=0, highlightthickness=0, padx=0, pady=0, spacing1=3, spacing3=3,
                                    selectbackground='#daeee4', selectforeground='#233d30')
        self.question_text.insert('1.0', question)
        self.question_text.configure(state='disabled')
        self.question_text.pack(side='left', fill='both', expand=True)
        if qlines > 5:
            scroll = ttk.Scrollbar(question_body, command=self.question_text.yview)
            self.question_text.configure(yscrollcommand=scroll.set)
            scroll.pack(side='right', fill='y')
        tk.Frame(panel, bg='#e9eeeb', height=1).pack(fill='x', pady=(0, round(10 * scale)))
        answer_heading = tk.Frame(panel, bg='white')
        answer_heading.pack(fill='x', pady=(0, round(6 * scale)))
        tk.Label(answer_heading, text='回答', bg='white', fg='#829088', font=('Microsoft YaHei UI', 10)).pack(side='left')
        def copy_answer():
            pyperclip.copy(answer)
            copy_button.configure(text='已复制')
        copy_button = tk.Button(answer_heading, text='复制', command=copy_answer, font=('Microsoft YaHei UI', 10),
                                fg='#27775a', bg='white', activebackground='#eff7f2',
                                bd=0, highlightthickness=0, cursor='hand2', padx=4, pady=0)
        copy_button.pack(side='right')
        body = tk.Frame(panel, bg='white')
        body.pack(fill='both', expand=True)
        output = tk.Text(body, wrap='word', font=answer_font, bg='white', fg='#24392e',
                         bd=0, highlightthickness=0, padx=0, pady=0, spacing1=3, spacing3=3,
                         selectbackground='#daeee4', selectforeground='#233d30')
        self.answer_text = output
        scroll = ttk.Scrollbar(body, command=output.yview)
        def scrolling(first, last):
            scroll.set(first, last)
            if float(first) > 0 or float(last) < 1:
                if not scroll.winfo_manager():
                    scroll.pack(side='right', fill='y', before=output)
            elif scroll.winfo_manager():
                scroll.pack_forget()
        output.configure(yscrollcommand=scrolling)
        output.pack(side='left', fill='both', expand=True)
        output.insert('1.0', answer)
        output.configure(state='disabled')
        self.window.update_idletasks()
        self.hwnd = user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
        style = user32.GetWindowLongPtrW(self.hwnd, -20)
        # Tk must map its child windows too. Merely showing the native wrapper
        # leaves a blank card on the interactive desktop.
        self.window.wm_attributes('-alpha', 0)
        user32.SetWindowLongPtrW(self.hwnd, -20, style | 0x08000080)
        self.window.deiconify()
        self.window.update_idletasks()
        gdi = ctypes.windll.gdi32
        gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi.CreateRoundRectRgn.restype = w.HANDLE
        user32.SetWindowRgn.argtypes = [w.HWND, w.HANDLE, w.BOOL]
        region = gdi.CreateRoundRectRgn(0, 0, width + 1, height + 1, round(18 * scale), round(18 * scale))
        if region and not user32.SetWindowRgn(self.hwnd, region, True):
            gdi.DeleteObject.argtypes = [w.HANDLE]
            gdi.DeleteObject(region)
        # Show the result without taking keyboard focus from the source document.
        user32.SetWindowPos(self.hwnd, None, x, y, width, height, 0x0050)
        self.window.wm_attributes('-alpha', 1)
        user32.SetWindowLongPtrW(self.hwnd, -20,
                                user32.GetWindowLongPtrW(self.hwnd, -20) & ~0x08000000 | 0x80)
        def drag_start(event):
            self.drag_offset = (event.x_root - self.window.winfo_rootx(), event.y_root - self.window.winfo_rooty())
        def drag(event):
            dx, dy = self.drag_offset
            user32.SetWindowPos(self.hwnd, None, event.x_root - dx, event.y_root - dy, 0, 0, 0x0011)
        for widget in (heading, heading.winfo_children()[0]):
            widget.bind('<Button-1>', drag_start)
            widget.bind('<B1-Motion>', drag)

    def close(self):
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()


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
                pystray.MenuItem('英文翻译（右 Alt + 右 Shift）', send('translate_hotkey')),
                pystray.MenuItem('选中文本问答（右 Alt + 空格）', send('ask_hotkey')),
                pystray.MenuItem('打开设置 / 查看上次结果', send('settings'), default=True),
                pystray.MenuItem('复制上次结果', send('copy_last')),
                pystray.MenuItem('退出轻声输入', send('quit'))))

    def start(self):
        self.icon.run_detached()

    def stop(self):
        self.icon.stop()
