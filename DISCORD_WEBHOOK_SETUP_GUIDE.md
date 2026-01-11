# Discord Webhook 配置指南

**目的**: 配置 Discord Webhook 以接收 Phase 2 Bundle 综合告警
**时间**: 约 5 分钟
**难度**: ⭐ 简单

---

## 📋 前提条件

- ✅ Discord 账号
- ✅ 拥有管理员权限的 Discord 服务器，或创建新服务器的权限

---

## 🚀 配置步骤

### 步骤 1: 创建 Discord Webhook

#### 选项 A: 在现有服务器中创建 Webhook

1. **打开 Discord** 并选择你的服务器

2. **进入频道设置**
   - 右键点击要接收告警的文字频道
   - 选择 **"编辑频道"** (Edit Channel)

3. **创建 Webhook**
   - 点击左侧 **"集成"** (Integrations) 选项卡
   - 点击 **"创建 Webhook"** (Create Webhook) 按钮

4. **配置 Webhook**
   - 名称: `Flow Radar Alerts` (或任意名称)
   - 头像: (可选) 上传机器人头像
   - 频道: 确认是你想要的频道

5. **复制 Webhook URL**
   - 点击 **"复制 Webhook URL"** (Copy Webhook URL) 按钮
   - URL 格式: `https://discord.com/api/webhooks/...`
   - ⚠️ **重要**: 不要分享此 URL！它可以被用来发送消息到你的频道

6. **保存设置**
   - 点击 **"保存更改"** (Save Changes)

#### 选项 B: 创建新服务器用于测试

如果你想单独测试，可以创建一个新的 Discord 服务器：

1. **创建服务器**
   - 点击 Discord 左侧的 **"+"** 按钮
   - 选择 **"创建我的服务器"** (Create My Own)
   - 选择 **"仅供我和我的朋友使用"**
   - 服务器名称: `Flow Radar Test`

2. **创建专用频道**
   - 在服务器中创建一个新的文字频道
   - 名称: `alerts` 或 `trading-signals`

3. **按选项 A 的步骤创建 Webhook**

---

### 步骤 2: 配置 Flow Radar

#### 方法 1: 使用环境变量 (推荐)

**Windows (PowerShell)**:
```powershell
# 临时设置（当前会话）
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# 永久设置
[System.Environment]::SetEnvironmentVariable("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL", "User")
```

**Windows (CMD)**:
```cmd
set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_URL
```

**Linux/Mac**:
```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"

# 永久设置 (添加到 ~/.bashrc 或 ~/.zshrc)
echo 'export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_WEBHOOK_URL"' >> ~/.bashrc
```

#### 方法 2: 直接修改配置文件

编辑 `config/settings.py`:

```python
# ==================== Discord 通知配置 ====================
CONFIG_DISCORD = {
    "enabled": True,  # ← 改为 True
    "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL",  # ← 替换为你的 URL
    "min_confidence": 50,                      # 最低置信度阈值
    "rate_limit_per_minute": 10,               # 每分钟最大通知数
    "embed_colors": {
        "buy": 0x00FF00,                       # 绿色
        "sell": 0xFF0000,                      # 红色
        "warning": 0xFFFF00,                   # 黄色
        "opportunity": 0x00BFFF,               # 天蓝色
        "normal": 0x808080,                    # 灰色
    },
    "include_fields": True,                    # 是否包含详细字段
}
```

**⚠️ 安全提醒**: 如果使用方法 2，请确保不要将 `config/settings.py` 提交到公共 Git 仓库！

---

### 步骤 3: 测试 Discord 连接

运行测试脚本验证配置：

```bash
python test_discord_webhook.py
```

**预期输出**:
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Discord Webhook 测试
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Discord 配置已加载
✓ Webhook URL 已设置
✓ Discord 已启用

正在发送测试消息...
✅ 测试消息发送成功！

请检查你的 Discord 频道，应该能看到测试消息。
```

**Discord 中应该收到**:
```
🧪 Flow Radar 测试消息

