#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日数据总结"""

import sys
import io
import gzip
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
import statistics

# 设置Windows控制台UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def load_today_data():
    """加载今天的数据"""
    storage_path = Path("C:/Users/rjtan/Downloads/flow-radar/storage/events")
    today = datetime.now().strftime("%Y-%m-%d")

    file_path = storage_path / f"DOGE_USDT_{today}.jsonl.gz"

    states = []

    if not file_path.exists():
        return states

    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    if event.get('type') == 'state':
                        data = event.get('data', {})
                        states.append({
                            'ts': event.get('ts'),
                            'time': datetime.fromtimestamp(event.get('ts')),
                            'state': data.get('state_name', 'Unknown'),
                            'score': data.get('score', 0),
                            'iceberg_ratio': data.get('iceberg_ratio', 0),
                            'price': data.get('price', 0),
                            'confidence': data.get('confidence', 0),
                            'recommendation': data.get('recommendation', ''),
                            'cvd': data.get('cvd_total', 0),
                        })
                except:
                    continue
    except:
        pass

    return states

def print_daily_summary():
    """打印每日总结"""
    states = load_today_data()

    if not states:
        print("今天还没有数据")
        return

    print("\n" + "="*60)
    print(f"📅 DOGE/USDT 今日数据总结")
    print("="*60)

    # 时间范围
    start_time = states[0]['time']
    end_time = states[-1]['time']
    duration = (end_time - start_time).total_seconds() / 3600

    print(f"\n⏰ 数据时段:")
    print(f"   开始: {start_time.strftime('%H:%M:%S')}")
    print(f"   结束: {end_time.strftime('%H:%M:%S')}")
    print(f"   时长: {duration:.1f} 小时")
    print(f"   数据点: {len(states)} 个")

    # 价格统计
    prices = [s['price'] for s in states if s['price'] > 0]
    if prices:
        price_change = ((prices[-1] - prices[0]) / prices[0]) * 100
        print(f"\n💰 价格表现:")
        print(f"   开盘: ${prices[0]:.5f}")
        print(f"   当前: ${prices[-1]:.5f}")
        print(f"   最高: ${max(prices):.5f}")
        print(f"   最低: ${min(prices):.5f}")
        print(f"   涨跌: {price_change:+.2f}%")

    # 市场状态分布
    state_counts = Counter([s['state'] for s in states])
    print(f"\n🔍 市场状态分布:")
    for state, count in state_counts.most_common():
        pct = (count / len(states)) * 100
        bar = "█" * int(pct/2)
        print(f"   {state:12s} {bar:30s} {pct:5.1f}% ({count}次)")

    # 冰山订单统计
    iceberg_ratios = [s['iceberg_ratio'] for s in states if s['iceberg_ratio'] > 0]
    if iceberg_ratios:
        avg_iceberg = statistics.mean(iceberg_ratios)
        print(f"\n🧊 冰山订单:")
        print(f"   平均买单比: {avg_iceberg*100:.1f}%")

        strong_buy = sum(1 for r in iceberg_ratios if r > 0.75)
        moderate_buy = sum(1 for r in iceberg_ratios if 0.65 <= r <= 0.75)
        neutral = sum(1 for r in iceberg_ratios if 0.45 < r < 0.65)
        sell = sum(1 for r in iceberg_ratios if r <= 0.45)

        total = len(iceberg_ratios)
        print(f"   超强买方 (>75%): {strong_buy:3d} 次 ({strong_buy/total*100:5.1f}%)")
        print(f"   偏多 (65-75%):   {moderate_buy:3d} 次 ({moderate_buy/total*100:5.1f}%)")
        print(f"   中性 (45-65%):   {neutral:3d} 次 ({neutral/total*100:5.1f}%)")
        print(f"   偏空 (<45%):     {sell:3d} 次 ({sell/total*100:5.1f}%)")

    # 今日关键事件
    print(f"\n🎯 今日要点:")

    # 找状态变化
    state_changes = []
    for i in range(1, len(states)):
        if states[i]['state'] != states[i-1]['state']:
            state_changes.append(states[i])

    if state_changes:
        print(f"   状态转换 {len(state_changes)} 次:")
        for s in state_changes[-5:]:
            print(f"   [{s['time'].strftime('%H:%M')}] ${s['price']:.5f} → {s['state']}")

    # 当前状态
    current = states[-1]
    print(f"\n📍 当前状态:")
    print(f"   {current['state']} | ${current['price']:.5f}")
    print(f"   分数:{current['score']} | 冰山买单:{current['iceberg_ratio']*100:.1f}% | 置信:{current['confidence']:.0f}%")
    print(f"   建议: {current['recommendation']}")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    print_daily_summary()
