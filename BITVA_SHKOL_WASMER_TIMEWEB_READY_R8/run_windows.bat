@echo off
setlocal
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r deploy\timeweb\requirements.txt
if not exist .env copy .env.example .env >nul
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
