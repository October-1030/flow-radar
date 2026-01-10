# K神战法 Phase 3 - 历史数据回测系统

## 概述

`kgod_backtest.py` 是 K神战法的历史数据回测系统，用于评估信号准确率和策略有效性。

## 功能特性

### 1. 双标签评估体系

- **Reversion Hit（回归命中）**: 价格回归到布林带中轨
- **Follow-through Hit（走轨命中）**: 价格延伸突破布林带上下轨

### 2. MAE/MFE 分析

- **MAE (Maximum Adverse Excursion)**: 最大不利波动
- **MFE (Maximum Favorable Excursion)**: 最大有利波动
- **风险回报比**: MFE/MAE

### 3. 分层统计

- **按信号类型**: KGOD_CONFIRM / EARLY_CONFIRM / PRE_ALERT / BAN
- **按置信度**: 90+ / 80-90 / 70-80 / 60-70 / <60
- **BAN 有效性**: 按原因分类统计

### 4. 输出报告

- **CSV 详细记录**: 每个信号的完整评估结果
- **摘要统计报告**: 准确率、置信度分层、MAE/MFE 等

## 快速开始

### 方式 1: 使用批处理脚本

```batch
run_backtest.bat
```

### 方式 2: 使用命令行

```bash
# 回测最近 3 天
python scripts/kgod_backtest.py --start_date 2026-01-07 --end_date 2026-01-09

# 只评估高置信度信号
python scripts/kgod_backtest.py --min_confidence 70.0

# 自定义观察窗口
python scripts/kgod_backtest.py --lookforward_bars 120
```

### 方式 3: 运行演示脚本

```bash
python scripts/test_backtest_demo.py
```

## 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mode` | 运行模式（signal_outcome_eval/full_replay） | signal_outcome_eval |
| `--symbol` | 交易对 | DOGE_USDT |
| `--start_date` | 开始日期（YYYY-MM-DD） | 最早数据 |
| `--end_date` | 结束日期（YYYY-MM-DD） | 最新数据 |
| `--timeframe` | K 线周期（1m/5m） | 1m |
| `--lookforward_bars` | 观察窗口（K 线根数） | 60 |
| `--regression_threshold` | 回归判定阈值（σ 倍数） | 0.5 |
| `--min_confidence` | 最低置信度过滤 | 0.0 |
| `--output_csv` | CSV 输出文件路径 | backtest_results.csv |
| `--output_report` | 报告输出文件路径 | backtest_report.txt |

## 运行模式

### Mode 1: signal_outcome_eval（推荐）

- **优点**: 快速、直接评估已有信号
- **适用场景**: 历史数据中已有 KGOD 信号事件
- **处理流程**:
  1. 读取历史事件数据
  2. 提取 KGOD 信号
  3. 聚合 K 线数据
  4. 评估每个信号的后续表现
  5. 生成统计报告

### Mode 2: full_replay（待实现）

- **优点**: 完整回放，可以调整参数重新生成信号
- **适用场景**: 需要测试不同参数配置
- **处理流程**:
  1. 读取历史事件数据
  2. 重新运行 KGodRadar.update()
  3. 生成信号并评估

## 示例输出

### CSV 文件（backtest_results.csv）

```csv
ts,signal_type,side,confidence,price,bb_mid,bb_upper,bb_lower,bb_sigma,reversion_hit,reversion_bar,reversion_price,followthrough_hit,followthrough_bar,followthrough_price,mae,mae_bar,mfe,mfe_bar,reasons
2026-01-08 16:50:00,KGOD_CONFIRM,BUY,86.9,0.14453,0.14453,0.14597,0.14308,0.00072,True,0,0.14453,True,21,0.14623,1.783,54,3.424,23,|z| >= 2.0; MACD 同向; Delta 强
```

### 摘要报告（backtest_report.txt）

```
============================================================
K神战法 Phase 3 回测报告
============================================================
时间范围: 2026-01-08 16:50:00 ~ 2026-01-08 20:10:00
交易对: DOGE/USDT
总信号数: 156

--- 信号统计 ---
PRE_ALERT: 89 个
EARLY_CONFIRM: 42 个
KGOD_CONFIRM: 18 个
BAN: 7 个

--- 准确率（Reversion Hit）---
KGOD_CONFIRM: 72.2% (13/18)
EARLY_CONFIRM: 64.3% (27/42)
PRE_ALERT: 58.4% (52/89) [样本充足]

--- 置信度分层 ---
90+: 85.7% (6/7)   ← 高置信度表现最佳
80-90: 70.0% (7/10)
70-80: 62.5% (5/8)
<70: 55.0% (6/11) [样本不足]

--- BAN 有效性 ---
BAN 有效率: 71.4% (5/7) [样本不足]
BAN 误杀率: 14.3% (1/7)

按原因分类：
- acceptance: 80.0% (4/5)
- bb_squeeze: 50.0% (1/2) [样本不足]

--- MAE/MFE 统计 ---
平均 MAE: 0.32σ (建议止损位)
平均 MFE: 1.15σ
风险回报比: 3.59x

============================================================
```

