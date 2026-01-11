# Discord Webhook 配置总结

**配置日期**: 2026-01-09
**状态**: ✅ 配置工具已准备就绪

---

## 📋 已完成的工作

### 1. 配置文档 ✅

| 文档 | 路径 | 用途 |
|------|------|------|
| 完整配置指南 | `DISCORD_WEBHOOK_SETUP_GUIDE.md` | 详细的配置步骤、故障排查、最佳实践 |
| 快速配置指南 | `DISCORD_QUICK_SETUP.md` | 3 分钟快速配置说明 |

**内容包含**:
- ✅ Discord Webhook 创建步骤（含截图说明）
- ✅ 两种配置方法（环境变量 vs 配置文件）
- ✅ 高级配置选项（阈值、速率限制、颜色）
- ✅ 故障排查指南（4+ 常见问题）
- ✅ 移动端配置说明（iOS + Android）
- ✅ 最佳实践建议

---

### 2. 测试工具 ✅

| 工具 | 路径 | 功能 |
|------|------|------|
| Discord 连接测试 | `test_discord_webhook.py` | 验证 Discord 配置，发送测试消息 |
| Bundle 告警演示 | `examples/p3_phase2_discord_demo.py` | 演示 Phase 2 Bundle 告警发送 |

**功能**:
- ✅ 自动检测配置状态
- ✅ 验证 Webhook URL 有效性
- ✅ 发送测试消息到 Discord
- ✅ 测试 Phase 2 Bundle 告警
- ✅ 显示详细错误信息和排查建议

---

### 3. 配置向导 ✅

| 平台 | 脚本 | 功能 |
|------|------|------|
| Windows | `setup_discord.bat` | 交互式配置向导 |
| Linux/Mac | `setup_discord.sh` | 交互式配置向导 |

**自动化功能**:
- ✅ 引导创建 Discord Webhook
- ✅ 自动设置环境变量
- ✅ 自动启用 Discord 配置
- ✅ 自动运行测试验证

---

## 🎯 配置步骤（用户需要做的）

### 快速配置（3 分钟）

1. **在 Discord 中创建 Webhook**
   - 右键点击频道 → 编辑频道
   - 集成 → 创建 Webhook
   - 复制 Webhook URL

2. **运行配置向导**
   ```bash
   # Windows
   setup_discord.bat

   # Linux/Mac
   ./setup_discord.sh
   ```

3. **测试配置**
   ```bash
   python test_discord_webhook.py
   ```

4. **开始接收告警**
   ```bash
   python alert_monitor.py --symbol DOGE/USDT
   ```

---

## 📊 当前配置状态

### Discord 配置

**位置**: `config/settings.py`

**当前设置**:
```python
CONFIG_DISCORD = {
    "enabled": False,  # ⚠️  需要改为 True
    "webhook_url": os.getenv("DISCORD_WEBHOOK_URL", ""),  # ⚠️  需要设置
    "min_confidence": 50,  # ✅ 默认值合理
    "rate_limit_per_minute": 10,  # ✅ 默认值合理
    "embed_colors": {...},  # ✅ 已配置
    "include_fields": True,  # ✅ 启用详细字段
}
```

**需要用户配置的项目**:
- [ ] 创建 Discord Webhook
- [ ] 设置 `DISCORD_WEBHOOK_URL` 环境变量
- [ ] 修改 `enabled: False` → `enabled: True`

---

### Phase 2 集成状态

**位置**: `config/settings.py`

**当前设置**:
```python
CONFIG_FEATURES = {
    "use_p3_phase2": True,  # ✅ 已启用
}
```

**状态**: ✅ Phase 2 已启用，等待 Discord 配置完成

---

## 🔔 Bundle 告警功能

### 触发条件

Phase 2 Bundle 告警会在以下情况自动发送：

1. **STRONG 级别信号**
   - STRONG_BUY 或 STRONG_SELL
   - 总是发送（高优先级）

2. **中等级别信号**
   - BUY 或 SELL
   - 置信度 > 60% 时发送

3. **WATCH 级别**
   - 信号冲突，观望
   - 不发送（避免信息过载）

---

### 告警内容

**Bundle 告警包含**:
- 🚀 综合建议（5 级: STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL）
- 💯 置信度百分比
- 📈 BUY 信号统计（数量、加权得分）
- 📉 SELL 信号统计（数量、加权得分）
- 💡 判断理由（简明扼要）
- 📊 信号明细（含置信度调整说明）
- ⏰ 时间戳

**示例**:
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
   ...
