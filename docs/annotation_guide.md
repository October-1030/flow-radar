# 冰山信号人工标注指南

**版本**: v1.0
**日期**: 2026-01-08
**用途**: 为 Flow Radar 冰山检测器提供人工标注样本，用于验证算法准确率

---

## 📊 标注表格结构

### 原始字段（从 CSV 导入）

| 字段名 | 说明 | 示例 |
|-------|------|------|
| ts | Unix 时间戳 | 1767775139.597447 |
| symbol | 交易对 | DOGE/USDT |
| side | 方向 | BUY / SELL |
| level | 信号级别 | CONFIRMED |
| confidence | 置信度 | 65.0 ~ 95.0 |
| price | 价格 | 0.15068 |
| cumulative_filled | 累计成交量 | 0（检测时） |
| refill_count | 补单次数 | 3 |
| intensity | 强度 | 3.78 |
| key | 信号唯一标识 | （可能为空） |
| snippet_path | 原始数据路径 | storage\events\DOGE_USDT_2026-01-07.jsonl.gz |
| offset | 行号 | 17 |

### 标注字段（需要添加）

| 字段名 | 说明 | 可选值 | 必填 |
|-------|------|--------|------|
| **annotation** | 主要标注结果 | HIT / MISS / UNCERTAIN | ✅ |
| **price_action** | 后续价格走势 | UP / DOWN / FLAT | 可选 |
| **actual_volume** | 实际观察到的成交量 | 数值 | 可选 |
| **confidence_check** | 置信度评估 | TOO_HIGH / APPROPRIATE / TOO_LOW | 可选 |
| **notes** | 备注 | 自由文本 | 可选 |
| **annotator** | 标注人 | 姓名/ID | 建议 |
| **annotation_time** | 标注时间 | YYYY-MM-DD HH:MM | 建议 |

---

## 🎯 标注标准

### 1. annotation（主标注）

#### HIT - 命中（真阳性）✅

**判断标准**：
- ✅ 价格位置确实存在大额挂单（通过盘口截图验证）
- ✅ 出现多次补单行为（订单被吃后立即补充）
- ✅ 补单金额与 `cumulative_filled` 相近
- ✅ 订单持续时间超过 5 分钟

**典型特征**：
```
示例 1: BUY 冰山
价格: 0.15068
refill_count: 3
intensity: 3.78
观察: 该价位挂单被吃后，1秒内重新出现相似金额挂单，重复 3 次
结论: HIT ✅
```

#### MISS - 未命中（假阳性）❌

**判断标准**：
- ❌ 价格位置无明显大额挂单
- ❌ "补单"实际上是不同账户的正常挂单
- ❌ 订单金额小于 1000 USDT（非冰山级别）
- ❌ 只出现 1-2 次就消失（可能是巧合）

**典型特征**：
```
示例 2: SELL 冰山（假阳性）
价格: 0.1487
refill_count: 3
观察: 3 次挂单的金额、位置差异较大，像是不同散户
结论: MISS ❌
```

#### UNCERTAIN - 不确定（需更多数据）⚠️

**判断标准**：
- ⚠️ 无法获取该时间点的盘口数据
- ⚠️ 行为模式介于冰山和正常挂单之间
- ⚠️ 补单次数刚好在阈值边缘（如 refill_count=3）
- ⚠️ 订单金额中等（1000-5000 USDT）

**处理方式**：
- 标注为 UNCERTAIN
- 在 notes 中详细说明原因
- 后续可补充标注

---

### 2. confidence_check（置信度评估）

评估算法给出的 `confidence` 是否合理：

| 评估 | 说明 | 示例 |
|------|------|------|
| **TOO_HIGH** | 置信度虚高 | 标注 MISS 但 confidence=95% |
| **APPROPRIATE** | 置信度合理 | 标注 HIT 且 confidence=85% |
| **TOO_LOW** | 置信度过低 | 标注 HIT 但 confidence=65% |

**用途**：用于校准置信度计算公式

---

### 3. price_action（价格走势）

记录信号出现后 **30 分钟内** 的价格变化：

| 走势 | 定义 | 示例 |
|------|------|------|
| **UP** | 上涨 > 0.3% | BUY 冰山出现后，价格从 0.1500 涨到 0.1505+ |
| **DOWN** | 下跌 > 0.3% | SELL 冰山出现后，价格从 0.1500 跌到 0.1495- |
| **FLAT** | 横盘 ±0.3% | 价格在 0.1498-0.1502 震荡 |

**注意**：价格走势 ≠ 标注结果
- 冰山订单可能是"防守"而非"进攻"
- HIT 的 BUY 冰山也可能价格不涨（压单阻力）

---

### 4. notes（备注）

记录任何有助于理解的信息：

**推荐记录内容**：
```
- "补单间隔均匀，明显是算法挂单"
- "第 3 次补单后价格突破，可能触发止损"
- "该时段市场波动大，难以判断"
- "价格位置是整数关口（0.15000）"
- "与前后 5 分钟的其他信号重叠"
```

