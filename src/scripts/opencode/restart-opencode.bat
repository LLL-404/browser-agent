@echo off
chcp 65001 >nul
title OpenCode 重启工具

echo 正在关闭 OpenCode...
taskkill /f /im OpenCode.exe >nul 2>&1

timeout /t 2 /nobreak >nul

echo 正在启动 OpenCode...
start "" "C:\Users\23501\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe"

echo OpenCode 已重启。
timeout /t 2 /nobreak >nul
