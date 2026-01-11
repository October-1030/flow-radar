@echo off
chcp 65001 > nul
REM Flow Radar 72小时验证启动脚本
REM 运行验收测试后启动监控

echo ========================================
echo Flow Radar 72小时验证
echo ========================================
echo.

REM 切换到项目目录
cd /d %~dp0

REM 设置 Python 编码
set PYTHONIOENCODING=utf-8

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
echo.

REM 启动监控 (前台运行)
python alert_monitor.py -s DOGE/USDT

pause
