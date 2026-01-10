# P3 优先级配置使用指南

## 概述

`config/p3_settings.py` 提供了信号优先级的外部化配置，用于多信号融合系统的排序和筛选。

## 核心设计原则

1. **数值越小优先级越高**
   - `1` = 最高优先级
   - `99` = 降级/未知类型

2. **层次化排序规则**
   - 优先级排序：`level_rank` > `type_rank` > `timestamp`（越新越靠前）

3. **配置外部化**
   - 可热更新，无需重启系统
   - 支持根据实战效果动态调整

4. **UI 层特殊处理**
   - **重要**: BAN 状态的信号应无视 rank 进行置顶（由 UI 层单独处理）

## 优先级映射

### Level Rank（信号级别优先级）

| Level      | Rank | 说明                     |
|------------|------|-------------------------|
| CRITICAL   | 1    | 临界事件（大额清算、连锁风险） |
| CONFIRMED  | 2    | 已确认（高置信度、多次验证）   |
| WARNING    | 3    | 警告级（中等风险）           |
| ACTIVITY   | 4    | 观察级（低置信度、待确认）     |
| *未知*     | 99   | 降级处理                   |

### Type Rank（信号类型优先级）

| Type    | Rank | 说明                           |
|---------|------|-------------------------------|
| liq     | 1    | 清算 - 已发生的强制平仓事件（最高） |
| whale   | 2    | 大单 - 已确认的真实资金流         |
| iceberg | 3    | 冰山 - 推测性检测（可能撤单）      |
| kgod    | 4    | K神 - 技术指标信号（可调整）       |
| *未知*  | 99   | 降级处理                        |

## API 使用

### 1. 信号排序（推荐）

```python
from config.p3_settings import get_sort_key

# 对信号列表按优先级排序
signals = [signal1, signal2, signal3]
sorted_signals = sorted(signals, key=get_sort_key)
```

**排序规则**：
- 先按 `level_rank`（数值越小越靠前）
- 再按 `type_rank`（数值越小越靠前）
- 最后按 `timestamp`（时间越新越靠前）

### 2. 信号比较

```python
from config.p3_settings import compare_signals

result = compare_signals(signal_a, signal_b)
# 返回: -1 (a 优先) | 0 (相同) | 1 (b 优先)
```

### 3. 获取单个信号的 Rank

```python
from config.p3_settings import get_level_rank, get_type_rank

level_rank = get_level_rank("CRITICAL")      # 返回: 1
type_rank = get_type_rank("liq")              # 返回: 1
```

### 4. 获取完整排序键

```python
from config.p3_settings import get_sort_key

signal = {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758400.0}
sort_key = get_sort_key(signal)
# 返回: (1, 1, -1704758400.0)
#       (level_rank, type_rank, -ts)
```

## 兼容性

### 支持的信号格式

1. **字典格式**
   ```python
   {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758400.0}
   # 或使用 "type" 字段
   {"level": "CRITICAL", "type": "liq", "ts": 1704758400.0}
   ```

2. **SignalEvent 对象**
   ```python
   from core.signal_schema import SignalEvent, SignalLevel, SignalType

   signal = SignalEvent(
       ts=1704758400.0,
       symbol="DOGE/USDT",
       side=SignalSide.BUY,
       level=SignalLevel.CRITICAL,
       confidence=95.0,
       price=0.15068,
       signal_type=SignalType.LIQ,
       key="liq:DOGE/USDT:BUY:CRITICAL:price_42000"
   )
   ```

3. **枚举类型**
   ```python
   # 自动处理枚举类型
   get_level_rank(SignalLevel.CRITICAL)     # 返回: 1
   get_type_rank(SignalType.LIQ)            # 返回: 1
   ```

## 实战调整策略

### 场景 1: K神信号频繁误报

如果 K神信号误报率高，可降低其优先级：

```python
# config/p3_settings.py
TYPE_RANK = {
    "liq": 1,
    "whale": 2,
    "iceberg": 3,
    "kgod": 5,        # 从 4 调整为 5（降低优先级）
}
```

### 场景 2: 冰山信号效果优于 K神

如果冰山信号表现优异，可调整：

```python
TYPE_RANK = {
    "liq": 1,
    "whale": 2,
    "iceberg": 3,     # 保持当前优先级
    "kgod": 6,        # 进一步降低 K神优先级
}
```

### 场景 3: 增加新的信号类型

```python
TYPE_RANK = {
    "liq": 1,
    "whale": 2,
    "new_signal": 3,  # 新增信号类型
    "iceberg": 4,     # 原冰山降级
    "kgod": 5,        # 原 K神降级
}
```

## 配置验证

导入模块时不会自动验证配置（避免初始化副作用）。如需手动验证：

```python
from config.p3_settings import validate_priority_config

try:
    validate_priority_config()
    print("✅ 配置验证通过")
except AssertionError as e:
    print(f"❌ 配置验证失败: {e}")
```

或直接运行配置文件：

```bash
python config/p3_settings.py
```

## 示例代码

### 完整排序示例

```python
from config.p3_settings import get_sort_key

# 混合信号列表
signals = [
    {"level": "ACTIVITY", "signal_type": "iceberg", "ts": 1704758400.0},
    {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758500.0},
    {"level": "CONFIRMED", "signal_type": "whale", "ts": 1704758600.0},
    {"level": "CONFIRMED", "signal_type": "kgod", "ts": 1704758700.0},
]

# 按优先级排序
sorted_signals = sorted(signals, key=get_sort_key)

# 输出
for sig in sorted_signals:
    print(f"[{sig['level']:9}] {sig['signal_type']:8} @ ts={sig['ts']}")

# 输出结果:
# [CRITICAL ] liq      @ ts=1704758500.0    <- 最高优先（level=1, type=1）
# [CONFIRMED] whale    @ ts=1704758600.0    <- 次高（level=2, type=2）
# [CONFIRMED] kgod     @ ts=1704758700.0    <- 中等（level=2, type=4）
# [ACTIVITY ] iceberg  @ ts=1704758400.0    <- 最低（level=4, type=3）
```

## 注意事项

1. **BAN 状态置顶**
   若信号携带 BAN 状态（走轨风险），UI 层应无视 rank 进行置顶显示。

2. **未知类型降级**
   未知的 level 或 type 会自动降级到 rank=99，排在最后。

3. **时间戳排序**
   相同 level 和 type 时，按时间戳排序（越新越靠前）。

4. **配置热更新**
   修改 `LEVEL_RANK` 或 `TYPE_RANK` 后，重新导入模块即可生效（无需重启）。

## 测试

运行集成测试以验证配置正确性：

```bash
python test_p3_priority.py
```

测试覆盖：
- SignalEvent 对象兼容性
- 枚举类型处理
- 字典和对象混合排序
- 未知类型降级
- 比较函数
- 配置验证

## 版本历史

- **v2.0** (2026-01-10): 重构优先级系统，支持 kgod 信号类型，移除 INFO 级别
- **v1.0** (2026-01-08): 初始版本，支持 liq/whale/iceberg 三种类型

## 参考文档

- `core/signal_schema.py` - 信号数据结构定义
- `docs/P3-2_multi_signal_design.md` - 多信号融合设计文档
