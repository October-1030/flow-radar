@echo off
chcp 65001 >nul
title Flow Radar - Web Dashboard

echo ====================================
echo    Flow Radar - Web 仪表板模式
echo ====================================
echo.
echo 启动选项:
echo   1. 终端 + Web 模式 (默认)
echo   2. 仅 Web 模式 (无终端 UI)
echo   3. 自定义端口
echo.

set /p choice="请选择 (1/2/3) [1]: "

if "%choice%"=="" set choice=1
if "%choice%"=="1" (
    echo.
    echo 启动终端 + Web 模式...
    python alert_monitor.py -s DOGE/USDT --web
)
if "%choice%"=="2" (
    echo.
    echo 启动仅 Web 模式...
    python alert_monitor.py -s DOGE/USDT --web-only
)
if "%choice%"=="3" (
    set /p port="请输入端口号 [8080]: "
    if "%port%"=="" set port=8080
    echo.
    echo 启动 Web 模式 (端口: %port%)...
    python alert_monitor.py -s DOGE/USDT --web --port %port%
)

pause
