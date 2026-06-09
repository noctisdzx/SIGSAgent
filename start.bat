@echo off
REM ============================================================
REM   SIGSAgent dev launcher (Windows .bat, double-click to run)
REM
REM   Opens two NEW console windows so you can watch both servers'
REM   live logs side-by-side, then opens the UI in your browser.
REM     - Backend  -> http://127.0.0.1:8000   (OpenAPI docs at /docs)
REM     - Frontend -> http://127.0.0.1:5680
REM
REM   Each child window uses `cmd /k`, so even if the server exits
REM   with an error the window stays open and you can read the
REM   traceback. Close the windows to stop the servers.
REM ============================================================

chcp 65001 >nul
setlocal EnableExtensions

REM Anchor everything to the directory this .bat lives in.
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo  =================================================
echo   SIGSAgent dev launcher
echo  -------------------------------------------------
echo   Repo root : %ROOT%
echo   Backend   : http://127.0.0.1:8000   (docs: /docs)
echo   Frontend  : http://127.0.0.1:5680
echo  =================================================
echo.

REM ---------- sanity checks ----------
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] `python` not found on PATH. Install Python 3.11+ first.
    pause
    exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] `npm` not found on PATH. Install Node.js 18+ first.
    pause
    exit /b 1
)

REM ---------- backend window ----------
REM Pick backend command depending on whether a local venv exists.
set "BACKEND_CMD=cd /d ""%ROOT%\backend"" && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level info"
if exist "%ROOT%\backend\.venv\Scripts\activate.bat" set "BACKEND_CMD=cd /d ""%ROOT%\backend"" && call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level info"

echo Starting backend window ...
start "SIGSAgent Backend (uvicorn 8000)" cmd /k "chcp 65001 >nul && %BACKEND_CMD%"

REM ---------- frontend window ----------
echo Starting frontend window ...
start "SIGSAgent Frontend (vite 5680)" cmd /k "chcp 65001 >nul && cd /d ""%ROOT%\frontend"" && npm run dev"

REM ---------- wait + open browser ----------
echo.
echo Waiting ~7s for servers to come up, then opening the UI ...
timeout /t 7 /nobreak >nul
start "" http://127.0.0.1:5680/

echo.
echo Both services are now running in their own windows.
echo Close those windows (or hit Ctrl+C inside them) to stop.
echo.

endlocal
REM Keep this launcher window briefly visible so the user sees the summary.
timeout /t 3 /nobreak >nul
exit /b 0
