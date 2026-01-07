# P3-2 多维度信号方案设计

**版本**: v1.1
**日期**: 2026-01-06
**状态**: 设计阶段 (不影响当前 72h 验证)
**依据**: 三方会谈第十六轮/十七轮/二十轮最终共识

## 修订历史

| 版本 | 日期 | 修订内容 | 依据 |
|------|------|---------|------|
| v1.1 | 2026-01-06 | 修正优先级规则：(level_rank, type_rank)，添加架构规范约束 | 三方会谈第二十轮共识 |
| v1.0 | 2026-01-05 | 初版设计文档 | 三方会谈第十六轮/十七轮共识 |

---

## 1. 统一信号架构

### 1.1 SignalEvent Schema v1

所有信号类型统一使用以下 Schema:

```json
{
  "type": "iceberg|whale|liq",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "side": "BUY|SELL",
  "level": "ACTIVITY|CONFIRMED|WARNING|CRITICAL",
  "key": "{type}:{symbol}:{side}:{level}:{bucket}",
  "data": {
    // 信号特定字段 (见各类型定义)
  },
  "confidence": 85.0,
  "related_signals": [
    "whale:DOGE/USDT:BUY:CONFIRMED:0.1508",
    "iceberg:DOGE/USDT:BUY:ACTIVITY:0.1508"
  ],
  "confidence_modifier": {
    "base": 70.0,
    "spoofing_penalty": -10.0,
    "related_boost": +25.0,
    "final": 85.0
  }
}
```

### 1.2 Key 结构规范

#### **Iceberg Key**
```
格式: iceberg:{symbol}:{side}:{level}:{price_bucket}
示例: iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508
```
- `price_bucket`: 价格4位小数分桶 (round(price, 4))
- `level`: ACTIVITY | CONFIRMED

#### **Whale Trade Key**
```
格式: whale:{symbol}:{side}:{level}:{time_bucket}
示例: whale:DOGE/USDT:BUY:CONFIRMED:2026-01-05T01:30
```
- `time_bucket`: 5分钟时间窗口 (ISO 8601, 精确到分钟, 向下取整到5分钟)
- `level`: ACTIVITY (单笔) | CONFIRMED (聚合)

#### **Liquidation Key**
```
格式: liq:{symbol}:{side}:{level}:market
示例: liq:DOGE/USDT:SELL:CRITICAL:market
```
- `level`: INFO | WARNING | CRITICAL
- 固定使用 `market` 作为 bucket (清算为市价单)

### 1.3 与现有 Iceberg 的解耦设计

```python
# 现有代码 (不改动)
class IcebergDetector:
    """冰山检测器 - 独立模块"""
    def detect(self, orderbook, trades) -> List[IcebergSignal]:
        ...

# 新增代码 (独立检测器)
class WhaleTradeDetector:
    """大额成交检测器 - 独立模块"""
    def detect(self, trades) -> List[WhaleSignal]:
        ...

class LiquidationMonitor:
    """清算监控器 - 独立模块"""
    def detect(self, liquidations) -> List[LiquidationSignal]:
        ...

# 统一信号管理器 (不影响现有逻辑)
class UnifiedSignalManager:
    """
    统一信号管理器 - Phase 1 仅做信号聚合和关联

    不改动现有检测逻辑，只负责:
    1. 从各检测器收集信号
    2. 构建 related_signals 关系
    3. 统一输出格式
    """
    def __init__(self):
        self.iceberg_detector = IcebergDetector()  # 现有
        self.whale_detector = WhaleTradeDetector()  # 新增
        self.liq_monitor = LiquidationMonitor()     # 新增

    def collect_all_signals(self, data):
        """收集所有类型信号 - 不影响现有检测"""
        icebergs = self.iceberg_detector.detect(...)
        whales = self.whale_detector.detect(...)
        liqs = self.liq_monitor.detect(...)

        return self._build_unified_signals(icebergs, whales, liqs)
```

**解耦原则**:
- ✅ 各检测器独立运行，互不干扰
- ✅ 现有冰山检测逻辑不变 (P0-P1-P2 改进保持)
- ✅ UnifiedSignalManager 作为可选层，不影响单独使用

---

## 2. 大额成交信号 (Whale Trade)

### 2.1 检测逻辑

#### **单笔阈值模式 (ACTIVITY)**
```python
CONFIG_WHALE = {
    "single_threshold_usd": 50000,  # 5万U单笔
    "time_window": 300,             # 5分钟窗口
}

def detect_single_whale(trade):
    """检测单笔大额成交"""
    value = trade['price'] * trade['quantity']
    if value >= CONFIG_WHALE['single_threshold_usd']:
        return WhaleSignal(
            level='ACTIVITY',
            side='BUY' if not trade['is_buyer_maker'] else 'SELL',
            price=trade['price'],
            volume=trade['quantity'],
            value_usd=value
        )
```

#### **聚合阈值模式 (CONFIRMED)**
```python
CONFIG_WHALE = {
    "aggregated_threshold_usd": 200000,  # 20万U聚合
    "aggregated_count": 3,               # 至少3笔
    "time_window": 300,                  # 5分钟窗口
}

def detect_aggregated_whale(trades, time_bucket):
    """检测5分钟内聚合大额成交"""
    buy_value = sum(t['price'] * t['quantity']
                    for t in trades if not t['is_buyer_maker'])
    sell_value = sum(t['price'] * t['quantity']
                     for t in trades if t['is_buyer_maker'])
    buy_count = sum(1 for t in trades if not t['is_buyer_maker'])
    sell_count = sum(1 for t in trades if t['is_buyer_maker'])

    signals = []
    if buy_value >= CONFIG_WHALE['aggregated_threshold_usd'] \
       and buy_count >= CONFIG_WHALE['aggregated_count']:
        signals.append(WhaleSignal(
            level='CONFIRMED',
            side='BUY',
            price_range=(min_price, max_price),  # 用于联动分析
            volume=total_buy_volume,
            value_usd=buy_value,
            trade_count=buy_count
        ))

    # 同理处理 SELL
    return signals
```

