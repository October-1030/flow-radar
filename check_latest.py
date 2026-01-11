#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查最新数据"""

import sys
import io
import gzip
import json
from pathlib import Path
from datetime import datetime

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

storage_path = Path("C:/Users/rjtan/OneDrive/文档/ProjectS/flow-radar/storage/events")

# 找最新文件
files = sorted(storage_path.glob("DOGE_USDT_*.jsonl.gz"), reverse=True)

print("="*70)
print("📊 最新数据检查")
print("="*70)

if not files:
    print("未找到数据文件")
else:
    latest = files[0]
    print(f"\n最新文件: {latest.name}")
    print(f"大小: {latest.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"修改时间: {datetime.fromtimestamp(latest.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")

    # 读取最后几行
    latest_state = None
    try:
        with gzip.open(latest, 'rt', encoding='utf-8') as f:
            lines = []
            for line in f:
                lines.append(line)
                if len(lines) > 100:
                    lines.pop(0)

            # 从后往前找最新的state
            for line in reversed(lines):
                try:
                    event = json.loads(line.strip())
                    if event.get('type') == 'state':
                        data = event.get('data', {})
                        latest_state = {
                            'time': datetime.fromtimestamp(event.get('ts')),
                            'state': data.get('state_name', 'Unknown'),
                            'price': data.get('price', 0),
                            'score': data.get('score', 0),
                            'iceberg_ratio': data.get('iceberg_ratio', 0),
                            'confidence': data.get('confidence', 0),
                            'recommendation': data.get('recommendation', ''),
                            'cvd': data.get('cvd_total', 0),
                        }
                        break
                except:
                    continue
    except Exception as e:
        print(f"读取错误: {e}")

    if latest_state:
        print(f"\n📍 最新状态 ({latest_state['time'].strftime('%Y-%m-%d %H:%M:%S')}):")
        print(f"   💰 价格: ${latest_state['price']:.5f}")
        print(f"   📈 分数: {latest_state['score']}/100")
        print(f"   🧊 冰山买单: {latest_state['iceberg_ratio']*100:.1f}%")
        print(f"   🟡 状态: {latest_state['state']}")
        print(f"   📋 建议: {latest_state['recommendation']}")
        print(f"   📊 CVD: {latest_state['cvd']:,.0f}")
        print(f"   🎯 置信度: {latest_state['confidence']:.1f}%")

        # 时间差
        now = datetime.now()
        time_diff = (now - latest_state['time']).total_seconds() / 60

        print(f"\n⏰ 数据新鲜度: {time_diff:.1f} 分钟前")

        if time_diff < 5:
            print("   ✅ 数据收集正常运行中")
        elif time_diff < 60:
            print(f"   ⚠️  数据 {time_diff:.0f} 分钟未更新")
        else:
            print(f"   🔴 数据 {time_diff/60:.1f} 小时未更新，程序可能已停止")

print("\n" + "="*70)
print(f"\n所有数据文件 ({len(files)} 个):")
for f in files[:6]:
    print(f"  {f.name:40s} {f.stat().st_size/1024/1024:6.1f} MB")

print("\n总数据量: {:.1f} MB".format(sum(f.stat().st_size for f in files) / 1024 / 1024))
print("="*70)
