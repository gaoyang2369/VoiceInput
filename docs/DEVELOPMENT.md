# 开发说明

## 目录

```text
app.py                    应用状态、录音、后台任务与结果回填
core.py                   SenseVoice、本地模型下载及 DeepSeek 请求/提示词
desktop.py                Windows 快捷键、托盘、录音浮条及问答卡片
selection.py              UI Automation 选文、Ctrl+C 备用读取及选区位置
start.bat                 环境准备、按依赖清单更新、后台启动
打开设置.bat              复用启动入口并传入 --settings
requirements.txt          固定直接依赖
tests/                    unittest 回归和 Windows 集成检查
.github/workflows/        Windows CI
```

运行生成的 `.venv/`、`models/`、`settings.json` 和 Python 缓存不属于提交内容。测试不生成图片、GIF 或预览窗口脚本；历史逐版说明已合并到 README。

## 线程和处理流程

Tk 主线程负责窗口与应用状态。录音回调仅收集音频；本地识别、模型请求和选文读取放在后台线程，通过事件队列回到主线程更新 UI。键盘钩子运行在带消息循环的专用线程中，只提交快捷键事件。

新录音和编辑原文后的重试共用 `App.process_text()`：听写可选择是否整理，英译走单次文字请求，问答通过 `answer_filtered()` 先整理问题再回答。问答不自动粘贴；听写和翻译回填前会检查源窗口、修饰键与任务编号，避免把过期结果输入到其他窗口。

整理是一次无状态 DeepSeek 请求，没有 agent 或历史对话。系统提示词 `dictation-v2` 将正文视为输入法内容，要求保留问句、残句和指令而不作答；以 JSON 传入 `transcript` / `vocabulary`，以 JSON Output 和 temperature=0 请求单一 `text` 字段。本地检查字段和类型后再提取纯文本，拒绝格式异常或截断结果。结构校验不验证语义，提示词效果需要单独做真实 API 评估。

常用词在 Tk 主线程读取并规范化，随任务快照传给后台整理；不作字符串全局替换，也不修改 SenseVoice 的声学识别。`processing.log` 仅记录模式、提示词版本、耗时、输出长度和异常状态，最多保留 1 MB 主文件和两个备份；不记录口述内容、常用词、密钥或完整响应。

选文和选区位置在开始录音前一起取得；结果和重试沿用该快照。UI Automation 边界不可用时回退到当时的鼠标坐标。坐标统一采用屏幕坐标，卡片布局根据显示器工作区限制位置与尺寸。

## 验证

在仓库根目录运行：

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m pip check
git diff --check
```

自动检查覆盖快捷键按键顺序和防重复、录音取消与异常释放、模式分发、问答两次调用顺序、原文保留、重试、选文失败与过期剪贴板、弹窗布局、加载动画、屏幕边界、配置容错及两个批处理入口。入口测试在临时目录内运行无界面示例，不启动真实应用或联网安装。

2026-11-05 本地验证使用 Windows / Python 3.13，58 项自动检查通过。自动测试不调用真实 DeepSeek，也不能代替实际麦克风、跨应用选文、混合 DPI 多屏和输入权限等级的验收。Python 3.12 和云端 CI 仍以工作流实际运行结果为准。

同日独立使用 `deepseek-flash` 进行了 14 个合成案例的真实 API 验证，14/14 通过：短问句、残句、对他人的提问、请求、正文中的指令、同音纠错、正确同音词保留、术语、自我纠正、否定及数字、不确定性、季度序数、列表和英文问句。原例“这段代码是什么意思”输出“这段代码是什么意思？”，“知道说什么意思”保留为“知道说什么意思。”。这些有限案例不代表所有识别错误都能修复。

手动复测（消耗 DeepSeek 额度，使用已有凭据或 `DEEPSEEK_API_KEY`，只发送脚本内的合成案例）：

```powershell
.venv\Scripts\python.exe tools/evaluate_cleanup.py --live
```

GitHub Actions 使用官方 [checkout](https://github.com/actions/checkout) 和 [setup-python](https://github.com/actions/setup-python) 的 v7 入口，只申请仓库内容读取权限，不发布或上传应用。

## 修改约定

- 运行时不要在后台线程直接操作 Tk 控件。
- 不要让键盘回调执行网络、音频或 UI 等耗时工作。
- 复用文字任务分发及共享模型请求，保留问题整理失败时的停止行为。
- 记录异常时不要输出密钥、请求头、完整服务响应或用户口述内容。
- 更新依赖后运行依赖检查和测试；启动入口会比较依赖清单与上次成功安装的副本。
- 修改 Windows 行为时增加相应回归检查；真实 API 测试应单独进行，不放入默认测试或 CI。

## 发布准备

README 是使用说明入口。只提交源码、测试、文档和工作流；不要提交虚拟环境、模型或个人设置。当前尚未选择项目许可证，补充 `LICENSE` 的决定由维护者作出。工作流配置仅在推送到 GitHub 后生效，本地整理不会自动提交、推送或创建 Release。
