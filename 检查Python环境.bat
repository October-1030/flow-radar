@echo off
chcp 65001 > nul
echo ============================================================
echo 检查 Python 环境
echo ============================================================
echo.

echo [1] 检查 Python 是否安装...
python --version
if errorlevel 1 (
    echo ❌ Python 未安装或未添加到 PATH
    echo.
    echo 请安装 Python 3.9 或更高版本
    echo 下载地址: https://www.python.org/downloads/
) else (
    echo ✅ Python 已安装
)

echo.
echo [2] 检查必要的库...
python -c "import ccxt, pandas, numpy" 2>nul
if errorlevel 1 (
    echo ❌ 缺少必要的库
    echo.
    echo 请运行安装脚本: install.bat
) else (
    echo ✅ 必要的库已安装
)

echo.
echo [3] 检查 alert_monitor.py 是否存在...
if exist "alert_monitor.py" (
    echo ✅ alert_monitor.py 存在
) else (
    echo ❌ alert_monitor.py 不存在
    echo 请确认在正确的目录
)

echo.
echo ============================================================
pause
