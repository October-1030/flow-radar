#!/usr/bin/env python3
"""
Confidence Modifier 单元测试

测试覆盖：
1. 同向共振增强（+0 ~ +25）
2. 反向冲突惩罚（-5 ~ -10）
3. 类型组合奖励（iceberg+whale=+10 等）
4. 边界值测试（置信度限制 [0, 100]）
5. 空关联列表处理

作者：Claude Code
日期：2026-01-09
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.confidence_modifier import ConfidenceModifier
from core.signal_schema import IcebergSignal, WhaleSignal, LiqSignal


# ==================== 测试辅助函数 ====================

def create_iceberg(side, confidence=75.0, ts=1704800000):
    """创建测试冰山信号"""
    return IcebergSignal(
        ts=ts,
        symbol="DOGE/USDT",
        side=side,
        level='CONFIRMED',
        confidence=confidence,
        price=0.15,
        key=f"iceberg_{side}_{ts}",
        signal_type='iceberg'
    )


def create_whale(side, confidence=80.0, ts=1704800000):
    """创建测试鲸鱼信号"""
    return WhaleSignal(
        ts=ts,
        symbol="DOGE/USDT",
        side=side,
        level='CONFIRMED',
        confidence=confidence,
        price=0.15,
        key=f"whale_{side}_{ts}",
        signal_type='whale'
    )


def create_liq(side, confidence=85.0, ts=1704800000):
    """创建测试清算信号"""
    return LiqSignal(
        ts=ts,
        symbol="DOGE/USDT",
        side=side,
        level='CRITICAL',
        confidence=confidence,
        price=0.15,
        key=f"liq_{side}_{ts}",
        signal_type='liq'
    )


# ==================== 测试 1: 同向共振增强 ====================

def test_resonance_boost():
    """测试同向共振增强"""
    print("\n" + "="*70)
    print("测试 1: 同向共振增强")
    print("="*70)

    modifier = ConfidenceModifier()

    # 测试用例 1: 无关联信号（基础值）
    signal = create_iceberg('BUY', 75.0)
    result = modifier.calculate_modifier(signal, [])

    assert result['resonance_boost'] == 0, "测试失败：无关联应为 0"
    assert result['final'] == 75.0, "测试失败：最终值应等于基础值"
    print("✅ 测试 1.1: 无关联信号 - PASS")

    # 测试用例 2: 1 个同向信号（+5）
    related = [create_iceberg('BUY', 80.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['resonance_boost'] == 5.0, f"测试失败：1个同向应 +5，实际 {result['resonance_boost']}"
    assert result['final'] == 80.0, f"测试失败：最终值应为 80，实际 {result['final']}"
    print("✅ 测试 1.2: 1个同向信号 (+5) - PASS")

    # 测试用例 3: 3 个同向信号（+15）
    related = [
        create_iceberg('BUY', 80.0, 1704800060),
        create_iceberg('BUY', 82.0, 1704800120),
        create_iceberg('BUY', 78.0, 1704800180),
    ]
    result = modifier.calculate_modifier(signal, related)

    assert result['resonance_boost'] == 15.0, f"测试失败：3个同向应 +15，实际 {result['resonance_boost']}"
    assert result['final'] == 90.0, f"测试失败：最终值应为 90，实际 {result['final']}"
    print("✅ 测试 1.3: 3个同向信号 (+15) - PASS")

    # 测试用例 4: 5 个同向信号（上限 +25）
    related = [create_iceberg('BUY', 80.0, 1704800000 + i*60) for i in range(1, 6)]
    result = modifier.calculate_modifier(signal, related)

    assert result['resonance_boost'] == 25.0, f"测试失败：5个同向应达上限 +25，实际 {result['resonance_boost']}"
    assert result['final'] == 100.0, f"测试失败：最终值应为 100，实际 {result['final']}"
    print("✅ 测试 1.4: 5个同向信号（上限 +25）- PASS")

    # 测试用例 5: 10 个同向信号（仍是上限 +25）
    related = [create_iceberg('BUY', 80.0, 1704800000 + i*60) for i in range(1, 11)]
    result = modifier.calculate_modifier(signal, related)

    assert result['resonance_boost'] == 25.0, f"测试失败：超过5个仍应为上限 +25，实际 {result['resonance_boost']}"
    print("✅ 测试 1.5: 10个同向信号（保持上限）- PASS")

    print("✅ 测试 1 完成：同向共振增强全部通过")


# ==================== 测试 2: 反向冲突惩罚 ====================

def test_conflict_penalty():
    """测试反向冲突惩罚"""
    print("\n" + "="*70)
    print("测试 2: 反向冲突惩罚")
    print("="*70)

    modifier = ConfidenceModifier()

    # 测试用例 1: 1 个反向信号（-5）
    signal = create_iceberg('BUY', 75.0)
    related = [create_iceberg('SELL', 70.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['conflict_penalty'] == -5.0, f"测试失败：1个反向应 -5，实际 {result['conflict_penalty']}"
    assert result['final'] == 70.0, f"测试失败：最终值应为 70，实际 {result['final']}"
    print("✅ 测试 2.1: 1个反向信号 (-5) - PASS")

    # 测试用例 2: 2 个反向信号（上限 -10）
    related = [
        create_iceberg('SELL', 70.0, 1704800060),
        create_iceberg('SELL', 72.0, 1704800120),
    ]
    result = modifier.calculate_modifier(signal, related)

    assert result['conflict_penalty'] == -10.0, f"测试失败：2个反向应达上限 -10，实际 {result['conflict_penalty']}"
    assert result['final'] == 65.0, f"测试失败：最终值应为 65，实际 {result['final']}"
    print("✅ 测试 2.2: 2个反向信号（上限 -10）- PASS")

    # 测试用例 3: 5 个反向信号（仍是上限 -10）
    related = [create_iceberg('SELL', 70.0, 1704800000 + i*60) for i in range(1, 6)]
    result = modifier.calculate_modifier(signal, related)

    assert result['conflict_penalty'] == -10.0, f"测试失败：超过2个仍应为上限 -10，实际 {result['conflict_penalty']}"
    print("✅ 测试 2.3: 5个反向信号（保持上限）- PASS")

    # 测试用例 4: 混合（同向 + 反向）
    signal = create_iceberg('BUY', 75.0)
    related = [
        create_iceberg('BUY', 80.0, 1704800060),  # 同向
        create_iceberg('BUY', 82.0, 1704800120),  # 同向
        create_iceberg('SELL', 70.0, 1704800180), # 反向
    ]
    result = modifier.calculate_modifier(signal, related)

    assert result['resonance_boost'] == 10.0, "测试失败：2个同向应 +10"
    assert result['conflict_penalty'] == -5.0, "测试失败：1个反向应 -5"
    assert result['final'] == 80.0, f"测试失败：最终值应为 80 (75+10-5)，实际 {result['final']}"
    print("✅ 测试 2.4: 混合信号（同向+反向）- PASS")

    print("✅ 测试 2 完成：反向冲突惩罚全部通过")


# ==================== 测试 3: 类型组合奖励 ====================

def test_type_combo_bonus():
    """测试类型组合奖励"""
    print("\n" + "="*70)
    print("测试 3: 类型组合奖励")
    print("="*70)

    modifier = ConfidenceModifier()

    # 测试用例 1: iceberg + whale（+10）
    signal = create_iceberg('BUY', 75.0)
    related = [create_whale('BUY', 80.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['type_bonus'] == 10.0, f"测试失败：iceberg+whale应 +10，实际 {result['type_bonus']}"
    assert result['final'] == 90.0, f"测试失败：最终值应为 90 (75+5+10)，实际 {result['final']}"
    print("✅ 测试 3.1: iceberg + whale (+10) - PASS")

    # 测试用例 2: iceberg + liq（+15）
    signal = create_iceberg('BUY', 75.0)
    related = [create_liq('BUY', 85.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['type_bonus'] == 15.0, f"测试失败：iceberg+liq应 +15，实际 {result['type_bonus']}"
    assert result['final'] == 95.0, f"测试失败：最终值应为 95 (75+5+15)，实际 {result['final']}"
    print("✅ 测试 3.2: iceberg + liq (+15) - PASS")

    # 测试用例 3: whale + liq（+20）
    signal = create_whale('BUY', 75.0)
    related = [create_liq('BUY', 85.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['type_bonus'] == 20.0, f"测试失败：whale+liq应 +20，实际 {result['type_bonus']}"
    assert result['final'] == 100.0, f"测试失败：最终值应为 100 (75+5+20，上限100)，实际 {result['final']}"
    print("✅ 测试 3.3: whale + liq (+20) - PASS")

    # 测试用例 4: 三类型齐全（+30）
    signal = create_iceberg('BUY', 60.0)
    related = [
        create_whale('BUY', 80.0, 1704800060),
        create_liq('BUY', 85.0, 1704800120),
    ]
    result = modifier.calculate_modifier(signal, related)

    assert result['type_bonus'] == 30.0, f"测试失败：三类型齐全应 +30，实际 {result['type_bonus']}"
    assert result['final'] == 100.0, f"测试失败：最终值应为 100 (60+10+30，上限100)，实际 {result['final']}"
    print("✅ 测试 3.4: 三类型齐全 (+30) - PASS")

    # 测试用例 5: 同类型无奖励
    signal = create_iceberg('BUY', 75.0)
    related = [create_iceberg('BUY', 80.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['type_bonus'] == 0.0, f"测试失败：同类型应无奖励，实际 {result['type_bonus']}"
    print("✅ 测试 3.5: 同类型无奖励 - PASS")

    print("✅ 测试 3 完成：类型组合奖励全部通过")


# ==================== 测试 4: 边界值测试 ====================

def test_boundary_values():
    """测试边界值"""
    print("\n" + "="*70)
    print("测试 4: 边界值测试")
    print("="*70)

    modifier = ConfidenceModifier()

    # 测试用例 1: 最终置信度不能超过 100
    signal = create_iceberg('BUY', 95.0)
    related = [
        create_iceberg('BUY', 90.0, 1704800000 + i*60) for i in range(1, 6)  # +25
    ]
    result = modifier.calculate_modifier(signal, related)

    assert result['final'] == 100.0, f"测试失败：最终值不能超过100，实际 {result['final']}"
    print("✅ 测试 4.1: 最终置信度上限 100 - PASS")

    # 测试用例 2: 最终置信度不能低于 0
    signal = create_iceberg('BUY', 5.0)
    related = [
        create_iceberg('SELL', 70.0, 1704800000 + i*60) for i in range(1, 6)  # -10
    ]
    result = modifier.calculate_modifier(signal, related)

    assert result['final'] == 0.0, f"测试失败：最终值不能低于0，实际 {result['final']}"
    print("✅ 测试 4.2: 最终置信度下限 0 - PASS")

    # 测试用例 3: 初始置信度为 0
    signal = create_iceberg('BUY', 0.0)
    related = [create_iceberg('BUY', 80.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['base'] == 0.0, "测试失败：基础值应为 0"
    assert result['final'] == 5.0, f"测试失败：最终值应为 5 (0+5)，实际 {result['final']}"
    print("✅ 测试 4.3: 初始置信度为 0 - PASS")

    # 测试用例 4: 初始置信度为 100
    signal = create_iceberg('BUY', 100.0)
    related = [create_iceberg('BUY', 80.0, 1704800060)]
    result = modifier.calculate_modifier(signal, related)

    assert result['final'] == 100.0, f"测试失败：最终值保持100，实际 {result['final']}"
    print("✅ 测试 4.4: 初始置信度为 100 - PASS")

    print("✅ 测试 4 完成：边界值测试全部通过")


# ==================== 测试 5: 空关联列表处理 ====================

def test_empty_relations():
    """测试空关联列表处理"""
    print("\n" + "="*70)
    print("测试 5: 空关联列表处理")
    print("="*70)

    modifier = ConfidenceModifier()

    # 测试用例 1: 空列表
    signal = create_iceberg('BUY', 75.0)
    result = modifier.calculate_modifier(signal, [])

    assert result['resonance_boost'] == 0.0, "测试失败：空列表共振应为 0"
    assert result['conflict_penalty'] == 0.0, "测试失败：空列表惩罚应为 0"
    assert result['type_bonus'] == 0.0, "测试失败：空列表奖励应为 0"
    assert result['final'] == 75.0, "测试失败：空列表最终值应等于基础值"
    print("✅ 测试 5.1: 空关联列表 - PASS")

    # 测试用例 2: None 关联列表（边界）
    try:
        result = modifier.calculate_modifier(signal, None)
        # 如果支持 None，应转换为空列表
        print("✅ 测试 5.2: None 关联列表 - PASS")
    except (TypeError, AttributeError):
        # 如果不支持 None，应抛出异常
        print("✅ 测试 5.2: None 关联列表抛出异常 - PASS")

    print("✅ 测试 5 完成：空关联列表处理通过")


# ==================== 测试 6: apply_modifier 方法 ====================

def test_apply_modifier():
    """测试 apply_modifier 方法"""
    print("\n" + "="*70)
    print("测试 6: apply_modifier 方法")
    print("="*70)

    modifier = ConfidenceModifier()

    # 测试用例 1: 应用修改到信号对象
    signal = create_iceberg('BUY', 75.0)
    related = [create_iceberg('BUY', 80.0, 1704800060)]

    # 应用前
    assert signal.confidence == 75.0, "测试失败：应用前置信度应为75"
    assert not signal.confidence_modifier, "测试失败：应用前modifier应为空"

    # 应用修改
    modifier.apply_modifier(signal, related)

    # 应用后
    assert signal.confidence == 80.0, f"测试失败：应用后置信度应为80，实际 {signal.confidence}"
    assert signal.confidence_modifier['base'] == 75.0, "测试失败：基础值应记录"
    assert signal.confidence_modifier['resonance_boost'] == 5.0, "测试失败：共振应记录"
    assert signal.confidence_modifier['final'] == 80.0, "测试失败：最终值应记录"
    print("✅ 测试 6.1: apply_modifier 应用成功 - PASS")

    # 测试用例 2: batch_apply_modifiers
    signals = [
        create_iceberg('BUY', 75.0, 1704800000),
        create_iceberg('BUY', 80.0, 1704800060),
    ]

    relations = {
        signals[0].key: [signals[1].key],
        signals[1].key: [signals[0].key],
    }

    modifier.batch_apply_modifiers(signals, relations)

    # 验证两个信号都被修改
    assert signals[0].confidence == 80.0, "测试失败：信号1应被修改"
    assert signals[1].confidence == 85.0, "测试失败：信号2应被修改"
    print("✅ 测试 6.2: batch_apply_modifiers 批量应用 - PASS")

    print("✅ 测试 6 完成：apply_modifier 方法通过")


# ==================== 主测试函数 ====================

def run_all_tests():
    """运行所有测试"""
    print("="*70)
    print("Confidence Modifier 单元测试")
    print("="*70)

    tests = [
        ("同向共振增强", test_resonance_boost),
        ("反向冲突惩罚", test_conflict_penalty),
        ("类型组合奖励", test_type_combo_bonus),
        ("边界值测试", test_boundary_values),
        ("空关联列表处理", test_empty_relations),
        ("apply_modifier 方法", test_apply_modifier),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"❌ 测试失败: {name}")
            print(f"   错误: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ 测试异常: {name}")
            print(f"   错误: {e}")
            failed += 1

    # 汇总
    print("\n" + "="*70)
    print("测试汇总")
    print("="*70)
    print(f"总测试数: {len(tests)}")
    print(f"通过: {passed}")
    print(f"失败: {failed}")
    print(f"通过率: {passed/len(tests)*100:.1f}%")

    if failed == 0:
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print(f"\n❌ {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(run_all_tests())
