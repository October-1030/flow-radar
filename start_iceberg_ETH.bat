@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting Iceberg Detector...
echo Monitoring: ETH/USDT
echo.
python iceberg_detector.py -s ETH/USDT
pause
