# 冰山订单人工标注模板

## 标注说明

本模板用于人工验证系统检测到的冰山订单信号质量。

## 评判标准

### 命中（HIT）✅
**定义**：系统检测准确，符合冰山订单特征

**判断依据**：
1. **明显补单行为**：订单量耗尽后在短时间内（≤30秒）恢复
2. **持续吃单现象**：价格档位持续被消耗但订单量维持稳定
3. **价格走势符合**：买单检测后价格上涨 / 卖单检测后价格下跌
4. **成交量验证**：cumulative_volume 与实际成交匹配

**补单次数要求**：
- ACTIVITY: ≥ 2次补单
- CONFIRMED: ≥ 3次补单

### 未命中（MISS）❌
**定义**：系统误报，不符合冰山订单特征

**常见误报原因**：
1. **Spoofing（虚假挂单）**：大单挂出后立即撤销，无实际成交
2. **散户博弈**：小额订单频繁进出，非单一大户行为
3. **价格反向**：检测后价格走势与预期相反
4. **成交量不足**：实际成交量远低于系统记录

### 不确定（UNCERTAIN）⚠️
**定义**：证据不足，无法明确判断

**常见情况**：
1. 补单行为存在但不明显（时间间隔接近阈值）
2. 价格走势横盘，无明确方向
3. 市场波动剧烈，难以归因
4. 数据不完整（时间窗口过短）

---

## 标注表格模板

| 序号 | 时间 | 币种 | 方向 | 价格 | 等级 | 置信度 | 补单次数 | 累计量 | 判断 | 理由 | 标注人 |
|-----|------|------|------|------|------|--------|---------|--------|------|------|--------|
| 1 | 2026-01-05 10:23 | DOGE/USDT | BUY | 0.1508 | CONFIRMED | 85% | 5 | 8500 | ✅ HIT | 明显补单5次，价格上涨1.2% | Alice |
| 2 | 2026-01-05 11:45 | DOGE/USDT | SELL | 0.1520 | ACTIVITY | 72% | 3 | 4200 | ⚠️ UNCERTAIN | 补单存在但价格横盘 | Bob |
| 3 | 2026-01-05 14:30 | DOGE/USDT | BUY | 0.1495 | CONFIRMED | 90% | 6 | 12000 | ❌ MISS | 检测后价格下跌2%，疑似误报 | Alice |

---

## 标注字段说明

| 字段 | 说明 | 来源 |
|------|------|------|
| 序号 | 信号编号 | 自动编号 |
| 时间 | 信号触发时间 | event.ts |
| 币种 | 交易对 | event.symbol |
| 方向 | BUY / SELL | event.data.side |
| 价格 | 检测价格 | event.data.price |
| 等级 | ACTIVITY / CONFIRMED | event.data.level |
| 置信度 | 系统计算的置信度 | event.data.confidence |
| 补单次数 | 记录的补单次数 | event.data.refill_count |
| 累计量 | 累计成交量 | event.data.cumulative_volume |
| 判断 | HIT / MISS / UNCERTAIN | 人工判断 |
| 理由 | 判断依据简述 | 人工填写 |
| 标注人 | 标注者ID | 人工填写 |

---

## 标注流程

### 1. 准备阶段
```bash
# 提取待标注信号（取最近72h的CONFIRMED信号）
python scripts/extract_signals_for_annotation.py --days 3 --level CONFIRMED --output annotations/batch_001.md
```

### 2. 标注步骤

**Step 1: 查看信号上下文**
- 打开 K线图，查看信号时间点前后的价格走势
- 查看订单簿回放（如果有）
- 查看成交明细

**Step 2: 验证补单行为**
- 检查 refill_count 是否与实际观察一致
- 验证补单时间间隔是否合理（≤30秒）

**Step 3: 验证价格走势**
- BUY信号：后续价格是否上涨？
- SELL信号：后续价格是否下跌？
- 观察时间窗口：5-15分钟

**Step 4: 综合判断**
- 结合以上证据给出 HIT / MISS / UNCERTAIN
- 简述理由（20字以内）

### 3. 质量控制

**双盲标注**：
- N=30的样本由2人独立标注
- 一致性 ≥ 80% 视为可信
- 不一致的case由第三人仲裁

**保守 vs 中性标准**：
- **保守**：有疑问就标UNCERTAIN，PRECISION优先
- **中性**：按证据倾向标注，平衡PRECISION和RECALL

