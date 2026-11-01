"""Local visual fixture, with synthetic text and no recording or API requests."""
import tkinter as tk
from desktop import AnswerWindow, enable_dpi_awareness

enable_dpi_awareness()
root = tk.Tk()
root.title('轻声输入 · 卡片预览')
root.geometry('540x430+0+60')
root.configure(bg='#f2f5f3')
tk.Label(root, text="OK, let's do the second test.", bg='#d8e9fa', fg='#24392e',
         font=('Segoe UI', 11)).place(x=24, y=45)
root.update_idletasks()
card = AnswerWindow(root)
card.show('把这句话翻译成中文。', '好，我们来做第二个测试：先将语音转成文字，再把它翻译成英文。',
          anchor=(24, 140, 350, 160))
root.after(120000, root.destroy)
root.mainloop()
