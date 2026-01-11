@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ========================================
echo   Flow Radar - Analysis System
echo   BTC/USDT
echo ========================================
echo.
python alert_monitor.py -s BTC/USDT
pause
