@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================
echo Flow Radar - 多币种监控启动器
echo ========================================
echo.
echo 正在启动 3 个监控窗口...
echo.

REM 启动 DOGE 监控（独立窗口）
start "Flow Radar - DOGE/USDT" cmd /k "chcp 65001 > nul && set PYTHONIOENCODING=utf-8 && python command_center.py -s DOGE/USDT"

REM 等待 2 秒避免同时启动冲突
timeout /t 2 /nobreak > nul

REM 启动 ETH 监控（独立窗口）
start "Flow Radar - ETH/USDT" cmd /k "chcp 65001 > nul && set PYTHONIOENCODING=utf-8 && python command_center.py -s ETH/USDT"

REM 等待 2 秒
timeout /t 2 /nobreak > nul

REM 启动 BTC 监控（独立窗口）
start "Flow Radar - BTC/USDT" cmd /k "chcp 65001 > nul && set PYTHONIOENCODING=utf-8 && python command_center.py -s BTC/USDT"

echo.
echo ✓ 已启动 3 个监控窗口：
echo   1. DOGE/USDT
echo   2. ETH/USDT
echo   3. BTC/USDT
echo.
echo 每个币种在独立的命令行窗口中运行。
echo 窗口标题显示对应的币种名称。
echo.
echo 按任意键关闭此窗口...
pause > nul
