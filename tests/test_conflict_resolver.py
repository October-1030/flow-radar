#!/usr/bin/env python3
"""
ConflictResolver 单元测试

功能测试：
1. 6 场景冲突解决矩阵
2. 无冲突场景
3. 多组冲突同时处理
4. 优先级排序验证
5. 置信度惩罚应用
6. 边界情况处理

作者：Claude Code
日期：2026-01-09
版本：v1.0（Phase 2）
"""

import sys
from pathlib import Path
from typing import List

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.conflict_resolver import ConflictResolver
from core.signal_schema import SignalEvent
from datetime import datetime


# ==================== 辅助函数 ====================

def create_signal(signal_type: str, level: str, side: str,
                 price: float, confidence: float, ts: int = None) -> SignalEvent:
    """创建测试信号"""
    if ts is None:
        ts = int(datetime.now().timestamp())

    return SignalEvent(
        signal_type=signal_type,
        level=level,
        side=side,
        symbol='TEST_USDT',
        price=price,
        confidence=confidence,
        ts=ts,
        key=f"{signal_type}_{level}_{side}_{price}_{ts}",
        related_signals=[],
        confidence_modifier={
            'base': confidence,
            'resonance_boost': 0.0,
            'conflict_penalty': 0.0,
            'type_bonus': 0.0,
            'time_decay': 0.0,
            'final': confidence
        },
        data={'description': f"Test {signal_type} {level} {side}"}
    )


# ==================== 测试 1: 6 场景冲突矩阵 ====================

