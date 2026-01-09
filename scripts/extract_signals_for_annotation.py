#!/usr/bin/env python3
"""
信号提取工具 - 为人工标注准备样本

功能：
1. 读取 storage/events/*.jsonl.gz 中的冰山信号
2. 抽样 N=30 个 CONFIRMED 信号
3. 输出到 CSV 格式（便于 Google Sheet 标注）

抽样策略：
- 时间分层：72h 平均分 6 个时段，每时段抽 5 个
- 买卖平衡：BUY/SELL 各约 15 个
- 置信度覆盖：高（80%+）、中（60-80%）、低（<60%）

输出字段：
ts, symbol, side, level, confidence, price, cumulative_filled, refill_count,
intensity, key, snippet_path, offset

隔离原则：
- 只做"读文件→抽样→导出"
- 不 import 运行中的核心模块（避免 side-effect）
- 不影响当前 72h 验证运行

作者：Claude Code
日期：2026-01-07
版本：v2.0 (三方会谈第二十二轮共识)
"""

import gzip
import json
import csv
import random
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from collections import defaultdict


# ==================== 配置参数 ====================

SAMPLE_SIZE = 30  # 抽样总数
TIME_BUCKETS = 6  # 时间分层数
SAMPLES_PER_BUCKET = 5  # 每时段抽样数

EVENTS_DIR = Path("storage/events")
OUTPUT_CSV = Path("docs/iceberg_annotation_samples.csv")

# CSV 输出字段
CSV_FIELDS = [
    'ts', 'symbol', 'side', 'level', 'confidence', 'price',
    'cumulative_filled', 'refill_count', 'intensity',
    'key', 'snippet_path', 'offset'
]


# ==================== 事件文件读取 ====================