```

---

## 🎨 告警颜色

| 建议级别 | Discord 颜色 | 含义 |
|----------|--------------|------|
| STRONG_BUY | 亮绿色 | 强烈看涨，多个高置信度信号共振 |
| BUY | 绿色 | 看涨，信号优势明显 |
| WATCH | 黄色 | 信号冲突或接近平衡，观望 |
| SELL | 橙红色 | 看跌，SELL 信号优势 |
| STRONG_SELL | 红色 | 强烈看跌，多个 SELL 信号 |

---

## ⚙️ 高级配置选项

### 调整告警阈值

**位置**: `config/settings.py`

```python
CONFIG_DISCORD = {
    "min_confidence": 50,  # 默认 50%
    # 建议值:
    # - 保守: 70% (只接收高质量告警)
    # - 中等: 50% (平衡)
    # - 激进: 30% (接收更多告警)
}
```

---

### 调整速率限制

```python
CONFIG_DISCORD = {
    "rate_limit_per_minute": 10,  # 默认每分钟 10 条
    # 建议值:
    # - 波动期: 15-20 (增加限制)
    # - 平静期: 5-8 (减少限制)
}
```

---

### 自定义颜色

```python
CONFIG_DISCORD = {
    "embed_colors": {
        "buy": 0x00FF00,      # 绿色（默认）
        "sell": 0xFF0000,     # 红色（默认）
        "warning": 0xFFFF00,  # 黄色（默认）
        "opportunity": 0x00BFFF,  # 天蓝色（默认）
        "normal": 0x808080,   # 灰色（默认）
    },
}
```

颜色值格式: `0xRRGGBB` (16进制 RGB)

---

## 📱 移动端通知

### 确保推送通知

1. **iOS**:
   - 设置 → 通知 → Discord → 允许通知
   - Discord 内设置 → 通知 → 推送通知

2. **Android**:
   - 设置 → 应用 → Discord → 通知 → 允许
   - Discord 内设置 → 通知

3. **频道通知**:
   - 右键点击告警频道 → 通知设置
   - 选择 "所有消息" 或 "@所有人"

---

## 🔧 故障排查

### 问题 1: 测试消息未收到

**检查清单**:
```bash
# 1. 检查环境变量
python -c "import os; print(os.getenv('DISCORD_WEBHOOK_URL', 'NOT SET'))"

# 2. 检查配置
python -c "from config.settings import CONFIG_DISCORD; print('Enabled:', CONFIG_DISCORD['enabled']); print('URL:', CONFIG_DISCORD['webhook_url'][:50] if CONFIG_DISCORD['webhook_url'] else 'NOT SET')"

# 3. 运行测试
python test_discord_webhook.py
```

---

### 问题 2: 错误 HTTP 404

**原因**: Webhook URL 无效或已删除

**解决**:
1. 进入 Discord → 频道设置 → 集成
2. 检查 Webhook 是否存在
3. 如被删除，重新创建
4. 更新 Webhook URL

---

### 问题 3: 错误 HTTP 429

**原因**: 发送过于频繁，被 Discord 限速

**解决**:
1. 等待 1-2 分钟
2. 降低 `rate_limit_per_minute`
3. 避免短时间内多次测试

---

## ✅ 配置完成检查清单

完成配置后，请确认：

- [ ] Discord Webhook 已创建
- [ ] Webhook URL 已设置（环境变量或配置文件）
- [ ] `CONFIG_DISCORD["enabled"]` = `True`
- [ ] 运行 `test_discord_webhook.py` 成功
- [ ] Discord 收到测试消息
- [ ] 运行 `examples/p3_phase2_discord_demo.py` 成功
- [ ] Discord 收到 Bundle 告警
- [ ] 手机端可以接收推送（如需要）

---

## 🚀 下一步

配置完成后:

1. **启动实时监控**
   ```bash
   python alert_monitor.py --symbol DOGE/USDT
   ```

2. **观察告警效果**
   - 等待市场出现高级别信号
   - 接收 Discord Bundle 告警
   - 评估告警质量

3. **参数调优**（可选）
   - 根据告警质量调整 `min_confidence`
   - 根据告警频率调整 `rate_limit_per_minute`

4. **扩展功能**（未来）
   - 添加多交易对监控
   - 集成更多检测器（whale, liq）
   - 自定义告警规则

---

## 📚 相关文档

| 文档 | 用途 |
|------|------|
| `DISCORD_WEBHOOK_SETUP_GUIDE.md` | 完整配置指南 |
| `DISCORD_QUICK_SETUP.md` | 快速配置（3 分钟）|
| `PHASE2_QUICK_START.md` | Phase 2 使用指南 |
| `P3-2_PHASE2_FINAL_STATUS.md` | Phase 2 完整报告 |
| `PHASE2_LIVE_TEST_REPORT.md` | 测试报告 |

---

**配置完成后，你将实时接收 Phase 2 的智能 Bundle 告警！** 🎉

---

*文档生成时间: 2026-01-09*
*Flow Radar Version: Phase 2 (Production Ready)*
