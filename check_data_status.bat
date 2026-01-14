@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   Flow Radar 数据状态检查
echo ============================================
echo.
echo 当前目录: %cd%
echo.

REM 检查 Python 是否可用
python --version 2>nul
if %errorlevel% neq 0 (
    echo [错误] Python 未安装或不在 PATH 中
    echo 请先安装 Python 并确保添加到 PATH
    pause
    exit /b 1
)

echo.
echo 正在运行检查脚本...
echo.

python -u check_data_status.py 2>&1

set PYERROR=%errorlevel%
echo.
echo ============================================

if %PYERROR% neq 0 (
    echo [错误] Python 脚本执行失败，错误码: %PYERROR%
    echo.
    echo 常见问题:
    echo   1. 确保在 flow-radar 目录下运行
    echo   2. 检查 storage 目录是否存在
    echo.
)

pause