### 2.2 阈值策略

#### **静态配置 (Phase 1)**
```python
# config/settings.py
CONFIG_WHALE = {
    # 静态阈值 (基于 DOGE 市值)
    "single_threshold_usd": 50000,       # 单笔5万U
    "aggregated_threshold_usd": 200000,  # 聚合20万U

    # 分级阈值 (未来扩展)
    "tiers": {
        "small_whale": 50000,   # 5万-20万
        "medium_whale": 200000, # 20万-100万
        "large_whale": 1000000, # 100万+
    }
}
```

#### **动态分位数 (Phase 2 扩展)**
```python
# 未来扩展 - 基于历史分位数自适应
class DynamicWhaleThreshold:
    """
    动态阈值引擎 - 参考现有 DynamicThresholdEngine

    Phase 2 实现:
    - 统计24小时交易额分布
    - P99 作为单笔阈值
    - P99.5 作为聚合阈值
    """
    def __init__(self, window_hours=24):
        self.trade_values = []  # 滑动窗口

    def get_threshold(self, percentile=99):
        """获取动态阈值"""
        if len(self.trade_values) < 1000:
            return CONFIG_WHALE['single_threshold_usd']
        return np.percentile(self.trade_values, percentile)
```

### 2.3 Key 使用与联动分析

#### **Key 结构**
```python
key = f"whale:{symbol}:{side}:{level}:{time_bucket}"

# 示例
"whale:DOGE/USDT:BUY:CONFIRMED:2026-01-05T01:30"
```

#### **Data 字段含 price_range**
```json
{
  "type": "whale",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "side": "BUY",
  "level": "CONFIRMED",
  "key": "whale:DOGE/USDT:BUY:CONFIRMED:2026-01-05T01:30",
  "data": {
    "price_range": [0.15050, 0.15120],  // 最低-最高价
    "avg_price": 0.15080,
    "total_volume": 1500000,
    "total_value_usd": 226200,
    "trade_count": 5
  },
  "confidence": 80.0
}
```

#### **与冰山信号关联**

**场景**: 同一价格区间出现鲸鱼成交 + 冰山买单 → 高置信度吸筹信号

```python
def find_related_signals(whale_signal, iceberg_signals):
    """
    Phase 1: 关联展示逻辑

    在 related_signals 数组中填充关联信号的 key
    """
    related = []

    # 检查价格区间重叠
    for ice in iceberg_signals:
        if (ice.side == whale_signal.side and
            whale_signal.price_range[0] <= ice.price <= whale_signal.price_range[1]):
            related.append(ice.key)

    return related

# 输出示例
{
  "type": "whale",
  "key": "whale:DOGE/USDT:BUY:CONFIRMED:2026-01-05T01:30",
  "related_signals": [
    "iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508",
    "iceberg:DOGE/USDT:BUY:ACTIVITY:0.1505"
  ],
  "confidence_modifier": {
    "base": 70.0,
    "related_boost": +15.0,  // 有关联冰山，提升置信度
    "final": 85.0
  }
}
```

---

## 3. 清算提醒信号 (Liquidation)

### 3.1 数据来源

#### **优先级 1: OKX WebSocket (实时流)**
```python
# OKX Liquidation Channel
ws_url = "wss://ws.okx.com:8443/ws/v5/public"
subscribe_msg = {
    "op": "subscribe",
    "args": [{
        "channel": "liquidation-orders",
        "instType": "SWAP",
        "instId": "DOGE-USDT-SWAP"
    }]
}

# 预期消息格式
{
  "arg": {"channel": "liquidation-orders", "instId": "DOGE-USDT-SWAP"},
  "data": [{
    "instId": "DOGE-USDT-SWAP",
    "side": "sell",  // 清算卖单 = 多头爆仓
    "posSide": "long",
    "bkPx": "0.1502",  // 破产价
    "sz": "100000",    // 清算量
    "bkLoss": "150.5", // 亏损额
    "ts": "1735523180086"
  }]
}
```

#### **优先级 2: OKX REST API (轮询降级)**
```python
# 如果 WebSocket 不可用，降级到 REST
# Endpoint: GET /api/v5/public/liquidation-orders
# Params: instType=SWAP, instId=DOGE-USDT-SWAP, limit=100

async def fetch_liquidations_rest(symbol):
    """REST API 降级获取清算数据"""
    url = "https://www.okx.com/api/v5/public/liquidation-orders"
    params = {
        "instType": "SWAP",
        "instId": f"{symbol.replace('/', '-')}-SWAP",
        "limit": 100
    }
    # 每30秒轮询一次
```

#### **优先级 3: 降级处理 (接口变动容错)**
```python
class LiquidationMonitor:
    """清算监控器 - 多级降级策略"""

    def __init__(self):
        self.data_source = 'websocket'  # websocket | rest | unavailable
        self.last_fetch_time = 0

    async def get_liquidations(self):
        """获取清算数据 - 带降级"""
        try:
            if self.data_source == 'websocket':
                return await self._fetch_ws()
        except Exception as e:
            console.print(f"[yellow]WebSocket 失败，降级到 REST: {e}[/yellow]")
            self.data_source = 'rest'

        try:
            if self.data_source == 'rest':
                return await self._fetch_rest()
        except Exception as e:
            console.print(f"[yellow]REST 失败，清算监控不可用: {e}[/yellow]")
            self.data_source = 'unavailable'

        return []  # 降级到空数据
```

