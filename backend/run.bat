@echo off
cd /d "%~dp0"
python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
echo.
echo Starting Just Here on http://127.0.0.1:8010
echo (8000 is often blocked/occupied on Windows)
echo.
uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