def test_conflict_scenarios():
    """测试所有 6 个冲突解决场景"""
    print("\n" + "="*70)
    print("测试 1: 6 场景冲突解决矩阵")
    print("="*70)

    resolver = ConflictResolver()
    base_ts = int(datetime.now().timestamp())

    # 场景 1: CRITICAL liq BUY vs CONFIRMED iceberg SELL → liq 胜出
    print("\n✓ 场景 1: CRITICAL liq vs CONFIRMED iceberg")
    sig1_buy = create_signal('liq', 'CRITICAL', 'BUY', 0.150, 85.0, base_ts)
    sig1_sell = create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 80.0, base_ts)

    result1 = resolver.resolve_conflicts([sig1_buy, sig1_sell])
    assert len(result1) == 2, "场景 1: 应返回两个信号"

    # 检查 liq 信号保持不变
    liq_signal = [s for s in result1 if s.signal_type == 'liq'][0]
    assert liq_signal.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "场景 1: liq 不应被惩罚"

    # 检查 iceberg 信号被惩罚
    iceberg_signal = [s for s in result1 if s.signal_type == 'iceberg'][0]
    assert iceberg_signal.confidence_modifier.get('conflict_penalty', 0) < 0, \
        "场景 1: iceberg 应被惩罚"

    print("✅ 测试 1.1: 场景 1 通过 - liq 优先于 iceberg")

    # 场景 2: CONFIRMED whale BUY vs CONFIRMED iceberg SELL → whale 胜出
    print("\n✓ 场景 2: CONFIRMED whale vs CONFIRMED iceberg")
    sig2_buy = create_signal('whale', 'CONFIRMED', 'BUY', 0.150, 85.0, base_ts)
    sig2_sell = create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 80.0, base_ts)

    result2 = resolver.resolve_conflicts([sig2_buy, sig2_sell])
    assert len(result2) == 2, "场景 2: 应返回两个信号"

    whale_signal = [s for s in result2 if s.signal_type == 'whale'][0]
    assert whale_signal.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "场景 2: whale 不应被惩罚"

    iceberg_signal = [s for s in result2 if s.signal_type == 'iceberg'][0]
    assert iceberg_signal.confidence_modifier.get('conflict_penalty', 0) < 0, \
        "场景 2: iceberg 应被惩罚"

    print("✅ 测试 1.2: 场景 2 通过 - whale 优先于 iceberg")

    # 场景 3: CONFIRMED iceberg BUY (85) vs CONFIRMED iceberg SELL (65) → 高置信度胜出
    print("\n✓ 场景 3: 同级同类，置信度优先")
    sig3_buy = create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 85.0, base_ts)
    sig3_sell = create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 65.0, base_ts)

    result3 = resolver.resolve_conflicts([sig3_buy, sig3_sell])
    assert len(result3) == 2, "场景 3: 应返回两个信号"

    high_conf = [s for s in result3 if s.confidence_modifier['base'] == 85.0][0]
    low_conf = [s for s in result3 if s.confidence_modifier['base'] == 65.0][0]

    assert high_conf.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "场景 3: 高置信度信号不应被惩罚"
    assert low_conf.confidence_modifier.get('conflict_penalty', 0) < 0, \
        "场景 3: 低置信度信号应被惩罚"

    print("✅ 测试 1.3: 场景 3 通过 - 高置信度优先")

    # 场景 4: WARNING iceberg BUY vs CRITICAL liq SELL → CRITICAL 胜出
    print("\n✓ 场景 4: 级别优先（WARNING vs CRITICAL）")
    sig4_buy = create_signal('iceberg', 'WARNING', 'BUY', 0.150, 85.0, base_ts)
    sig4_sell = create_signal('liq', 'CRITICAL', 'SELL', 0.150, 80.0, base_ts)

    result4 = resolver.resolve_conflicts([sig4_buy, sig4_sell])
    assert len(result4) == 2, "场景 4: 应返回两个信号"

    critical_signal = [s for s in result4 if s.level == 'CRITICAL'][0]
    warning_signal = [s for s in result4 if s.level == 'WARNING'][0]

    assert critical_signal.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "场景 4: CRITICAL 不应被惩罚"
    assert warning_signal.confidence_modifier.get('conflict_penalty', 0) < 0, \
        "场景 4: WARNING 应被惩罚"

    print("✅ 测试 1.4: 场景 4 通过 - CRITICAL 优先于 WARNING")

    # 场景 5: ACTIVITY iceberg BUY vs CONFIRMED whale SELL → CONFIRMED 胜出
    print("\n✓ 场景 5: 级别优先（ACTIVITY vs CONFIRMED）")
    sig5_buy = create_signal('iceberg', 'ACTIVITY', 'BUY', 0.150, 85.0, base_ts)
    sig5_sell = create_signal('whale', 'CONFIRMED', 'SELL', 0.150, 80.0, base_ts)

    result5 = resolver.resolve_conflicts([sig5_buy, sig5_sell])
    assert len(result5) == 2, "场景 5: 应返回两个信号"

    confirmed_signal = [s for s in result5 if s.level == 'CONFIRMED'][0]
    activity_signal = [s for s in result5 if s.level == 'ACTIVITY'][0]

    assert confirmed_signal.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "场景 5: CONFIRMED 不应被惩罚"
    assert activity_signal.confidence_modifier.get('conflict_penalty', 0) < 0, \
        "场景 5: ACTIVITY 应被惩罚"

    print("✅ 测试 1.5: 场景 5 通过 - CONFIRMED 优先于 ACTIVITY")

    # 场景 6: 同级同类 BUY vs SELL（置信度相同）→ 都被惩罚
    print("\n✓ 场景 6: 同级同类同置信度 → 都惩罚")
    sig6_buy = create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 75.0, base_ts)
    sig6_sell = create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 75.0, base_ts)

    result6 = resolver.resolve_conflicts([sig6_buy, sig6_sell])
    assert len(result6) == 2, "场景 6: 应返回两个信号"

    # 都应被惩罚
    for sig in result6:
        assert sig.confidence_modifier.get('conflict_penalty', 0) < 0, \
            "场景 6: 同级同类同置信度都应被惩罚"

    print("✅ 测试 1.6: 场景 6 通过 - 同级同类都被惩罚")

    print("\n✅ 测试 1 完成：6 场景冲突解决全部通过")


# ==================== 测试 2: 无冲突场景 ====================

def test_no_conflicts():
    """测试无冲突场景"""
    print("\n" + "="*70)
    print("测试 2: 无冲突场景")
    print("="*70)

    resolver = ConflictResolver()
    base_ts = int(datetime.now().timestamp())

    # 测试 2.1: 全部同向信号
    print("\n✓ 测试 2.1: 全部 BUY 信号")
    all_buy = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0, base_ts),
        create_signal('whale', 'CONFIRMED', 'BUY', 0.151, 85.0, base_ts),
        create_signal('liq', 'CRITICAL', 'BUY', 0.152, 90.0, base_ts),
    ]

    result1 = resolver.resolve_conflicts(all_buy)
    assert len(result1) == 3, "测试 2.1: 应保留所有信号"

    # 检查没有惩罚
    for sig in result1:
        assert sig.confidence_modifier.get('conflict_penalty', 0) == 0, \
            "测试 2.1: 同向信号不应被惩罚"

    print("✅ 测试 2.1: 全 BUY 信号无冲突")

    # 测试 2.2: 价格不重叠
    print("\n✓ 测试 2.2: 价格不重叠")
    no_overlap = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.100, 80.0, base_ts),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.200, 85.0, base_ts),
    ]

    result2 = resolver.resolve_conflicts(no_overlap)
    assert len(result2) == 2, "测试 2.2: 应保留所有信号"

    for sig in result2:
        assert sig.confidence_modifier.get('conflict_penalty', 0) == 0, \
            "测试 2.2: 价格不重叠不应冲突"

    print("✅ 测试 2.2: 价格不重叠无冲突")

    # 测试 2.3: 时间窗口外
    print("\n✓ 测试 2.3: 时间窗口外")
    time_separate = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0, base_ts),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 85.0, base_ts + 400),  # 6.67 分钟后
    ]

    result3 = resolver.resolve_conflicts(time_separate)
    assert len(result3) == 2, "测试 2.3: 应保留所有信号"

    for sig in result3:
        assert sig.confidence_modifier.get('conflict_penalty', 0) == 0, \
            "测试 2.3: 时间窗口外不应冲突"

    print("✅ 测试 2.3: 时间窗口外无冲突")

    print("\n✅ 测试 2 完成：无冲突场景全部通过")


