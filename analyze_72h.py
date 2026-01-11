#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""72小时数据分析脚本"""

import sys
import io
import gzip
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
import statistics

# 设置Windows控制台UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def load_events(file_path):
    """加载事件数据"""
    events = []
    try:
        with gzip.open(file_path, 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    events.append(event)
                except:
                    continue
    except Exception as e:
        print(f"警告: 读取文件时出错 {file_path}: {e}")
    return events

def analyze_states(events):
    """分析市场状态变化"""
    states = []
    for event in events:
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
                'divergence': data.get('divergence', '')
            })
    return states

def analyze_trades(events):
    """分析交易数据"""
    all_trades = []
    for event in events:
        if event.get('type') == 'trades':
            trades = event.get('data', [])
            for trade in trades:
                all_trades.append({
                    'price': trade.get('price', 0),
                    'quantity': trade.get('quantity', 0),
                    'is_buy': not trade.get('is_buyer_maker', True),  # buyer_maker=卖单
                    'timestamp': trade.get('timestamp', 0)
                })
    return all_trades

def print_summary(states, trades):
    """打印分析摘要"""
    if not states:
        print("⚠️  没有状态数据")
        return

    print("\n" + "="*80)
    print("📊 DOGE/USDT 72小时盘面分析报告")
    print("="*80)

    # 时间范围
    start_time = states[0]['time']
    end_time = states[-1]['time']
    duration_hours = (end_time - start_time).total_seconds() / 3600

    print(f"\n⏰ 分析时间段:")
    print(f"   开始: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   结束: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   时长: {duration_hours:.1f} 小时")
    print(f"   数据点: {len(states)} 个状态快照")

    # 价格走势
    prices = [s['price'] for s in states if s['price'] > 0]
    if prices:
        price_change = ((prices[-1] - prices[0]) / prices[0]) * 100
        print(f"\n💰 价格走势:")
        print(f"   起始价: ${prices[0]:.5f}")
        print(f"   当前价: ${prices[-1]:.5f}")
        print(f"   最高价: ${max(prices):.5f}")
        print(f"   最低价: ${min(prices):.5f}")
        print(f"   涨跌幅: {price_change:+.2f}%")

    # 市场状态统计
    state_counts = Counter([s['state'] for s in states])
    print(f"\n🔍 市场状态分布:")
    total = len(states)
    for state, count in state_counts.most_common():
        percentage = (count / total) * 100
        print(f"   {state:12s}: {count:4d} 次 ({percentage:5.1f}%)")

    # 冰山订单分析
    iceberg_ratios = [s['iceberg_ratio'] for s in states if s['iceberg_ratio'] > 0]
    if iceberg_ratios:
        avg_iceberg = statistics.mean(iceberg_ratios)
        print(f"\n🧊 冰山订单分析:")
        print(f"   平均买单比例: {avg_iceberg*100:.1f}%")
        print(f"   最高买单比例: {max(iceberg_ratios)*100:.1f}%")
        print(f"   最低买单比例: {min(iceberg_ratios)*100:.1f}%")

        strong_buy_periods = sum(1 for r in iceberg_ratios if r > 0.65)
        strong_sell_periods = sum(1 for r in iceberg_ratios if r < 0.35)
        print(f"   强买期 (>65%): {strong_buy_periods} 次 ({strong_buy_periods/len(iceberg_ratios)*100:.1f}%)")
        print(f"   强卖期 (<35%): {strong_sell_periods} 次 ({strong_sell_periods/len(iceberg_ratios)*100:.1f}%)")

    # 综合分数统计
    scores = [s['score'] for s in states if s['score'] > 0]
    if scores:
        avg_score = statistics.mean(scores)
        print(f"\n📈 综合分数统计:")
        print(f"   平均分数: {avg_score:.1f}")
        print(f"   最高分数: {max(scores)}")
        print(f"   最低分数: {min(scores)}")

        bullish = sum(1 for s in scores if s >= 60)
        bearish = sum(1 for s in scores if s <= 35)
        neutral = len(scores) - bullish - bearish
        print(f"   看涨 (≥60): {bullish} 次 ({bullish/len(scores)*100:.1f}%)")
        print(f"   看跌 (≤35): {bearish} 次 ({bearish/len(scores)*100:.1f}%)")
        print(f"   中性: {neutral} 次 ({neutral/len(scores)*100:.1f}%)")

    # CVD分析
    cvds = [s['cvd'] for s in states if s['cvd'] != 0]
    if cvds:
        print(f"\n📊 累计成交量差 (CVD):")
        print(f"   起始CVD: {cvds[0]:,.0f}")
        print(f"   当前CVD: {cvds[-1]:,.0f}")
        print(f"   CVD变化: {cvds[-1] - cvds[0]:+,.0f}")
        print(f"   最大CVD: {max(cvds):,.0f}")
        print(f"   最小CVD: {min(cvds):,.0f}")

    # 操作建议统计
    recommendations = Counter([s['recommendation'] for s in states if s['recommendation']])
    if recommendations:
        print(f"\n💡 操作建议分布:")
        for rec, count in recommendations.most_common():
            percentage = (count / len(states)) * 100
            print(f"   {rec:15s}: {count:4d} 次 ({percentage:5.1f}%)")

    # 关键事件识别
    print(f"\n🎯 关键事件:")

    # 找出状态转换点
    state_changes = []
    for i in range(1, len(states)):
        if states[i]['state'] != states[i-1]['state']:
            state_changes.append({
                'time': states[i]['time'],
                'from': states[i-1]['state'],
                'to': states[i]['state'],
                'price': states[i]['price']
            })

    if state_changes:
        print(f"   状态转换 {len(state_changes)} 次:")
        for change in state_changes[-10:]:  # 显示最近10次
            print(f"   [{change['time'].strftime('%m-%d %H:%M')}] ${change['price']:.5f} - {change['from']} → {change['to']}")

    # 当前状态
    current = states[-1]
    print(f"\n📍 当前市场状态:")
    print(f"   状态: {current['state']}")
    print(f"   价格: ${current['price']:.5f}")
    print(f"   分数: {current['score']}")
    print(f"   冰山买单比: {current['iceberg_ratio']*100:.1f}%")
    print(f"   置信度: {current['confidence']:.1f}%")
    print(f"   建议: {current['recommendation']}")
    print(f"   背离: {current['divergence']}")

    # 交易量分析
    if trades:
        print(f"\n📦 交易量统计:")
        buy_trades = [t for t in trades if t['is_buy']]
        sell_trades = [t for t in trades if not t['is_buy']]

        buy_volume = sum(t['quantity'] for t in buy_trades)
        sell_volume = sum(t['quantity'] for t in sell_trades)
        total_volume = buy_volume + sell_volume

        print(f"   总交易数: {len(trades):,}")
        print(f"   买单数: {len(buy_trades):,} ({len(buy_trades)/len(trades)*100:.1f}%)")
        print(f"   卖单数: {len(sell_trades):,} ({len(sell_trades)/len(trades)*100:.1f}%)")
        print(f"   买入量: {buy_volume:,.0f} DOGE ({buy_volume/total_volume*100:.1f}%)")
        print(f"   卖出量: {sell_volume:,.0f} DOGE ({sell_volume/total_volume*100:.1f}%)")
        print(f"   买卖比: {buy_volume/sell_volume:.2f}")

    print("\n" + "="*80)

def main():
    storage_path = Path("C:/Users/rjtan/Downloads/flow-radar/storage/events")

    all_states = []
    all_trades = []

    # 加载所有数据文件
    for file_path in sorted(storage_path.glob("DOGE_USDT_*.jsonl.gz")):
        print(f"正在加载 {file_path.name}...")
        events = load_events(file_path)
        states = analyze_states(events)
        trades = analyze_trades(events)
        all_states.extend(states)
        all_trades.extend(trades)
        print(f"  加载了 {len(states)} 个状态, {len(trades)} 笔交易")

    # 按时间排序
    all_states.sort(key=lambda x: x['ts'])
    all_trades.sort(key=lambda x: x['timestamp'])

    # 打印分析报告
    print_summary(all_states, all_trades)

if __name__ == "__main__":
    main()
