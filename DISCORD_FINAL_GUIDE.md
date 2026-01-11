# Discord Webhook 配置完整指南

**文档版本**: 1.0
**创建日期**: 2026-01-09
**系统状态**: Phase 2 就绪，等待 Discord 配置

---

## 📊 当前状态

### ✅ 已完成的工作

1. **Phase 2 核心功能** - 完全就绪
   - ✅ 信号融合引擎（关联检测）
   - ✅ 置信度调整器（共振+冲突）
   - ✅ 冲突解决器（6场景矩阵）
   - ✅ Bundle 综合建议（5级建议）

2. **Discord 集成代码** - 完全实现
   - ✅ DiscordNotifier 类
   - ✅ send_bundle_alert() 方法
   - ✅ 告警格式化（Embed 消息）
   - ✅ 速率限制和错误处理

3. **配置工具** - 全部就绪
   - ✅ 交互式配置向导（setup_discord.bat/.sh）
   - ✅ 测试脚本（test_discord_webhook.py）
   - ✅ 模拟测试（test_discord_simulation.py）
   - ✅ 完整文档（3级文档体系）

### ⚠️ 待完成的配置

**需要用户完成的唯一步骤**：

1. ❌ 创建 Discord Webhook（需要 Discord 账号）
2. ❌ 设置 Webhook URL（环境变量或配置文件）
3. ❌ 启用 Discord（修改 config/settings.py）

**估计时间**: 3-5 分钟

---

## 🚀 快速配置（3 种方法）

### 方法 1: 自动配置向导 ⭐ 推荐

#### Windows 用户：

```cmd
setup_discord.bat
```

#### Linux/Mac 用户：

```bash
chmod +x setup_discord.sh
./setup_discord.sh
```

**向导会自动完成**：
1. 引导你创建 Discord Webhook
2. 设置环境变量 `DISCORD_WEBHOOK_URL`
3. 启用 Discord（修改 settings.py）
4. 运行测试验证配置

**结果**：
- ✅ Webhook URL 已设置
- ✅ Discord 已启用
- ✅ 测试消息已发送
- ✅ 可以接收 Bundle 告警

---

### 方法 2: 快速手动配置（3 步）

#### 步骤 1: 创建 Webhook（2 分钟）

1. 打开 Discord → 选择服务器
2. 右键点击频道 → **编辑频道**
3. 点击 **集成** 选项卡
4. 点击 **创建 Webhook** 按钮
5. 命名为 "Flow Radar Alerts"
6. 点击 **复制 Webhook URL**

**URL 格式示例**：
```
https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyz...
```

⚠️ **安全提醒**：不要分享此 URL！

---

#### 步骤 2: 设置 Webhook URL（1 分钟）

**Windows (PowerShell)**：
```powershell
# 临时设置（当前会话）
$env:DISCORD_WEBHOOK_URL = "你的_WEBHOOK_URL"

# 永久设置（推荐）
[System.Environment]::SetEnvironmentVariable("DISCORD_WEBHOOK_URL", "你的_WEBHOOK_URL", "User")

# 验证
echo $env:DISCORD_WEBHOOK_URL
```

**Windows (CMD)**：
```cmd
# 永久设置
setx DISCORD_WEBHOOK_URL "你的_WEBHOOK_URL"
```

**Linux/Mac**：
```bash
# 临时设置
export DISCORD_WEBHOOK_URL="你的_WEBHOOK_URL"

# 永久设置（添加到 shell 配置）
echo 'export DISCORD_WEBHOOK_URL="你的_WEBHOOK_URL"' >> ~/.bashrc
source ~/.bashrc
```

---

#### 步骤 3: 启用 Discord（1 分钟）

编辑 `config/settings.py`：

```python
# 找到这一行（第 139 行附近）
CONFIG_DISCORD = {
    "enabled": False,  # ← 改为 True
    ...
}

# 修改为：
CONFIG_DISCORD = {
    "enabled": True,   # ← 改为 True
    ...
}
```

保存文件。

---

