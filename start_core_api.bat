@echo off
echo ===================================================
echo Starting CaRAG Core Backend (Engine) on Port 8000...
echo ===================================================

:: Ensure we are in the root directory of the script
cd /d "%~dp0"

:: Move into the core_backend folder so python paths (like import src) resolve correctly
cd core_backend

:: Check if the virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Python Virtual Environment not found at core_backend\venv!
    pause
    exit /b
)

:: Run uvicorn from inside core_backend
"venv\Scripts\python.exe" -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
