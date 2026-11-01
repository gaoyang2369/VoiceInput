@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto failed
)
if not exist ".venv\ready-v2.txt" (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
  echo ready> .venv\ready-v2.txt
)
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0
:failed
echo Setup or launch failed. Requires 64-bit Python 3.11-3.13 and internet access.
pause
exit /b 1
