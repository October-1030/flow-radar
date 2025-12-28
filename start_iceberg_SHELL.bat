@echo off
cd /d "%~dp0"
echo Starting Iceberg Detector...
echo Monitoring: SHELL/USDT
echo.
python iceberg_detector.py -s SHELL/USDT
pause
