@echo off
cd /d "%~dp0"
echo ========================================
echo   Flow Radar - Auto Alert Monitor
echo   DOGE/USDT
echo ========================================
echo.
echo   This will monitor and ALERT you with sound!
echo   You can do other things, just listen for beeps.
echo.
echo   Buy signal: High-pitched beeps
echo   Sell signal: Low-pitched beeps
echo   Warning: Rapid beeps
echo.
echo ========================================
echo.
python alert_monitor.py -s DOGE/USDT
pause
