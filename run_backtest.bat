@echo off
REM K神战法 Phase 3 回测快速启动脚本
REM 默认回测最近 3 天的数据

echo ========================================
echo K神战法 Phase 3 历史数据回测
echo ========================================
echo.

REM 激活虚拟环境（如果存在）
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM 运行回测（最近 3 天）
python scripts\kgod_backtest.py ^
    --symbol DOGE_USDT ^
    --start_date 2026-01-07 ^
    --end_date 2026-01-09 ^
    --mode signal_outcome_eval ^
    --min_confidence 0.0 ^
    --lookforward_bars 60 ^
    --output_csv backtest_results.csv ^
    --output_report backtest_report.txt

echo.
echo ========================================
echo 回测完成! 请查看:
echo   - backtest_results.csv
echo   - backtest_report.txt
echo ========================================
pause
