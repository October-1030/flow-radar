# K神战法回测系统 - 快速开始指南

## 第一步：运行演示脚本

```bash
python scripts/test_backtest_demo.py
```

这将生成模拟数据并运行回测，输出：
- `demo_backtest_results.csv`: 详细评估记录
- `demo_backtest_report.txt`: 摘要统计报告

## 第二步：查看演示结果

### 查看 CSV（Excel/文本编辑器）

```bash
notepad demo_backtest_results.csv
```

### 查看报告（文本编辑器）

```bash
notepad demo_backtest_report.txt
```

示例输出：
```
============================================================
K神战法 Phase 3 回测报告
============================================================
交易对: DEMO/USDT
总信号数: 14

--- 信号统计 ---
KGOD_CONFIRM: 4 个
EARLY_CONFIRM: 3 个
PRE_ALERT: 5 个
BAN: 2 个

--- 准确率（Reversion Hit）---
KGOD_CONFIRM: 100.0% (4/4)
EARLY_CONFIRM: 100.0% (3/3)
PRE_ALERT: 100.0% (5/5)

--- MAE/MFE 统计 ---
平均 MAE: 4.26σ (建议止损位)
平均 MFE: 5.16σ
风险回报比: 1.21x
============================================================
```

## 第三步：回测真实历史数据

### 方法 1: 使用批处理脚本

```batch
run_backtest.bat
```

### 方法 2: 使用命令行

```bash
# 回测最近 3 天
python scripts/kgod_backtest.py --start_date 2026-01-07 --end_date 2026-01-09

# 查看结果
notepad backtest_report.txt
```

## 第四步：自定义回测参数

```bash
# 只评估高置信度信号（>= 70）
python scripts/kgod_backtest.py \
    --min_confidence 70.0 \
    --start_date 2025-12-29 \
    --end_date 2026-01-09

# 使用 5 分钟 K 线（更长周期）
python scripts/kgod_backtest.py \
    --timeframe 5m \
    --lookforward_bars 120

# 调整回归阈值（更宽松）
python scripts/kgod_backtest.py \
    --regression_threshold 1.0
```

## 常用命令速查

| 场景 | 命令 |
|------|------|
| 快速演示 | `python scripts/test_backtest_demo.py` |
| 回测 1 天 | `python scripts/kgod_backtest.py --start_date 2026-01-09 --end_date 2026-01-09` |
| 回测 1 周 | `python scripts/kgod_backtest.py --start_date 2026-01-03 --end_date 2026-01-09` |
| 高置信度过滤 | `python scripts/kgod_backtest.py --min_confidence 70` |
| 长观察窗口 | `python scripts/kgod_backtest.py --lookforward_bars 120` |
| 5 分钟 K 线 | `python scripts/kgod_backtest.py --timeframe 5m` |

## 理解输出结果

### Reversion Hit（回归命中率）

- **含义**: 信号触发后，价格回归到布林带中轨的比例
- **高命中率**: 适合均值回归策略（逆势交易）
- **低命中率**: 可能出现趋势延续（顺势交易）

### Follow-through Hit（走轨命中率）

- **含义**: 信号触发后，价格突破布林带上下轨的比例
- **高命中率**: 趋势强劲，适合顺势加仓
- **低命中率**: 价格震荡，趋势不明显

### MAE/MFE

- **MAE（最大不利波动）**: 建议止损位参考
  - 示例: MAE = 0.32σ → 止损设在 0.4σ
- **MFE（最大有利波动）**: 建议止盈位参考
  - 示例: MFE = 1.15σ → 止盈设在 1.0σ
- **风险回报比**: MFE/MAE
  - 示例: 3.59x → 每承受 1 单位风险，可获得 3.59 单位回报

## 下一步

1. **分析历史数据**: 找出哪些条件下信号最准确
2. **优化参数**: 调整置信度阈值、观察窗口
3. **实盘验证**: 在模拟盘测试策略
4. **持续监控**: 定期回测最新数据，更新策略

## 需要帮助？

查看完整文档: `scripts/README_BACKTEST.md`