### 方法 3: 配置文件直接设置（不推荐）

⚠️ **安全风险**：将 Webhook URL 写入配置文件会导致敏感信息泄露（如果提交到 Git）。

如果你确定要使用此方法：

编辑 `config/settings.py`：

```python
CONFIG_DISCORD = {
    "enabled": True,
    "webhook_url": "https://discord.com/api/webhooks/你的_URL",  # ← 粘贴 URL
    ...
}
```

**⚠️ 重要**：确保 `config/settings.py` 在 `.gitignore` 中！

---

## 🧪 测试配置

### 测试 1: 基础连接测试

```bash
python test_discord_webhook.py
```

**预期输出**：
```
┌──────────────────────┐
│ Discord Webhook 测试 │
└──────────────────────┘
✓ Discord 配置已加载

      Discord 配置状态
┌──────────────┬────────────────────┐
│ Webhook URL  │ ✓ 已设置           │
│ Discord 状态 │ ✓ 已启用           │
│ 最低置信度   │ 50%                │
│ 速率限制     │ 10 条/分钟         │
└──────────────┴────────────────────┘

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
```

**Discord 中应该收到 2 条消息**：
1. 测试消息（简单文本）
2. Bundle 告警演示（完整 Embed 格式）

---

### 测试 2: 模拟告警预览（无需 Webhook）

```bash
python test_discord_simulation.py
```

**功能**：
- 显示 Bundle 告警格式
- 验证 Phase 2 处理流程
- 不实际发送到 Discord

**用途**：
- 在配置前预览告警样式
- 调试告警格式
- 验证 Phase 2 功能

---

## 📱 在 Discord 中查看告警

### 告警 1: 测试消息

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

---

### 告警 2: Phase 2 Bundle 告警（完整格式）

```
🔔 综合信号告警 - DOGE_USDT

🚀 建议操作: **STRONG_BUY** (置信度: 82%)
📈 BUY 信号: 4 个（加权得分: 1600）
📉 SELL 信号: 1 个（加权得分: 112）

💡 判断理由:
4 个高置信度 BUY 信号，形成共振（+60 置信度增强），
1 个 SELL 信号因冲突被惩罚。

📊 信号明细（共 5 个）:

1. 🟢 💥 **CRITICAL** liq BUY @0.15
   置信度: 100% (基础 92%, +15 共振 -5 冲突 +30 组合)

2. 🟢 🐋 **CONFIRMED** whale BUY @0.15005
   置信度: 100% (基础 88%, +15 共振 -5 冲突 +30 组合)

3. 🟢 🧊 **CONFIRMED** iceberg BUY @0.15002
   置信度: 100% (基础 85%, +15 共振 -5 冲突 +30 组合)
   补单: 4 次, 强度: 3.41

4. 🔴 🧊 **WARNING** iceberg SELL @0.15015
   置信度: 75% (基础 65%, -20 冲突 +30 组合)
   补单: 2 次, 强度: 2.05

5. 🟢 🧊 **ACTIVITY** iceberg BUY @0.14997
   置信度: 100% (基础 68%, +15 共振 -5 冲突 +30 组合)
   补单: 3 次, 强度: 2.25

⏰ 时间: 2026-01-09 11:37:38
```

**Discord 颜色说明**：
- **亮绿色** (STRONG_BUY): 强烈看涨
- **绿色** (BUY): 看涨
- **黄色** (WATCH): 观望
- **橙色** (SELL): 看跌
- **红色** (STRONG_SELL): 强烈看跌

---

## 🎯 开始接收实时告警

配置完成后，启动实时监控：

```bash
python alert_monitor.py --symbol DOGE/USDT
```

### 告警触发条件

Phase 2 Bundle 告警会在以下情况自动发送到 Discord：

1. **STRONG 级别信号**（总是发送）
   - STRONG_BUY 或 STRONG_SELL
   - 多个高置信度信号共振

2. **中等级别信号**（置信度 > 60%）
   - BUY 或 SELL
   - 信号优势明显