### 3.2 触发条件

#### **单事件阈值**
```python
CONFIG_LIQUIDATION = {
    # 单笔清算阈值
    "single_threshold_usd": 100000,  # 10万U

    # 分级阈值
    "levels": {
        "info": 50000,      # 5万-10万: INFO
        "warning": 100000,  # 10万-50万: WARNING
        "critical": 500000, # 50万+: CRITICAL
    }
}

def classify_liquidation(liq):
    """分级清算信号"""
    value = float(liq['sz']) * float(liq['bkPx'])

    if value >= CONFIG_LIQUIDATION['levels']['critical']:
        return 'CRITICAL'
    elif value >= CONFIG_LIQUIDATION['levels']['warning']:
        return 'WARNING'
    elif value >= CONFIG_LIQUIDATION['levels']['info']:
        return 'INFO'
    else:
        return None  # 忽略小额清算
```

#### **速率事件 (聚合检测)**
```python
CONFIG_LIQUIDATION = {
    # 速率阈值
    "rate_window": 60,        # 1分钟窗口
    "rate_threshold_usd": 500000,  # 50万U/分钟
    "rate_count": 10,         # 至少10笔清算
}

class LiquidationRateDetector:
    """清算速率检测器"""

    def __init__(self):
        self.recent_liqs = []  # (timestamp, value, side)

    def detect_cascade(self, current_ts):
        """
        检测清算连锁反应

        条件:
        1. 1分钟内至少10笔清算
        2. 总额超过50万U
        3. 同一方向 (多头爆仓 or 空头爆仓)
        """
        window_start = current_ts - CONFIG_LIQUIDATION['rate_window']

        # 过滤窗口内的清算
        window_liqs = [l for l in self.recent_liqs if l[0] >= window_start]

        if len(window_liqs) < CONFIG_LIQUIDATION['rate_count']:
            return None

        # 按方向分组
        long_liq = sum(v for ts, v, s in window_liqs if s == 'long')
        short_liq = sum(v for ts, v, s in window_liqs if s == 'short')

        if long_liq >= CONFIG_LIQUIDATION['rate_threshold_usd']:
            return LiquidationSignal(
                level='CRITICAL',
                side='SELL',  # 多头爆仓 → 卖压
                event_type='cascade',
                total_value=long_liq,
                count=len([l for l in window_liqs if l[2] == 'long'])
            )

        if short_liq >= CONFIG_LIQUIDATION['rate_threshold_usd']:
            return LiquidationSignal(
                level='CRITICAL',
                side='BUY',  # 空头爆仓 → 买压
                event_type='cascade',
                total_value=short_liq,
                count=len([l for l in window_liqs if l[2] == 'short'])
            )

        return None
```

### 3.3 告警级别分层

```python
class LiquidationSignal:
    """清算信号"""

    # 告警级别定义
    LEVEL_INFO = 'INFO'          # 常规清算，记录但不告警
    LEVEL_WARNING = 'WARNING'    # 中型清算，控制台提示
    LEVEL_CRITICAL = 'CRITICAL'  # 大型清算或连锁，Discord 告警

    def __init__(self, level, side, event_type, total_value, count=1):
        self.level = level
        self.side = side
        self.event_type = event_type  # 'single' | 'cascade'
        self.total_value = total_value
        self.count = count
        self.key = self._make_key()

    def _make_key(self):
        """生成 key: liq:symbol:side:level:market"""
        return f"liq:{symbol}:{self.side}:{self.level}:market"

    def should_discord_notify(self):
        """判断是否发送 Discord 通知"""
        return self.level in ['WARNING', 'CRITICAL']
```

**告警消息示例**:

```
INFO (控制台):
📊 清算 | DOGE/USDT | 多头爆仓 75,000U

WARNING (控制台 + Discord):
⚠️ 清算警告 | DOGE/USDT
🔴 多头爆仓 250,000U @ $0.1502
可能引发连锁反应

CRITICAL (控制台 + Discord + 声音):
🚨 清算连锁 | DOGE/USDT
🔴 多头爆仓 520,000U (12笔/分钟)
⚠️ 建议暂避风险
```

---

## 4. 多信号架构

### 4.1 信号优先级

#### **优先级定义 (修正版 - 三方会谈第二十轮共识)**

**核心规则**: 优先级 sort_key = (level_rank, type_rank)
- **先按 level 排序，再按 type 排序**
- 示例: CRITICAL Iceberg > INFO Liquidation (level 优先于 type)

**level_rank 枚举映射** (越小优先级越高):
```python
LEVEL_PRIORITY = {
    'CRITICAL': 1,   # 最高优先 - 严重事件
    'CONFIRMED': 2,  # 已确认信号
    'WARNING': 3,    # 警告级别
    'ACTIVITY': 4,   # 观察级别
    'INFO': 5,       # 最低优先 - 信息记录
}
```

**type_rank 枚举映射** (同 level 时才比较):
```python
TYPE_PRIORITY = {
    'liq': 1,      # 清算 - 市场风险最高
    'whale': 2,    # 鲸鱼成交 - 真实资金流
    'iceberg': 3,  # 冰山订单 - 需验证确认
}
```

