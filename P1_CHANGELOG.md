# P1 改进总结文档

> PriceLevel 统一 + 置信度增强 + 配置外部化
> 更新日期: 2026-01-04

---

## 1. 改动概述

本次升级包含三个 P1 优先级改进，统一代码结构并增强置信度计算：

| 编号 | 改进项 | 问题描述 | 解决方案 |
|------|--------|----------|----------|
| P1-1 | PriceLevel 统一 | `alert_monitor.py` 和 `iceberg_detector.py` 各有独立 PriceLevel 类，P0 改进未同步 | 创建 `core/price_level.py` 作为单一来源 |
| P1-2 | 置信度计算增强 | `_calculate_confidence()` 未集成 P0-3 的 spoofing 惩罚 | 统一使用 `PriceLevel.calculate_confidence()` |
| P1-Config | 配置外部化 | 迟滞阈值、spoofing 阈值等硬编码在类中 | 提取到 `CONFIG_PRICE_LEVEL` 字典 |

---

## 2. 核心代码变更

### P1-1: 统一 PriceLevel 模块

**新增文件: `core/price_level.py`**

```python
# 统一的 PriceLevel 类，整合 P0 改进
from core.price_level import PriceLevel, IcebergLevel, CONFIG_PRICE_LEVEL
```

**关键特性:**
- 包含 P0-1 迟滞检测字段 (peak_quantity, is_depleted, iceberg_strength)
- 包含 P0-3 Spoofing 检测字段 (explanation_ratio, is_suspicious)
- 包含 `get_iceberg_level()` 方法 (NONE/ACTIVITY/CONFIRMED)
- 兼容旧代码的 `max_visible` 字段

**验收:**
```bash
grep -r "class PriceLevel" *.py
# 结果: 只有 core/price_level.py:72:class PriceLevel:
```

---

### P1-2: 置信度计算增强

**旧代码 (alert_monitor.py):**
```python
def _calculate_confidence(self, level: PriceLevel) -> float:
    confidence = 50.0
    # 仅基于 intensity、refill_count、cumulative_filled
    # 无 spoofing 惩罚
    return min(95.0, confidence)
```

**新代码:**
```python
def _calculate_confidence(self, level: PriceLevel) -> float:
    """使用 PriceLevel 的统一 calculate_confidence 方法"""
    return level.calculate_confidence()
```

**PriceLevel.calculate_confidence() 实现:**
```python
def calculate_confidence(self) -> float:
    cfg = CONFIG_PRICE_LEVEL
    confidence = 50.0

    # 基于强度、补单次数、成交量加分
    if self.intensity >= 10: confidence += 20
    elif self.intensity >= 5: confidence += 10
    # ...

    # P1-2: 应用 spoofing 惩罚
    multiplier = self.get_confidence_multiplier()
    confidence *= multiplier

    # P1-2: 可疑信号的置信度上限
    if self.is_suspicious:
        confidence = min(confidence, cfg['confidence_cap_suspicious'])

    return min(95.0, confidence)
```

**惩罚乘数规则:**
| explanation_ratio | 乘数 | 说明 |
|-------------------|------|------|
| ≥ 0.7 | 1.0 | 无惩罚 |
| 0.3 ~ 0.7 | 0.6 | 中等惩罚 |
| < 0.3 | 0.3 | 严重惩罚 |
| is_suspicious=True | cap=60 | 上限封顶 |

---

### P1-Config: 配置外部化

**新增配置字典 (core/price_level.py):**
```python
CONFIG_PRICE_LEVEL = {
    # 迟滞阈值 (P0-1)
    "depletion_ratio": 0.2,             # 耗尽阈值: 剩余 < 20%
    "recovery_ratio": 0.5,              # 恢复阈值: 恢复到 > 50%
    "refill_time_limit": 30.0,          # 补单时间窗口 (秒)

    # 强度衰减 (P0-1)
    "strength_decay": 0.95,             # 强度衰减系数
    "strength_boost": 0.3,              # 补单强度增加
    "strength_threshold": 0.5,          # 强度阈值

    # Spoofing 检测 (P0-3)
    "spoofing_threshold": 0.3,          # 低于此比例视为可疑
    "min_quantity_for_spoofing_check": 100.0,

    # 置信度惩罚 (P1-2)
    "confidence_cap_suspicious": 60.0,  # 可疑信号上限
    "penalty_tiers": {
        "high": {"min_ratio": 0.7, "multiplier": 1.0},
        "medium": {"min_ratio": 0.3, "multiplier": 0.6},
        "low": {"min_ratio": 0.0, "multiplier": 0.3},
    },

    # IcebergLevel 判断阈值
    "confirmed_absorption": 3.0,
    "confirmed_refill_count": 3,
}
```

---

## 3. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `core/price_level.py` | **新增** | 统一 PriceLevel + IcebergLevel + CONFIG |
| `iceberg_detector.py` | 修改 | 删除旧 PriceLevel，导入新模块 |
| `alert_monitor.py` | 修改 | 删除旧 PriceLevel/IcebergLevel，简化置信度计算 |

---

## 4. 测试验证

### 语法检查
```bash
python -m py_compile core/price_level.py
python -m py_compile iceberg_detector.py
python -m py_compile alert_monitor.py
# 结果: All syntax OK
```

### 导入测试
```python
from core.price_level import PriceLevel, IcebergLevel, CONFIG_PRICE_LEVEL

pl = PriceLevel(price=100.0)
print(pl.calculate_confidence())  # 50.0 (基础值)

# 模拟 spoofing
pl.record_disappeared(1000.0)
pl.explain_with_trade(100.0)  # 10% 解释率
print(pl.is_suspicious)  # True
print(pl.calculate_confidence())  # ≤ 60 (被封顶)
```

### 单元测试用例

**置信度惩罚测试:**
```python
from core.price_level import PriceLevel

# 正常信号
level = PriceLevel(price=100.0)
level.cumulative_filled = 5000
level.refill_count = 10
level.explanation_ratio = 0.8  # 高解释率
conf = level.calculate_confidence()
assert conf > 80  # 高置信度

# 可疑信号
level2 = PriceLevel(price=100.0)
level2.cumulative_filled = 5000
level2.refill_count = 10
level2.disappeared_quantity = 1000
level2.explained_quantity = 100  # 10% 解释率
level2._update_explanation_ratio()
conf2 = level2.calculate_confidence()
assert conf2 <= 60  # 被封顶
assert level2.is_suspicious == True
```

---

## 5. 向后兼容

- `max_visible` 字段保留，兼容旧代码
- `IcebergLevel` 枚举值改为整数 (0/1/2)，原字符串值已废弃
- `get_confidence_penalty()` 方法保留，返回扣除值
- 新增 `get_confidence_multiplier()` 返回乘数
- 新增 `calculate_confidence()` 统一计算

---

## 6. 后续 P2 改进项

| 编号 | 改进项 | 说明 |
|------|--------|------|
| P2-1 | deque 性能优化 | TradeDeduplicator 的 `list.pop(0)` → `deque` |
| P2-2 | 冰山信号持久化 | 冰山检测结果写入 events 日志 |
| P2-3 | 告警降噪 | 相似告警合并，避免刷屏 |
| P2-4 | 状态恢复增强 | 冰山检测状态持久化 |
| P2-5 | 健康检查 | 心跳监控、异常自动重启 |

---

*文档生成时间: 2026-01-04*
