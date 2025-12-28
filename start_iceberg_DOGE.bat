@echo off
cd /d "%~dp0"
echo Starting Iceberg Detector...
echo Monitoring: DOGE/USDT
echo.
python iceberg_detector.py -s DOGE/USDT
pause