**比较器实现**:
```python
def signal_priority(signal):
    """
    计算信号综合优先级 (修正版)

    返回: (level_rank, type_rank)
    排序逻辑:
    1. 先比较 level: CRITICAL(1) > CONFIRMED(2) > ... > INFO(5)
    2. level 相同时比较 type: liq(1) > whale(2) > iceberg(3)

    示例排序结果:
    - (1, 3) CRITICAL Iceberg    排第1
    - (1, 1) CRITICAL Liquidation 排第2 (同 CRITICAL，但 type 更高)
    - (2, 1) CONFIRMED Liquidation 排第3
    - (5, 1) INFO Liquidation     排最后
    """
    return (
        LEVEL_PRIORITY.get(signal['level'], 99),
        TYPE_PRIORITY.get(signal['type'], 99)
    )

# 使用示例
signals.sort(key=signal_priority)  # 最高优先级排在前面
```

**架构要求**:
1. **配置外部化**: level_rank 和 type_rank 映射定义在 `config/settings.py`
2. **比较逻辑原子化**: 封装在 `core/utils.py::compare_signal_priority()` 或 `UnifiedSignalManager`
3. **严禁重复**: 不同检测器中禁止重写排序逻辑

#### **优先级场景 (修正版)**

**场景 1: level 优先，type 次之**
```python
# 同时出现 3 种信号，不同 level
signals = [
    iceberg_signal(level='CONFIRMED', confidence=85),  # (2, 3)
    whale_signal(level='CONFIRMED', confidence=80),    # (2, 2)
    liq_signal(level='WARNING', confidence=90)         # (3, 1)
]

# 排序后顺序 (先比较 level，再比较 type)
# 1. iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508     (2, 3) ← level=CONFIRMED 最高
# 2. whale:DOGE/USDT:BUY:CONFIRMED:01:30        (2, 2) ← 同 CONFIRMED，type 更高
# 3. liq:DOGE/USDT:SELL:WARNING:market          (3, 1) ← level=WARNING 较低
```

**场景 2: CRITICAL level 压倒一切**
```python
# CRITICAL 级别的冰山 > 其他任何信号
signals = [
    iceberg_signal(level='CRITICAL', confidence=95),   # (1, 3)
    liq_signal(level='WARNING', confidence=90),        # (3, 1)
    whale_signal(level='CONFIRMED', confidence=85)     # (2, 2)
]

# 排序后顺序
# 1. iceberg CRITICAL   (1, 3) ← CRITICAL 级别最高，虽然 type 最低
# 2. whale CONFIRMED    (2, 2)
# 3. liq WARNING        (3, 1)
```

**场景 3: 同 level 时按 type 排序**
```python
# 都是 CONFIRMED 级别，按 type 区分
signals = [
    iceberg_signal(level='CONFIRMED', confidence=85),  # (2, 3)
    whale_signal(level='CONFIRMED', confidence=80),    # (2, 2)
    liq_signal(level='CONFIRMED', confidence=90)       # (2, 1) [假设清算也有CONFIRMED]
]

# 排序后顺序 (level 相同，比较 type)
# 1. liq CONFIRMED      (2, 1) ← type=liq 最高
# 2. whale CONFIRMED    (2, 2) ← type=whale 次之
# 3. iceberg CONFIRMED  (2, 3) ← type=iceberg 最低
```

### 4.2 Bundle Alert 设计

#### **时间窗口聚合 (500ms)**
```python
CONFIG_BUNDLE = {
    "window_ms": 500,  # 500毫秒窗口
    "max_signals": 5,  # 最多合并5个信号
}

class BundleAlertManager:
    """Bundle Alert 管理器 - Phase 1 实现"""

    def __init__(self):
        self.pending_signals = []  # (timestamp, signal)
        self.last_flush_time = 0

    def add_signal(self, signal, timestamp):
        """添加信号到待发送队列"""
        self.pending_signals.append((timestamp, signal))

        # 检查是否应该立即刷新
        if self._should_flush(timestamp):
            self.flush_bundle(timestamp)

    def _should_flush(self, current_ts):
        """判断是否刷新 bundle"""
        if not self.pending_signals:
            return False

        # 最早信号的时间
        earliest_ts = self.pending_signals[0][0]

        # 超过 500ms 窗口
        if (current_ts - earliest_ts) * 1000 >= CONFIG_BUNDLE['window_ms']:
            return True

        # 信号数达到上限
        if len(self.pending_signals) >= CONFIG_BUNDLE['max_signals']:
            return True

        return False

    def flush_bundle(self, current_ts):
        """
        刷新 Bundle，生成 Discord 增强卡片

        Phase 1: 只合并相同 symbol 的信号
        """
        if not self.pending_signals:
            return

        # 按 symbol 分组
        by_symbol = {}
        for ts, sig in self.pending_signals:
            sym = sig['symbol']
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(sig)

        # 为每个 symbol 生成 Bundle
        for symbol, signals in by_symbol.items():
            self._send_bundle_discord(symbol, signals)

        # 清空队列
        self.pending_signals = []
        self.last_flush_time = current_ts
```

#### **Discord 增强卡片格式**

**单信号卡片 (现有格式)**:
```json
{
  "title": "📈 BUY | DOGE/USDT",
  "description": "检测到冰山买单，置信度 85%",
  "color": 0x00FF00,
  "fields": [
    {"name": "💰 价格", "value": "$0.150800"},
    {"name": "🎯 置信度", "value": "85%"}
  ]
}
```

**Bundle 卡片 (多信号合并)**:
```json
{
  "title": "🔥 多信号联动 | DOGE/USDT",
  "description": "检测到 3 种信号同时出现，高置信度机会",
  "color": 0xFF6600,  // 橙色 - 多信号特殊颜色
  "fields": [
    {
      "name": "🚨 清算信号",
      "value": "⚠️ 多头爆仓 250,000U @ $0.1502",
      "inline": false
    },
    {
      "name": "🐋 鲸鱼成交",
      "value": "✓ 买入 226,200U (5笔) @ $0.1505-0.1512",
      "inline": false
    },
    {
      "name": "🧊 冰山买单",
      "value": "✓ 确认 @ $0.1508, 累计 8,500 DOGE",
      "inline": false
    },
    {
      "name": "📊 综合置信度",
      "value": "92%",
      "inline": true
    },
    {
      "name": "🎯 操作建议",
      "value": "强烈关注，多方力量显著",
      "inline": true
    }
  ],
  "footer": {"text": "Flow Radar • Bundle Alert"}
}
```