# ==================== 测试 3: 多组冲突同时处理 ====================

def test_multi_group_conflicts():
    """测试多组冲突同时处理"""
    print("\n" + "="*70)
    print("测试 3: 多组冲突同时处理")
    print("="*70)

    resolver = ConflictResolver()
    base_ts = int(datetime.now().timestamp())

    # 创建两组冲突：
    # 组1: 0.150 价格 BUY vs SELL
    # 组2: 0.200 价格 BUY vs SELL
    signals = [
        # 组1
        create_signal('liq', 'CRITICAL', 'BUY', 0.150, 90.0, base_ts),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 75.0, base_ts),

        # 组2
        create_signal('whale', 'CONFIRMED', 'BUY', 0.200, 85.0, base_ts),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.200, 70.0, base_ts),
    ]

    result = resolver.resolve_conflicts(signals)
    assert len(result) == 4, "测试 3: 应返回所有信号"

    # 验证组1: liq 胜出，iceberg 被惩罚
    group1_liq = [s for s in result if s.signal_type == 'liq' and s.price == 0.150][0]
    group1_ice = [s for s in result if s.signal_type == 'iceberg' and s.price == 0.150][0]

    assert group1_liq.confidence_modifier.get('conflict_penalty', 0) == 0
    assert group1_ice.confidence_modifier.get('conflict_penalty', 0) < 0

    # 验证组2: whale 胜出，iceberg 被惩罚
    group2_whale = [s for s in result if s.signal_type == 'whale' and s.price == 0.200][0]
    group2_ice = [s for s in result if s.signal_type == 'iceberg' and s.price == 0.200][0]

    assert group2_whale.confidence_modifier.get('conflict_penalty', 0) == 0
    assert group2_ice.confidence_modifier.get('conflict_penalty', 0) < 0

    print("✅ 测试 3.1: 多组冲突独立处理")

    print("\n✅ 测试 3 完成：多组冲突处理通过")


# ==================== 测试 4: 冲突组内优先级 ====================

def test_conflict_group_priority():
    """测试冲突组内优先级判定"""
    print("\n" + "="*70)
    print("测试 4: 冲突组内优先级判定")
    print("="*70)

    resolver = ConflictResolver()
    base_ts = int(datetime.now().timestamp())

    # 测试 4.1: 多个 BUY vs 多个 SELL，验证高优先级信号保护
    print("\n✓ 测试 4.1: 多对多冲突中的优先级")
    signals = [
        # 高优先级 BUY
        create_signal('liq', 'CRITICAL', 'BUY', 0.150, 90.0, base_ts),
        # 低优先级 SELL
        create_signal('iceberg', 'INFO', 'SELL', 0.150, 60.0, base_ts),
        create_signal('iceberg', 'ACTIVITY', 'SELL', 0.150, 65.0, base_ts),
    ]

    result = resolver.resolve_conflicts(signals)
    assert len(result) == 3, "测试 4.1: 应保留所有信号"

    # CRITICAL liq 不应被惩罚
    liq_signal = [s for s in result if s.signal_type == 'liq'][0]
    assert liq_signal.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "测试 4.1: CRITICAL liq 不应被惩罚"

    # 低级别 iceberg 应被惩罚
    for sig in result:
        if sig.signal_type == 'iceberg':
            assert sig.confidence_modifier.get('conflict_penalty', 0) < 0, \
                "测试 4.1: 低优先级信号应被惩罚"

    print("✅ 测试 4.1: 冲突组内优先级正确")

    # 测试 4.2: 类型优先级（liq > whale > iceberg）
    print("\n✓ 测试 4.2: 类型优先级验证")
    signals2 = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 85.0, base_ts),
        create_signal('whale', 'CONFIRMED', 'SELL', 0.150, 85.0, base_ts),
    ]

    result2 = resolver.resolve_conflicts(signals2)
    whale = [s for s in result2 if s.signal_type == 'whale'][0]
    iceberg = [s for s in result2 if s.signal_type == 'iceberg'][0]

    assert whale.confidence_modifier.get('conflict_penalty', 0) == 0, \
        "测试 4.2: whale 应优先于 iceberg"
    assert iceberg.confidence_modifier.get('conflict_penalty', 0) < 0, \
        "测试 4.2: iceberg 应被惩罚"

    print("✅ 测试 4.2: 类型优先级正确")

    print("\n✅ 测试 4 完成：冲突组内优先级验证通过")


