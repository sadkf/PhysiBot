@echo off
REM 与 PhysiBot.cmd 相同；部分用户习惯找 .bat 文件名
chcp 65001 >nul
cd /d "%~dp0"
title PhysiBot
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap_and_run.ps1"
if errorlevel 1 pause
