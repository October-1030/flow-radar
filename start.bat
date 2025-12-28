@echo off
cd /d "%~dp0"
echo Starting Flow Radar...
echo Monitoring: DOGE/USDT
echo.
python command_center.py
pause