**Bundle 生成逻辑**:
```python
def _send_bundle_discord(self, symbol, signals):
    """
    生成 Bundle Discord 卡片

    Phase 1: 简单列举所有信号
    Phase 2: 智能判断信号关系，给出综合建议
    """
    # 按优先级排序
    signals.sort(key=signal_priority)

    # 构建 Embed
    embed = {
        "title": f"🔥 多信号联动 | {symbol}",
        "description": f"检测到 {len(signals)} 种信号同时出现",
        "color": 0xFF6600,  # 橙色
        "fields": []
    }

    # 添加每个信号的字段
    for sig in signals:
        field = self._signal_to_field(sig)
        embed["fields"].append(field)

    # 计算综合置信度 (加权平均)
    total_conf = sum(s['confidence'] * TYPE_PRIORITY[s['type']]
                     for s in signals)
    weight_sum = sum(TYPE_PRIORITY[s['type']] for s in signals)
    avg_conf = total_conf / weight_sum if weight_sum > 0 else 50

    embed["fields"].append({
        "name": "📊 综合置信度",
        "value": f"{avg_conf:.0f}%",
        "inline": True
    })

    # 发送
    asyncio.create_task(self.discord.send_embed(embed))

def _signal_to_field(self, signal):
    """将信号转换为 Discord field"""
    if signal['type'] == 'iceberg':
        return {
            "name": "🧊 冰山买单" if signal['side'] == 'BUY' else "🧊 冰山卖单",
            "value": f"{'✓' if signal['level'] == 'CONFIRMED' else '?'} "
                     f"@ ${signal['data']['price']:.6f}, "
                     f"累计 {signal['data']['cumulative_volume']:.0f}",
            "inline": False
        }
    elif signal['type'] == 'whale':
        return {
            "name": "🐋 鲸鱼成交",
            "value": f"{'买入' if signal['side'] == 'BUY' else '卖出'} "
                     f"{signal['data']['total_value_usd']:,.0f}U "
                     f"({signal['data']['trade_count']}笔)",
            "inline": False
        }
    elif signal['type'] == 'liq':
        return {
            "name": "🚨 清算信号",
            "value": f"{'多头' if signal['side'] == 'SELL' else '空头'}爆仓 "
                     f"{signal['data']['total_value']:,.0f}U",
            "inline": False
        }
```

### 4.3 节流策略适配

#### **按 type 隔离节流**
```python
def _make_throttle_key(self, signal):
    """
    生成节流 key (含 type 字段)

    Phase 1: 使用 signal.key 作为节流 key
    不同类型信号的节流状态独立管理
    """
    return signal['key']

# 示例
throttle_keys = {
    "iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508": {...},
    "whale:DOGE/USDT:BUY:CONFIRMED:2026-01-05T01:30": {...},
    "liq:DOGE/USDT:SELL:WARNING:market": {...}
}
# 三种信号互不干扰
```

#### **复用现有 throttle 引擎**
```python
# 现有节流逻辑 (alert_monitor.py:528-609)
def _is_alert_throttled(
    self, level, message,
    side=None, price=None,
    iceberg_level=None,
    prev_iceberg_level=None
) -> bool:
    """
    P2-3.1: 检查告警是否被节流

    Phase 1 扩展:
    - 添加 signal_type 参数
    - 使用 signal.key 替代手动拼接
    """
    # 直接使用 signal['key']
    alert_key = signal['key']

    # 其余逻辑不变
    ...
```

#### **Bundle Alert 的节流处理**

**问题**: Bundle 包含多个信号，如何节流？

**方案**: Bundle 本身不节流，但构成 Bundle 的各信号分别节流

```python
def flush_bundle(self, current_ts):
    """刷新 Bundle - 带节流检查"""
    if not self.pending_signals:
        return

    # 过滤已被节流的信号
    valid_signals = []
    for ts, sig in self.pending_signals:
        if not self._is_signal_throttled(sig):
            valid_signals.append(sig)

    # 如果过滤后还有信号，才发送 Bundle
    if valid_signals:
        if len(valid_signals) == 1:
            # 只剩1个信号，发送单信号卡片
            self._send_single_signal(valid_signals[0])
        else:
            # 多个信号，发送 Bundle 卡片
            self._send_bundle_discord(symbol, valid_signals)

    self.pending_signals = []

def _is_signal_throttled(self, signal):
    """检查单个信号是否被节流"""
    # 复用现有 _is_alert_throttled 逻辑
    return self._alert_throttle_manager.is_throttled(signal['key'])
```

### 4.4 多信号冲突处理规则

#### **冲突场景定义**

**场景 1: 方向冲突**
```python
# 同时出现买卖信号
signals = [
    iceberg_signal(side='BUY', confidence=85),
    whale_signal(side='SELL', confidence=80)
]

# 处理规则: 高优先级优先
# whale (type_priority=2) > iceberg (type_priority=3)
# → 采信 whale SELL 信号
```

**场景 2: 级别冲突**
```python
# 同一类型不同级别
signals = [
    iceberg_signal(level='ACTIVITY', confidence=60),
    iceberg_signal(level='CONFIRMED', confidence=85)
]

# 处理规则: 高级别覆盖低级别
# CONFIRMED > ACTIVITY
# → 采信 CONFIRMED 信号，忽略 ACTIVITY
```

