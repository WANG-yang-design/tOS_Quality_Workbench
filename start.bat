@echo off
chcp 65001 >nul 2>&1
title tOS Quality Workbench

set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"

REM -- Read ports from .env --
set "BACKEND_PORT=8018"
set "FRONTEND_PORT=8088"
if exist "%ROOT%.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%ROOT%.env") do (
        if "%%a"=="PORT" set "BACKEND_PORT=%%b"
        if "%%a"=="VITE_FRONTEND_PORT" set "FRONTEND_PORT=%%b"
    )
)
REM trim spaces
for /f "tokens=*" %%i in ("%BACKEND_PORT%") do set "BACKEND_PORT=%%i"
for /f "tokens=*" %%i in ("%FRONTEND_PORT%") do set "FRONTEND_PORT=%%i"

echo.
echo ========================================
echo    tOS Quality Workbench
echo ========================================
echo    Backend port:  %BACKEND_PORT%
echo    Frontend port: %FRONTEND_PORT%
echo ========================================
echo.

echo [0/3] Cleaning old processes...
taskkill /FI "WINDOWTITLE eq tOS-Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq tOS-Frontend*" /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do taskkill /PID %%p /F >nul 2>&1

echo [1/3] Starting Backend on port %BACKEND_PORT%...
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
    echo      Creating virtual environment...
    python -m venv "%BACKEND%\.venv"
)
(
    echo @echo off
    echo title tOS-Backend
    echo cd /d "%ROOT%"
    echo call backend\.venv\Scripts\activate.bat
    echo pip install -r backend\requirements.txt -q
    echo echo.
    echo echo Backend ready: http://localhost:%BACKEND_PORT%
    echo echo Press Ctrl+C to stop
    echo echo.
    echo python -m uvicorn backend.app:app --reload --host 0.0.0.0 --port %BACKEND_PORT%
) > "%TEMP%\tos_backend_start.cmd"
start "tOS-Backend" cmd /k "%TEMP%\tos_backend_start.cmd"

echo      Waiting for backend...
:WAIT_BACKEND
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 goto WAIT_BACKEND
echo      Backend OK

echo [2/3] Starting Frontend on port %FRONTEND_PORT%...
cd /d "%FRONTEND%"
if not exist "node_modules" (
    echo      Installing npm dependencies...
    npm install --silent
)
(
    echo @echo off
    echo title tOS-Frontend
    echo cd /d "%FRONTEND%"
    echo echo.
    echo echo Frontend ready: http://localhost:%FRONTEND_PORT%
    echo echo Press Ctrl+C to stop
    echo echo.
    echo npm run dev
) > "%TEMP%\tos_frontend_start.cmd"
start "tOS-Frontend" cmd /k "%TEMP%\tos_frontend_start.cmd"

echo      Waiting for frontend...
:WAIT_FRONTEND
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":%FRONTEND_PORT% " | findstr "LISTENING" >nul 2>&1
if errorlevel 1 goto WAIT_FRONTEND
echo      Frontend OK

echo [3/3] Opening browser...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /r "IPv4.*[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*"') do (
    set "LOCAL_IP=%%a"
    goto :GOT_IP
)
:GOT_IP
set "LOCAL_IP=%LOCAL_IP: =%"
start http://localhost:%FRONTEND_PORT%

echo.
echo ========================================
echo    All services started!
echo ========================================
echo.
echo    Local:       http://localhost:%FRONTEND_PORT%
echo    LAN:         http://%LOCAL_IP%:%FRONTEND_PORT%
echo    Backend:     http://localhost:%BACKEND_PORT%
echo    API Docs:    http://localhost:%BACKEND_PORT%/docs
echo.
echo    Close this window = services keep running
echo    To stop everything: run stop.bat
echo.
pause
