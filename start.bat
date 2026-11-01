@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -c "import struct,sys; sys.exit(0 if sys.version_info >= (3,12) and struct.calcsize('P') == 8 else 1)"
  if errorlevel 1 goto failed
  python -m venv .venv
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -c "import struct,sys; sys.exit(0 if sys.version_info >= (3,12) and struct.calcsize('P') == 8 else 1)"
if errorlevel 1 goto failed
fc /b "requirements.txt" ".venv\installed-requirements.txt" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
  copy /y "requirements.txt" ".venv\installed-requirements.txt" >nul
  if errorlevel 1 goto failed
)
start "" ".venv\Scripts\pythonw.exe" app.py %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Setup or launch failed. Requires 64-bit Python 3.12+ and internet access.
pause
exit /b 1
