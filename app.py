import ctypes
from ctypes import wintypes
import json
import os
import sys
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import sounddevice as sd
import keyring
import pyperclip
from pynput import keyboard
from core import ROOT, Transcriber, cleanup, download_model, model_ready
from desktop import GlobalShortcut, StatusPopup, Tray

SERVICE = 'LocalVoiceInput.DeepSeek'
USER = 'api-key'
CONFIG = ROOT / 'settings.json'
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = wintypes.HWND


class App:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.recording = False
        self.stream = None
        self.engine = None
        self.target = None
        self.frames = []
        self.audio_warning = False
        self.closed = False
        self.settings_event = None
        self.operation = 0
        self.last_hotkey = 0.0
        self.key = os.environ.get('DEEPSEEK_API_KEY', '')
        try:
            self.key = keyring.get_password(SERVICE, USER) or self.key
        except Exception:
            pass
        settings = {}
        try:
            settings = json.loads(CONFIG.read_text('utf-8'))
        except (OSError, ValueError):
            pass
        root.title('轻声输入 · 本地识别 + DeepSeek')
        root.geometry('820x740')
        root.minsize(680, 620)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', font=('Microsoft YaHei UI', 10))
        style.configure('TButton', font=('Microsoft YaHei UI', 10), padding=7)
        panel = ttk.Frame(root, padding=22)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='轻声输入', font=('Microsoft YaHei UI', 23, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='录音留在本机 · 仅整理时向 DeepSeek 发送文字').pack(anchor='w', pady=(4, 14))
        row = ttk.Frame(panel)
        row.pack(fill='x')
        ttk.Label(row, text='DeepSeek 密钥').pack(side='left')
        self.key_var = tk.StringVar(value=self.key)
        ttk.Entry(row, textvariable=self.key_var, show='●', width=38).pack(side='left', padx=10, fill='x', expand=True)
        ttk.Button(row, text='保存密钥', command=self.save_key).pack(side='left')
        ttk.Button(row, text='删除密钥', command=self.delete_key).pack(side='left', padx=(6, 0))
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=10)
        ttk.Label(row, text='整理模型').pack(side='left')
        self.model = tk.StringVar(value=settings.get('model', 'deepseek-flash'))
        ttk.Entry(row, textvariable=self.model, width=23).pack(side='left', padx=10)
        self.polish = tk.BooleanVar(value=settings.get('polish', True))
        self.auto = tk.BooleanVar(value=settings.get('auto_paste', True))
        ttk.Checkbutton(row, text='DeepSeek 整理', variable=self.polish).pack(side='left')
        ttk.Checkbutton(row, text='快捷键录音后自动粘贴', variable=self.auto).pack(side='left', padx=8)
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=(0, 12))
        ttk.Label(row, text='麦克风').pack(side='left')
        self.device_ids = [None]
        names = ['系统默认麦克风']
        try:
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels'] > 0:
                    self.device_ids.append(i)
                    names.append(f'{i}: {device["name"]}')
        except Exception:
            pass
        self.mic = ttk.Combobox(row, values=names, state='readonly')
        self.mic.current(0)
        if settings.get('microphone') in names:
            self.mic.current(names.index(settings['microphone']))
        self.mic.pack(side='left', fill='x', expand=True, padx=10)
        self.download_button = ttk.Button(row, text='下载语音模型', command=self.download)
        self.download_button.pack(side='left')
        self.record_button = ttk.Button(panel, text='开始录音   右 Alt', command=self.toggle)
        self.record_button.pack(fill='x', pady=4)
        self.status = tk.StringVar(value='就绪' if model_ready() else '首次使用：先下载语音模型，再保存 DeepSeek 密钥。')
        ttk.Label(panel, textvariable=self.status, wraplength=740).pack(anchor='w', pady=8)
        self.level = ttk.Progressbar(panel, maximum=100)
        self.level.pack(fill='x', pady=(0, 8))
        ttk.Label(panel, text='识别原文（可编辑）').pack(anchor='w')
        self.raw = tk.Text(panel, height=6, wrap='word', font=('Microsoft YaHei UI', 11), undo=True)
        self.raw.pack(fill='both', expand=True, pady=5)
        ttk.Label(panel, text='整理结果（自动分段 / 列点）').pack(anchor='w', pady=(6, 0))
        self.result = tk.Text(panel, height=6, wrap='word', font=('Microsoft YaHei UI', 11), undo=True)
        self.result.pack(fill='both', expand=True, pady=5)
        row = ttk.Frame(panel)
        row.pack(fill='x', pady=8)
        ttk.Button(row, text='重新整理原文', command=self.retry).pack(side='left')
        ttk.Button(row, text='复制原文', command=lambda: self.copy(self.raw)).pack(side='left', padx=8)
        ttk.Button(row, text='复制结果', command=lambda: self.copy(self.result)).pack(side='left')
        ttk.Button(row, text='保存设置并转到后台', command=self.hide_settings).pack(side='right')
        ttk.Label(panel, text='单独轻按右 Alt 开始，再按一次结束；单次最多 90 秒。\n浮条左侧 × 取消，右侧 ✓ 完成；自动粘贴到原输入窗口。', wraplength=740).pack(anchor='w')
        self.shortcut_status = tk.StringVar(value='右 Alt 全局监听：正在启动…')
        ttk.Label(panel, textvariable=self.shortcut_status).pack(anchor='w')
        self.popup = StatusPopup(root, self.events)
        self.tray = Tray(self.events)
        self.tray.start()
        self.hotkeys = GlobalShortcut(lambda: self.events.put(('hotkey', None)),
                                     lambda msg: self.events.put(('shortcut_error', msg)),
                                     lambda: self.events.put(('shortcut_ready', None)))
        try:
            self.hotkeys.start()
        except Exception:
            self.status.set('全局快捷键不可用，可用按钮录音。')
        self.drain_timer = root.after(80, self.drain)
        root.protocol('WM_DELETE_WINDOW', self.hide_settings)
        if self.key and model_ready() and '--settings' not in sys.argv:
            root.withdraw()
            self.popup.show('轻声输入已就绪 · 右 Alt 开始 / 结束', 4000)

    def hide_settings(self):
        self.save_settings()
        self.root.withdraw()
        if not self.recording and not self.busy:
            self.popup.show('已转到后台 · 从托盘图标打开设置', 3000)

    def show_settings(self):
        self.root.deiconify()
        self.root.lift()

    def save_settings(self):
        CONFIG.write_text(json.dumps({'model': self.model.get().strip(),
            'auto_paste': self.auto.get(), 'polish': self.polish.get(),
            'microphone': self.mic.get()}, ensure_ascii=False), 'utf-8')

    def save_key(self):
        value = self.key_var.get().strip()
        if not value:
            messagebox.showinfo('密钥', '请在密码框中填入 DeepSeek API 密钥。')
            return
        try:
            keyring.set_password(SERVICE, USER, value)
            self.key = value
            self.save_settings()
            self.status.set('密钥已保存到 Windows 凭据管理器。')
        except Exception:
            messagebox.showerror('保存失败', '无法写入 Windows 凭据管理器，密钥未保存。')

    def delete_key(self):
        try:
            if keyring.get_password(SERVICE, USER):
                keyring.delete_password(SERVICE, USER)
            self.key = ''
            self.key_var.set('')
            self.status.set('已删除本应用保存的密钥。')
        except Exception:
            messagebox.showerror('删除失败', '无法访问 Windows 凭据管理器。')

    def background(self, fn):
        self.busy = True
        self.record_button.configure(state='disabled')
        self.download_button.configure(state='disabled')
        def run():
            try:
                fn()
            except Exception as exc:
                # Never display request objects, headers, credentials or raw server bodies.
                self.events.put(('error', str(exc) if isinstance(exc, RuntimeError) else '操作失败，请检查网络、模型文件或麦克风设置。'))
            finally:
                self.events.put(('idle', None))
        threading.Thread(target=run, daemon=True).start()

    def download(self):
        if self.busy or self.recording:
            return
        if not messagebox.askokcancel('下载语音模型', '从 sherpa-onnx 官方 GitHub 下载 SenseVoice 模型包，压缩包约 155 MB，模型约 230 MB。是否下载？'):
            return
        def run():
            download_model(lambda s: self.events.put(('status', s)))
            self.engine = Transcriber()
            self.events.put(('status', '模型准备完成，可以开始录音。'))
        self.background(run)

    def toggle(self, via_hotkey=False):
        if self.busy:
            self.popup.processing()
            return
        if self.recording:
            self.stop()
            return
        if not model_ready():
            self.status.set('请先点击“下载语音模型”。')
            self.popup.show('模型尚未准备好，请从托盘打开设置下载模型。', 6000)
            return
        self.operation += 1
        self.target = user32.GetForegroundWindow() if via_hotkey else None
        self.should_paste = bool(via_hotkey and self.auto.get())
        self.frames = []
        self.audio_warning = False
        self.popup.show('正在打开麦克风…')
        self.root.update_idletasks()
        device = self.device_ids[self.mic.current()]
        try:
            self.sample_rate = int(sd.query_devices(device, 'input')['default_samplerate'])
            def callback(data, frame_count, timing, status):
                if status:
                    self.audio_warning = True
                # Bound recording memory, even if the UI thread is blocked.
                if sum_size[0] < self.sample_rate * 90:
                    self.frames.append(data.copy())
                    sum_size[0] += len(data)
            sum_size = [0]
            self.stream = sd.InputStream(device=device, samplerate=self.sample_rate,
                                         channels=1, dtype='float32', callback=callback)
            self.stream.start()
        except Exception:
            if self.stream:
                self.stream.close()
                self.stream = None
            self.status.set('无法打开麦克风，请检查 Windows 麦克风权限并选择正确设备。')
            self.popup.show('无法打开麦克风，请从托盘打开设置检查设备。', 7000)
            return
        self.recording = True
        self.started = time.monotonic()
        self.record_button.configure(text='结束录音   右 Alt')
        self.download_button.configure(state='disabled')
        self.status.set('正在录音…')
        self.popup.listen()

    def cancel(self):
        if not self.recording:
            return
        self.recording = False
        self.operation += 1
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.frames = []
        self.level['value'] = 0
        self.record_button.configure(text='开始录音   右 Alt')
        self.download_button.configure(state='normal')
        self.status.set('已取消录音。')
        self.popup.show('已取消录音', 1800)

    def stop(self):
        self.recording = False
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.record_button.configure(text='开始录音   右 Alt')
        self.level['value'] = 0
        if not self.frames:
            self.status.set('没有录到音频。')
            self.popup.show('没有录到声音，请检查麦克风。', 4000)
            self.download_button.configure(state='normal')
            return
        samples = np.concatenate(self.frames).reshape(-1)
        self.frames = []
        if len(samples) < self.sample_rate * 0.25 or float(np.max(np.abs(samples))) < 0.0005:
            self.status.set('录音太短或未检测到声音，请检查麦克风。')
            self.popup.show('录音太短或没有声音，请重试。', 4000)
            self.download_button.configure(state='normal')
            return
        self.replace(self.raw, '')
        self.replace(self.result, '')
        do_polish = self.polish.get()
        api_key = self.key_var.get().strip()
        model = self.model.get().strip()
        paste = self.should_paste and not self.audio_warning
        target = self.target
        self.status.set('本地识别中…' + ('录音有丢帧，请核对原文。' if self.audio_warning else ''))
        self.popup.processing()
        rate = self.sample_rate
        def run():
            start = time.monotonic()
            if self.engine is None:
                self.engine = Transcriber()
            text = self.engine.transcribe(samples, rate)
            self.events.put(('raw', text))
            if not text:
                self.events.put(('status', '没有识别到文字。'))
                return
            elapsed = time.monotonic() - start
            if do_polish:
                self.events.put(('processing', '正在整理文字…'))
            self.events.put(('status', f'本地识别 {elapsed:.1f} 秒；' + ('DeepSeek 整理中…' if do_polish else '完成。')))
            final = cleanup(text, api_key, model) if do_polish else text
            self.events.put(('result', final))
            self.events.put(('done', (final, paste, target, elapsed, self.audio_warning)))
        self.background(run)

    def retry(self):
        if self.busy or self.recording:
            return
        text = self.raw.get('1.0', 'end-1c').strip()
        if not text:
            self.status.set('请先录音，或在原文框输入文字。')
            return
        api_key = self.key_var.get().strip()
        model = self.model.get().strip()
        self.status.set('DeepSeek 整理中…')
        self.popup.processing()
        def run():
            final = cleanup(text, api_key, model)
            self.events.put(('result', final))
            self.events.put(('polished', None))
        self.background(run)

    def copy(self, widget):
        text = widget.get('1.0', 'end-1c')
        if text:
            pyperclip.copy(text)
            self.status.set('已复制，可切换到输入框按 Ctrl + V。')

    @staticmethod
    def replace(widget, text):
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)

    def drain(self):
        if self.closed:
            return
        if self.drain_timer is not None:
            self.root.after_cancel(self.drain_timer)
            self.drain_timer = None
        if self.settings_event and ctypes.windll.kernel32.WaitForSingleObject(self.settings_event, 0) == 0:
            self.show_settings()
        while True:
            try:
                kind, data = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'hotkey':
                if time.monotonic() - self.last_hotkey >= 0.35:
                    self.last_hotkey = time.monotonic()
                    self.toggle(via_hotkey=True)
            elif kind == 'settings':
                self.show_settings()
            elif kind == 'cancel':
                self.cancel()
            elif kind == 'finish':
                if self.recording:
                    self.stop()
            elif kind == 'copy_last':
                self.copy(self.result)
                self.popup.show('已复制上次整理结果', 2500)
            elif kind == 'quit':
                self.close()
                return
            elif kind == 'shortcut_error':
                self.show_settings()
                self.shortcut_status.set('右 Alt 全局监听：启动失败')
                self.status.set(data)
                self.popup.show(data, 10000)
            elif kind == 'shortcut_ready':
                self.shortcut_status.set('右 Alt 全局监听：已就绪（单独轻按并松开）')
            elif kind == 'processing':
                self.popup.processing()
            elif kind == 'polished':
                self.status.set('整理完成，可复制结果。')
                self.popup.complete()
            elif kind == 'status' or kind == 'error':
                self.status.set(data)
                if kind == 'error' or not self.busy:
                    self.popup.show(data, 10000 if kind == 'error' else 6000)
            elif kind == 'raw':
                self.replace(self.raw, data)
            elif kind == 'result':
                self.replace(self.result, data)
            elif kind == 'idle':
                self.busy = False
                self.record_button.configure(state='normal')
                self.download_button.configure(state='normal')
                if self.popup.timer is None:
                    self.popup.show(self.status.get(), 6000)
            elif kind == 'done':
                final, paste, target, elapsed, warning = data
                self.status.set(f'完成，本地识别耗时 {elapsed:.1f} 秒。' + ('录音有丢帧，请核对文字。' if warning else '可复制结果。'))
                self.popup.complete()
                if paste:
                    operation = self.operation
                    self.root.after(120, lambda t=final, h=target, o=operation: self.paste(t, h, operation=o))
        if self.recording:
            seconds = time.monotonic() - self.started
            self.status.set(f'正在录音… {seconds:.0f} / 90 秒')
            level = 0
            if self.frames:
                level = min(1, float(np.sqrt(np.mean(self.frames[-1] ** 2))) * 12)
                self.level['value'] = level * 100
            self.popup.listen(level)
            if seconds >= 90:
                self.stop()
        self.drain_timer = self.root.after(80, self.drain)

    def paste(self, text, target, attempt=0, operation=None):
        # Never switch focus to a potentially stale window or paste while modifiers are held.
        modifiers = (0x10, 0x11, 0x12, 0x5B, 0x5C)
        if self.closed or (operation is not None and operation != self.operation):
            return
        if self.recording or self.busy or user32.GetForegroundWindow() != target:
            self.status.set('结果已保留；前台窗口或按键状态变化，请手动复制。')
            self.popup.show('输入窗口已切换，结果保留在托盘中，可复制。', 6000)
            return
        if any(user32.GetAsyncKeyState(k) & 0x8000 for k in modifiers):
            if attempt < 30:
                self.root.after(100, lambda: self.paste(text, target, attempt + 1, operation))
            else:
                self.popup.show('按键尚未松开，结果已保留，可从托盘复制。', 6000)
            return
        try:
            pyperclip.copy(text)
            controller = keyboard.Controller()
            with controller.pressed(keyboard.Key.ctrl):
                controller.press('v')
                controller.release('v')
            self.status.set('已向原输入窗口发送粘贴；如未出现文字，可手动复制。')
            self.popup.complete()
        except Exception:
            self.status.set('自动粘贴失败，请点击“复制结果”。')
            self.popup.show('自动输入失败，请从托盘复制结果。', 6000)

    def close(self):
        self.closed = True
        if self.drain_timer is not None:
            self.root.after_cancel(self.drain_timer)
            self.drain_timer = None
        if self.stream:
            self.stream.stop()
            self.stream.close()
        self.hotkeys.stop()
        self.tray.stop()
        self.popup.close()
        self.root.destroy()


if __name__ == '__main__':
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    settings_event = kernel32.CreateEventW(None, False, False, 'Local\\LocalVoiceInputV2Settings')
    instance = kernel32.CreateMutexW(None, False, 'Local\\LocalVoiceInputV2')
    if kernel32.GetLastError() == 183:
        kernel32.SetEvent(settings_event)
    else:
        app = App(tk.Tk())
        app.settings_event = settings_event
        app.root.mainloop()
