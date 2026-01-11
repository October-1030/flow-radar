@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting Iceberg Detector...
echo Monitoring: BTC/USDT
echo.
python iceberg_detector.py -s BTC/USDT
pause