**场景 3: 时间冲突**
```python
# 短时间内多次同类信号
signals = [
    whale_signal(ts=1735523180, side='BUY'),
    whale_signal(ts=1735523200, side='BUY'),  # 20秒后
]

# 处理规则: 节流机制处理
# 第二个信号会被节流拦截
```

#### **冲突解决矩阵**

| 信号1 类型 | 信号1 方向 | 信号2 类型 | 信号2 方向 | 解决策略 |
|---------|--------|---------|--------|---------|
| liq | SELL | whale | BUY | ⚠️ 警告: 清算卖压 vs 鲸鱼买入，观望 |
| liq | SELL | iceberg | BUY | ✅ 正常: 清算引发抄底，关注冰山 |
| whale | BUY | iceberg | BUY | ✅ 增强: 同向信号，提升置信度 |
| whale | BUY | iceberg | SELL | ⚠️ 冲突: 按优先级采信 whale |
| iceberg | BUY | iceberg | SELL | ⚠️ 博弈: 多空均衡，降低置信度 |

#### **冲突处理代码**

```python
class ConflictResolver:
    """信号冲突解决器"""

    def resolve(self, signals):
        """
        解决信号冲突

        返回: (primary_signal, conflict_warning)
        """
        if len(signals) <= 1:
            return signals[0] if signals else None, None

        # 按优先级排序
        signals.sort(key=signal_priority)
        primary = signals[0]

        # 检查方向冲突
        sides = set(s['side'] for s in signals)
        if len(sides) > 1:
            # 方向不一致
            warning = self._build_conflict_warning(signals)
            return primary, warning

        # 方向一致，增强置信度
        primary['confidence_modifier']['related_boost'] = +15.0
        primary['confidence'] += 15.0

        return primary, None

    def _build_conflict_warning(self, signals):
        """构建冲突警告"""
        types = [s['type'] for s in signals]
        sides = [s['side'] for s in signals]

        return {
            "type": "conflict",
            "message": f"信号方向冲突: {types} {sides}",
            "recommendation": "建议观望，等待方向明确"
        }
```

---

## 5. 历史数据回放接口

### 5.1 回放数据格式定义

#### **输入格式 (与事件日志兼容)**
```python
# 现有 EventLogger 格式 (core/event_logger.py)
# 直接复用 JSONL.gz 格式

# 回放文件: storage/events/DOGE_USDT_2026-01-05.jsonl.gz
{
  "type": "orderbook|trades|state|iceberg|whale|liq",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "data": {...}
}
```

#### **扩展字段 (Phase 2)**
```python
# 为回放添加 ground_truth 标注
{
  "type": "iceberg",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "data": {...},

  # 回放专用字段
  "replay_metadata": {
    "ground_truth": "HIT",  // HIT | MISS | UNCERTAIN
    "annotator": "human",
    "annotation_time": 1735530000,
    "price_change_15m": +2.5  // 15分钟后价格变化 (%)
  }
}
```

### 5.2 离线评估方法

#### **回放引擎设计**
```python
class SignalReplayer:
    """
    多信号回放引擎

    用途:
    1. 回放历史事件流，验证检测逻辑
    2. 计算信号准确率 (precision, recall)
    3. 优化阈值参数
    """

    def __init__(self, event_file):
        self.replayer = EventReplayer(event_file)
        self.detectors = {
            'iceberg': IcebergDetector(),
            'whale': WhaleTradeDetector(),
            'liq': LiquidationMonitor()
        }
        self.results = {
            'iceberg': {'TP': 0, 'FP': 0, 'FN': 0},
            'whale': {'TP': 0, 'FP': 0, 'FN': 0},
            'liq': {'TP': 0, 'FP': 0, 'FN': 0}
        }

    def replay(self):
        """回放事件流"""
        for event in self.replayer.replay():
            # 根据事件类型路由
            if event['type'] == 'orderbook':
                self._process_orderbook(event)
            elif event['type'] == 'trades':
                self._process_trades(event)
            # ...

    def _process_orderbook(self, event):
        """处理订单簿事件 - 触发冰山检测"""
        icebergs = self.detectors['iceberg'].detect(
            orderbook=event['data'],
            timestamp=event['ts']
        )

        # 如果有 ground_truth，进行评估
        for ice in icebergs:
            self._evaluate_signal('iceberg', ice, event)

    def _evaluate_signal(self, sig_type, signal, event):
        """
        评估信号准确性

        TP (True Positive): 检测到 + 标注为 HIT
        FP (False Positive): 检测到 + 标注为 MISS
        FN (False Negative): 未检测到 + 标注为 HIT
        """
        ground_truth = event.get('replay_metadata', {}).get('ground_truth')

        if ground_truth == 'HIT':
            self.results[sig_type]['TP'] += 1
        elif ground_truth == 'MISS':
            self.results[sig_type]['FP'] += 1
        # UNCERTAIN 不计入评估

    def calculate_metrics(self):
        """计算评估指标"""
        metrics = {}
        for sig_type, counts in self.results.items():
            tp = counts['TP']
            fp = counts['FP']
            fn = counts['FN']

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

            metrics[sig_type] = {
                'precision': precision,
                'recall': recall,
                'f1': f1,
                'samples': tp + fp + fn
            }

        return metrics
```

#### **评估报告格式**
```python
# 输出示例
{
  "replay_file": "storage/events/DOGE_USDT_2026-01-05.jsonl.gz",
  "time_range": ["2026-01-05 00:00:00", "2026-01-05 23:59:59"],
  "metrics": {
    "iceberg": {
      "precision": 0.75,  // 75% 准确率
      "recall": 0.60,     // 60% 召回率
      "f1": 0.67,
      "samples": 20
    },
    "whale": {
      "precision": 0.85,
      "recall": 0.70,
      "f1": 0.77,
      "samples": 15
    },
    "liq": {
      "precision": 0.90,
      "recall": 0.80,
      "f1": 0.85,
      "samples": 10
    }
  },
  "confusion_matrix": {
    "iceberg": {
      "TP": 12, "FP": 4, "FN": 4
    }
  }
}
```

