@echo off
REM Phase 2 实时监控测试脚本
REM 运行 2 分钟后自动停止

echo ========================================
echo Phase 2 Real-Time Monitoring Test
echo ========================================
echo.
echo Testing DOGE/USDT for 2 minutes...
echo Phase 2 is enabled (use_p3_phase2: True)
echo.
echo Press Ctrl+C to stop earlier if needed
echo ========================================
echo.

timeout /t 120 /nobreak python alert_monitor.py --symbol DOGE/USDT

echo.
echo ========================================
echo Test completed!
echo Check the output above for Phase 2 processing
echo ========================================
pause
