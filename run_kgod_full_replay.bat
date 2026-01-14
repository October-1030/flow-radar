@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   K神战法回测 - 完整回放模式
echo   从历史数据重新生成信号
echo   最低置信度: 60
echo ============================================
echo.
echo 当前目录: %cd%
echo.

python scripts/kgod_backtest.py --mode full_replay --min_confidence 60

if %errorlevel% neq 0 (
    echo.
    echo [错误] 回测脚本执行失败，错误码: %errorlevel%
)

echo.
echo ============================================
echo   回测完成，按任意键退出
echo ============================================
pause >nul