## 指标说明

### Reversion Hit（回归命中）

- **定义**: 价格在观察窗口内回归到布林带中轨
- **判定条件**: `|price - mid_band| <= regression_threshold * sigma`
- **用途**: 评估均值回归策略的有效性

### Follow-through Hit（走轨命中）

- **定义**: 价格在观察窗口内延伸到布林带上下轨
- **判定条件**:
  - BUY 信号: `price >= upper_band`
  - SELL 信号: `price <= lower_band`
- **用途**: 评估趋势延续的概率

### MAE（最大不利波动）

- **定义**: 信号触发后的最大反向波动
- **计算**:
  - BUY 信号: `(entry_price - min_price) / sigma`
  - SELL 信号: `(max_price - entry_price) / sigma`
- **用途**: 确定止损位

### MFE（最大有利波动）

- **定义**: 信号触发后的最大正向波动
- **计算**:
  - BUY 信号: `(max_price - entry_price) / sigma`
  - SELL 信号: `(entry_price - min_price) / sigma`
- **用途**: 确定止盈位

## 数据要求

### 输入数据

- 位置: `storage/events/*.jsonl.gz`
- 格式: JSONL (每行一个 JSON 对象)
- 压缩: gzip
- 必需事件类型:
  - `orderbook`: 订单簿快照（用于提取价格）
  - `trades`: 成交数据（用于提取价格）
  - `state`: 状态数据（用于提取价格）
  - `signal` 或 `kgod_signal`: KGOD 信号（Mode 1 需要）

### 文件命名规范

```
{SYMBOL}_{YYYY-MM-DD}.jsonl.gz
```

示例:
```
DOGE_USDT_2026-01-09.jsonl.gz
```

## 常见问题

### Q: 为什么提取不到 KGOD 信号？

A: 历史数据可能没有记录 KGOD 信号事件。这种情况下：
1. 确认历史数据中是否有 `type: kgod_signal` 或 `type: signal` 的事件
2. 考虑使用 Mode 2（full_replay）重新生成信号

### Q: 回归阈值如何设置？

A: `regression_threshold` 表示距离中轨多少个标准差算"回归成功"：
- `0.5`: 距离中轨 0.5σ 以内（较严格）
- `1.0`: 距离中轨 1.0σ 以内（适中）
- `1.5`: 距离中轨 1.5σ 以内（宽松）

### Q: 观察窗口多长合适？

A: `lookforward_bars` 取决于交易周期：
- 1 分钟 K 线 + 60 根 = 1 小时观察窗口
- 5 分钟 K 线 + 60 根 = 5 小时观察窗口

建议根据实际持仓时间调整。

### Q: 样本不足怎么办？

A: 报告中标注 "[样本不足]" 的类别统计置信度较低：
- 扩大回测日期范围
- 降低 `min_confidence` 阈值
- 等待积累更多历史数据

## 技术架构

### 核心模块

1. **HistoricalDataLoader**: 历史数据加载器
2. **KlineBuilder**: K 线聚合器
3. **SignalExtractor**: 信号提取器
4. **SignalEvaluator**: 信号评估器
5. **ReportGenerator**: 报告生成器

### 依赖

- `numpy`: 数值计算
- `pandas`: 数据处理
- `core.kgod_radar`: K神雷达模块
- `config.kgod_settings`: 配置参数

## 开发路线图

- [x] Mode 1: signal_outcome_eval（信号结果评估）
- [x] 双标签评估（Reversion / Follow-through）
- [x] MAE/MFE 统计
- [x] 置信度分层分析
- [x] BAN 有效性评估
- [x] CSV 详细记录
- [x] 摘要统计报告
- [ ] Mode 2: full_replay（完整回放）
- [ ] 参数优化功能
- [ ] 可视化图表生成
- [ ] 多币种对比分析

## 贡献指南

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License
