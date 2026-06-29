@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title tOS Quality Workbench - Stop

REM -- Read ports from .env --
set "BACKEND_PORT=8018"
set "FRONTEND_PORT=8088"
if exist "%~dp0.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%~dp0.env") do (
        if "%%a"=="PORT" set "BACKEND_PORT=%%b"
        if "%%a"=="VITE_FRONTEND_PORT" set "FRONTEND_PORT=%%b"
    )
)
for /f "tokens=*" %%i in ("%BACKEND_PORT%") do set "BACKEND_PORT=%%i"
for /f "tokens=*" %%i in ("%FRONTEND_PORT%") do set "FRONTEND_PORT=%%i"

echo.
echo ========================================
echo    Stopping tOS Quality Workbench...
echo ========================================
echo.

echo Stopping backend (port %BACKEND_PORT%)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%BACKEND_PORT% " ^| findstr "LISTENING"') do (
    echo    Killing PID %%p
    taskkill /PID %%p /T /F >nul 2>&1
)

echo Stopping frontend (port %FRONTEND_PORT%)...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%FRONTEND_PORT% " ^| findstr "LISTENING"') do (
    echo    Killing PID %%p
    taskkill /PID %%p /T /F >nul 2>&1
)

echo Cleaning up cmd windows...
taskkill /FI "WINDOWTITLE eq tOS-Backend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq tOS-Frontend*" /F >nul 2>&1

echo.
echo Done. All services stopped.
echo.
pause
