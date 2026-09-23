@echo off
cd /d "%~dp0"
py -3 -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Setup complete. Run start.cmd.
pause
exit /b 0
:error
echo Setup failed. Install Python 3.12 and check the error above.
pause
exit /b 1
