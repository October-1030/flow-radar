# Discord Webhook 快速配置

**目标**: 3 分钟内完成 Discord Webhook 配置
**难度**: ⭐ 简单

---

## 🚀 3 步完成配置

### 方式 1: 使用配置向导 (推荐)

#### Windows:
```cmd
setup_discord.bat
```

#### Linux/Mac:
```bash
chmod +x setup_discord.sh
./setup_discord.sh
```

**配置向导会自动完成**:
1. 引导你创建 Discord Webhook
2. 设置环境变量
3. 启用 Discord 功能
4. 运行测试验证

---

### 方式 2: 手动配置 (3 步)

#### 步骤 1: 创建 Webhook (在 Discord 中)

1. 打开 Discord → 选择服务器
2. 右键点击频道 → **编辑频道**
3. **集成** → **创建 Webhook**
4. **复制 Webhook URL**

#### 步骤 2: 设置环境变量

**Windows (PowerShell)**:
```powershell
$env:DISCORD_WEBHOOK_URL = "你的_WEBHOOK_URL"
```

**Linux/Mac**:
```bash
export DISCORD_WEBHOOK_URL="你的_WEBHOOK_URL"
```

#### 步骤 3: 启用 Discord

编辑 `config/settings.py`:
```python
CONFIG_DISCORD = {
    "enabled": True,  # ← 改为 True
    "webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),
    ...
}
```

---

## 🧪 测试配置

```bash
python test_discord_webhook.py
```

**预期**: Discord 频道收到测试消息 ✅

---

## 📱 开始接收告警

```bash
python alert_monitor.py --symbol DOGE/USDT
```

当检测到高级别信号时，将自动发送 Bundle 告警到 Discord！

---

## 📚 完整文档

- **详细配置指南**: `DISCORD_WEBHOOK_SETUP_GUIDE.md`
- **故障排查**: 同上文档包含完整排查步骤
- **Phase 2 说明**: `PHASE2_QUICK_START.md`

---

## ❓ 常见问题

**Q: Webhook URL 在哪里找？**
A: Discord 频道 → 编辑频道 → 集成 → Webhooks

**Q: 测试消息未收到？**
A: 检查 URL 是否正确，确认 Discord enabled = True

**Q: 如何停止告警？**
A: 修改配置 `enabled: False` 或停止监控程序

---

**配置完成后，你就可以在 Discord 接收 Phase 2 的智能告警了！** 🎉
