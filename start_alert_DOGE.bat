@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ========================================
echo   Flow Radar - Analysis System
echo   DOGE/USDT
echo ========================================
echo.
echo   Features:
echo   1. Surface signals (Score/Trend/Whale)
echo   2. Hidden signals (Iceberg detection)
echo   3. Smart judgment (Wash/Dump/Real)
echo.
echo   Sound alerts on important signals!
echo.
echo ========================================
echo.
python alert_monitor.py -s DOGE/USDT
pause
