@echo off
cd /d "%~dp0"
echo Open http://127.0.0.1:8765 in your browser. Keep this window open.
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe app.py
) else (
  py -3 app.py
)
pause
