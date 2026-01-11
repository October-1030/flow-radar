@echo off
chcp 65001 > nul
echo ========================================
echo Flow Radar - 72小时运行环境检查
echo ========================================
echo.

echo [检查1] 睡眠设置
powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | findstr /C:"当前交流电源设置索引:" /C:"Current AC Power Setting Index:"
echo.

echo [检查2] 休眠设置
powercfg /query SCHEME_CURRENT SUB_SLEEP HIBERNATEIDLE | findstr /C:"当前交流电源设置索引:" /C:"Current AC Power Setting Index:"
echo.

echo [检查3] 网络连接
ping -n 1 okx.com > nul && echo ✓ 网络正常 || echo ✗ 网络异常
echo.

echo [检查4] Python进程
tasklist | findstr python.exe && echo ✓ Flow Radar 正在运行 || echo ⚠ 未检测到运行中的程序
echo.

echo ========================================
echo 建议：
echo 1. 如果睡眠/休眠不是0x00000000，需要手动设置为"从不"
echo 2. 打开 Windows 设置暂停更新1周
echo 3. 确保网络稳定
echo ========================================
pause
