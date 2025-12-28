@echo off
chcp 65001 >nul
title Flow Radar - 流动性雷达
cd /d "%~dp0"

echo.
echo  ========================================
echo   Flow Radar - 流动性雷达
echo   默认监控: DOGE/USDT
echo  ========================================
echo.

python command_center.py

pause
