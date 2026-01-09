# 🚀 标注表格快速上手

**5 分钟快速开始标注！**

---

## 📂 文件说明

| 文件 | 说明 | 用途 |
|------|------|------|
| `iceberg_annotation_samples.csv` | 原始样本（只读） | 仅查看，不编辑 |
| **`iceberg_annotation_template.csv`** | 标注模板（可编辑） | 👈 你要用这个！ |
| `annotation_guide.md` | 详细标注指南 | 遇到问题时查阅 |

---

## ⚡ 3 步快速开始

### Step 1: 打开表格（2 选 1）

#### 方法 A: Google Sheets（推荐）
1. 打开 [Google Sheets](https://sheets.google.com)
2. 点击 **文件 → 导入 → 上传**
3. 选择 `docs/iceberg_annotation_template.csv`
4. 导入设置：分隔符 = 逗号，编码 = UTF-8

#### 方法 B: Excel
1. 打开 Excel
2. 文件 → 打开 → 选择 `iceberg_annotation_template.csv`
3. 编码选择 **UTF-8**

---

### Step 2: 设置下拉菜单（推荐）

**Google Sheets 操作**:

1. 选中 `annotation` 列（N 列）
2. 数据 → 数据验证
3. 条件：列表来源 → 输入 `HIT,MISS,UNCERTAIN`
4. 保存

重复以上步骤：
- `confidence_check` 列（O 列）：`TOO_HIGH,APPROPRIATE,TOO_LOW`
- `price_action` 列（P 列）：`UP,DOWN,FLAT`

**Excel 操作**:
数据 → 数据验证 → 列表 → 输入值（用逗号分隔）

---

### Step 3: 开始标注！

**表格列说明**:

| 列 | 字段 | 说明 | 操作 |
|----|------|------|------|
| A-L | 原始数据 | 时间、价格、方向等 | **只读** |
| M | **readable_time** | 可读时间 | 参考 |
| N | **annotation** | 主标注 | **必填**: HIT/MISS/UNCERTAIN |
| O | confidence_check | 置信度评估 | 可选 |
| P | price_action | 价格走势 | 可选 |
| Q | actual_volume | 实际成交量 | 可选 |
| R | **notes** | 备注 | 建议填写 |
| S | annotator | 标注人 | 建议填写 |
| T | annotation_time | 标注时间 | 建议填写 |

---

## 📋 标注速查表

### annotation（N 列）- 必填

| 选项 | 含义 | 什么时候选 |
|------|------|-----------|
| **HIT** | 命中 ✅ | 确实是冰山订单（补单行为明显） |
| **MISS** | 未命中 ❌ | 不是冰山订单（误报） |
| **UNCERTAIN** | 不确定 ⚠️ | 无法判断（需在 notes 说明原因） |

**判断技巧**:
```
HIT 的典型特征：
- refill_count ≥ 3（补单次数多）
- intensity > 5（强度高）
- confidence ≥ 75%（置信度中高）
- 补单行为规律（时间间隔均匀）

MISS 的典型特征：
- 看起来像不同账户的正常挂单
- 金额、位置变化大
- 只出现 1-2 次就消失
```

---

## 💡 标注示例

### 示例 1: 明显的 HIT ✅

```
ts: 1767787722.252899
readable_time: 2026-01-07 04:08:42
side: BUY
confidence: 95.0%
refill_count: 7
intensity: 10.4

annotation: HIT
confidence_check: APPROPRIATE
notes: 补单 7 次，强度很高，明显是算法挂单
```

### 示例 2: 明显的 MISS ❌

```
ts: 1767775139.597447
readable_time: 2026-01-07 00:38:59
side: BUY
confidence: 65.0%
refill_count: 3
intensity: 3.8

annotation: MISS
confidence_check: TOO_HIGH
notes: 只补单 3 次，强度较低，更像散户挂单，置信度 65% 偏高
```

### 示例 3: 不确定 ⚠️

```
ts: 1767777582.320583
readable_time: 2026-01-07 01:13:02
side: SELL
confidence: 65.0%
refill_count: 3
intensity: 3.3

annotation: UNCERTAIN
notes: 处于阈值边缘，无法获取该时间盘口数据验证
```

---

## 📊 标注进度追踪

在表格最上方添加统计公式（Google Sheets）：

```
已标注: =COUNTA(N2:N31)
HIT 数量: =COUNTIF(N2:N31,"HIT")
MISS 数量: =COUNTIF(N2:N31,"MISS")
准确率: =COUNTIF(N2:N31,"HIT")/(COUNTIF(N2:N31,"HIT")+COUNTIF(N2:N31,"MISS"))
```

目标：30 个样本全部标注完成！

---

## ⏱️ 预计时间

- **快速模式**: 30-45 分钟（只填 annotation）
- **标准模式**: 60-90 分钟（填 annotation + notes）
- **完整模式**: 90-120 分钟（所有列都填写）

**建议**：先用快速模式标注一遍，有疑问的标记 UNCERTAIN，后续再补充详细信息。

---

## 🎯 完成后

### 1. 保存文件
- Google Sheets: 文件 → 下载 → CSV
- Excel: 另存为 → CSV (UTF-8)
- 文件名: `iceberg_annotation_samples_labeled.csv`

### 2. 放回项目目录
```
docs/
  ├── iceberg_annotation_samples.csv          (原始)
  ├── iceberg_annotation_template.csv         (空白模板)
  └── iceberg_annotation_samples_labeled.csv  (👈 你标注后的结果)
```

### 3. 提交结果（可选）
```bash
git add docs/iceberg_annotation_samples_labeled.csv
git commit -m "Add human annotation for 30 iceberg signals"
git push
```

---

## ❓ 常见问题

**Q: 我不知道怎么判断 HIT 还是 MISS？**
A: 查看 `annotation_guide.md` 的详细标准，或先标注 UNCERTAIN + 在 notes 说明疑问

**Q: readable_time 显示不对？**
A: 这是 UTC+8 北京时间，如果不对请检查系统时区设置

**Q: 需要看原始盘口数据吗？**
A: 不强制，根据 refill_count、intensity、confidence 三个字段就能做基本判断

**Q: 标注多长时间的价格走势？**
A: 建议统一看信号出现后 30 分钟内的价格变化

**Q: 标注完成后怎么分析？**
A: 等所有标注完成后，会有专门的分析脚本生成报告

---

## 🆘 需要帮助？

遇到问题时：
1. 查看 `annotation_guide.md`（详细指南）
2. 在 notes 列记录你的疑问
3. 标注为 UNCERTAIN 继续进行
4. 联系技术支持获取帮助

---

**祝标注顺利！🎯**

预计完成时间：1-2 小时
目标：为 Flow Radar 提供高质量的验证数据！
