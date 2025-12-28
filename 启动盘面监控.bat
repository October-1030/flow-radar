@echo off
chcp 65001 >nul
title Flow Radar - 盘面监控
cd /d "%~dp0"

echo.
echo  ========================================
echo   Flow Radar - 盘面监控 (System M)
echo   默认监控: DOGE/USDT
echo  ========================================
echo.

python main.py

pause