---

## 统计分析

### 计算指标

```python
# Precision（准确率）
precision = HIT / (HIT + MISS)

# 按等级统计
precision_confirmed = HIT_CONFIRMED / (HIT_CONFIRMED + MISS_CONFIRMED)
precision_activity = HIT_ACTIVITY / (HIT_ACTIVITY + MISS_ACTIVITY)

# 按置信度区间统计
precision_high = HIT(conf≥80) / (HIT(conf≥80) + MISS(conf≥80))
precision_med = HIT(60≤conf<80) / (HIT(60≤conf<80) + MISS(60≤conf<80))
```

### 预期目标

| 等级 | Precision目标 | 说明 |
|------|--------------|------|
| CONFIRMED | ≥ 70% | 高置信信号，要求准确率高 |
| ACTIVITY | ≥ 50% | 活动信号，允许更多探索性检测 |
| 全部 | ≥ 60% | 整体准确率要求 |

---

## 示例标注（参考）

### Example 1: 典型命中

**信号信息**：
- 时间: 2026-01-05 10:23:45
- 币种: DOGE/USDT
- 方向: BUY
- 价格: $0.1508
- 等级: CONFIRMED
- 置信度: 85%
- 补单次数: 5
- 累计成交: 8500 DOGE

**观察证据**：
- 10:23 - 买单从12000降到2000
- 10:23:15 - 恢复到10000（第1次补单）
- 10:23:40 - 耗尽后再次恢复（第2次补单）
- ...共观察到5次明显补单
- 10:25 - 价格上涨到 $0.1520 (+0.8%)
- 10:30 - 价格继续上涨到 $0.1535 (+1.8%)

**判断**: ✅ HIT
**理由**: 补单行为清晰，价格走势符合预期

---

### Example 2: Spoofing误报

**信号信息**：
- 时间: 2026-01-05 14:30:12
- 币种: DOGE/USDT
- 方向: BUY
- 价格: $0.1495
- 等级: ACTIVITY
- 置信度: 65%
- 补单次数: 2
- 累计成交: 1200 DOGE

**观察证据**：
- 14:30 - 大单8000挂出
- 14:30:05 - 订单簿显示订单消失（非成交，是撤单）
- 14:30:20 - 又出现6000买单
- 14:30:25 - 再次撤单
- 实际成交量<500，远低于系统记录的1200
- 价格无明显变化

**判断**: ❌ MISS
**理由**: Spoofing行为，撤单而非成交

---

### Example 3: 证据不足

**信号信息**：
- 时间: 2026-01-05 18:45:30
- 币种: DOGE/USDT
- 方向: SELL
- 价格: $0.1510
- 等级: ACTIVITY
- 置信度: 68%
- 补单次数: 2
- 累计成交: 3500 DOGE

**观察证据**：
- 18:45 - 卖单确实有补单迹象
- 但市场整体波动大
- 价格横盘震荡，无明确趋势
- 难以判断是否为真实大户行为

**判断**: ⚠️ UNCERTAIN
**理由**: 补单存在但市场混乱，证据不足

---

## 批次管理

### 建议批次划分

| 批次 | 时间范围 | 样本数 | 标注人 | 标准 | 状态 |
|------|---------|--------|--------|------|------|
| Batch_001 | 12/29-12/31 | 30 | Alice, Bob | 保守 | ⏳ 进行中 |
| Batch_002 | 01/01-01/02 | 30 | Alice, Charlie | 中性 | 🔜 待开始 |
| Batch_003 | 01/03-01/04 | 30 | Bob, Charlie | 保守 | 🔜 待开始 |

---

## 附录：快速查询

### 从事件日志提取信号
```python
import gzip, json
from pathlib import Path

def extract_iceberg_signals(date_str):
    """提取指定日期的冰山信号"""
    filepath = f"storage/events/DOGE_USDT_{date_str}.jsonl.gz"
    signals = []

    with gzip.open(filepath, 'rt') as f:
        for line in f:
            event = json.loads(line)
            if event.get('type') == 'iceberg':
                signals.append(event)

    return signals

# 使用示例
signals = extract_iceberg_signals('2026-01-05')
for s in signals:
    print(f"{s['ts']} | {s['data']['side']} | {s['data']['price']} | {s['data']['level']}")
```

---

**生成时间**: 2026-01-05
**版本**: v1.0
**维护者**: Flow Radar Team
