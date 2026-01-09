#!/usr/bin/env python3
"""
P3-2 Phase 2 演示脚本

功能：
1. 读取历史事件数据（storage/events/*.jsonl.gz）
2. 使用 process_signals_v2() 处理信号
3. 展示信号融合、置信度调整、冲突解决效果
4. 生成综合建议
5. 输出详细报告

作者：Claude Code
日期：2026-01-09
版本：v2.0（Phase 2）
"""

import sys
from pathlib import Path
import gzip
import json
from datetime import datetime
from typing import List, Dict

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_signal_manager import UnifiedSignalManager
from core.signal_schema import IcebergSignal
from core.bundle_advisor import BundleAdvisor


# ==================== 数据读取 ====================

def read_event_files(events_dir: Path, max_files: int = 2) -> List[Dict]:
    """
    读取事件文件中的冰山信号

    Args:
        events_dir: 事件目录
        max_files: 最多读取文件数

    Returns:
        冰山信号字典列表
    """
    print(f"\n{'='*70}")
    print("步骤 1: 读取历史事件数据")
    print(f"{'='*70}")

    event_files = sorted(events_dir.glob("*.jsonl.gz"))[-max_files:]

    if not event_files:
        print(f"❌ 未找到事件文件: {events_dir}")
        return []

    print(f"找到 {len(event_files)} 个事件文件（只读取最新 {max_files} 个）:")
    for f in event_files:
        print(f"  📁 {f.name}")

    iceberg_signals = []

    for event_file in event_files:
        try:
            with gzip.open(event_file, 'rt', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        if event.get('type') == 'iceberg':
                            iceberg_signals.append(event)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"  ⚠️  读取 {event_file.name} 失败: {e}")
            continue

    print(f"\n✅ 成功读取 {len(iceberg_signals)} 个冰山信号")
    return iceberg_signals


# ==================== Phase 2 处理演示 ====================

def demo_phase2_processing(iceberg_dicts: List[Dict]):
    """
    演示 Phase 2 信号处理流程

    Args:
        iceberg_dicts: 冰山信号字典列表
    """
    print(f"\n{'='*70}")
    print("步骤 2: Phase 2 信号处理（完整流程）")
    print(f"{'='*70}")

    # 初始化管理器
    manager = UnifiedSignalManager()
    print("✅ UnifiedSignalManager 初始化完成")

    # 收集信号
    print(f"\n📥 收集信号...")
    signals = manager.collect_signals(icebergs=iceberg_dicts)
    print(f"✅ 收集到 {len(signals)} 个信号")

    # Phase 2 处理
    print(f"\n🔄 执行 Phase 2 处理流程...")
    print("   1️⃣  信号融合（填充 related_signals）")
    print("   2️⃣  置信度调整（计算 confidence_modifier）")
    print("   3️⃣  冲突解决（处理 BUY vs SELL）")
    print("   4️⃣  优先级排序")
    print("   5️⃣  降噪去重")
    print("   6️⃣  生成综合建议")

    result = manager.process_signals_v2(signals)

    print(f"\n✅ Phase 2 处理完成！")
    print(f"   处理后信号数: {len(result['signals'])}")
    print(f"   综合建议: {result['advice']['advice']}")
    print(f"   建议置信度: {result['advice']['confidence']*100:.1f}%")

    return result


# ==================== 结果分析 ====================