3. **WATCH 级别**（不发送）
   - 信号冲突或接近平衡
   - 避免信息过载

### 告警频率控制

默认配置（`config/settings.py`）：

```python
CONFIG_DISCORD = {
    "min_confidence": 50,              # 最低置信度阈值（%）
    "rate_limit_per_minute": 10,       # 每分钟最多 10 条
}
```

**调整建议**：
- **保守**：`min_confidence: 70`（只接收高质量告警）
- **中等**：`min_confidence: 50`（平衡，推荐）
- **激进**：`min_confidence: 30`（接收更多告警）

---

## 📊 Phase 2 功能说明

### 信号融合（Signal Fusion）

**算法**：价格重叠 + 时间窗口

```python
关联条件:
1. 时间窗口内（5 分钟）
2. 同交易对
3. 价格范围重叠（±0.1%）
```

**结果**：
- 每个信号的 `related_signals` 字段填充关联信号列表
- 80% 信号关联率（测试数据）

---

### 置信度调整（Confidence Modifier）

**调整因子**：

1. **同向共振增强**（+0 ~ +25）
   - 每个同向信号 +5%
   - 上限 +25%

2. **反向冲突惩罚**（-5 ~ -10）
   - 每个反向信号 -5%
   - 上限 -10%

3. **类型组合奖励**（+10 ~ +30）
   - iceberg + whale = +10
   - iceberg + liq = +15
   - whale + liq = +20
   - 三种组合 = +30

**示例**：
```
基础置信度: 85%
+ 共振增强: +15% (3个同向信号)
- 冲突惩罚: -5% (1个反向信号)
+ 类型组合: +30% (liq + whale + iceberg)
---------------------------------
最终置信度: 100% (限制在 0-100)
```

---

### 冲突解决（Conflict Resolver）

**6 场景优先级矩阵**：

| 场景 | BUY 信号 | SELL 信号 | 胜出者 | 理由 |
|------|----------|-----------|--------|------|
| 1 | CRITICAL liq | CONFIRMED iceberg | liq | 清算优先 |
| 2 | CONFIRMED whale | CONFIRMED iceberg | whale | 成交优先 |
| 3 | CONFIRMED iceberg | CONFIRMED iceberg | 高置信度 | 同类型比较 |
| 4 | WARNING | CRITICAL | CRITICAL | 级别优先 |
| 5 | ACTIVITY | CONFIRMED | CONFIRMED | 级别优先 |
| 6 | 同级同类 | 同级同类 | 都保留 | 标记冲突，降低置信度 |

---

### Bundle 综合建议（Bundle Advisor）

**判断逻辑**：

```python
weighted_buy = Σ(BUY信号置信度 × 类型权重)
weighted_sell = Σ(SELL信号置信度 × 类型权重)

类型权重:
- liq: 3
- whale: 2
- iceberg: 1

建议级别:
- weighted_buy / weighted_sell > 1.5  → STRONG_BUY
- weighted_buy > weighted_sell        → BUY
- weighted_sell / weighted_buy > 1.5  → STRONG_SELL
- weighted_sell > weighted_buy        → SELL
- 其他                                → WATCH
```

**输出**：
- 5 级建议（STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL）
- 置信度百分比
- 判断理由（简明扼要）
- 信号明细（含置信度调整说明）

---

## 🔧 故障排查

### 问题 1: 测试消息未收到

**检查配置**：

```bash
# 1. 检查环境变量
python -c "import os; print('Webhook:', os.getenv('DISCORD_WEBHOOK_URL', 'NOT SET')[:50])"

# 2. 检查配置文件
python -c "from config.settings import CONFIG_DISCORD; print('Enabled:', CONFIG_DISCORD['enabled']); print('URL:', CONFIG_DISCORD['webhook_url'][:50] if CONFIG_DISCORD['webhook_url'] else 'NOT SET')"

# 3. 重新运行测试
python test_discord_webhook.py
```

