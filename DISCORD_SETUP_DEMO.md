# Discord Webhook 配置演示

**日期**: 2026-01-09
**当前状态**: 未配置
**预计配置时间**: 3-5 分钟

---

## 📊 当前配置状态

根据自动检测，当前配置状态如下：

```
============================================================
Discord Configuration Status
============================================================

Discord Enabled: ❌ No (need to change to True)

Webhook URL Configuration:
  ❌ Not Configured
     Need to set DISCORD_WEBHOOK_URL environment variable

Other Settings:
  ✅ Min Confidence: 50%
  ✅ Rate Limit: 10 messages/min
  ✅ Include Fields: True

============================================================
Configuration Required:
============================================================
❌ 1. Enable Discord in config/settings.py
❌ 2. Set Discord Webhook URL
```

---

## 🎯 配置步骤演示

### 方式 1: 使用自动配置向导 ⭐ (推荐)

#### Windows 用户:

```cmd
setup_discord.bat
```

**向导会自动引导你完成**:

```
========================================
Discord Webhook Configuration Wizard
Flow Radar - Phase 2 Bundle Alerts
========================================

Step 1: Create Discord Webhook
========================================

Please follow these steps in Discord:

1. Go to your Discord server
2. Right-click on the channel for alerts
3. Select "Edit Channel"
4. Click "Integrations" tab
5. Click "Create Webhook"
6. Name it: "Flow Radar Alerts"
7. Click "Copy Webhook URL"

Press any key when you have copied the Webhook URL...

Step 2: Configure Webhook URL
========================================

Please paste your Discord Webhook URL:
(Example: https://discord.com/api/webhooks/...)

Webhook URL: [你粘贴 URL 这里]

Webhook URL received: https://discord.com/api/webhooks/...

Step 3: Set Environment Variable
========================================

Setting DISCORD_WEBHOOK_URL environment variable...
[OK] Environment variable set successfully!

Step 4: Enable Discord in Configuration
========================================

Updating config/settings.py...
Configuration updated successfully!

Step 5: Test Configuration
========================================

Running test script...

[测试脚本会自动运行，验证配置]

========================================
Configuration Complete!
========================================

Next steps:
1. Check your Discord channel for test message
2. Run: python alert_monitor.py --symbol DOGE/USDT
3. Receive real-time Bundle alerts!
```

---

#### Linux/Mac 用户:

```bash
chmod +x setup_discord.sh
./setup_discord.sh
```

向导流程与 Windows 版本相同。

---

### 方式 2: 手动配置 (3 步)

#### 步骤 1: 在 Discord 中创建 Webhook

**详细步骤**:

1. **打开 Discord 应用**
   - 桌面版或网页版都可以
   - 登录你的账号

2. **选择或创建服务器**
   - 如果有现有服务器，直接使用
   - 或创建新服务器: 点击左侧 **"+"** → **"创建我的服务器"**
   - 服务器名称建议: `Flow Radar Test` 或 `Trading Alerts`

3. **创建专用频道**（推荐）
   - 右键点击服务器名称 → **"创建频道"**
   - 频道类型: **文字频道**
   - 频道名称: `alerts` 或 `trading-signals`
   - 点击 **"创建频道"**

4. **打开频道设置**
   - 右键点击刚创建的频道
   - 选择 **"编辑频道"** (Edit Channel)

5. **创建 Webhook**
   - 点击左侧 **"集成"** (Integrations) 选项卡
   - 找到 **"Webhook"** 部分
   - 点击 **"创建 Webhook"** (Create Webhook) 按钮

6. **配置 Webhook**
   - **名称**: 输入 `Flow Radar Alerts`
   - **头像**: (可选) 上传机器人图标
   - **频道**: 确认是正确的频道

7. **复制 Webhook URL**
   - 点击 **"复制 Webhook URL"** (Copy Webhook URL) 按钮
   - URL 格式类似: `https://discord.com/api/webhooks/1234567890/abcdefg...`
   - ⚠️ **重要**: 不要分享此 URL！任何人拥有此 URL 都可以向你的频道发送消息

8. **保存设置**
   - 点击 **"保存更改"** (Save Changes) 按钮

**完成！** 你的 Webhook 已创建。

---

#### 步骤 2: 设置 Webhook URL

现在需要将 Webhook URL 配置到 Flow Radar。

**方式 A: 使用环境变量** (推荐)

**Windows PowerShell**:
```powershell
# 临时设置（当前会话）
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# 永久设置（推荐）
[System.Environment]::SetEnvironmentVariable("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL", "User")

# 验证设置
echo $env:DISCORD_WEBHOOK_URL
```

