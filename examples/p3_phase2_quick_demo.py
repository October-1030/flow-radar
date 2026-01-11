#!/usr/bin/env python3
"""
P3-2 Phase 2 快速演示脚本

功能：使用合成数据快速展示 Phase 2 核心功能
- 信号融合
- 置信度调整
- 冲突解决
- Bundle 建议生成

作者：Claude Code
日期：2026-01-09
版本：v1.0（Phase 2 Quick Demo）
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_signal_manager import UnifiedSignalManager
from core.bundle_advisor import BundleAdvisor


# ==================== 创建演示数据 ====================

def create_demo_signals():
    """创建演示用的信号数据"""
    base_ts = int(datetime.now().timestamp())

    # 模拟真实场景：DOGE/USDT 在 0.150 价格附近的多个信号
    demo_data = [
        # 场景 1: 强烈 BUY 信号群（价格 0.1500 附近）
        {
            'type': 'liq',
            'symbol': 'DOGE_USDT',
            'ts': base_ts,
            'side': 'BUY',
            'level': 'CRITICAL',
            'price': 0.1500,
            'confidence': 92.0,
            'liquidation_price': 0.1500,
            'liquidated_value': 85000,
        },
        {
            'type': 'whale',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 30,  # 30 秒后
            'side': 'BUY',
            'level': 'CONFIRMED',
            'price': 0.1501,
            'confidence': 88.0,
            'avg_price': 0.1501,
            'total_qty': 150000,
        },
        {
            'type': 'iceberg',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 60,  # 1 分钟后
            'side': 'BUY',
            'level': 'CONFIRMED',
            'price': 0.1502,
            'confidence': 85.0,
            'intensity': 3.5,
            'refill_count': 4,
            'cumulative_filled': 12000,
        },

        # 场景 2: 弱 SELL 信号（应被冲突解决器惩罚）
        {
            'type': 'iceberg',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 90,  # 1.5 分钟后
            'side': 'SELL',
            'level': 'WARNING',
            'price': 0.1503,
            'confidence': 70.0,
            'intensity': 2.1,
            'refill_count': 2,
            'cumulative_filled': 5000,
        },

        # 场景 3: 另一个价格区域的独立信号（0.1600，不会关联）
        {
            'type': 'iceberg',
            'symbol': 'DOGE_USDT',
            'ts': base_ts + 120,  # 2 分钟后
            'side': 'BUY',
            'level': 'ACTIVITY',
            'price': 0.1600,
            'confidence': 65.0,
            'intensity': 1.8,
            'refill_count': 2,
            'cumulative_filled': 3000,
        },
    ]

    return demo_data


# ==================== 演示流程 ====================

def main():
    """主演示函数"""
    print("="*70)
    print("P3-2 Phase 2 快速演示")
    print("="*70)
    print("\n本演示展示 Phase 2 核心功能：")
    print("  🔗 信号融合（related_signals）")
    print("  📊 置信度调整（confidence_modifier）")
    print("  ⚔️  冲突解决（BUY vs SELL）")
    print("  💡 综合建议（STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL）")

    # 步骤 1: 创建演示数据
    print(f"\n{'='*70}")
    print("步骤 1: 创建演示数据")
    print(f"{'='*70}")

    demo_signals = create_demo_signals()
    print(f"\n✅ 创建了 {len(demo_signals)} 个信号:")
    for i, sig in enumerate(demo_signals, 1):
        print(f"  {i}. {sig['level']} {sig['type']} {sig['side']} @{sig['price']} (置信度: {sig['confidence']}%)")

    # 步骤 2: 初始化 UnifiedSignalManager
    print(f"\n{'='*70}")
    print("步骤 2: 初始化 UnifiedSignalManager")
    print(f"{'='*70}")

    manager = UnifiedSignalManager()
    print("\n✅ UnifiedSignalManager 初始化完成")

    # 步骤 3: 收集信号（转换为 SignalEvent）
    print(f"\n{'='*70}")
    print("步骤 3: 收集信号")
    print(f"{'='*70}")

    # 按类型分组
    icebergs = [s for s in demo_signals if s['type'] == 'iceberg']
    whales = [s for s in demo_signals if s['type'] == 'whale']
    liqs = [s for s in demo_signals if s['type'] == 'liq']

    signals = manager.collect_signals(
        icebergs=icebergs,
        whales=whales,
        liqs=liqs
    )

    print(f"\n✅ 收集到 {len(signals)} 个 SignalEvent 对象")

    # 步骤 4: 执行 Phase 2 处理
    print(f"\n{'='*70}")
    print("步骤 4: 执行 Phase 2 处理流程")
    print(f"{'='*70}")
    print("\n处理步骤:")
    print("  1️⃣  信号融合（填充 related_signals）")
    print("  2️⃣  置信度调整（计算 confidence_modifier）")
    print("  3️⃣  冲突解决（处理 BUY vs SELL）")
    print("  4️⃣  优先级排序")
    print("  5️⃣  降噪去重")
    print("  6️⃣  生成综合建议")

    result = manager.process_signals_v2(signals)

    print(f"\n✅ Phase 2 处理完成！")
    print(f"   处理后信号数: {len(result['signals'])}")
    print(f"   综合建议: {result['advice']['advice']}")
    print(f"   建议置信度: {result['advice']['confidence']*100:.1f}%")

    # 步骤 5: 分析处理结果
    print(f"\n{'='*70}")
    print("步骤 5: Phase 2 效果分析")
    print(f"{'='*70}")

    processed_signals = result['signals']
    advice = result['advice']

    # 5.1 信号融合效果
    print(f"\n1️⃣  信号融合效果:")
    with_relations = [s for s in processed_signals if s.related_signals]
    print(f"   有关联的信号: {len(with_relations)}/{len(processed_signals)} " +
          f"({len(with_relations)/len(processed_signals)*100:.1f}%)")

    if with_relations:
        total_relations = sum(len(s.related_signals) for s in with_relations)
        avg_relations = total_relations / len(with_relations)
        print(f"   平均关联数: {avg_relations:.1f}")
        print(f"   总关联关系: {total_relations}")

    # 5.2 置信度调整效果
    print(f"\n2️⃣  置信度调整效果:")
    with_boost = [s for s in processed_signals
                  if s.confidence_modifier.get('resonance_boost', 0) > 0]
    with_penalty = [s for s in processed_signals
                   if s.confidence_modifier.get('conflict_penalty', 0) < 0]
    with_bonus = [s for s in processed_signals
                  if s.confidence_modifier.get('type_bonus', 0) > 0]

    if with_boost:
        total_boost = sum(s.confidence_modifier.get('resonance_boost', 0) for s in with_boost)
        print(f"   共振增强: {len(with_boost)} 个信号，总增强: +{total_boost:.0f}")

    if with_penalty:
        total_penalty = sum(s.confidence_modifier.get('conflict_penalty', 0) for s in with_penalty)
        print(f"   冲突惩罚: {len(with_penalty)} 个信号，总惩罚: {total_penalty:.0f}")

    if with_bonus:
        total_bonus = sum(s.confidence_modifier.get('type_bonus', 0) for s in with_bonus)
        print(f"   类型奖励: {len(with_bonus)} 个信号，总奖励: +{total_bonus:.0f}")

    # 5.3 综合建议
    print(f"\n3️⃣  综合建议:")
    print(f"   建议级别: {advice['advice']}")
    print(f"   建议置信度: {advice['confidence']*100:.1f}%")
    print(f"   BUY 信号: {advice['buy_count']} 个（加权: {advice['weighted_buy']:.0f}）")
    print(f"   SELL 信号: {advice['sell_count']} 个（加权: {advice['weighted_sell']:.0f}）")
    print(f"   建议理由: {advice['reason']}")

    # 步骤 6: 展示信号详情
    print(f"\n{'='*70}")
    print(f"步骤 6: 信号详情（前 3 个）")
    print(f"{'='*70}")

    for i, sig in enumerate(processed_signals[:3], 1):
        print(f"\n{'─'*70}")
        print(f"信号 {i}: {sig.level} {sig.signal_type} {sig.side} @{sig.price}")
        print(f"{'─'*70}")
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
            for rel_key in sig.related_signals[:2]:
                print(f"    → {rel_key}")
            if len(sig.related_signals) > 2:
                print(f"    ... 还有 {len(sig.related_signals)-2} 个")

    # 步骤 7: Bundle 告警预览
    print(f"\n{'='*70}")
    print("步骤 7: Bundle 告警消息预览")
    print(f"{'='*70}")

    advisor = BundleAdvisor()
    message = advisor.format_bundle_alert(advice, processed_signals)

    print("\n" + message)

    # 完成总结
    print(f"\n{'='*70}")
    print("✅ Phase 2 演示完成！")
    print(f"{'='*70}")

    print(f"\n📊 关键指标:")
    print(f"   原始信号: {len(demo_signals)}")
    print(f"   处理后: {len(processed_signals)}")
    print(f"   关联信号数: {len(with_relations)}")
    print(f"   综合建议: {advice['advice']}")
    print(f"   建议置信度: {advice['confidence']*100:.1f}%")

    print(f"\n💡 Phase 2 核心特性:")
    print(f"   ✅ 信号融合：自动检测价格+时间关联")
    print(f"   ✅ 置信度调整：同向共振增强，反向冲突惩罚")
    print(f"   ✅ 冲突解决：优先级矩阵（类型>级别>置信度）")
    print(f"   ✅ 综合建议：加权计算，多级建议")
    print(f"   ✅ 告警格式：清晰展示，操作建议明确")

    return 0


if __name__ == "__main__":
    exit(main())
