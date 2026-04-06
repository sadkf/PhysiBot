@echo off
chcp 65001 >nul
title PhysiBot 一键启动程序

echo ========================================
echo        欢迎使用 PhysiBot
echo ========================================
echo 正在准备环境，可能需要几分钟下载运行库（如果网络慢，请耐心等待）...

powershell -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0run.ps1'"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 启动过程中发生错误，请查看上方红色提示。
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo ✅ 程序已退出。
pause
