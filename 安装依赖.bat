@echo off
chcp 65001 >nul
title 安装依赖
cd /d "%~dp0"

echo.
echo  正在安装依赖...
echo.

pip install -r requirements.txt

echo.
echo  安装完成！
echo.

pause
