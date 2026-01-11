@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting Command Center...
echo Monitoring: SHELL/USDT
echo.
python command_center.py -s SHELL/USDT
pause
