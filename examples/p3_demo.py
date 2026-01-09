#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - 完整演示

功能：
1. 读取历史事件数据（storage/events/*.jsonl.gz）
2. 提取冰山信号
3. 使用 UnifiedSignalManager 处理
4. 展示信号关联、排序、去重全流程
5. 生成可视化报告

作者：Claude Code
日期：2026-01-08
版本：v1.0
"""

import sys
from pathlib import Path
import gzip
import json
from datetime import datetime
from collections import defaultdict
from typing import List, Dict

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_signal_manager import UnifiedSignalManager
from core.signal_schema import IcebergSignal
from config.p3_settings import LEVEL_PRIORITY, TYPE_PRIORITY


# ==================== 数据读取 ====================

def read_event_files(events_dir: Path, max_files: int = 3) -> List[Dict]:
    """
    读取事件文件中的冰山信号

    Args:
        events_dir: 事件目录
        max_files: 最多读取文件数（避免数据量过大）

    Returns:
        冰山信号列表
    """
    print(f"\n{'='*60}")
    print("步骤 1: 读取历史事件数据")
    print(f"{'='*60}")

    event_files = sorted(events_dir.glob("*.jsonl.gz"))[-max_files:]  # 只取最新的几个文件

    if not event_files:
        print(f"❌ 未找到事件文件: {events_dir}")
        return []

    print(f"找到 {len(event_files)} 个事件文件（只读取最新 {max_files} 个）:")
    for f in event_files:
        print(f"  - {f.name}")

    iceberg_signals = []

    for event_file in event_files:
        try:
            with gzip.open(event_file, 'rt', encoding='utf-8') as f:
                for line_num, line in enumerate(f, start=1):
                    try:
                        event = json.loads(line.strip())

                        # 只提取冰山信号
                        if event.get('type') == 'iceberg':
                            iceberg_signals.append(event)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"  警告: 读取 {event_file.name} 失败: {e}")
            continue

    print(f"\n✅ 成功读取 {len(iceberg_signals)} 个冰山信号")
    return iceberg_signals


# ==================== 信号处理 ====================

def process_signals_demo(iceberg_dicts: List[Dict]) -> tuple:
    """
    使用 UnifiedSignalManager 处理信号

    Args:
        iceberg_dicts: 冰山信号字典列表

    Returns:
        (manager, processed_signals)
    """
    print(f"\n{'='*60}")
    print("步骤 2: 使用 UnifiedSignalManager 处理信号")
    print(f"{'='*60}")

    # 初始化管理器
    manager = UnifiedSignalManager()
    print("✅ UnifiedSignalManager 初始化完成")

    # 收集信号
    print(f"\n收集信号...")
    signals = manager.collect_signals(icebergs=iceberg_dicts)
    print(f"✅ 收集到 {len(signals)} 个信号")

    # 展示信号类型分布
    level_dist = defaultdict(int)
    for sig in signals:
        level_dist[sig.level] += 1

    print(f"\n信号级别分布:")
    for level in sorted(level_dist.keys(), key=lambda l: LEVEL_PRIORITY.get(l, 999)):
        count = level_dist[level]
        pct = count / len(signals) * 100 if signals else 0
        print(f"  {level:12s}: {count:4d} ({pct:5.1f}%)")

    # 处理信号
    print(f"\n处理信号（关联、排序、去重）...")
    processed = manager.process_signals(signals)
    print(f"✅ 处理完成，得到 {len(processed)} 个信号")

    # 统计信息
    stats = manager.get_stats()
    print(f"\n统计信息:")
    print(f"  总收集数: {stats['total_collected']}")
    print(f"  去重数量: {stats['deduplicated']}")
    print(f"  关联数量: {stats['correlated']}")
    print(f"  历史大小: {stats['history_size']}")

    return manager, processed


# ==================== 结果分析 ====================

def analyze_results(processed: List[IcebergSignal]):
    """
    分析处理后的信号

    Args:
        processed: 处理后的信号列表
    """
    print(f"\n{'='*60}")
    print("步骤 3: 分析处理结果")
    print(f"{'='*60}")

    if not processed:
        print("❌ 没有信号可分析")
        return

    # 1. 优先级分布
    print(f"\n1️⃣ 优先级分布（排序后）:")
    priority_counts = defaultdict(int)
    for sig in processed:
        priority = (sig.level, sig.signal_type)
        priority_counts[priority] += 1

    for priority, count in sorted(priority_counts.items(),
                                   key=lambda x: (LEVEL_PRIORITY.get(x[0][0], 999),
                                                 TYPE_PRIORITY.get(x[0][1], 999))):
        level, sig_type = priority
        pct = count / len(processed) * 100
        print(f"  {level:12s} / {sig_type:8s}: {count:4d} ({pct:5.1f}%)")

    # 2. 信号关联分析
    print(f"\n2️⃣ 信号关联分析:")
    with_relations = [s for s in processed if s.related_signals]
    without_relations = [s for s in processed if not s.related_signals]

    print(f"  有关联: {len(with_relations):4d} ({len(with_relations)/len(processed)*100:5.1f}%)")
    print(f"  无关联: {len(without_relations):4d} ({len(without_relations)/len(processed)*100:5.1f}%)")

    if with_relations:
        relation_counts = [len(s.related_signals) for s in with_relations]
        avg_relations = sum(relation_counts) / len(relation_counts)
        max_relations = max(relation_counts)
        print(f"  平均关联数: {avg_relations:.1f}")
        print(f"  最多关联数: {max_relations}")

    # 3. 置信度分析
    print(f"\n3️⃣ 置信度分析:")
    confidences = [s.confidence for s in processed]
    if confidences:
        print(f"  最小值: {min(confidences):.1f}%")
        print(f"  最大值: {max(confidences):.1f}%")
        print(f"  平均值: {sum(confidences)/len(confidences):.1f}%")

        # 置信度分段
        high = len([c for c in confidences if c >= 85])
        mid = len([c for c in confidences if 65 <= c < 85])
        low = len([c for c in confidences if c < 65])

        print(f"  高置信度 (≥85%): {high:4d} ({high/len(confidences)*100:5.1f}%)")
        print(f"  中置信度 (65-85%): {mid:4d} ({mid/len(confidences)*100:5.1f}%)")
        print(f"  低置信度 (<65%): {low:4d} ({low/len(confidences)*100:5.1f}%)")

    # 4. 买卖方向分布
    print(f"\n4️⃣ 买卖方向分布:")
    buy_signals = [s for s in processed if s.side == 'BUY']
    sell_signals = [s for s in processed if s.side == 'SELL']

    print(f"  BUY:  {len(buy_signals):4d} ({len(buy_signals)/len(processed)*100:5.1f}%)")
    print(f"  SELL: {len(sell_signals):4d} ({len(sell_signals)/len(processed)*100:5.1f}%)")

    # 5. 时间跨度
    print(f"\n5️⃣ 时间跨度:")
    timestamps = [s.ts for s in processed]
    if timestamps:
        min_ts = min(timestamps)
        max_ts = max(timestamps)
        duration = (max_ts - min_ts) / 3600  # 小时

        print(f"  开始时间: {datetime.fromtimestamp(min_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  结束时间: {datetime.fromtimestamp(max_ts).strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  时间跨度: {duration:.1f} 小时")


# ==================== 示例展示 ====================

def show_examples(processed: List[IcebergSignal], num: int = 5):
    """
    展示示例信号

    Args:
        processed: 处理后的信号列表
        num: 展示数量
    """
    print(f"\n{'='*60}")
    print(f"步骤 4: 示例信号展示（前 {num} 个）")
    print(f"{'='*60}")

    if not processed:
        print("❌ 没有信号可展示")
        return

    for i, sig in enumerate(processed[:num], 1):
        print(f"\n信号 {i}:")
        print(f"  类型: {sig.signal_type}")
        print(f"  级别: {sig.level}")
        print(f"  方向: {sig.side}")
        print(f"  价格: {sig.price}")
        print(f"  置信度: {sig.confidence:.1f}%")
        print(f"  补单次数: {sig.refill_count}")
        print(f"  强度: {sig.intensity:.2f}")
        print(f"  时间: {sig.get_readable_time()}")
        print(f"  Key: {sig.key}")

        if sig.related_signals:
            print(f"  关联信号 ({len(sig.related_signals)} 个):")
            for rel in sig.related_signals[:3]:  # 只显示前 3 个
                print(f"    → {rel}")


# ==================== 生成报告 ====================

def generate_report(manager: UnifiedSignalManager, processed: List[IcebergSignal],
                   output_file: Path):
    """
    生成文本报告

    Args:
        manager: UnifiedSignalManager 实例
        processed: 处理后的信号列表
        output_file: 输出文件路径
    """
    print(f"\n{'='*60}")
    print("步骤 5: 生成报告")
    print(f"{'='*60}")

    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# P3-2 多信号综合判断系统 - 演示报告\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # 统计信息
        stats = manager.get_stats()
        f.write("## 统计信息\n\n")
        f.write(f"- 总收集数: {stats['total_collected']}\n")
        f.write(f"- 处理后数量: {len(processed)}\n")
        f.write(f"- 去重数量: {stats['deduplicated']}\n")
        f.write(f"- 关联数量: {stats['correlated']}\n")
        f.write(f"- 去重率: {stats['deduplicated']/stats['total_collected']*100:.1f}%\n\n")

        # 优先级分布
        f.write("## 优先级分布\n\n")
        f.write("| 级别 | 类型 | 数量 | 占比 |\n")
        f.write("|------|------|------|------|\n")

        priority_counts = defaultdict(int)
        for sig in processed:
            priority = (sig.level, sig.signal_type)
            priority_counts[priority] += 1

        for priority, count in sorted(priority_counts.items(),
                                       key=lambda x: (LEVEL_PRIORITY.get(x[0][0], 999),
                                                     TYPE_PRIORITY.get(x[0][1], 999))):
            level, sig_type = priority
            pct = count / len(processed) * 100 if processed else 0
            f.write(f"| {level} | {sig_type} | {count} | {pct:.1f}% |\n")

        # 信号示例
        f.write("\n## 信号示例（前 10 个）\n\n")
        for i, sig in enumerate(processed[:10], 1):
            f.write(f"### 信号 {i}\n\n")
            f.write(f"- **级别**: {sig.level}\n")
            f.write(f"- **方向**: {sig.side}\n")
            f.write(f"- **价格**: {sig.price}\n")
            f.write(f"- **置信度**: {sig.confidence:.1f}%\n")
            f.write(f"- **补单次数**: {sig.refill_count}\n")
            f.write(f"- **强度**: {sig.intensity:.2f}\n")
            f.write(f"- **时间**: {sig.get_readable_time()}\n")

            if sig.related_signals:
                f.write(f"- **关联信号**: {len(sig.related_signals)} 个\n")

            f.write("\n")

    print(f"✅ 报告已生成: {output_file}")


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("="*60)
    print("P3-2 多信号综合判断系统 - 完整演示")
    print("="*60)
    print("\n这是一个端到端的演示，展示 P3-2 架构的完整流程：")
    print("1. 读取历史事件数据")
    print("2. 使用 UnifiedSignalManager 处理")
    print("3. 分析处理结果")
    print("4. 展示示例信号")
    print("5. 生成报告")

    # 配置
    events_dir = Path("storage/events")
    output_file = Path("docs/p3_demo_report.md")

    # 检查目录
    if not events_dir.exists():
        print(f"\n❌ 错误: 事件目录不存在: {events_dir}")
        print("   请确保 72h 验证已运行并生成了事件文件")
        return 1

    # 步骤 1: 读取数据
    iceberg_dicts = read_event_files(events_dir, max_files=2)  # 只读 2 个文件避免数据量过大

    if not iceberg_dicts:
        print("\n❌ 没有可用的冰山信号数据")
        return 1

    # 步骤 2: 处理信号
    manager, processed = process_signals_demo(iceberg_dicts)

    if not processed:
        print("\n❌ 信号处理失败")
        return 1

    # 步骤 3: 分析结果
    analyze_results(processed)

    # 步骤 4: 展示示例
    show_examples(processed, num=5)

    # 步骤 5: 生成报告
    generate_report(manager, processed, output_file)

    # 完成
    print(f"\n{'='*60}")
    print("✅ 演示完成！")
    print(f"{'='*60}")
    print(f"\n📊 报告位置: {output_file}")
    print(f"\n💡 下一步:")
    print(f"   1. 查看生成的报告")
    print(f"   2. 根据报告调整配置参数")
    print(f"   3. 考虑实际集成到 alert_monitor.py")

    return 0


if __name__ == "__main__":
    exit(main())
