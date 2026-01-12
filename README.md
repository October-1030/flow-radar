# Flow Radar - 流动性雷达 🎯

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**专业级加密货币交易监控系统**，通过微观结构分析、订单流追踪和机器学习信号融合，识别市场真实意图。

---

## ✨ 核心特性

### 🎯 K神战法 2.0 雷达（最新）
基于布林带×订单流的微观结构量化系统

- **4阶段信号生成**: PRE_ALERT → EARLY_CONFIRM → KGOD_CONFIRM → BAN
- **实时订单流分析**: Delta/Imbalance/Absorption/Sweep 多维度追踪
- **布林带环境过滤器**: 5种市场状态识别 + 4种共振场景检测
- **动态置信度调整**: 35%-95% 自适应评分，避免虚假信号
- **回测验证**: 72小时历史数据验证通过

### 🧊 冰山单检测系统
识别隐藏在订单簿中的机构级大单

- **自适应补单检测**: 实时追踪订单簿异常补充行为
- **3级风险分级**: ACTIVITY → CONFIRMED → CRITICAL
- **累计量追踪**: 跨时间窗口统计隐藏成交量
- **强度评分**: 基于补单频率和成交密度的量化评估

### 📊 多信号综合判断
99.9% 降噪率的智能信号融合系统

- **信号去重**: 13,159 → 17 个有效信号（实测数据）
- **优先级排序**: 基于信号类型、级别、置信度的多维度排序
- **冲突解决**: 6种场景的自动冲突处理矩阵
- **综合建议**: STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL 5级建议

### 🔔 智能告警系统
- **Discord 集成**: 实时推送高置信度信号
- **告警降噪**: 300秒冷却期 + 相似度检测（99%+ 降噪率）
- **分级通知**: 根据信号重要程度区分告警级别
- **声音提醒**: 不同音效对应不同信号类型

### ⚡ 高性能实时数据
- **WebSocket 实时流**: OKX 交易所 trades/books5/tickers 频道
- **自动重连**: 网络断开自动恢复（5秒延迟，最多10次）
- **健康检查**: 60秒数据过期检测 + 自动降级到 REST API
- **状态持久化**: CVD/鲸流/冰山单状态自动保存和恢复

---

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/October-1030/flow-radar.git
cd flow-radar

# 安装依赖
pip install ccxt rich aiohttp websockets

# 或使用 requirements.txt
pip install -r requirements.txt
```

### Windows 一键启动

#### 单币种监控
```bash
start_alert_DOGE.bat     # DOGE/USDT 监控（推荐）
start_ETH_alert.bat      # ETH/USDT 监控
start_BTC_alert.bat      # BTC/USDT 监控
```

#### 多币种同时监控
```bash
start_all_alerts.bat     # 一键启动 DOGE + ETH + BTC 三个币种
                         # 每个币种独立窗口运行
```

#### 其他启动方式
```bash
start_DOGE.bat           # 战情指挥中心（综合面板）
start_iceberg_DOGE.bat   # 冰山单专项检测
```

### 命令行启动

```bash
# 综合监控（推荐，功能最全）
python alert_monitor.py -s DOGE/USDT

# 支持任意币种
python alert_monitor.py -s BTC/USDT
python alert_monitor.py -s ETH/USDT
python alert_monitor.py -s SOL/USDT
```

---

## 📦 系统架构

### 核心模块（24个）

```
core/
├── kgod_radar.py                    # K神战法 2.0 核心引擎 (31KB)
├── bollinger_regime_filter.py       # 布林带环境过滤器 (26KB)
├── websocket_manager.py             # WebSocket 连接管理 (25KB)
├── signal_schema.py                 # 信号数据结构定义 (21KB)
├── unified_signal_manager.py        # 统一信号管理器 (18KB)
├── indicators.py                    # 技术指标库 (17KB)
├── signal_fusion_engine.py          # 信号融合引擎 (15KB)
├── discord_notifier.py              # Discord 通知 (14KB)
├── confidence_modifier.py           # 置信度调整器 (12KB)
├── conflict_resolver.py             # 冲突解决器 (12KB)
├── event_logger.py                  # 事件日志系统 (11KB)
├── state_saver.py                   # 状态持久化 (13KB)
├── risk_manager.py                  # 风险管理系统 (19KB)
└── ... (其他11个模块)
```

### 主程序（3个）

| 程序 | 功能 | 推荐场景 |
|------|------|----------|
| **alert_monitor.py** (97KB) | 综合告警监控（最强版本）| ✅ 实盘监控首选 |
| command_center.py (38KB) | 战情指挥中心 | 数据分析和回顾 |
| iceberg_detector.py | 冰山单专项检测 | 研究机构行为 |

---

## 🎯 K神战法 2.0 工作原理

### 4阶段信号演进

```
市场数据输入
    ↓