#### **参数优化接口 (Phase 2 扩展)**
```python
class ThresholdOptimizer:
    """
    阈值优化器

    用途: 通过回放历史数据，找到最优阈值
    """

    def optimize(self, event_file, param_ranges):
        """
        网格搜索最优参数

        Args:
            event_file: 回放文件
            param_ranges: 参数范围
                {
                    'whale.single_threshold_usd': [30000, 50000, 100000],
                    'iceberg.depletion_ratio': [0.1, 0.2, 0.3]
                }

        Returns:
            best_params: 最优参数组合
            best_f1: 最高 F1 分数
        """
        best_params = None
        best_f1 = 0

        # 网格搜索
        for params in self._generate_param_grid(param_ranges):
            # 应用参数
            self._apply_params(params)

            # 回放评估
            replayer = SignalReplayer(event_file)
            replayer.replay()
            metrics = replayer.calculate_metrics()

            # 计算综合 F1
            avg_f1 = sum(m['f1'] for m in metrics.values()) / len(metrics)

            if avg_f1 > best_f1:
                best_f1 = avg_f1
                best_params = params

        return best_params, best_f1
```

---

## 6. 实施路线图

### Phase 1: 基础架构 (当前 72h 验证后)
**时间**: 72h 验证完成后 2-3 天
**目标**: 不影响现有冰山检测，添加新信号类型

**任务**:
- [ ] 创建 `WhaleTradeDetector` 类 (独立文件)
- [ ] 创建 `LiquidationMonitor` 类 (独立文件)
- [ ] 创建 `UnifiedSignalManager` (不改动现有逻辑)
- [ ] 扩展 `EventLogger` 支持 whale 和 liq 类型
- [ ] 实现基础 Bundle Alert (500ms 窗口)
- [ ] 适配节流引擎支持新 key 格式
- [ ] 添加简单冲突检测 (控制台警告)

**验证标准**:
- 现有冰山检测逻辑不变 (P0-P1-P2 保持)
- 新信号类型独立记录到事件日志
- Discord 可发送 Bundle 卡片

### Phase 2: 智能关联 (Phase 1 稳定后)
**时间**: Phase 1 后 1 周
**目标**: 信号间智能关联分析

**任务**:
- [ ] 实现 `related_signals` 关联逻辑
- [ ] 置信度调整器 (基于关联信号)
- [ ] 冲突解决矩阵完整实现
- [ ] Bundle Alert 智能建议生成

**验证标准**:
- 同价格区间信号能正确关联
- Bundle 卡片包含综合建议
- 冲突场景有明确处理规则

### Phase 3: 动态优化 (Phase 2 后)
**时间**: Phase 2 后持续迭代
**目标**: 自适应阈值和回放评估

**任务**:
- [ ] 实现动态鲸鱼阈值 (分位数法)
- [ ] 完善回放引擎 (ground_truth 支持)
- [ ] 阈值优化器 (网格搜索)
- [ ] 定期评估报告生成

**验证标准**:
- 阈值能根据市场变化自适应
- 回放评估生成准确率报告
- 参数优化提升 F1 分数

---

## 7. 技术约束

### 7.1 解耦约束
- ✅ 各检测器必须独立运行，互不依赖
- ✅ 现有冰山检测逻辑不得修改 (P0-P1-P2 保持)
- ✅ UnifiedSignalManager 作为可选层，不强制使用

### 7.2 性能约束
- 单次信号检测耗时 < 10ms
- Bundle 窗口延迟 < 500ms
- 回放评估速度 > 100 events/s

### 7.3 兼容性约束
- 事件日志格式向后兼容 (老格式仍可读取)
- Discord 消息格式兼容现有 webhook
- 节流引擎复用现有逻辑

### 7.4 数据质量约束
- 清算数据源必须有降级方案 (WebSocket → REST → unavailable)
- 所有信号必须记录 confidence_modifier (便于审查)
- Key 格式必须全局唯一 (支持跨类型去重)

### 7.5 架构规范约束 (三方会谈第二十轮共识)

#### **配置外部化要求**
```python
# config/settings.py - 强制定义优先级映射
CONFIG_SIGNAL_PRIORITY = {
    "level_rank": {
        "CRITICAL": 1,
        "CONFIRMED": 2,
        "WARNING": 3,
        "ACTIVITY": 4,
        "INFO": 5,
    },
    "type_rank": {
        "liq": 1,
        "whale": 2,
        "iceberg": 3,
    }
}
```

**约束**:
- ✅ level_rank 和 type_rank 映射**必须**定义在 `config/settings.py`
- ✅ 便于未来调整优先级而不改动核心代码
- ❌ **禁止**在检测器内部硬编码优先级值

