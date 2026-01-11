#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""关键信号提醒"""

import sys
import io
import gzip
import json
from pathlib import Path
from datetime import datetime

# 设置Windows控制台UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def get_recent_states(minutes=30):
    """获取最近N分钟的状态"""
    storage_path = Path("C:/Users/rjtan/Downloads/flow-radar/storage/events")

    # 找到最新的文件
    files = sorted(storage_path.glob("DOGE_USDT_*.jsonl.gz"), reverse=True)
    if not files:
        return []

    states = []
    cutoff_time = datetime.now().timestamp() - (minutes * 60)

    # 读取最近的文件
    for file_path in files[:2]:  # 只读最近2个文件
        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        if event.get('type') == 'state':
                            ts = event.get('ts')
                            if ts < cutoff_time:
                                continue

                            data = event.get('data', {})
                            states.append({
                                'ts': ts,
                                'time': datetime.fromtimestamp(ts),
                                'state': data.get('state_name', 'Unknown'),
                                'score': data.get('score', 0),
                                'iceberg_ratio': data.get('iceberg_ratio', 0),
                                'price': data.get('price', 0),
                                'confidence': data.get('confidence', 0),
                                'recommendation': data.get('recommendation', ''),
                            })
                    except:
                        continue
        except:
            continue

    states.sort(key=lambda x: x['ts'])
    return states

def check_alerts():
    """检查关键信号"""
    states = get_recent_states(30)

    if not states:
        print("⚠️  暂无最近数据")
        return

    current = states[-1]
    prev_10 = states[-10:] if len(states) >= 10 else states

    print("\n" + "="*60)
    print("🔔 关键信号提醒")
    print("="*60)

    print(f"\n⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊 当前状态: {current['state']} | ${current['price']:.5f}")

    alerts = []

    # 1. 状态变化提醒
    if len(states) > 1 and states[-1]['state'] != states[-2]['state']:
        alerts.append({
            'level': '🟡',
            'type': '状态变化',
            'message': f"{states[-2]['state']} → {current['state']}"
        })

    # 2. 强吸筹信号
    if current['state'] == '暗中吸筹' and current['iceberg_ratio'] > 0.8:
        avg_iceberg = sum(s['iceberg_ratio'] for s in prev_10) / len(prev_10)
        if avg_iceberg > 0.75:
            alerts.append({
                'level': '🟢',
                'type': '强吸筹',
                'message': f"持续强吸筹！冰山买单 {current['iceberg_ratio']*100:.1f}% (近期平均 {avg_iceberg*100:.1f}%)"
            })

    # 3. 分数突破
    if len(states) > 5:
        prev_scores = [s['score'] for s in states[-6:-1]]
        avg_prev_score = sum(prev_scores) / len(prev_scores)

        if current['score'] >= 60 and avg_prev_score < 55:
            alerts.append({
                'level': '🟢',
                'type': '分数突破',
                'message': f"分数突破60！当前{current['score']} (之前平均{avg_prev_score:.1f})"
            })
        elif current['score'] <= 35 and avg_prev_score > 40:
            alerts.append({
                'level': '🔴',
                'type': '分数下跌',
                'message': f"分数跌破35！当前{current['score']} (之前平均{avg_prev_score:.1f})"
            })

    # 4. 冰山买单剧变
    if len(states) > 5:
        prev_icebergs = [s['iceberg_ratio'] for s in states[-6:-1]]
        avg_prev_iceberg = sum(prev_icebergs) / len(prev_icebergs)

        iceberg_change = current['iceberg_ratio'] - avg_prev_iceberg

        if iceberg_change > 0.15:  # 上升超过15%
            alerts.append({
                'level': '🟢',
                'type': '买单激增',
                'message': f"冰山买单激增！从{avg_prev_iceberg*100:.1f}% → {current['iceberg_ratio']*100:.1f}%"
            })
        elif iceberg_change < -0.15:  # 下降超过15%
            alerts.append({
                'level': '🔴',
                'type': '买单骤减',
                'message': f"冰山买单骤减！从{avg_prev_iceberg*100:.1f}% → {current['iceberg_ratio']*100:.1f}%"
            })

    # 5. 诱多出货警告
    if current['state'] == '诱多出货':
        alerts.append({
            'level': '🚨',
            'type': '诱多出货',
            'message': f"诱多出货警告！分数{current['score']}但冰山买单仅{current['iceberg_ratio']*100:.1f}%"
        })

    # 6. 真实上涨确认
    if current['state'] == '真实上涨':
        alerts.append({
            'level': '🚀',
            'type': '上涨确认',
            'message': f"真实上涨确认！分数{current['score']} + 冰山买单{current['iceberg_ratio']*100:.1f}%"
        })

    # 7. 价格剧烈波动
    if len(states) > 10:
        prices = [s['price'] for s in states[-10:]]
        price_change = ((prices[-1] - prices[0]) / prices[0]) * 100

        if abs(price_change) > 2:  # 10个数据点内涨跌超过2%
            emoji = '📈' if price_change > 0 else '📉'
            alerts.append({
                'level': emoji,
                'type': '价格波动',
                'message': f"短期剧烈波动 {price_change:+.2f}%"
            })

    # 打印提醒
    if alerts:
        print(f"\n⚡ 检测到 {len(alerts)} 个关键信号:\n")
        for i, alert in enumerate(alerts, 1):
            print(f"{i}. {alert['level']} 【{alert['type']}】")
            print(f"   {alert['message']}\n")
    else:
        print(f"\n✅ 市场平稳，暂无特殊信号")

    # 当前建议
    print(f"💡 当前建议: {current['recommendation']}")
    print(f"📊 置信度: {current['confidence']:.1f}%")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    check_alerts()