def read_iceberg_signals(events_dir: Path) -> List[Dict]:
    """
    读取所有冰山信号事件

    Args:
        events_dir: 事件文件目录

    Returns:
        [(signal, snippet_path, offset), ...]
    """
    signals = []

    # 遍历所有 .jsonl.gz 文件
    event_files = sorted(events_dir.glob("*.jsonl.gz"))

    print(f"找到 {len(event_files)} 个事件文件")

    for event_file in event_files:
        print(f"正在读取: {event_file.name}")

        try:
            with gzip.open(event_file, 'rt', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    try:
                        event = json.loads(line.strip())

                        # 只提取冰山信号
                        if event.get('type') == 'iceberg':
                            # 添加定位信息
                            signal_with_meta = {
                                **event,
                                'snippet_path': str(event_file),
                                'offset': line_num
                            }
                            signals.append(signal_with_meta)

                    except json.JSONDecodeError as e:
                        print(f"  警告: {event_file.name}:{line_num} JSON 解析失败: {e}")
                        continue

        except Exception as e:
            print(f"  错误: 无法读取 {event_file.name}: {e}")
            continue

    print(f"\n总共读取到 {len(signals)} 个冰山信号")
    return signals


# ==================== 信号过滤 ====================

def filter_confirmed_signals(signals: List[Dict]) -> List[Dict]:
    """
    过滤出 CONFIRMED 级别的信号

    Args:
        signals: 所有冰山信号

    Returns:
        CONFIRMED 信号列表
    """
    confirmed = []

    for sig in signals:
        # 检查 level 字段（可能在 data 中或顶层）
        level = sig.get('level') or sig.get('data', {}).get('level')

        if level == 'CONFIRMED':
            confirmed.append(sig)

    print(f"过滤后得到 {len(confirmed)} 个 CONFIRMED 信号")
    return confirmed


# ==================== 分层抽样 ====================

def stratified_sampling(signals: List[Dict]) -> List[Dict]:
    """
    分层抽样算法

    策略：
    1. 按时间分层（6 个时段）
    2. 每时段按买卖方向分层
    3. 每层按置信度覆盖

    Args:
        signals: CONFIRMED 信号列表

    Returns:
        抽样后的信号列表（最多 30 个）
    """
    if not signals:
        print("警告: 没有可用信号进行抽样")
        return []

    # 1. 计算时间范围
    timestamps = [sig['ts'] for sig in signals]
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    time_range = max_ts - min_ts
    bucket_duration = time_range / TIME_BUCKETS if time_range > 0 else 1

    print(f"\n时间范围: {datetime.fromtimestamp(min_ts)} 到 {datetime.fromtimestamp(max_ts)}")
    print(f"每时段时长: {bucket_duration / 3600:.1f} 小时")

    # 2. 按时间和方向分组
    buckets = defaultdict(lambda: {'BUY': [], 'SELL': []})

    for sig in signals:
        # 计算时间桶索引
        bucket_idx = min(
            int((sig['ts'] - min_ts) / bucket_duration),
            TIME_BUCKETS - 1
        )

        # 获取买卖方向
        side = sig.get('side') or sig.get('data', {}).get('side', 'BUY')

        buckets[bucket_idx][side].append(sig)

    # 3. 从每个时段抽样
    sampled = []

    for bucket_idx in range(TIME_BUCKETS):
        buy_signals = buckets[bucket_idx]['BUY']
        sell_signals = buckets[bucket_idx]['SELL']

        # 计算本时段应抽样数
        target_buy = SAMPLES_PER_BUCKET // 2
        target_sell = SAMPLES_PER_BUCKET - target_buy

        # 从 BUY 抽样
        if buy_signals:
            # 按置信度排序后抽样（覆盖高中低）
            buy_signals_sorted = sorted(
                buy_signals,
                key=lambda s: s.get('confidence', s.get('data', {}).get('confidence', 0))
            )
            sampled_buy = sample_with_coverage(buy_signals_sorted, target_buy)
            sampled.extend(sampled_buy)
            print(f"  时段 {bucket_idx+1}: BUY 抽样 {len(sampled_buy)}/{len(buy_signals)}")

        # 从 SELL 抽样
        if sell_signals:
            sell_signals_sorted = sorted(
                sell_signals,
                key=lambda s: s.get('confidence', s.get('data', {}).get('confidence', 0))
            )
            sampled_sell = sample_with_coverage(sell_signals_sorted, target_sell)
            sampled.extend(sampled_sell)
            print(f"  时段 {bucket_idx+1}: SELL 抽样 {len(sampled_sell)}/{len(sell_signals)}")

    # 4. 如果不足 30 个，补充随机抽样
    if len(sampled) < SAMPLE_SIZE:
        remaining = [s for s in signals if s not in sampled]
        need = min(SAMPLE_SIZE - len(sampled), len(remaining))
        if need > 0:
            additional = random.sample(remaining, need)
            sampled.extend(additional)
            print(f"\n补充随机抽样 {need} 个信号")

    # 5. 如果超过 30 个，随机删减
    if len(sampled) > SAMPLE_SIZE:
        sampled = random.sample(sampled, SAMPLE_SIZE)

    print(f"\n最终抽样结果: {len(sampled)} 个信号")
    return sampled


def sample_with_coverage(signals: List[Dict], target: int) -> List[Dict]:
    """
    从排序后的信号中抽样，确保覆盖高中低置信度

    Args:
        signals: 按置信度排序的信号列表
        target: 目标抽样数

    Returns:
        抽样结果
    """
    if not signals:
        return []

    n = len(signals)
    if n <= target:
        return signals

    # 分三段抽样（低、中、高置信度）
    low_end = n // 3
    mid_start = n // 3
    mid_end = 2 * n // 3
    high_start = 2 * n // 3

    samples_per_tier = max(1, target // 3)

    sampled = []

    # 低置信度抽样
    if low_end > 0:
        sampled.extend(random.sample(signals[:low_end], min(samples_per_tier, low_end)))

    # 中置信度抽样
    mid_signals = signals[mid_start:mid_end]
    if mid_signals:
        sampled.extend(random.sample(mid_signals, min(samples_per_tier, len(mid_signals))))

    # 高置信度抽样
    high_signals = signals[high_start:]
    if high_signals:
        remaining = target - len(sampled)
        sampled.extend(random.sample(high_signals, min(remaining, len(high_signals))))

    return sampled


# ==================== CSV 输出 ====================

def export_to_csv(signals: List[Dict], output_path: Path):
    """
    导出信号到 CSV 文件

    Args:
        signals: 信号列表
        output_path: 输出文件路径
    """
    # 确保输出目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 提取字段值
    rows = []
    for sig in signals:
        data = sig.get('data', {})

        row = {
            'ts': sig.get('ts', 0),
            'symbol': sig.get('symbol', data.get('symbol', '')),
            'side': sig.get('side', data.get('side', '')),
            'level': sig.get('level', data.get('level', '')),
            'confidence': sig.get('confidence', data.get('confidence', 0)),
            'price': data.get('price', 0),
            'cumulative_filled': data.get('cumulative_filled', 0),
            'refill_count': data.get('refill_count', 0),
            'intensity': data.get('intensity', 0),
            'key': sig.get('key', ''),
            'snippet_path': sig.get('snippet_path', ''),
            'offset': sig.get('offset', 0),
        }
        rows.append(row)

    # 按时间排序
    rows.sort(key=lambda r: r['ts'])

    # 写入 CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ 已导出 {len(rows)} 个信号到: {output_path}")

    # 打印统计信息
    print("\n📊 统计信息:")
    print(f"  - BUY 信号: {sum(1 for r in rows if r['side'] == 'BUY')}")
    print(f"  - SELL 信号: {sum(1 for r in rows if r['side'] == 'SELL')}")

    confidences = [r['confidence'] for r in rows]
    if confidences:
        print(f"  - 置信度范围: {min(confidences):.1f}% - {max(confidences):.1f}%")
        print(f"  - 平均置信度: {sum(confidences) / len(confidences):.1f}%")


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("=" * 60)
    print("Flow Radar - 信号提取工具 v2.0")
    print("三方会谈第二十二轮共识")
    print("=" * 60)
    print()

    # 1. 检查事件目录
    if not EVENTS_DIR.exists():
        print(f"❌ 错误: 事件目录不存在: {EVENTS_DIR}")
        return

    # 2. 读取所有冰山信号
    print("Step 1: 读取事件文件...")
    all_signals = read_iceberg_signals(EVENTS_DIR)

    if not all_signals:
        print("❌ 错误: 没有找到任何冰山信号")
        return

    # 3. 过滤 CONFIRMED 信号
    print("\nStep 2: 过滤 CONFIRMED 信号...")
    confirmed_signals = filter_confirmed_signals(all_signals)

    if not confirmed_signals:
        print("❌ 错误: 没有找到 CONFIRMED 级别的信号")
        print("   提示: 可能需要等待 72h 验证运行一段时间后再抽样")
        return

    # 4. 分层抽样
    print("\nStep 3: 分层抽样...")
    sampled_signals = stratified_sampling(confirmed_signals)

    if not sampled_signals:
        print("❌ 错误: 抽样失败")
        return

    # 5. 导出 CSV
    print("\nStep 4: 导出 CSV...")
    export_to_csv(sampled_signals, OUTPUT_CSV)

    print("\n" + "=" * 60)
    print("✅ 信号提取完成！")
    print("=" * 60)
    print(f"\n下一步：")
    print(f"1. 打开 {OUTPUT_CSV}")
    print(f"2. 导入到 Google Sheet")
    print(f"3. 添加 'annotation' 列（HIT/MISS/UNCERTAIN）")
    print(f"4. 进行人工标注")


if __name__ == "__main__":
    main()