**Windows CMD**:
```cmd
# 临时设置
set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL

# 永久设置
setx DISCORD_WEBHOOK_URL "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"
```

**Linux/Mac**:
```bash
# 临时设置
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"' >> ~/.bashrc
source ~/.bashrc
```

**方式 B: 直接修改配置文件**

编辑 `config/settings.py`，找到 `CONFIG_DISCORD` 部分：

```python
# ==================== Discord 通知配置 ====================
CONFIG_DISCORD = {
    "enabled": False,  # 暂时保持 False
    "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL",  # ← 粘贴你的 URL
    "min_confidence": 50,
    "rate_limit_per_minute": 10,
    "embed_colors": {
        "buy": 0x00FF00,
        "sell": 0xFF0000,
        "warning": 0xFFFF00,
        "opportunity": 0x00BFFF,
        "normal": 0x808080,
    },
    "include_fields": True,
}
```

⚠️ **安全提醒**: 如果使用方式 B，确保不要将 `config/settings.py` 提交到公共 Git 仓库！

---

#### 步骤 3: 启用 Discord

编辑 `config/settings.py`，将 `enabled` 改为 `True`:

```python
CONFIG_DISCORD = {
    "enabled": True,  # ← 改为 True
    ...
}
```

保存文件。

---

## 🧪 验证配置

### 运行测试脚本

```bash
python test_discord_webhook.py
```

**预期输出（配置正确）**:

```
┌──────────────────────┐
│ Discord Webhook 测试 │
└──────────────────────┘
✓ Discord 配置已加载

      Discord 配置状态
┌──────────────┬────────────────────────────┐
│ 配置项       │ 状态                       │
├──────────────┼────────────────────────────┤
│ Webhook URL  │ ✓ 已设置                   │
│              │ https://discord.com/api... │
│ Discord 状态 │ ✓ 已启用                   │
│ 最低置信度   │ 50%                        │
│ 速率限制     │ 10 条/分钟                 │
└──────────────┴────────────────────────────┘

正在初始化 Discord 通知器...
✓ Discord 通知器初始化成功

正在发送测试消息...
✅ 测试消息发送成功！

请检查你的 Discord 频道，应该能看到测试消息。

============================================================
测试 Phase 2 Bundle 告警
============================================================

创建测试信号...
✓ 创建了 3 个测试信号

执行 Phase 2 处理...
✓ Phase 2 处理完成，建议: STRONG_BUY

发送 Bundle 告警到 Discord...
✅ Bundle 告警发送成功！

请检查 Discord 频道，应该能看到详细的 Bundle 告警消息。

============================================================
测试总结
============================================================
基础 Discord 连接    ✅ 通过
Phase 2 Bundle 告警  ✅ 通过

🎉 所有测试通过！Discord Webhook 配置成功！

现在你可以运行实时监控，接收 Phase 2 Bundle 告警：
  python alert_monitor.py --symbol DOGE/USDT
```

---

### 在 Discord 中查看消息

配置成功后，你的 Discord 频道应该收到两条消息：

**消息 1: 测试消息**
```
🧪 Flow Radar 测试消息

这是一条测试消息，用于验证 Discord Webhook 配置。

如果你看到这条消息，说明配置成功！

💰 价格: $1.234560
🎯 置信度: 100%
📊 评分: 100
🌀 状态: 测试模式

⏰ 时间: 2026-01-09 11:15:00
Flow Radar
```

**消息 2: Bundle 告警演示**
```
🔔 综合信号告警 - TEST_USDT

🚀 建议操作: **STRONG_BUY** (置信度: 77%)
📈 BUY 信号: 3 个（加权得分: 1565）
📉 SELL 信号: 0 个（加权得分: 0）

💡 判断理由:
3 个高置信度 BUY 信号，形成共振（+30 置信度增强）。

📊 信号明细（共 3 个）:

1. 🟢 💥 **CRITICAL** liq BUY @1.0
   置信度: 100% (基础 92%, +10 共振 +30 组合)

2. 🟢 🐋 **CONFIRMED** whale BUY @1.001
   置信度: 100% (基础 88%, +10 共振 +30 组合)

3. 🟢 🧊 **CONFIRMED** iceberg BUY @1.002
   置信度: 100% (基础 85%, +10 共振 +30 组合)

📊 市场状态:
当前价格: $1.000000
CVD: 10000.00
鲸鱼流: $5000.00

⏰ 时间: 2026-01-09 11:15:00
Flow Radar - P3-2 Phase 2 | 信号数: 3
```

---

## 🎊 配置成功！

