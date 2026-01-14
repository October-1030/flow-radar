@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   K神战法回测 - 全部历史数据
echo   最低置信度: 60
echo   版本: v2 (含信号文件加载)
echo ============================================
echo.
echo 当前目录: %cd%
echo 检查信号文件...
dir /b storage\signals\*.jsonl 2>nul | find /c ".jsonl"
echo.

python scripts/kgod_backtest.py --min_confidence 60

if %errorlevel% neq 0 (
    echo.
    echo [错误] 回测脚本执行失败，错误码: %errorlevel%
)

echo.
echo ============================================
echo   回测完成，按任意键退出
echo ============================================
pause >nul
