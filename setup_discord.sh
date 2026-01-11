#!/bin/bash
# Discord Webhook 配置向导 (Linux/Mac)
# 这个脚本会引导你完成 Discord Webhook 配置

echo "========================================"
echo "Discord Webhook Configuration Wizard"
echo "Flow Radar - Phase 2 Bundle Alerts"
echo "========================================"
echo

echo "Step 1: Create Discord Webhook"
echo "========================================"
echo
echo "Please follow these steps in Discord:"
echo
echo "1. Go to your Discord server"
echo "2. Right-click on the channel for alerts"
echo "3. Select 'Edit Channel'"
echo "4. Click 'Integrations' tab"
echo "5. Click 'Create Webhook'"
echo "6. Name it: 'Flow Radar Alerts'"
echo "7. Click 'Copy Webhook URL'"
echo
read -p "Press Enter when you have copied the Webhook URL..."
echo

echo "Step 2: Configure Webhook URL"
echo "========================================"
echo
echo "Please paste your Discord Webhook URL:"
echo "(Example: https://discord.com/api/webhooks/...)"
echo
read -p "Webhook URL: " WEBHOOK_URL

if [ -z "$WEBHOOK_URL" ]; then
    echo
    echo "[ERROR] Webhook URL cannot be empty!"
    echo "Please run this script again."
    exit 1
fi

echo
echo "Webhook URL received: ${WEBHOOK_URL:0:50}..."
echo

echo "Step 3: Set Environment Variable"
echo "========================================"
echo
echo "Setting DISCORD_WEBHOOK_URL environment variable..."

# Export for current session
export DISCORD_WEBHOOK_URL="$WEBHOOK_URL"

# Add to shell config for persistence
SHELL_CONFIG=""
if [ -f "$HOME/.bashrc" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
elif [ -f "$HOME/.zshrc" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
fi

if [ -n "$SHELL_CONFIG" ]; then
    # Check if already exists
    if grep -q "DISCORD_WEBHOOK_URL" "$SHELL_CONFIG"; then
        echo "[INFO] DISCORD_WEBHOOK_URL already exists in $SHELL_CONFIG"
        echo "[INFO] Please update it manually if needed"
    else
        echo "export DISCORD_WEBHOOK_URL=\"$WEBHOOK_URL\"" >> "$SHELL_CONFIG"
        echo "[OK] Added to $SHELL_CONFIG"
        echo "[INFO] Run 'source $SHELL_CONFIG' to apply in current terminal"
    fi
else
    echo "[WARNING] Could not find shell config file (.bashrc or .zshrc)"
    echo "[INFO] Please add this line to your shell config manually:"
    echo "export DISCORD_WEBHOOK_URL=\"$WEBHOOK_URL\""
fi

echo

echo "Step 4: Enable Discord in Configuration"
echo "========================================"
echo
echo "Updating config/settings.py..."

# 使用 Python 更新配置
python3 -c "import re; content = open('config/settings.py', 'r', encoding='utf-8').read(); content = re.sub(r'\"enabled\":\s*False,\s*#\s*是否启用', '\"enabled\": True,  # 是否启用', content); open('config/settings.py', 'w', encoding='utf-8').write(content); print('[OK] Discord enabled in config/settings.py')" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "Configuration updated successfully!"
else
    echo "[INFO] Please manually update config/settings.py:"
    echo
    echo "CONFIG_DISCORD = {"
    echo "    \"enabled\": True,  # <-- Change to True"
    echo "    ..."
    echo "}"
fi

echo

echo "Step 5: Test Configuration"
echo "========================================"
echo
echo "Running test script..."
echo

python3 test_discord_webhook.py

echo
echo "========================================"
echo "Configuration Complete!"
echo "========================================"
echo
echo "Next steps:"
echo "1. Check your Discord channel for test message"
echo "2. Run: python alert_monitor.py --symbol DOGE/USDT"
echo "3. Receive real-time Bundle alerts!"
echo
echo "For more information, see:"
echo "- DISCORD_WEBHOOK_SETUP_GUIDE.md"
echo "- PHASE2_QUICK_START.md"
echo
