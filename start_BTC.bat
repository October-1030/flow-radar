@echo off
cd /d "%~dp0"
echo Starting Command Center...
echo Monitoring: BTC/USDT
echo.
python command_center.py -s BTC/USDT
pause
