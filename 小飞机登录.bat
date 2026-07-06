@echo off
chcp 65001 >nul
title 小飞机登录 - 写入服务器数据库
echo ============================================================
echo   小飞机 短信登录 -^> 写入服务器数据库(124.223.55.175)
echo   用于服务器无法自动登录的小飞机账号(需短信验证码)
echo ============================================================
echo.
echo 账号ID对照(在看板"账号管理"页每行也能看到):
echo    1 = 小飞机·sdjr@shun.tt
echo    5 = 小飞机·ayh@kdys001.com
echo    6 = 小飞机·135796@qq.com
echo.
set /p AID=请输入要登录的账号ID:
echo.
echo [1/2] 即将弹出"隧道"窗口，请在其中输入服务器 root 密码，连接后保持该窗口打开
start "服务器隧道-登录期间请勿关闭" ssh -N -L 5433:127.0.0.1:5433 root@124.223.55.175
echo.
echo    隧道窗口输入密码、无报错后 = 连接成功
pause
set DATABASE_URL=postgresql://postgres:postgres@localhost:5433/ad_data
cd /d "%~dp0pipeline"
echo.
echo [2/2] 打开浏览器登录小飞机，完成短信验证；成功后脚本自动抓取凭证写入服务器库
python auth_login.py %AID%
echo.
echo 完成。现在可以关闭"隧道"窗口了。
pause