如果你看到了上述两条消息，恭喜！Discord Webhook 配置成功！

### 下一步：

1. **启动实时监控**
   ```bash
   python alert_monitor.py --symbol DOGE/USDT
   ```

2. **观察真实告警**
   - 系统会自动检测市场信号
   - 当出现高级别信号或信号组合时
   - Discord 会收到 Phase 2 Bundle 综合告警

3. **调整参数**（可选）
   - 如果告警太多，提高 `min_confidence`
   - 如果告警太少，降低 `min_confidence`
   - 默认值 50% 是平衡的选择

---

## 🔧 故障排查

### 问题 1: 测试消息未收到

**检查清单**:

```bash
# 1. 检查环境变量
python -c "import os; print('Webhook:', os.getenv('DISCORD_WEBHOOK_URL', 'NOT SET')[:50])"

# 2. 检查配置
python -c "from config.settings import CONFIG_DISCORD; print('Enabled:', CONFIG_DISCORD['enabled']); print('URL:', CONFIG_DISCORD['webhook_url'][:50] if CONFIG_DISCORD['webhook_url'] else 'NOT SET')"

# 3. 重新运行测试
python test_discord_webhook.py
```

**可能原因**:
- ❌ Webhook URL 未正确复制（检查是否完整）
- ❌ Discord 未启用（检查 `enabled: True`）
- ❌ 环境变量未生效（重启终端或使用配置文件）
- ❌ Webhook 被删除（重新创建）

---

### 问题 2: 错误 "HTTP 404"

**原因**: Webhook URL 无效或已被删除

**解决方案**:
1. 进入 Discord → 频道设置 → 集成
2. 检查 Webhook 是否存在
3. 如果不存在，重新创建
4. 复制新的 URL 并更新配置

---

### 问题 3: 错误 "HTTP 429"

**原因**: 发送过于频繁，被 Discord 限速

**解决方案**:
1. 等待 1-2 分钟后重试
2. 不要短时间内多次运行测试脚本
3. 降低 `rate_limit_per_minute` 配置

---

## 📱 移动端配置（可选）

### iOS

1. **安装 Discord App**
   - App Store → 搜索 "Discord"
   - 安装并登录

2. **启用推送通知**
   - iPhone 设置 → 通知 → Discord → 允许通知
   - Discord 设置 → 通知 → 推送通知

3. **配置频道通知**
   - 长按告警频道
   - 通知设置 → 选择 "所有消息"

4. **测试**
   - 运行 `python test_discord_webhook.py`
   - 手机应该收到推送通知

### Android

1. **安装 Discord App**
   - Google Play → 搜索 "Discord"
   - 安装并登录

2. **启用推送通知**
   - 系统设置 → 应用 → Discord → 通知 → 允许
   - Discord 设置 → 通知

3. **配置频道通知**
   - 长按告警频道
   - 通知设置 → 选择适合的级别

4. **测试**
   - 运行测试脚本
   - 手机应该收到通知

---

## 🎯 配置完成检查清单

- [ ] Discord Webhook 已创建
- [ ] Webhook URL 已复制
- [ ] 环境变量已设置 或 配置文件已修改
- [ ] `CONFIG_DISCORD["enabled"]` = `True`
- [ ] 运行 `test_discord_webhook.py` 成功
- [ ] Discord 频道收到测试消息
- [ ] Discord 频道收到 Bundle 告警演示
- [ ] 手机端可以接收推送（如需要）

---

## 📚 参考文档

| 文档 | 用途 |
|------|------|
| `DISCORD_QUICK_SETUP.md` | 快速配置（3 分钟）|
| `DISCORD_WEBHOOK_SETUP_GUIDE.md` | 完整配置指南 |
| `DISCORD_CONFIGURATION_SUMMARY.md` | 配置状态总结 |
| `PHASE2_QUICK_START.md` | Phase 2 使用指南 |

---

## 🆘 需要帮助？

如果在配置过程中遇到问题：

1. **查看详细文档**
   ```bash
   # 打开完整配置指南
   cat DISCORD_WEBHOOK_SETUP_GUIDE.md
   ```

2. **检查日志**
   ```bash
   # 运行监控程序查看详细日志
   python alert_monitor.py --symbol DOGE/USDT
   ```

3. **检查 Discord 开发者控制台**
   - 打开 Discord → F12（开发者工具）
   - 查看网络请求和错误信息

---

**配置完成后，你就可以实时接收 Phase 2 的智能 Bundle 告警了！** 🎉

---

*演示文档生成时间: 2026-01-09*
*Flow Radar Version: Phase 2 (Production Ready)*
