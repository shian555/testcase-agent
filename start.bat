@echo off
title AI Test Platform
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and check "Add to PATH".
    pause
    exit /b 1
)

REM First run: install dependencies automatically
python -c "import streamlit, pandas, plotly, openpyxl" 2>nul
if errorlevel 1 (
    echo [First run] Installing dependencies, please wait...
    pip install -r requirements.txt
)

echo.
echo ================================================
echo   AI Test Platform   http://localhost:8501
echo   Browser will open automatically.
echo   Close this window to stop the server.
echo ================================================
echo.

REM Open browser once the server is up (about 4s), then run headless
REM (headless skips Streamlit's first-run email prompt)
start "" /min cmd /c "timeout /t 4 /nobreak >nul && start "" http://localhost:8501"
python -m streamlit run app.py --server.headless true

echo.
echo Server stopped.
pause
