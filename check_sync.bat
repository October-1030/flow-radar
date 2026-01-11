@echo off
chcp 65001 > nul

REM 创建结果文件
set RESULT=同步验证结果.txt

echo 正在检查同步状态，请稍候...
echo.

(
echo ============================================================
echo OneDrive 同步验证结果
echo 验证时间: %date% %time%
echo ============================================================
echo.

echo [1] 检查关键文件是否存在
echo ----------------------------------------
if exist "config\settings.py" (
    echo ✅ config\settings.py 存在
) else (
    echo ❌ config\settings.py 不存在 - 同步未完成！
)

if exist "scripts\kgod_backtest.py" (
    echo ✅ scripts\kgod_backtest.py 存在
) else (
    echo ❌ scripts\kgod_backtest.py 不存在 - 同步未完成！
)

if exist "KGOD_PHASE3_COMPLETION.md" (
    echo ✅ KGOD_PHASE3_COMPLETION.md 存在
) else (
    echo ❌ KGOD_PHASE3_COMPLETION.md 不存在 - 同步未完成！
)

if exist "core\unified_signal_manager.py" (
    echo ✅ core\unified_signal_manager.py 存在
) else (
    echo ❌ core\unified_signal_manager.py 不存在 - 同步未完成！
)

echo.
echo [2] 检查 K神战法配置
echo ----------------------------------------
if exist "config\settings.py" (
    findstr /C:"use_kgod_radar" config\settings.py 2>nul
    if errorlevel 1 (
        echo ⚠️ 找不到 use_kgod_radar 配置
    )
) else (
    echo ❌ config\settings.py 不存在
)

echo.
echo [3] 检查文件修改时间
echo ----------------------------------------
if exist "config\settings.py" (
    dir "config\settings.py" | findstr "settings.py"
)
if exist "scripts\kgod_backtest.py" (
    dir "scripts\kgod_backtest.py" | findstr "kgod_backtest.py"
)

echo.
echo [4] 检查 Git 最新提交
echo ----------------------------------------
git log -1 --oneline 2>nul
if errorlevel 1 (
    echo ⚠️ Git 未初始化或不在 git 仓库中
)

echo.
echo ============================================================
echo 验证结论
echo ============================================================
echo.
echo 如果上述检查显示：
echo   ✅ 所有关键文件都存在
echo   ✅ use_kgod_radar: True
echo   ✅ 文件修改时间是今天（2026-01-10）
echo   ✅ Git commit 是 249427a
echo.
echo 则说明 OneDrive 同步成功！可以启动监控程序。
echo.
echo 如果有 ❌ 标记，说明同步还未完成，请再等待 5-10 分钟。
echo ============================================================

) > "%RESULT%"

echo 检查完成！结果已保存到: %RESULT%
echo.
echo 正在打开结果文件...
notepad "%RESULT%"
