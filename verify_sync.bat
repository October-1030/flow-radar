@echo off
chcp 65001 > nul

REM 输出到文件和屏幕
set LOG_FILE=sync_verification_result.txt

echo ============================================================ > %LOG_FILE%
echo OneDrive 同步验证脚本 >> %LOG_FILE%
echo 验证时间: %date% %time% >> %LOG_FILE%
echo ============================================================ >> %LOG_FILE%
echo. >> %LOG_FILE%

echo ============================================================
echo OneDrive 同步验证脚本
echo 验证时间: %date% %time%
echo ============================================================
echo.

echo [1] 检查关键文件是否存在...
if exist "config\settings.py" (
    echo ✅ config\settings.py 存在
) else (
    echo ❌ config\settings.py 不存在
)

if exist "scripts\kgod_backtest.py" (
    echo ✅ scripts\kgod_backtest.py 存在
) else (
    echo ❌ scripts\kgod_backtest.py 不存在
)

if exist "KGOD_PHASE3_COMPLETION.md" (
    echo ✅ KGOD_PHASE3_COMPLETION.md 存在
) else (
    echo ❌ KGOD_PHASE3_COMPLETION.md 不存在
)

echo.
echo [2] 检查 K神战法配置...
findstr /C:"use_kgod_radar" config\settings.py
echo.

echo [3] 查看最近修改的文件（前 10 个）...
dir /O-D /A-D | findstr /V "DIR" | findstr /V "个文件" | findstr /V "个目录" | findstr /V "可用字节" | head -10
echo.

echo [4] 检查 git 最新提交...
git log -1 --oneline
echo.

echo ============================================================
echo 验证完成！
echo.
echo 如果上述输出显示：
echo - ✅ 关键文件存在
echo - use_kgod_radar: True
echo - 文件修改时间是最近的（今天）
echo - git commit 是 249427a
echo.
echo 则说明 OneDrive 已成功同步！
echo ============================================================
pause
