@echo off
chcp 65001 > nul
title K神战法 回测报告生成器

echo ============================================================
echo K神战法 2.0 回测报告生成器
echo ============================================================
echo.
echo 本脚本将分析已保存的监控数据，生成回测报告
echo.
echo ============================================================
echo.

REM 获取今天和3天前的日期（用于回测范围）
echo [1] 准备回测数据...
echo.

REM 检查事件数据文件是否存在
if not exist "storage\events\DOGE_USDT_*.jsonl.gz" (
    echo ❌ 未找到监控数据文件！
    echo.
    echo 请先运行"启动K神监控.bat"让程序运行至少几个小时，
    echo 收集足够的数据后再生成回测报告。
    echo.
    echo ============================================================
    pause
    exit /b 1
)

echo ✅ 找到监控数据文件
echo.
echo [2] 开始生成回测报告...
echo.
echo 这可能需要几分钟，请耐心等待...
echo.
echo ============================================================
echo.

REM 运行回测脚本（使用最近7天的数据）
python scripts\kgod_backtest.py --days 7

if errorlevel 1 (
    echo.
    echo ============================================================
    echo ❌ 回测报告生成失败！
    echo ============================================================
    echo.
    echo 可能原因：
    echo 1. 数据不足（需要至少几小时的监控数据）
    echo 2. Python 库缺失
    echo 3. 脚本执行错误
    echo.
    echo 请检查上方错误信息
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo ✅ 回测报告生成成功！
    echo ============================================================
    echo.
    echo 报告文件已保存：
    echo - backtest_results.csv  （详细数据表）
    echo - backtest_report.txt   （统计摘要）
    echo.

    REM 检查报告文件是否存在
    if exist "backtest_report.txt" (
        echo 正在打开统计摘要报告...
        echo.
        notepad backtest_report.txt
    )

    if exist "backtest_results.csv" (
        echo 详细数据表可用 Excel 打开查看
        echo.
    )

    echo ============================================================
)

echo.
pause
