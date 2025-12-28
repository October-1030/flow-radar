@echo off
cd /d "%~dp0"
echo Starting Iceberg Detector...
echo Monitoring: ETH/USDT
echo.
python iceberg_detector.py -s ETH/USDT
pause