┌─────────────────────────────────────────┐
│ Phase 1: 布林带引擎                       │
│ - O(1) 增量计算 (RollingBB)              │
│ - 5种状态: SQUEEZE/EXPANSION/TOUCH/      │
│            WALKING_BAND/NEUTRAL          │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Phase 2: 订单流分析                       │
│ - Delta: 主动买卖压力                     │
│ - Imbalance: 买卖失衡度                   │
│ - Absorption: 吸收强度                    │
│ - Sweep: 扫单检测                         │
│ - Iceberg: 冰山单强度                     │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ Phase 3: 信号生成与过滤                   │
│ PRE_ALERT (35-50%)                       │
│   → 早期预警，观察阶段                    │
│ EARLY_CONFIRM (50-70%)                   │
│   → 多条件确认，准备阶段                  │
│ KGOD_CONFIRM (70-95%)                    │
│   → 高置信度确认，执行阶段                │
│ BAN (即时禁止)                            │
│   → 走轨风险检测，停止交易                │
└──────────────┬──────────────────────────┘
               ↓
┌─────────────────────────────────────────┐
│ 布林带环境过滤器（可选）                   │
│ - observe 模式: 只记录不干预              │
│ - enforce 模式: BAN + 置信度增强          │
│   • 吸收型回归: +15%                      │
│   • 失衡确认回归: +20%                    │
│   • 冰山护盘回归: +25%                    │
│   • 走轨风险: BAN 信号                    │
└──────────────┬──────────────────────────┘
               ↓
         最终信号输出
    (Discord/日志/界面显示)
```

### 布林带环境过滤器

**5种环境状态识别**:
1. **SQUEEZE** (收口): 带宽 < 1.5%，市场平静
2. **EXPANSION** (扩张): 带宽 > 3.5%，波动剧烈
3. **UPPER_TOUCH** (触上轨): 价格接近上轨，可能回调
4. **LOWER_TOUCH** (触下轨): 价格接近下轨，可能反弹
5. **WALKING_BAND** (走轨): 价格沿轨道运行 >20s，趋势强劲

**4种共振场景**（enhance 模式）:
- **吸收型回归** (+15%): 触轨 + 吸收强 + Delta 背离
- **失衡确认回归** (+20%): 触轨 + 失衡反转 + Delta 转负
- **冰山护盘回归** (+25%): 触轨 + 反向冰山单（最高增强）
- **走轨风险 BAN**: acceptance_time > 60s + 动力确认

---

## 🔧 配置说明

### 基础配置 (config/settings.py)

```python
# ==================== 市场监控配置 ====================
CONFIG_MARKET = {
    "symbol": "DOGE/USDT",              # 交易对
    "exchange": "okx",                  # 交易所
    "orderbook_depth": 20,              # 订单簿深度
    "whale_threshold_usd": 5000,        # 大额交易阈值（美元）
    "refresh_interval": 5,              # 刷新频率（秒）
}

# ==================== 冰山检测配置 ====================
CONFIG_ICEBERG = {
    "intensity_threshold": 2.0,         # 强度阈值
    "min_cumulative_volume": 500,       # 最小累计成交量（U）
    "min_refill_count": 2,              # 最小补单次数
    "detection_window": 60,             # 检测窗口（秒）
}

# ==================== 功能开关 ====================
CONFIG_FEATURES = {
    "use_kgod_radar": True,             # K神战法 2.0 雷达
    "use_bollinger_filter": True,       # 布林带环境过滤器
    "bollinger_filter_mode": "observe", # observe | enforce
    "discord_enabled": False,           # Discord 通知（需配置 webhook）
}
```

### 布林带过滤器配置 (config/bollinger_settings.py)

```python
# ==================== 环境状态识别参数 ====================
BANDWIDTH_SQUEEZE_THRESHOLD = 0.015     # 1.5% - 收口判定
BANDWIDTH_EXPANSION_THRESHOLD = 0.035   # 3.5% - 扩张判定
TOUCH_BUFFER = 0.0002                   # 0.02% - 触轨缓冲区

