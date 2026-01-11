# P0 改进总结文档

> iceberg_detector.py 核心逻辑升级
> 更新日期: 2026-01-03

---

## 1. 改动概述

本次升级包含三个 P0 优先级改进，针对冰山订单检测的准确性和可靠性进行优化：

| 编号 | 改进项 | 问题描述 | 解决方案 |
|------|--------|----------|----------|
| P0-1 | 补单检测迟滞 | 订单完全耗尽后(visible_quantity=0)无法检测补单 | 引入迟滞阈值 + 时间约束 + iceberg_strength 连续值 |
| P0-2 | 成交去重 | WebSocket 可能收到重复成交导致误判 | 使用 (timestamp, id) 组合键 + TTL seen-set |
| P0-3 | Spoofing 过滤 | 无法区分真实成交与撤单假象 | 引入 explanation_ratio 解释比例机制 |

---

## 2. 核心代码变更

### P0-1: 补单检测迟滞机制

**新增 PriceLevel 字段:**
```python
# P0-1: 迟滞检测相关字段
peak_quantity: float = 0.0              # 历史峰值挂单量
is_depleted: bool = False               # 是否处于耗尽状态
depletion_time: Optional[datetime] = None  # 耗尽发生时间
iceberg_strength: float = 0.0           # 连续冰山强度值 (0.0 - 1.0+)

# 迟滞阈值常量
DEPLETION_RATIO: float = 0.2            # 耗尽阈值 (低于峰值20%视为耗尽)
RECOVERY_RATIO: float = 0.5             # 恢复阈值 (恢复到峰值50%视为补单)
REFILL_TIME_LIMIT: float = 30.0         # 补单时间窗口 (秒)
STRENGTH_DECAY: float = 0.95            # 强度衰减系数
STRENGTH_BOOST: float = 0.3             # 补单强度增加
```

**状态机更新逻辑 (update 方法):**
```python
def update(self, new_quantity: float, timestamp: datetime) -> bool:
    """更新价格档位，返回是否检测到补单"""
    self.last_quantity = self.visible_quantity
    self.visible_quantity = new_quantity
    self.last_update = timestamp

    # 强度自然衰减
    self.iceberg_strength *= self.STRENGTH_DECAY

    # 更新峰值
    if new_quantity > self.peak_quantity:
        self.peak_quantity = new_quantity

    refill_detected = False
    depletion_threshold = self.peak_quantity * self.DEPLETION_RATIO
    recovery_threshold = self.peak_quantity * self.RECOVERY_RATIO

    if not self.is_depleted:
        # 正常状态 -> 检测是否耗尽
        if new_quantity <= depletion_threshold and self.peak_quantity > 0:
            self.is_depleted = True
            self.depletion_time = timestamp
    else:
        # 耗尽状态 -> 检测是否补单
        if new_quantity >= recovery_threshold:
            # 检查时间约束
            if self.depletion_time:
                elapsed = (timestamp - self.depletion_time).total_seconds()
                if elapsed <= self.REFILL_TIME_LIMIT:
                    refill_detected = True
                    self.refill_count += 1
                    self.iceberg_strength = min(2.0, self.iceberg_strength + self.STRENGTH_BOOST)
            # 重置状态
            self.is_depleted = False
            self.depletion_time = None
            self.peak_quantity = new_quantity

    return refill_detected
```

---

### P0-2: 成交去重器

**新增 TradeDeduplicator 类:**
```python
class TradeDeduplicator:
    """
    P0-2: 成交去重器
    使用 (timestamp, trade_id) 组合键进行去重
    """
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._seen: Dict[str, datetime] = {}
        self._order: List[str] = []  # TODO: 可优化为 deque

    def _make_key(self, timestamp: int, trade_id: str) -> str:
        """生成唯一键"""
        trade_id_str = str(trade_id) if trade_id is not None else ""
        return f"{timestamp}:{trade_id_str}"

    def is_duplicate(self, timestamp: int, trade_id: str) -> bool:
        """检查是否重复，非重复则记录"""
        key = self._make_key(timestamp, trade_id)
        if key in self._seen:
            return True
        # 新记录
        self._seen[key] = datetime.now()
        self._order.append(key)
        # LRU 淘汰
        while len(self._order) > self.max_size:
            oldest_key = self._order.pop(0)
            self._seen.pop(oldest_key, None)
        return False

    def filter_trades(self, trades: List[Dict]) -> List[Dict]:
        """过滤重复成交"""
        unique_trades = []
        for trade in trades:
            ts = trade.get('timestamp', 0)
            tid = trade.get('id', trade.get('trade_id', ''))
            if not self.is_duplicate(ts, tid):
                unique_trades.append(trade)
        return unique_trades
```

**集成到 IcebergDetector:**
```python
# __init__ 中
self.trade_deduplicator = TradeDeduplicator(max_size=1000)

# run_once 中
trades = await self.exchange.watch_trades(self.symbol)
trades = self.trade_deduplicator.filter_trades(trades)
```

