@echo off
cd /d "%~dp0"
echo Starting Command Center...
echo Monitoring: DOGE/USDT
echo.
python command_center.py -s DOGE/USDT
pause