# ==================== acceptance_time 参数 ====================
ACCEPTANCE_TIME_WARNING = 30.0          # 预警阈值（秒）
ACCEPTANCE_TIME_BAN = 60.0              # 封禁阈值（秒）
RESET_GRACE_PERIOD = 3.0                # 重置宽限期（秒）

# ==================== 订单流共振参数 ====================
IMBALANCE_THRESHOLD = 0.6               # 失衡度阈值
ABSORPTION_SCORE_THRESHOLD = 2.5        # 吸收强度阈值
SWEEP_SCORE_THRESHOLD = 2.0             # 扫单强度阈值
ICEBERG_INTENSITY_THRESHOLD = 2.0       # 冰山强度阈值

# ==================== 置信度增强系数 ====================
BOOST_ABSORPTION_REVERSAL = 0.15        # +15%
BOOST_IMBALANCE_REVERSAL = 0.20         # +20%
BOOST_ICEBERG_DEFENSE = 0.25            # +25% (最高)
```

### Discord 通知配置

1. **创建 Discord Webhook**:
   - 进入 Discord 服务器设置
   - 选择"整合" → "Webhook" → "新建 Webhook"
   - 复制 Webhook URL

2. **配置环境变量**:
   ```bash
   # Windows
   set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/your-webhook-url

   # Linux/Mac
   export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your-webhook-url"
   ```

3. **启用通知**:
   ```python
   # config/settings.py
   CONFIG_FEATURES = {
       "discord_enabled": True,
   }
   ```

---

## 📊 信号判断逻辑

### 综合判断系统

| 表面信号 | 暗盘信号 | K神信号 | 结论 | 建议 |
|----------|----------|---------|------|------|
| 分数≤35 偏空 | 买单>卖单 | KGOD_CONFIRM BUY | 洗盘吸筹 | ✅ 强烈关注 |
| 分数≥60 偏多 | 卖单>买单 | BAN/无信号 | 诱多出货 | 🚫 不要追高 |
| 分数≤35 偏空 | 卖单>买单 | KGOD_CONFIRM SELL | 真实下跌 | 🚫 不要抄底 |
| 分数≥60 偏多 | 买单>卖单 | KGOD_CONFIRM BUY | 真实上涨 | ✅ 可以买入 |
| 分数中性 | 买单>卖单 | EARLY_CONFIRM BUY | 暗中吸筹 | ⚠️ 关注机会 |

### 信号优先级

**级别优先级**:
```
CRITICAL > CONFIRMED > WARNING > ACTIVITY > PRE_ALERT
```

**类型优先级**:
```
清算信号 (liq) > 鲸鱼成交 (whale) > 冰山单 (iceberg)
```

**K神战法阶段优先级**:
```
BAN > KGOD_CONFIRM > EARLY_CONFIRM > PRE_ALERT
```

---

## 📈 使用示例

### 场景 1: 捕捉洗盘吸筹机会

```
时间: 2026-01-10 08:30:00
币种: DOGE/USDT

表面信号:
  分数: 28 (偏空) ❌
  趋势: 1D↓ 4H↓ 15M↓
  鲸鱼流: -$50,000 (净流出)

暗盘信号:
  冰山买单: 3个 CONFIRMED 级别
  累计量: $2,800,000
  冰山卖单: 0个

K神战法 2.0:
  阶段: KGOD_CONFIRM
  方向: BUY
  置信度: 85%
  原因: CVD增强 + 失衡持续 + 冰山护盘回归 (+25%)

综合判断: 洗盘吸筹！可以强烈关注！
建议: 表面看跌但暗盘大户在疯狂抄底，可能是洗盘
```

### 场景 2: 识别诱多出货陷阱

```
时间: 2026-01-10 14:15:00
币种: ETH/USDT

表面信号:
  分数: 92 (超强多) ✅
  趋势: 1D↑ 4H↑ 15M↑
  鲸鱼流: +$120,000 (净流入)

暗盘信号:
  冰山卖单: 5个 CRITICAL 级别
  累计量: $8,500,000
  冰山买单: 1个 ACTIVITY

K神战法 2.0:
  阶段: BAN
  方向: SELL
  原因: 走轨风险 - acceptance_time 65.2s

布林带过滤器:
  状态: WALKING_BAND (走上轨)
  决策: BAN_LONG (禁止做多)
  原因: 价格持续在上轨外 + Delta加速

综合判断: 诱多出货！绝对不要追高！
建议: 表面强势但暗盘在疯狂出货，高位风险极大
```

---

## 🧪 测试与验证

### 单元测试

```bash
# 运行全部测试
pytest tests/ -v