---

### P0-3: Spoofing 过滤机制

**新增 PriceLevel 字段:**
```python
# P0-3: Spoofing 检测相关字段
disappeared_quantity: float = 0.0       # 订单簿消失量
explained_quantity: float = 0.0         # 被实际成交解释的量
explanation_ratio: float = 1.0          # 解释比例
is_suspicious: bool = False             # 是否可疑 (ratio < 0.3)
SPOOFING_THRESHOLD: float = 0.3         # Spoofing阈值
```

**新增方法:**
```python
def record_disappeared(self, quantity: float):
    """记录订单簿消失量"""
    if quantity > 0:
        self.disappeared_quantity += quantity
        self._update_explanation_ratio()

def explain_with_trade(self, trade_volume: float):
    """用实际成交解释消失量"""
    if trade_volume > 0:
        self.explained_quantity += trade_volume
        self._update_explanation_ratio()

def _update_explanation_ratio(self):
    """更新解释比例"""
    if self.disappeared_quantity > 0:
        self.explanation_ratio = min(1.0, self.explained_quantity / self.disappeared_quantity)
    else:
        self.explanation_ratio = 1.0
    self.is_suspicious = self.explanation_ratio < self.SPOOFING_THRESHOLD

def get_confidence_penalty(self) -> float:
    """获取置信度惩罚系数"""
    if self.explanation_ratio >= 0.7:
        return 1.0   # 无惩罚
    elif self.explanation_ratio >= 0.5:
        return 0.8   # 轻微惩罚
    elif self.explanation_ratio >= 0.3:
        return 0.5   # 中等惩罚
    else:
        return 0.2   # 严重惩罚
```

**修改 is_iceberg 属性:**
```python
@property
def is_iceberg(self) -> bool:
    """判断是否为冰山订单"""
    has_refills = self.refill_count >= 2
    has_strength = self.iceberg_strength >= 0.3
    not_suspicious = not self.is_suspicious  # P0-3: 排除可疑信号
    # TODO: 观察 'or' 条件是否导致误报
    return (has_refills or has_strength) and not_suspicious
```

---

## 3. TODO 待观察项

| 位置 | 类型 | 说明 |
|------|------|------|
| `PriceLevel.is_iceberg` (line ~175) | 逻辑观察 | `has_refills or has_strength` 的 'or' 条件可能导致误报，需要实盘观察后决定是否改为 'and' |
| `TradeDeduplicator` (line ~274-275) | 性能优化 | `list.pop(0)` 是 O(n) 操作，如果高频场景下性能不足，可改用 `collections.deque(maxlen=1000)` |
| `PriceLevel.is_iceberg` (line ~179) | 策略选择 | 当前直接排除 suspicious 信号，备选方案是仅降低置信度而不完全排除 |

---

## 4. 测试建议

### 基础功能测试
```bash
# 语法检查
python -m py_compile iceberg_detector.py

# 模块导入测试
python -c "from iceberg_detector import IcebergDetector, PriceLevel, TradeDeduplicator; print('OK')"
```

### 单元测试用例

**P0-1 迟滞机制测试:**
```python
from iceberg_detector import PriceLevel
from datetime import datetime, timedelta

# 测试正常补单检测
level = PriceLevel(price=100.0, side='buy')
level.peak_quantity = 1000.0
level.visible_quantity = 1000.0

t0 = datetime.now()
# 耗尽
level.update(150.0, t0)  # 低于 20% 阈值
assert level.is_depleted == True

# 10秒内补单
t1 = t0 + timedelta(seconds=10)
refill = level.update(600.0, t1)  # 恢复到 50%+
assert refill == True
assert level.refill_count == 1
```

**P0-2 去重测试:**
```python
from iceberg_detector import TradeDeduplicator

dedup = TradeDeduplicator(max_size=100)
trades = [
    {'timestamp': 1000, 'id': 'a'},
    {'timestamp': 1000, 'id': 'a'},  # 重复
    {'timestamp': 1001, 'id': 'b'},
]
unique = dedup.filter_trades(trades)
assert len(unique) == 2
```

**P0-3 Spoofing 测试:**
```python
from iceberg_detector import PriceLevel

level = PriceLevel(price=100.0, side='buy')
# 大量消失但少量成交 = 可疑
level.record_disappeared(1000.0)
level.explain_with_trade(100.0)  # 只解释 10%
assert level.explanation_ratio < 0.3
assert level.is_suspicious == True
```

### 实盘验证
```bash
# 启动监控，观察日志中的冰山检测输出
python alert_monitor.py -s DOGE/USDT --web

# 关注以下指标变化:
# - iceberg_strength 是否合理累积
# - refill_count 是否正确计数
# - is_suspicious 标记是否准确
```

---

## 变更文件清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `iceberg_detector.py` | 修改 | 核心冰山检测逻辑升级 |
| `P0_CHANGELOG.md` | 新增 | 本文档 |

---

*文档生成时间: 2026-01-03*