这是一条测试消息，用于验证 Discord Webhook 配置。

如果你看到这条消息，说明配置成功！

⏰ 时间: 2026-01-09 11:00:00
```

---

### 步骤 4: 测试 Phase 2 Bundle 告警

运行 Phase 2 演示脚本，验证 Bundle 告警发送：

```bash
python examples/p3_phase2_discord_demo.py
```

**预期 Discord 消息**:
```
🔔 综合信号告警 - DOGE_USDT

🚀 建议操作: **STRONG_BUY** (置信度: 77%)
📈 BUY 信号: 4 个（加权得分: 1565）
📉 SELL 信号: 1 个（加权得分: 120）

💡 判断理由:
3 个高置信度 BUY 信号，形成共振（+30 置信度增强），
1 个 SELL 信号因冲突被惩罚。

📊 信号明细（共 5 个）:

1. 🟢 💥 **CRITICAL** liq BUY @0.15
   置信度: 100% (基础 92%, +10 共振 -5 冲突 +30 组合)

2. 🟢 🐋 **CONFIRMED** whale BUY @0.1501
   置信度: 100% (基础 88%, +10 共振 -5 冲突 +30 组合)

... (更多信号)

⏰ 时间: 2026-01-09 11:00:00
```

---

## 🎛️ 高级配置

### 调整告警阈值

如果收到太多告警，可以提高置信度阈值：

```python
CONFIG_DISCORD = {
    "enabled": True,
    "webhook_url": "...",
    "min_confidence": 70,  # 从 50 提高到 70（只发送高置信度告警）
}
```

### 调整速率限制

防止告警过载：

```python
CONFIG_DISCORD = {
    "enabled": True,
    "webhook_url": "...",
    "rate_limit_per_minute": 5,  # 从 10 降到 5（每分钟最多 5 条）
}
```

### 自定义颜色

更改告警消息的颜色：

```python
CONFIG_DISCORD = {
    "enabled": True,
    "webhook_url": "...",
    "embed_colors": {
        "buy": 0x00FF00,      # 绿色（默认）
        "sell": 0xFF0000,     # 红色（默认）
        "warning": 0xFFA500,  # 橙色（修改）
        "opportunity": 0x1E90FF,  # 亮蓝色（修改）
        "normal": 0x808080,   # 灰色（默认）
    },
}
```

---

## 🔧 故障排查

### 问题 1: 测试消息未收到

**症状**: 运行测试脚本后，Discord 没有收到消息

**可能原因和解决方案**:

1. **Webhook URL 错误**
   ```bash
   # 检查 URL 格式
   echo $DISCORD_WEBHOOK_URL
   # 应该是: https://discord.com/api/webhooks/...
   ```

2. **Discord 未启用**
   ```python
   # 检查 config/settings.py
   CONFIG_DISCORD = {
       "enabled": True,  # 确认是 True
   }
   ```

3. **环境变量未设置**
   ```bash
   # 检查环境变量
   python -c "import os; print('URL:', os.getenv('DISCORD_WEBHOOK_URL', 'NOT SET'))"
   ```

4. **Webhook 被删除**
   - 进入 Discord 频道设置 → 集成
   - 确认 Webhook 仍然存在
   - 如果被删除，重新创建并更新 URL

---

### 问题 2: 错误 "HTTP 404"

**症状**: 测试脚本显示 `HTTP 404: Not Found`

**原因**: Webhook URL 无效或已被删除

**解决方案**:
1. 进入 Discord 频道设置 → 集成
2. 删除旧的 Webhook
3. 创建新的 Webhook
4. 复制新的 URL 并更新配置

---

### 问题 3: 错误 "HTTP 429"

**症状**: 测试脚本显示 `HTTP 429: Rate Limited`

**原因**: 发送消息过于频繁，被 Discord 限速

**解决方案**:
1. 等待 1-2 分钟后重试
2. 降低 `rate_limit_per_minute` 配置
3. 避免短时间内多次运行测试脚本

---

### 问题 4: 告警消息格式错乱

**症状**: Discord 消息显示格式不正确

**原因**: Discord Markdown 渲染问题

**解决方案**:
1. 检查 `core/bundle_advisor.py` 中的 `format_bundle_alert()` 方法
2. 确保使用 Discord 支持的 Markdown 格式：
   - `**粗体**`
   - `*斜体*`
   - `:emoji_name:` (表情符号)

---

## 📱 移动端接收告警

### iOS

1. **安装 Discord App**
   - App Store 搜索 "Discord"
   - 安装并登录

2. **启用推送通知**
   - 进入 Discord 设置 → 通知
   - 确保 "推送通知" 已启用
   - 为告警频道启用 "@所有人" 通知（如需要）

3. **测试**
   - 运行测试脚本
   - 应该在手机上收到推送通知

### Android

1. **安装 Discord App**
   - Google Play 搜索 "Discord"
   - 安装并登录

2. **启用推送通知**
   - 进入 Discord 设置 → 通知
   - 确保允许通知
   - 为告警频道配置通知设置

3. **测试**
   - 运行测试脚本
   - 应该在手机上收到推送通知

---

## 🎯 最佳实践

### 1. 使用专用频道

创建一个专门的告警频道（如 `#trading-alerts`），避免与其他消息混淆。