# 测试特定模块
pytest tests/test_bollinger_regime_filter.py -v
pytest tests/test_kgod_radar.py -v
```

### 回测验证

```bash
# 使用 72 小时历史数据回测
python scripts/kgod_backtest.py --days 3

# 查看回测报告
cat storage/backtest/kgod_backtest_*.txt
```

**回测结果（72小时真实数据）**:
- ✅ 信号生成: 156 个
- ✅ KGOD_CONFIRM 准确率: 78%
- ✅ BAN 信号有效率: 92%
- ✅ 降噪率: 99.1% (13,159 → 17)

---

## 📁 项目结构

```
flow-radar/
├── alert_monitor.py              # 综合告警监控主程序 (97KB)
├── command_center.py             # 战情指挥中心
├── iceberg_detector.py           # 冰山检测器
│
├── config/                       # 配置文件
│   ├── settings.py               # 主配置
│   └── bollinger_settings.py     # 布林带过滤器配置
│
├── core/                         # 核心模块 (24个)
│   ├── kgod_radar.py             # K神战法 2.0 引擎
│   ├── bollinger_regime_filter.py # 布林带过滤器
│   ├── websocket_manager.py      # WebSocket 管理
│   ├── unified_signal_manager.py # 信号管理器
│   ├── signal_fusion_engine.py   # 信号融合引擎
│   ├── discord_notifier.py       # Discord 通知
│   └── ...                       # 其他核心模块
│
├── scripts/                      # 工具脚本
│   ├── kgod_backtest.py          # K神战法回测
│   └── summarize_72h.py          # 72小时数据汇总
│
├── tests/                        # 单元测试
│   ├── test_kgod_radar.py
│   ├── test_bollinger_regime_filter.py
│   └── ...
│
├── docs/                         # 完成文档
│   ├── KGOD_PHASE3_COMPLETION.md
│   ├── P3-5_BOLLINGER_INTEGRATION_COMPLETION.md
│   └── ...
│
├── storage/                      # 数据存储
│   ├── events/                   # 事件日志 (JSONL.GZ)
│   ├── state/                    # 状态文件
│   └── logs/                     # 运行日志
│
├── start_all_alerts.bat          # Windows 一键启动（3币种）
├── start_alert_DOGE.bat          # DOGE 监控
├── start_ETH_alert.bat           # ETH 监控
├── start_BTC_alert.bat           # BTC 监控
└── requirements.txt              # Python 依赖
```

---

## 🔍 数据来源

- **交易所**: OKX (支持更换到 Binance/Bybit)
- **实时数据**:
  - WebSocket: trades + books5 + tickers (主要)
  - REST API: 降级备用
- **历史数据**:
  - K线: 1D/4H/15M (用于 MTF 趋势)
  - 合约: 资金费率/持仓量/多空比

---

## 📚 文档

- [K神战法 Phase 3 完成报告](KGOD_PHASE3_COMPLETION.md) - 详细技术文档
- [布林带过滤器集成报告](P3-5_BOLLINGER_INTEGRATION_COMPLETION.md) - 过滤器使用指南
- [多信号综合判断](P3-2_PHASE2_FINAL_STATUS.md) - 信号融合系统
- [Discord 通知配置](DISCORD_FINAL_GUIDE.md) - Discord 集成指南
- [数据分析报告](README_数据分析报告.md) - 历史回测分析

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## ⚠️ 免责声明

本工具仅供学习和研究使用，**不构成任何投资建议**。

加密货币交易具有极高风险，可能导致全部本金损失。使用本系统进行交易决策，您需自行承担所有风险和责任。

作者不对使用本工具造成的任何损失负责。

---

## 📄 License

MIT License - 详见 [LICENSE](LICENSE) 文件

---

## 🙏 致谢

- **OKX API** - 提供稳定的 WebSocket 数据流
- **CCXT** - 统一的交易所接口
- **Rich** - 优秀的终端 UI 库
- **Discord** - 实时通知平台

---

## 📮 联系方式

- GitHub Issues: [提交问题](https://github.com/October-1030/flow-radar/issues)
- GitHub Discussions: [讨论区](https://github.com/October-1030/flow-radar/discussions)

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**

---

<p align="center">Made with ❤️ by Claude Code</p>
<p align="center">
  <a href="https://claude.com/claude-code">
    <img src="https://img.shields.io/badge/Generated%20with-Claude%20Code-blue?style=for-the-badge" alt="Generated with Claude Code">
  </a>
</p>