**可能原因**：
- ❌ Webhook URL 未正确复制（检查是否完整）
- ❌ Discord 未启用（检查 `enabled: True`）
- ❌ 环境变量未生效（重启终端或使用配置文件）
- ❌ Webhook 被删除（重新创建）

---

### 问题 2: 错误 "HTTP 404"

**原因**：Webhook URL 无效或已被删除

**解决方案**：
1. 进入 Discord → 频道设置 → 集成
2. 检查 Webhook 是否存在
3. 如果不存在，重新创建
4. 复制新的 URL 并更新配置

---

### 问题 3: 错误 "HTTP 429"

**原因**：发送过于频繁，被 Discord 限速

**解决方案**：
1. 等待 1-2 分钟后重试
2. 不要短时间内多次运行测试脚本
3. 降低 `rate_limit_per_minute` 配置

---

### 问题 4: 告警太多或太少

**调整阈值**：

编辑 `config/settings.py`：

```python
CONFIG_DISCORD = {
    # 告警太多 → 提高阈值
    "min_confidence": 70,  # 从 50 提高到 70

    # 告警太少 → 降低阈值
    "min_confidence": 30,  # 从 50 降低到 30
}
```

重启监控程序：

```bash
python alert_monitor.py --symbol DOGE/USDT
```

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

## ✅ 配置完成检查清单

完成配置后，请确认以下所有项目：

- [ ] Discord Webhook 已创建
- [ ] Webhook URL 已复制
- [ ] 环境变量已设置 **或** 配置文件已修改
- [ ] `CONFIG_DISCORD["enabled"]` = `True`
- [ ] 运行 `test_discord_webhook.py` 成功
- [ ] Discord 频道收到测试消息
- [ ] Discord 频道收到 Bundle 告警演示
- [ ] 手机端可以接收推送（如需要）
- [ ] 启动 `alert_monitor.py` 正常运行
- [ ] 理解告警触发条件和频率控制

---

## 📚 相关文档索引

| 文档 | 用途 | 详细程度 |
|------|------|----------|
| `DISCORD_QUICK_SETUP.md` | 3 分钟快速配置 | ⭐ 简单 |
| `DISCORD_SETUP_DEMO.md` | 详细配置演示 | ⭐⭐ 中等 |
| `DISCORD_CONFIGURATION_SUMMARY.md` | 配置状态总结 | ⭐⭐ 中等 |
| `DISCORD_FINAL_GUIDE.md` | 完整配置指南（本文档） | ⭐⭐⭐ 详细 |
| `PHASE2_QUICK_START.md` | Phase 2 使用指南 | ⭐⭐ 中等 |
| `P3-2_PHASE2_FINAL_STATUS.md` | Phase 2 完整报告 | ⭐⭐⭐ 详细 |
| `PHASE2_LIVE_TEST_REPORT.md` | Phase 2 测试报告 | ⭐⭐⭐ 详细 |

---

## 🎊 配置完成后的体验

### 实时监控运行中

```bash
$ python alert_monitor.py --symbol DOGE/USDT

[11:45:23] ✓ WebSocket 已连接
[11:45:24] 📊 开始监控 DOGE/USDT
[11:45:25] 🔍 检测中...
[11:46:30] 🧊 发现冰山信号 (ACTIVITY, BUY, @0.1404)
[11:46:31] ⏸️  信号已节流（等待更高级别）
[11:48:15] 🧊 发现冰山信号 (CONFIRMED, BUY, @0.1405)
[11:48:16] 🐋 发现鲸鱼信号 (CONFIRMED, BUY, @0.1406)
[11:48:17] ⚡ 信号共振检测！
[11:48:18] 🔔 发送 Bundle 告警到 Discord
[11:48:19] ✅ Discord 告警发送成功
```

### 在 Discord 中

你的告警频道会收到：

```
🔔 综合信号告警 - DOGE_USDT

🚀 建议操作: **BUY** (置信度: 75%)
📈 BUY 信号: 2 个（加权得分: 265）
📉 SELL 信号: 0 个

💡 判断理由:
2 个高置信度 BUY 信号形成共振，无反向冲突。

📊 信号明细...

[消息颜色: 绿色]
```

