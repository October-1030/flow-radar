@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================
echo Flow Radar - 依赖安装
echo ========================================
echo.
echo 正在安装依赖包...
pip install -r requirements.txt
echo.
echo ========================================
echo 安装完成！
echo ========================================
echo.
echo 现在可以运行：
echo   start_alert_DOGE.bat   - 综合判断系统
echo   start_DOGE.bat         - 战情指挥中心
echo.
pause