def analyze_phase2_results(result: Dict):
    """
    分析 Phase 2 处理结果

    Args:
        result: process_signals_v2() 返回结果
    """
    signals = result['signals']
    advice = result['advice']
    stats = result['stats']

    print(f"\n{'='*70}")
    print("步骤 3: Phase 2 效果分析")
    print(f"{'='*70}")

    # 1. 信号融合效果
    print(f"\n1️⃣  信号融合效果:")
    with_relations = [s for s in signals if s.related_signals]
    print(f"   有关联的信号: {len(with_relations)}/{len(signals)} "
          f"({len(with_relations)/len(signals)*100:.1f}%)")

    if with_relations:
        total_relations = sum(len(s.related_signals) for s in with_relations)
        avg_relations = total_relations / len(with_relations)
        print(f"   平均关联数: {avg_relations:.1f}")
        print(f"   总关联关系: {total_relations}")

    # 2. 置信度调整效果
    print(f"\n2️⃣  置信度调整效果:")
    with_boost = [s for s in signals
                  if s.confidence_modifier.get('resonance_boost', 0) > 0]
    with_penalty = [s for s in signals
                   if s.confidence_modifier.get('conflict_penalty', 0) < 0]
    with_bonus = [s for s in signals
                  if s.confidence_modifier.get('type_bonus', 0) > 0]

    print(f"   共振增强: {len(with_boost)} 个信号")
    if with_boost:
        total_boost = sum(s.confidence_modifier.get('resonance_boost', 0)
                         for s in with_boost)
        print(f"              总增强: +{total_boost:.0f}")

    print(f"   冲突惩罚: {len(with_penalty)} 个信号")
    if with_penalty:
        total_penalty = sum(s.confidence_modifier.get('conflict_penalty', 0)
                          for s in with_penalty)
        print(f"              总惩罚: {total_penalty:.0f}")

    print(f"   类型组合: {len(with_bonus)} 个信号")
    if with_bonus:
        total_bonus = sum(s.confidence_modifier.get('type_bonus', 0)
                         for s in with_bonus)
        print(f"              总奖励: +{total_bonus:.0f}")

    # 3. 冲突解决效果
    print(f"\n3️⃣  冲突解决效果:")
    conflict_stats = stats.get('conflict_stats', {})
    print(f"   检测到冲突: {conflict_stats.get('conflicts_detected', 0)} 个")
    print(f"   已解决冲突: {conflict_stats.get('conflicts_resolved', 0)} 个")
    print(f"   惩罚信号数: {conflict_stats.get('signals_penalized', 0)} 个")

    # 4. 综合建议
    print(f"\n4️⃣  综合建议:")
    print(f"   建议级别: {advice['advice']}")
    print(f"   建议置信度: {advice['confidence']*100:.1f}%")
    print(f"   BUY 信号: {advice['buy_count']} 个（加权: {advice['weighted_buy']:.0f}）")
    print(f"   SELL 信号: {advice['sell_count']} 个（加权: {advice['weighted_sell']:.0f}）")
    print(f"   建议理由: {advice['reason']}")

    # 5. 性能统计
    print(f"\n5️⃣  性能统计:")
    fusion_stats = stats.get('fusion_stats', {})
    print(f"   总比较次数: {fusion_stats.get('total_checks', 0)}")
    print(f"   关联关系数: {fusion_stats.get('relations_found', 0)}")
    print(f"   处理耗时: {fusion_stats.get('processing_time', 0)*1000:.2f} ms")


# ==================== 信号展示 ====================