#### **比较逻辑原子化要求**
```python
# core/utils.py 或 UnifiedSignalManager
def compare_signal_priority(signal1: Dict, signal2: Dict) -> int:
    """
    统一信号优先级比较逻辑

    Returns:
        -1: signal1 优先级更高
         0: 优先级相同
         1: signal2 优先级更高
    """
    from config.settings import CONFIG_SIGNAL_PRIORITY

    level1 = CONFIG_SIGNAL_PRIORITY['level_rank'].get(signal1['level'], 99)
    level2 = CONFIG_SIGNAL_PRIORITY['level_rank'].get(signal2['level'], 99)

    if level1 != level2:
        return -1 if level1 < level2 else 1

    type1 = CONFIG_SIGNAL_PRIORITY['type_rank'].get(signal1['type'], 99)
    type2 = CONFIG_SIGNAL_PRIORITY['type_rank'].get(signal2['type'], 99)

    if type1 != type2:
        return -1 if type1 < type2 else 1

    return 0

def get_signal_sort_key(signal: Dict) -> Tuple[int, int]:
    """获取信号排序键 (level_rank, type_rank)"""
    from config.settings import CONFIG_SIGNAL_PRIORITY
    return (
        CONFIG_SIGNAL_PRIORITY['level_rank'].get(signal['level'], 99),
        CONFIG_SIGNAL_PRIORITY['type_rank'].get(signal['type'], 99)
    )
```

**约束**:
- ✅ 比较逻辑**必须**封装为独立函数（`core/utils.py` 或 `UnifiedSignalManager`）
- ✅ 所有检测器使用统一的 `get_signal_sort_key()` 或 `compare_signal_priority()`
- ❌ **严禁**在不同检测器中重复书写排序逻辑
- ❌ **严禁**在业务代码中直接访问 `TYPE_PRIORITY`/`LEVEL_PRIORITY` 字典

#### **代码审查检查点**
Phase 1 实施时必须验证:
1. ✅ `config/settings.py` 包含 `CONFIG_SIGNAL_PRIORITY` 定义
2. ✅ `core/utils.py` 或 `UnifiedSignalManager` 包含比较函数
3. ✅ 所有排序操作调用 `get_signal_sort_key()`
4. ❌ 不存在硬编码的优先级值 (如 `if type == 'liq': priority = 1`)
5. ❌ 不存在重复的排序逻辑实现

---

## 8. 风险与缓解

### 风险 1: 新信号干扰现有检测
**缓解**: 独立检测器 + 可选 UnifiedSignalManager

### 风险 2: Bundle Alert 增加延迟
**缓解**: 500ms 窗口 + 异步发送

### 风险 3: 清算数据源不稳定
**缓解**: 多级降级 (WebSocket → REST → unavailable)

### 风险 4: 信号冲突导致误判
**缓解**: 优先级矩阵 + 冲突警告

### 风险 5: 节流策略失效
**缓解**: 复用现有引擎 + 独立 key 隔离

---

## 9. 附录

### 9.1 完整配置示例

```python
# config/settings.py - 新增配置

# 鲸鱼成交配置
CONFIG_WHALE = {
    "enabled": True,
    "single_threshold_usd": 50000,
    "aggregated_threshold_usd": 200000,
    "aggregated_count": 3,
    "time_window": 300,  # 5分钟
}

# 清算监控配置
CONFIG_LIQUIDATION = {
    "enabled": True,
    "data_source": "websocket",  # websocket | rest
    "single_threshold_usd": 100000,
    "rate_window": 60,
    "rate_threshold_usd": 500000,
    "rate_count": 10,
    "levels": {
        "info": 50000,
        "warning": 100000,
        "critical": 500000,
    }
}

# Bundle Alert 配置
CONFIG_BUNDLE = {
    "enabled": True,
    "window_ms": 500,
    "max_signals": 5,
    "min_signals": 2,  # 至少2个信号才触发 Bundle
}

# 信号优先级配置
CONFIG_SIGNAL_PRIORITY = {
    "type_priority": {
        "liq": 1,
        "whale": 2,
        "iceberg": 3,
    },
    "level_priority": {
        "CRITICAL": 1,
        "CONFIRMED": 2,
        "WARNING": 3,
        "ACTIVITY": 4,
        "INFO": 5,
    }
}
```

### 9.2 完整 Schema 示例

#### Iceberg Signal
```json
{
  "type": "iceberg",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "side": "BUY",
  "level": "CONFIRMED",
  "key": "iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508",
  "data": {
    "price": 0.150800,
    "cumulative_volume": 8500.0,
    "visible_depth": 1200.0,
    "intensity": 2.5,
    "refill_count": 5
  },
  "confidence": 85.0,
  "related_signals": [],
  "confidence_modifier": {
    "base": 70.0,
    "spoofing_penalty": 0.0,
    "intensity_boost": +15.0,
    "final": 85.0
  }
}
```

#### Whale Signal
```json
{
  "type": "whale",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "side": "BUY",
  "level": "CONFIRMED",
  "key": "whale:DOGE/USDT:BUY:CONFIRMED:2026-01-05T01:30",
  "data": {
    "price_range": [0.15050, 0.15120],
    "avg_price": 0.15080,
    "total_volume": 1500000,
    "total_value_usd": 226200,
    "trade_count": 5
  },
  "confidence": 80.0,
  "related_signals": [
    "iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508"
  ],
  "confidence_modifier": {
    "base": 70.0,
    "volume_boost": +10.0,
    "final": 80.0
  }
}
```

#### Liquidation Signal
```json
{
  "type": "liq",
  "ts": 1735523180.0864,
  "symbol": "DOGE/USDT",
  "side": "SELL",
  "level": "CRITICAL",
  "key": "liq:DOGE/USDT:SELL:CRITICAL:market",
  "data": {
    "event_type": "cascade",
    "total_value": 520000,
    "count": 12,
    "avg_price": 0.1502,
    "position_side": "long"
  },
  "confidence": 95.0,
  "related_signals": [],
  "confidence_modifier": {
    "base": 85.0,
    "cascade_boost": +10.0,
    "final": 95.0
  }
}
```

---

**文档结束**

本设计文档为 P3-2 多维度信号方案的完整技术规范，待 72 小时验证完成后进入 Phase 1 实施阶段。