---

## 📝 标注流程

### Step 1: 准备工作

1. 打开 Google Sheets 导入 CSV
2. 添加标注列：`annotation`, `confidence_check`, `price_action`, `notes`, `annotator`
3. 冻结首行（便于滚动查看）

### Step 2: 逐条标注

对于每条信号：

1. **查看基础信息**
   - 时间：`ts` → 转换为可读时间（用公式 `=TEXT((A2+8*3600)/86400+DATE(1970,1,1),"yyyy-mm-dd hh:mm:ss")`）
   - 方向：BUY/SELL
   - 置信度：confidence
   - 补单次数：refill_count

2. **回溯原始数据**（可选）
   - 根据 `snippet_path` 和 `offset` 定位到事件日志
   - 查看该时间段前后的完整交易记录
   - 使用工具解压 `.jsonl.gz` 文件：
     ```bash
     gzip -dc storage\events\DOGE_USDT_2026-01-07.jsonl.gz | sed -n '17p'
     ```

3. **做出判断**
   - 填写 `annotation`: HIT / MISS / UNCERTAIN
   - 填写 `confidence_check`: 评估置信度是否合理
   - 填写 `notes`: 记录判断依据

4. **（可选）验证价格走势**
   - 在 TradingView 或交易所 K 线图查看该时间点
   - 记录 30 分钟内的价格变化
   - 填写 `price_action`: UP / DOWN / FLAT

### Step 3: 质量控制

标注完成后检查：
- [ ] 每条记录都有 `annotation` 值
- [ ] UNCERTAIN 的记录都有 `notes` 说明原因
- [ ] 买卖方向的标注比例大致均衡
- [ ] 高置信度（85%+）的信号中 HIT 率较高

---

## 📊 Google Sheets 公式辅助

### 1. 时间戳转换（添加到列 M）

```
=TEXT((A2+8*3600)/86400+DATE(1970,1,1),"yyyy-mm-dd hh:mm:ss")
```
将 Unix 时间戳转换为北京时间（UTC+8）

### 2. 数据验证（下拉菜单）

选中 `annotation` 列 → 数据 → 数据验证：
- 列表来源：`HIT,MISS,UNCERTAIN`

选中 `confidence_check` 列：
- 列表来源：`TOO_HIGH,APPROPRIATE,TOO_LOW`

选中 `price_action` 列：
- 列表来源：`UP,DOWN,FLAT`

### 3. 统计公式（汇总区）

```
HIT 数量:    =COUNTIF(M:M,"HIT")
MISS 数量:   =COUNTIF(M:M,"MISS")
准确率:      =COUNTIF(M:M,"HIT")/(COUNTIF(M:M,"HIT")+COUNTIF(M:M,"MISS"))
```

---

## 🎯 标注目标

### 样本量要求
- **最小可用样本**: 30 个（当前批次）
- **理想样本量**: 100-200 个（多批次累积）
- **分层要求**: 每个置信度段（65%/75%/85%/95%）至少 10 个样本

### 质量要求
- **标注一致性**: 同一标注员对相似信号的判断一致
- **标注速度**: 平均 2-3 分钟/条（含数据回溯）
- **UNCERTAIN 比例**: 建议 < 20%

### 用途
1. **算法验证**: 计算冰山检测器的准确率、召回率
2. **置信度校准**: 调整置信度计算公式
3. **阈值优化**: 确定最佳的 refill_count、intensity 阈值

---

## 📂 输出格式

标注完成后，导出为 CSV：
- 文件名: `iceberg_annotation_samples_labeled.csv`
- 保存位置: `docs/`
- 编码: UTF-8

后续可用于：
```python
# 分析标注结果
import pandas as pd
df = pd.read_csv('docs/iceberg_annotation_samples_labeled.csv')

# 计算准确率
hit_rate = (df['annotation'] == 'HIT').sum() / len(df)
print(f"命中率: {hit_rate:.1%}")

# 按置信度分组分析
df.groupby('confidence')['annotation'].value_counts()
```

---

## ⚠️ 注意事项

1. **避免确认偏误**: 不要因为 confidence 高就倾向于标注 HIT
2. **客观标准**: 基于观察到的行为，而非"感觉"
3. **记录不确定**: 遇到模糊情况，诚实标注 UNCERTAIN + 详细说明
4. **时间窗口一致**: 所有样本使用相同的观察时长（建议 30 分钟）
5. **数据隐私**: 标注数据仅用于算法改进，不对外公开

---

## 📞 问题反馈

标注过程中遇到的问题：
- 标准不清晰 → 在 notes 中记录，后续讨论
- 数据缺失 → 标注 UNCERTAIN
- 技术问题 → 查看 `docs/annotation_troubleshooting.md`

---

**Happy Annotating! 🎯**
