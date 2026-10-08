@echo off
setlocal
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r deploy\timeweb\requirements.txt
if not exist .env copy .env.example .env >nul
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
