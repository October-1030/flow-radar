@echo off
REM Flow Radar 72小时验证启动脚本
REM 运行验收测试后启动监控

echo ========================================
echo Flow Radar 72小时验证
echo ========================================
echo.

REM 切换到项目目录
cd /d %~dp0

REM 运行验收测试
echo [1/2] 运行验收测试...
python tests/test_acceptance.py
if errorlevel 1 (
    echo.
    echo 验收测试失败，请修复后重试
    pause
    exit /b 1
)

echo.
echo [2/2] 启动72小时验证...
echo 日志文件: logs/72h_run_%date:~0,4%%date:~5,2%%date:~8,2%.log
echo.

REM 启动监控 (前台运行，方便查看)
python alert_monitor.py -s DOGE/USDT 2>&1 | tee logs/72h_run_%date:~0,4%%date:~5,2%%date:~8,2%.log

pause
