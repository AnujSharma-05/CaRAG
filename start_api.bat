@echo off
echo ===================================================
echo Starting CaRAG Live API...
echo ===================================================

:: Ensure we are in the root directory
cd /d "%~dp0"

:: Check if the virtual environment exists
if not exist "core_backend\venv\Scripts\python.exe" (
    echo [ERROR] Python Virtual Environment not found at core_backend\venv!
    pause
    exit /b
)

:: Run Uvicorn through the python executable to avoid path issues
"core_backend\venv\Scripts\python.exe" -m uvicorn live.backend.src.main:app --reload --port 8001