### 手机推送

如果配置了移动端，你的手机会收到：

```
Discord 通知

Flow Radar Alerts
🔔 综合信号告警 - DOGE/USDT
🚀 建议操作: BUY (置信度: 75%)
```

---

## 🚀 下一步行动

配置完成后，你可以：

1. **观察告警质量**
   - 运行监控 24 小时
   - 评估告警准确性
   - 调整置信度阈值

2. **参数调优**
   ```python
   # 如果告警太多：
   CONFIG_DISCORD = {
       "min_confidence": 70,  # 提高阈值
   }

   # 如果告警太少：
   CONFIG_DISCORD = {
       "min_confidence": 40,  # 降低阈值
   }
   ```

3. **扩展监控**
   - 添加更多交易对（BTC, ETH, SHELL）
   - 集成 WhaleDetector（鲸鱼检测）
   - 集成 LiquidationMonitor（清算监控）

4. **回测优化**
   - 使用历史数据验证 Phase 2 效果
   - 调整信号权重和阈值
   - 优化冲突解决策略

---

## 💡 最佳实践

### 1. 告警管理

- ✅ 创建专用频道接收告警（避免干扰其他讨论）
- ✅ 设置合理的置信度阈值（避免信息过载）
- ✅ 定期检查告警历史（评估质量）
- ❌ 不要在公共频道发送告警（避免泄露策略）

### 2. 安全措施

- ✅ 使用环境变量存储 Webhook URL（不提交到 Git）
- ✅ 定期更换 Webhook URL（如怀疑泄露）
- ✅ 限制 Discord 频道权限（只允许信任的成员）
- ❌ 不要在代码中硬编码 Webhook URL

### 3. 性能优化

- ✅ 使用合理的速率限制（避免被 Discord 限速）
- ✅ 监控系统资源使用（CPU、内存、网络）
- ✅ 定期清理历史数据（避免存储膨胀）
- ❌ 不要同时运行多个监控实例

---

## 📞 获取帮助

如果在配置过程中遇到问题：

1. **查看故障排查部分**（本文档）
2. **运行诊断命令**：
   ```bash
   python -c "from config.settings import CONFIG_DISCORD; import os; print('Discord 配置检查:'); print('Enabled:', CONFIG_DISCORD['enabled']); print('Webhook URL:', 'SET' if os.getenv('DISCORD_WEBHOOK_URL') or CONFIG_DISCORD['webhook_url'] else 'NOT SET')"
   ```
3. **查看详细日志**：
   ```bash
   python alert_monitor.py --symbol DOGE/USDT --verbose
   ```
4. **测试单个组件**：
   ```bash
   # 测试 Discord 连接
   python test_discord_webhook.py

   # 测试 Phase 2 处理
   python test_discord_simulation.py

   # 测试 WebSocket 连接
   python test_websocket.py
   ```

---

## 🎉 总结

**你现在拥有的完整系统**：

1. ✅ **Phase 2 多信号综合判断系统**
   - 信号融合、置信度调整、冲突解决、综合建议

2. ✅ **Discord 实时告警系统**
   - Bundle 格式化、速率限制、错误处理

3. ✅ **完整的配置工具链**
   - 自动向导、测试脚本、模拟测试、文档

4. ✅ **生产级别的监控能力**
   - 实时 WebSocket、信号检测、智能告警

**只需完成 3 步配置**：
1. 创建 Discord Webhook（2 分钟）
2. 设置环境变量（1 分钟）
3. 启用 Discord（1 分钟）

**然后享受**：
- 📱 手机推送实时告警
- 🎯 智能 Bundle 综合建议
- 📊 详细信号分析报告
- 🚀 高质量交易信号

---

**配置完成后，你将拥有一个完全自动化的加密货币交易信号监控和告警系统！**

---

*文档版本: 1.0*
*创建日期: 2026-01-09*
*Flow Radar Phase 2 - Production Ready*