def show_signal_examples(signals: List[IcebergSignal], num: int = 5):
    """
    展示示例信号

    Args:
        signals: 信号列表
        num: 展示数量
    """
    print(f"\n{'='*70}")
    print(f"步骤 4: 信号详情展示（前 {num} 个）")
    print(f"{'='*70}")

    if not signals:
        print("❌ 没有信号可展示")
        return

    for i, sig in enumerate(signals[:num], 1):
        print(f"\n{'─'*70}")
        print(f"信号 {i}: {sig.level} {sig.signal_type} {sig.side}")
        print(f"{'─'*70}")
        print(f"  价格: {sig.price}")
        print(f"  时间: {sig.get_readable_time()}")
        print(f"  置信度: {sig.confidence:.1f}%")

        # 置信度调整明细
        modifier = sig.confidence_modifier
        if modifier:
            print(f"\n  置信度调整明细:")
            print(f"    基础: {modifier.get('base', 0):.1f}%")
            if modifier.get('resonance_boost', 0) > 0:
                print(f"    共振增强: +{modifier.get('resonance_boost', 0):.1f}")
            if modifier.get('conflict_penalty', 0) < 0:
                print(f"    冲突惩罚: {modifier.get('conflict_penalty', 0):.1f}")
            if modifier.get('type_bonus', 0) > 0:
                print(f"    类型奖励: +{modifier.get('type_bonus', 0):.1f}")
            print(f"    最终: {modifier.get('final', 0):.1f}%")

        # 关联信号
        if sig.related_signals:
            print(f"\n  关联信号: {len(sig.related_signals)} 个")
            for rel_key in sig.related_signals[:3]:
                print(f"    → {rel_key}")
            if len(sig.related_signals) > 3:
                print(f"    ... 还有 {len(sig.related_signals)-3} 个")

        # 冰山特有字段
        if sig.signal_type == 'iceberg':
            print(f"\n  冰山详情:")
            print(f"    补单次数: {sig.refill_count}")
            print(f"    强度: {sig.intensity:.2f}")
            print(f"    累计成交: {sig.cumulative_filled:.2f} USDT")


# ==================== Bundle 告警预览 ====================

def show_bundle_alert(advice: Dict, signals: List[IcebergSignal]):
    """
    展示 Bundle 告警消息预览

    Args:
        advice: 建议数据
        signals: 信号列表
    """
    print(f"\n{'='*70}")
    print("步骤 5: Bundle 告警消息预览")
    print(f"{'='*70}")

    advisor = BundleAdvisor()
    message = advisor.format_bundle_alert(advice, signals)

    print("\n" + message)


# ==================== 主函数 ====================

def main():
    """主函数"""
    print("="*70)
    print("P3-2 Phase 2 完整演示")
    print("="*70)
    print("\n本演示将展示 Phase 2 的全部功能：")
    print("  ✨ 信号融合（related_signals）")
    print("  ✨ 置信度调整（confidence_modifier）")
    print("  ✨ 冲突解决（6 场景矩阵）")
    print("  ✨ 综合建议（STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL）")
    print("  ✨ Bundle 告警格式")

    # 配置
    events_dir = Path("storage/events")

    # 检查目录
    if not events_dir.exists():
        print(f"\n❌ 错误: 事件目录不存在: {events_dir}")
        print("   请确保 72h 验证已运行并生成了事件文件")
        return 1

    # 步骤 1: 读取数据
    iceberg_dicts = read_event_files(events_dir, max_files=2)

    if not iceberg_dicts:
        print("\n❌ 没有可用的冰山信号数据")
        return 1

    # 步骤 2: Phase 2 处理
    result = demo_phase2_processing(iceberg_dicts)

    if not result['signals']:
        print("\n❌ 信号处理失败")
        return 1

    # 步骤 3: 结果分析
    analyze_phase2_results(result)

    # 步骤 4: 信号展示
    show_signal_examples(result['signals'], num=5)

    # 步骤 5: Bundle 告警预览
    show_bundle_alert(result['advice'], result['signals'])

    # 完成
    print(f"\n{'='*70}")
    print("✅ Phase 2 演示完成！")
    print(f"{'='*70}")
    print(f"\n📊 关键指标:")
    print(f"   原始信号: {len(iceberg_dicts)}")
    print(f"   处理后: {len(result['signals'])}")
    print(f"   去重率: {(1 - len(result['signals'])/len(iceberg_dicts))*100:.1f}%")
    print(f"   综合建议: {result['advice']['advice']}")
    print(f"   处理耗时: {result['stats'].get('fusion_stats', {}).get('processing_time', 0)*1000:.2f} ms")

    print(f"\n💡 下一步:")
    print(f"   1. 查看 Phase 2 效果分析")
    print(f"   2. 根据需要调整 config/p3_fusion_config.py 参数")
    print(f"   3. 运行单元测试验证正确性")
    print(f"   4. 集成到 alert_monitor.py")

    return 0


if __name__ == "__main__":
    exit(main())
