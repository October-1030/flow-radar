@echo off
REM Discord Webhook 配置向导 (Windows)
REM 这个脚本会引导你完成 Discord Webhook 配置

echo ========================================
echo Discord Webhook Configuration Wizard
echo Flow Radar - Phase 2 Bundle Alerts
echo ========================================
echo.

echo Step 1: Create Discord Webhook
echo ========================================
echo.
echo Please follow these steps in Discord:
echo.
echo 1. Go to your Discord server
echo 2. Right-click on the channel for alerts
echo 3. Select "Edit Channel"
echo 4. Click "Integrations" tab
echo 5. Click "Create Webhook"
echo 6. Name it: "Flow Radar Alerts"
echo 7. Click "Copy Webhook URL"
echo.
echo Press any key when you have copied the Webhook URL...
pause >nul
echo.

echo Step 2: Configure Webhook URL
echo ========================================
echo.
echo Please paste your Discord Webhook URL:
echo (Example: https://discord.com/api/webhooks/...)
echo.
set /p WEBHOOK_URL="Webhook URL: "

if "%WEBHOOK_URL%"=="" (
    echo.
    echo [ERROR] Webhook URL cannot be empty!
    echo Please run this script again.
    pause
    exit /b 1
)

echo.
echo Webhook URL received: %WEBHOOK_URL:~0,50%...
echo.

echo Step 3: Set Environment Variable
echo ========================================
echo.
echo Setting DISCORD_WEBHOOK_URL environment variable...

REM Set for current session
set DISCORD_WEBHOOK_URL=%WEBHOOK_URL%

REM Set permanently for user
setx DISCORD_WEBHOOK_URL "%WEBHOOK_URL%" >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [OK] Environment variable set successfully!
) else (
    echo [WARNING] Failed to set permanent environment variable.
    echo You may need to set it manually in System Properties.
)

echo.

echo Step 4: Enable Discord in Configuration
echo ========================================
echo.
echo Updating config/settings.py...

REM 使用 Python 更新配置
python -c "import re; content = open('config/settings.py', 'r', encoding='utf-8').read(); content = re.sub(r'\"enabled\":\s*False,\s*#\s*是否启用', '\"enabled\": True,  # 是否启用', content); open('config/settings.py', 'w', encoding='utf-8').write(content); print('[OK] Discord enabled in config/settings.py')" 2>nul

if %ERRORLEVEL% EQU 0 (
    echo Configuration updated successfully!
) else (
    echo [INFO] Please manually update config/settings.py:
    echo.
    echo CONFIG_DISCORD = {
    echo     "enabled": True,  # ^<-- Change to True
    echo     ...
    echo }
)

echo.

echo Step 5: Test Configuration
echo ========================================
echo.
echo Running test script...
echo.

python test_discord_webhook.py

echo.
echo ========================================
echo Configuration Complete!
echo ========================================
echo.
echo Next steps:
echo 1. Check your Discord channel for test message
echo 2. Run: python alert_monitor.py --symbol DOGE/USDT
echo 3. Receive real-time Bundle alerts!
echo.
echo For more information, see:
echo - DISCORD_WEBHOOK_SETUP_GUIDE.md
echo - PHASE2_QUICK_START.md
echo.
pause
