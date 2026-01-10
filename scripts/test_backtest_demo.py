"""
K神战法回测系统演示脚本
用模拟数据演示回测功能
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.kgod_backtest import SignalEvaluator, ReportGenerator


def generate_mock_data():
    """生成模拟数据用于测试"""
    # 生成模拟 K 线数据
    np.random.seed(42)
    n_bars = 500

    # 基础价格
    base_price = 0.15
    prices = base_price + np.cumsum(np.random.randn(n_bars) * 0.0005)

    # 创建 K 线 DataFrame
    start_time = datetime(2026, 1, 9, 0, 0, 0)
    timestamps = [start_time + timedelta(minutes=i) for i in range(n_bars)]

    klines = pd.DataFrame({
        'ts': timestamps,
        'open': prices,
        'high': prices * 1.002,
        'low': prices * 0.998,
        'close': prices,
        'volume': np.random.randint(100, 1000, n_bars),
    })

    klines['ts_unix'] = klines['ts'].astype(np.int64) // 10**9

    # 生成模拟 K神信号
    signals = []

    # KGOD_CONFIRM 信号（高置信度）
    for i in [50, 150, 300, 420]:
        if i >= len(klines):
            continue

        signal = {
            'ts': klines.iloc[i]['ts_unix'],
            'stage': 'KGOD_CONFIRM',
            'side': 'BUY' if np.random.rand() > 0.5 else 'SELL',
            'confidence': 75 + np.random.rand() * 20,  # 75-95
            'reasons': ['|z| >= 2.0', 'MACD 同向', 'Delta 强'],
            'debug': {
                'bb': {
                    'mid': klines.iloc[i]['close'],
                    'upper': klines.iloc[i]['close'] * 1.01,
                    'lower': klines.iloc[i]['close'] * 0.99,
                }
            }
        }
        signals.append(signal)

    # EARLY_CONFIRM 信号（中置信度）
    for i in [80, 200, 350]:
        if i >= len(klines):
            continue

        signal = {
            'ts': klines.iloc[i]['ts_unix'],
            'stage': 'EARLY_CONFIRM',
            'side': 'BUY' if np.random.rand() > 0.5 else 'SELL',
            'confidence': 55 + np.random.rand() * 15,  # 55-70
            'reasons': ['|z| >= 1.8', 'MACD 确认'],
            'debug': {
                'bb': {
                    'mid': klines.iloc[i]['close'],
                    'upper': klines.iloc[i]['close'] * 1.008,
                    'lower': klines.iloc[i]['close'] * 0.992,
                }
            }
        }
        signals.append(signal)

    # PRE_ALERT 信号（低置信度）
    for i in [30, 100, 180, 270, 380]:
        if i >= len(klines):
            continue

        signal = {
            'ts': klines.iloc[i]['ts_unix'],
            'stage': 'PRE_ALERT',
            'side': 'BUY' if np.random.rand() > 0.5 else 'SELL',
            'confidence': 30 + np.random.rand() * 20,  # 30-50
            'reasons': ['|z| >= 1.4'],
            'debug': {
                'bb': {
                    'mid': klines.iloc[i]['close'],
                    'upper': klines.iloc[i]['close'] * 1.006,
                    'lower': klines.iloc[i]['close'] * 0.994,
                }
            }
        }
        signals.append(signal)

    # BAN 信号
    for i in [120, 250]:
        if i >= len(klines):
            continue

        signal = {
            'ts': klines.iloc[i]['ts_unix'],
            'stage': 'BAN',
            'side': 'BUY' if np.random.rand() > 0.5 else 'SELL',
            'confidence': 0.0,
            'reasons': ['价格持续在上轨上方 >30s'],
            'debug': {}
        }
        signals.append(signal)

    return klines, signals


def main():
    """运行演示"""
    print("=" * 60)
    print("K神战法 Phase 3 回测系统演示")
    print("=" * 60)
    print()

    # 生成模拟数据
    print("生成模拟数据...")
    klines, signals = generate_mock_data()
    print(f"  - K 线数量: {len(klines)}")
    print(f"  - 信号数量: {len(signals)}")
    print()

    # 配置
    config = {
        'symbol': 'DEMO/USDT',
        'lookforward_bars': 60,
        'regression_threshold': 0.5,
        'followthrough_k_sigma': 2.0,
    }

    # 评估信号
    print("评估信号...")
    evaluator = SignalEvaluator(config)
    results = []

    for signal in signals:
        result = evaluator.evaluate_signal(signal, klines)
        if 'error' not in result:
            results.append(result)

    print(f"  - 评估完成: {len(results)} 个有效结果")
    print()

    # 生成报告
    print("生成报告...")
    generator = ReportGenerator(results, config)

    # 保存 CSV
    generator.save_csv('demo_backtest_results.csv')

    # 生成摘要
    summary = generator.generate_summary()

    # 保存摘要
    with open('demo_backtest_report.txt', 'w', encoding='utf-8') as f:
        f.write(summary)

    print()
    print(summary)
    print()
    print("演示完成！")
    print("  - CSV 输出: demo_backtest_results.csv")
    print("  - 报告输出: demo_backtest_report.txt")


if __name__ == '__main__':
    main()
