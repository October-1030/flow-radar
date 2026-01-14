@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   K神战法回测 - 指定日期范围
echo   日期: 2026-01-12 ~ 2026-01-13
echo   最低置信度: 60
echo ============================================
echo.
echo 当前目录: %cd%
echo.

python scripts/kgod_backtest.py --start_date 2026-01-12 --end_date 2026-01-13 --min_confidence 60

if %errorlevel% neq 0 (
    echo.
    echo [错误] 回测脚本执行失败，错误码: %errorlevel%
)

echo.
echo ============================================
echo   回测完成，按任意键退出
echo ============================================
pause >nul