# ==================== 测试 5: 置信度惩罚应用 ====================

def test_confidence_penalty_application():
    """测试置信度惩罚正确应用"""
    print("\n" + "="*70)
    print("测试 5: 置信度惩罚应用")
    print("="*70)

    resolver = ConflictResolver()
    base_ts = int(datetime.now().timestamp())

    # 创建冲突信号
    sig_buy = create_signal('liq', 'CRITICAL', 'BUY', 0.150, 85.0, base_ts)
    sig_sell = create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 80.0, base_ts)

    result = resolver.resolve_conflicts([sig_buy, sig_sell])

    # 检查失败者被标记
    loser = [s for s in result if s.signal_type == 'iceberg'][0]

    assert 'conflict_penalty' in loser.confidence_modifier, \
        "测试 5: 失败者应有 conflict_penalty 字段"
    assert loser.confidence_modifier['conflict_penalty'] < 0, \
        "测试 5: conflict_penalty 应为负值"

    # 检查最终置信度更新
    expected_final = loser.confidence_modifier['base'] + loser.confidence_modifier['conflict_penalty']
    expected_final = max(0, min(100, expected_final))  # 限制在 [0, 100]

    assert loser.confidence_modifier['final'] == expected_final, \
        f"测试 5: 最终置信度应为 {expected_final}"

    print("✅ 测试 5.1: 置信度惩罚正确应用")

    print("\n✅ 测试 5 完成：置信度惩罚应用通过")


# ==================== 测试 6: 边界情况 ====================

def test_edge_cases():
    """测试边界情况"""
    print("\n" + "="*70)
    print("测试 6: 边界情况处理")
    print("="*70)

    resolver = ConflictResolver()

    # 测试 6.1: 空列表
    print("\n✓ 测试 6.1: 空列表")
    result1 = resolver.resolve_conflicts([])
    assert result1 == [], "测试 6.1: 空列表应返回空列表"
    print("✅ 测试 6.1: 空列表处理正确")

    # 测试 6.2: 单个信号
    print("\n✓ 测试 6.2: 单个信号")
    single = [create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0)]
    result2 = resolver.resolve_conflicts(single)
    assert len(result2) == 1, "测试 6.2: 单个信号应保留"
    assert result2[0].confidence_modifier.get('conflict_penalty', 0) == 0, \
        "测试 6.2: 单个信号不应被惩罚"
    print("✅ 测试 6.2: 单个信号处理正确")

    # 测试 6.3: 极端置信度
    print("\n✓ 测试 6.3: 极端置信度")
    base_ts = int(datetime.now().timestamp())
    extreme = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 0.0, base_ts),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.150, 100.0, base_ts),
    ]
    result3 = resolver.resolve_conflicts(extreme)
    assert len(result3) == 2, "测试 6.3: 应返回两个信号"

    # 验证置信度保持在 [0, 100] 范围
    for sig in result3:
        assert 0 <= sig.confidence_modifier['final'] <= 100, \
            "测试 6.3: 最终置信度应在 [0, 100] 范围内"

    print("✅ 测试 6.3: 极端置信度处理正确")

    print("\n✅ 测试 6 完成：边界情况处理全部通过")


# ==================== 主测试函数 ====================

def main():
    """运行所有测试"""
    print("="*70)
    print("ConflictResolver 单元测试")
    print("="*70)

    try:
        # 运行所有测试
        test_conflict_scenarios()       # 测试 1: 6 场景
        test_no_conflicts()             # 测试 2: 无冲突
        test_multi_group_conflicts()    # 测试 3: 多组冲突
        test_conflict_group_priority()  # 测试 4: 冲突组优先级
        test_confidence_penalty_application()  # 测试 5: 惩罚应用
        test_edge_cases()               # 测试 6: 边界情况

        # 汇总
        print("\n" + "="*70)
        print("测试汇总")
        print("="*70)
        print("总测试数: 6")
        print("通过: 6")
        print("失败: 0")
        print("通过率: 100.0%")
        print("\n✅ 所有测试通过！")

        return 0

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
