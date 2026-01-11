#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速查看当前市场状态"""

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

def get_latest_state():
    """获取最新的市场状态"""
    storage_path = Path("C:/Users/rjtan/Downloads/flow-radar/storage/events")

    # 找到最新的文件
    files = sorted(storage_path.glob("DOGE_USDT_*.jsonl.gz"), reverse=True)
    if not files:
        return None

    latest_state = None

    # 读取最新文件
    try:
        with gzip.open(files[0], 'rt', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line.strip())
                    if event.get('type') == 'state':
                        data = event.get('data', {})
                        latest_state = {
                            'ts': event.get('ts'),
                            'time': datetime.fromtimestamp(event.get('ts')),
                            'state': data.get('state_name', 'Unknown'),
                            'score': data.get('score', 0),
                            'iceberg_ratio': data.get('iceberg_ratio', 0),
                            'price': data.get('price', 0),
                            'confidence': data.get('confidence', 0),
                            'recommendation': data.get('recommendation', ''),
                            'conclusion': data.get('conclusion', ''),
                            'cvd': data.get('cvd_total', 0),
                            'divergence': data.get('divergence', '')
                        }
                except:
                    continue
    except:
        pass

    return latest_state

def get_data_collection_stats():
    """获取数据收集统计"""
    storage_path = Path("C:/Users/rjtan/Downloads/flow-radar/storage/events")
    files = list(storage_path.glob("DOGE_USDT_*.jsonl.gz"))

    total_size = sum(f.stat().st_size for f in files)

    stats = {
        'file_count': len(files),
        'total_size_mb': total_size / 1024 / 1024,
        'files': []
    }

    for f in sorted(files):
        stats['files'].append({
            'name': f.name,
            'size_mb': f.stat().st_size / 1024 / 1024,
            'modified': datetime.fromtimestamp(f.stat().st_mtime)
        })

    return stats

def print_status():
    """打印当前状态"""
    print("\n" + "="*60)
    print("📊 DOGE/USDT 实时状态")
    print("="*60)

    # 获取最新状态
    state = get_latest_state()

    if not state:
        print("⚠️  暂无数据")
        return

    # 时间信息
    now = datetime.now()
    time_diff = (now - state['time']).total_seconds() / 60

    print(f"\n⏰ 更新时间: {state['time'].strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   ({time_diff:.1f}分钟前)" if time_diff < 60 else f"   ({time_diff/60:.1f}小时前)")

    # 市场状态
    state_emoji = {
        '暗中吸筹': '🟢',
        '真实上涨': '🟢',
        '多空博弈': '🟡',
        '暗中出货': '🔴',
        '诱多出货': '🔴',
        '真实下跌': '🔴'
    }
    emoji = state_emoji.get(state['state'], '⚪')

    print(f"\n{emoji} 市场状态: {state['state']}")
    print(f"💰 当前价格: ${state['price']:.5f}")
    print(f"📈 综合分数: {state['score']}/100")
    print(f"🧊 冰山买单: {state['iceberg_ratio']*100:.1f}%")

    # 置信度条
    conf_bar = "█" * int(state['confidence']/5) + "░" * (20 - int(state['confidence']/5))
    print(f"📊 置信度: [{conf_bar}] {state['confidence']:.1f}%")

    print(f"\n💡 结论: {state['conclusion']}")
    print(f"📋 建议: {state['recommendation']}")

    if state['divergence']:
        div_emoji = "📈" if state['divergence'] == 'bullish' else "📉" if state['divergence'] == 'bearish' else "➡️"
        print(f"{div_emoji} 背离: {state['divergence']}")

    if state['cvd']:
        cvd_emoji = "🟢" if state['cvd'] > 0 else "🔴"
        print(f"{cvd_emoji} CVD: {state['cvd']:,.0f}")

    # 关键提醒
    print(f"\n🔔 关键指标:")

    alerts = []

    if state['iceberg_ratio'] > 0.8:
        alerts.append("✅ 超强买单！冰山买单 >80%")
    elif state['iceberg_ratio'] > 0.65:
        alerts.append("✅ 买方占优，冰山买单 >65%")
    elif state['iceberg_ratio'] < 0.35:
        alerts.append("⚠️  卖方占优，冰山买单 <35%")

    if state['score'] >= 60:
        alerts.append("📈 表面偏多，分数≥60")
    elif state['score'] <= 35:
        alerts.append("📉 表面偏空，分数≤35")

    if state['state'] == '暗中吸筹' and state['iceberg_ratio'] > 0.75:
        alerts.append("🎯 洗盘吸筹机会！")
    elif state['state'] == '诱多出货':
        alerts.append("🚨 诱多出货警告！不要追高")
    elif state['state'] == '真实上涨':
        alerts.append("🚀 真实上涨确认！")

    if alerts:
        for alert in alerts:
            print(f"   {alert}")
    else:
        print(f"   - 市场相对平静")

    # 数据收集统计
    stats = get_data_collection_stats()
    print(f"\n📦 数据收集状态:")
    print(f"   文件数: {stats['file_count']}")
    print(f"   总大小: {stats['total_size_mb']:.1f} MB")

    if stats['files']:
        latest = stats['files'][-1]
        collection_time = (now - latest['modified']).total_seconds() / 60
        print(f"   最新文件: {latest['name']} ({latest['size_mb']:.1f} MB)")
        print(f"   最后更新: {latest['modified'].strftime('%H:%M:%S')} ({collection_time:.1f}分钟前)")

        if collection_time > 5:
            print(f"   ⚠️  数据超过5分钟未更新，检查程序是否运行")
        else:
            print(f"   ✅ 数据收集正常运行中")

    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    print_status()