### 2. 设置合理的阈值

```python
# 推荐配置
CONFIG_DISCORD = {
    "enabled": True,
    "min_confidence": 60,  # 中等阈值，过滤低质量信号
    "rate_limit_per_minute": 8,  # 适中的速率限制
}
```

### 3. 定期审查告警质量

- 记录告警消息
- 对比实际市场走势
- 根据准确率调整 `min_confidence`

### 4. 备份 Webhook URL

- 将 Webhook URL 保存到密码管理器
- 如果 Webhook 被删除，可以快速恢复

### 5. 多设备接收

- 在手机和电脑上都安装 Discord
- 确保重要告警不会错过

---

## ✅ 配置检查清单

完成配置后，请确认以下项目：

- [ ] Discord Webhook 已创建
- [ ] Webhook URL 已复制
- [ ] `CONFIG_DISCORD["enabled"]` 设置为 `True`
- [ ] Webhook URL 已配置（环境变量或配置文件）
- [ ] 运行 `test_discord_webhook.py` 成功
- [ ] Discord 频道收到测试消息
- [ ] 运行 Phase 2 演示脚本成功
- [ ] Discord 频道收到 Bundle 告警
- [ ] 手机端可以接收推送通知（如需要）

---

## 📚 相关资源

- **Discord Developer Portal**: https://discord.com/developers/docs/resources/webhook
- **Discord Markdown 指南**: https://support.discord.com/hc/en-us/articles/210298617
- **Flow Radar 文档**:
  - Phase 2 快速入门: `PHASE2_QUICK_START.md`
  - 最终状态报告: `P3-2_PHASE2_FINAL_STATUS.md`
  - 测试报告: `PHASE2_LIVE_TEST_REPORT.md`

---

## 🆘 需要帮助？

如果遇到问题：

1. **检查日志**
   ```bash
   python alert_monitor.py --symbol DOGE/USDT
   # 查看控制台输出中的 Discord 相关错误
   ```

2. **运行调试模式**
   ```python
   # 在 core/discord_notifier.py 中添加
   console.print(f"[cyan]DEBUG: Webhook URL: {self.webhook_url[:50]}...[/cyan]")
   ```

3. **查看完整错误信息**
   - Discord 通知器会在控制台打印详细错误
   - 错误信息包含 HTTP 状态码和响应内容

---

**配置完成后，你就可以实时接收 Phase 2 的 Bundle 综合告警了！** 🎉

---

*配置指南最后更新: 2026-01-09*
*Flow Radar Version: Phase 2 (Production Ready)*
