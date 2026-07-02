@echo off
chcp 65001 >nul
title Ad Data Platform - Manual Backfill
cd /d "%~dp0pipeline"
echo ============================================================
echo   Manual backfill: 2025-01-01 to today, all platforms/levels/logins
echo   Resumable: already-crawled days are skipped automatically.
echo ============================================================
echo.
python backfill.py 2025-01-01
echo.
echo Backfill finished. Press any key to close...
pause >nul
