@echo off
cd /d "%~dp0"
echo Starting Command Center...
echo Monitoring: ETH/USDT
echo.
python command_center.py -s ETH/USDT
pause
