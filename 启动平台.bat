@echo off
chcp 65001 >nul
title Ad Data Platform - Backend (localhost:8770)
cd /d "%~dp0pipeline"
echo ============================================================
echo   Ad Data Platform - Backend Service
echo   Local access:  http://localhost:8770
echo   LAN access:    http://10.102.130.181:8770
echo   Close this window to STOP the service.
echo ============================================================
echo.
python -m uvicorn app:app --host 0.0.0.0 --port 8770 --log-level info
echo.
echo Service stopped. Press any key to close...
pause >nul
