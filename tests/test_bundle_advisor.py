#!/usr/bin/env python3
"""
BundleAdvisor 单元测试

功能测试：
1. 5 种建议级别（STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL）
2. 加权计算验证（type_weight × level_weight × confidence）
3. 告警格式化
4. 边界情况处理
5. 理由生成

作者：Claude Code
日期：2026-01-09
版本：v1.0（Phase 2）
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.bundle_advisor import BundleAdvisor
from core.signal_schema import SignalEvent


# ==================== 辅助函数 ====================

def create_signal(signal_type: str, level: str, side: str,
                 price: float, confidence: float) -> SignalEvent:
    """创建测试信号"""
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
        }
    )


# ==================== 测试 1: STRONG_BUY 场景 ====================

def test_strong_buy():
    """测试 STRONG_BUY 建议生成"""
    print("\n" + "="*70)
    print("测试 1: STRONG_BUY 建议生成")
    print("="*70)

    advisor = BundleAdvisor()

    # 场景 1.1: 3 个高质量 BUY vs 1 个低质量 SELL
    print("\n✓ 测试 1.1: 多个高质量 BUY 信号")
    signals = [
        create_signal('liq', 'CRITICAL', 'BUY', 0.150, 90.0),
        create_signal('whale', 'CONFIRMED', 'BUY', 0.150, 85.0),
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0),
        create_signal('iceberg', 'WARNING', 'SELL', 0.151, 65.0),
    ]

    result = advisor.generate_advice(signals)

    assert result['advice'] == 'STRONG_BUY', \
        f"测试 1.1: 应为 STRONG_BUY，实际为 {result['advice']}"
    assert result['buy_count'] == 3, "测试 1.1: buy_count 应为 3"
    assert result['sell_count'] == 1, "测试 1.1: sell_count 应为 1"
    assert result['weighted_buy'] > result['weighted_sell'] * 1.5, \
        "测试 1.1: weighted_buy 应 > weighted_sell * 1.5"
    assert result['confidence'] > 0.0, \
        "测试 1.1: 置信度应 > 0"
    assert result['confidence'] <= 1.0, \
        "测试 1.1: 置信度应 <= 1.0"

    print(f"  建议: {result['advice']}")
    print(f"  BUY加权: {result['weighted_buy']:.1f}, SELL加权: {result['weighted_sell']:.1f}")
    print(f"  置信度: {result['confidence']*100:.1f}%")
    print("✅ 测试 1.1: STRONG_BUY 生成正确")

    # 场景 1.2: 单个 CRITICAL liq BUY
    print("\n✓ 测试 1.2: 单个 CRITICAL 信号")
    signals2 = [
        create_signal('liq', 'CRITICAL', 'BUY', 0.150, 95.0),
    ]

    result2 = advisor.generate_advice(signals2)
    assert result2['advice'] == 'STRONG_BUY', \
        f"测试 1.2: 单个 CRITICAL 应为 STRONG_BUY"

    print(f"  建议: {result2['advice']}")
    print("✅ 测试 1.2: 单个 CRITICAL 信号正确")

    print("\n✅ 测试 1 完成：STRONG_BUY 场景全部通过")


# ==================== 测试 2: BUY 场景 ====================

def test_buy():
    """测试 BUY 建议生成"""
    print("\n" + "="*70)
    print("测试 2: BUY 建议生成")
    print("="*70)

    advisor = BundleAdvisor()

    # 场景 2.1: BUY 略强于 SELL（加权比 ~1.2）
    print("\n✓ 测试 2.1: BUY 略强于 SELL")
    signals = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0),
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 75.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 85.0),
        create_signal('iceberg', 'WARNING', 'SELL', 0.151, 70.0),
    ]

    result = advisor.generate_advice(signals)

    assert result['advice'] == 'BUY', \
        f"测试 2.1: 应为 BUY，实际为 {result['advice']}"
    assert result['buy_count'] == 2, "测试 2.1: buy_count 应为 2"
    assert result['sell_count'] == 2, "测试 2.1: sell_count 应为 2"
    assert result['weighted_buy'] > result['weighted_sell'], \
        "测试 2.1: weighted_buy 应 > weighted_sell"
    assert result['weighted_buy'] <= result['weighted_sell'] * 1.5, \
        "测试 2.1: weighted_buy 应 <= weighted_sell * 1.5"

    print(f"  建议: {result['advice']}")
    print(f"  BUY加权: {result['weighted_buy']:.1f}, SELL加权: {result['weighted_sell']:.1f}")
    print("✅ 测试 2.1: BUY 生成正确")

    print("\n✅ 测试 2 完成：BUY 场景全部通过")


# ==================== 测试 3: WATCH 场景 ====================

def test_watch():
    """测试 WATCH 建议生成"""
    print("\n" + "="*70)
    print("测试 3: WATCH 建议生成")
    print("="*70)

    advisor = BundleAdvisor()

    # 场景 3.1: BUY 和 SELL 势均力敌
    print("\n✓ 测试 3.1: 势均力敌")
    signals = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 80.0),
    ]

    result = advisor.generate_advice(signals)

    assert result['advice'] == 'WATCH', \
        f"测试 3.1: 应为 WATCH，实际为 {result['advice']}"
    assert result['buy_count'] == 1, "测试 3.1: buy_count 应为 1"
    assert result['sell_count'] == 1, "测试 3.1: sell_count 应为 1"

    print(f"  建议: {result['advice']}")
    print(f"  BUY加权: {result['weighted_buy']:.1f}, SELL加权: {result['weighted_sell']:.1f}")
    print("✅ 测试 3.1: WATCH 生成正确")

    # 场景 3.2: 多对多势均力敌
    print("\n✓ 测试 3.2: 多对多势均力敌")
    signals2 = [
        create_signal('whale', 'CONFIRMED', 'BUY', 0.150, 85.0),
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 75.0),
        create_signal('whale', 'CONFIRMED', 'SELL', 0.151, 85.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 75.0),
    ]

    result2 = advisor.generate_advice(signals2)
    assert result2['advice'] == 'WATCH', \
        f"测试 3.2: 多对多应为 WATCH"

    print(f"  建议: {result2['advice']}")
    print("✅ 测试 3.2: 多对多 WATCH 正确")

    print("\n✅ 测试 3 完成：WATCH 场景全部通过")


# ==================== 测试 4: SELL 场景 ====================

def test_sell():
    """测试 SELL 建议生成"""
    print("\n" + "="*70)
    print("测试 4: SELL 建议生成")
    print("="*70)

    advisor = BundleAdvisor()

    # 场景 4.1: SELL 略强于 BUY（加权比 ~1.2）
    print("\n✓ 测试 4.1: SELL 略强于 BUY")
    signals = [
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 85.0),
        create_signal('iceberg', 'WARNING', 'BUY', 0.150, 70.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 80.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 75.0),
    ]

    result = advisor.generate_advice(signals)

    assert result['advice'] == 'SELL', \
        f"测试 4.1: 应为 SELL，实际为 {result['advice']}"
    assert result['buy_count'] == 2, "测试 4.1: buy_count 应为 2"
    assert result['sell_count'] == 2, "测试 4.1: sell_count 应为 2"
    assert result['weighted_sell'] > result['weighted_buy'], \
        "测试 4.1: weighted_sell 应 > weighted_buy"
    assert result['weighted_sell'] <= result['weighted_buy'] * 1.5, \
        "测试 4.1: weighted_sell 应 <= weighted_buy * 1.5"

    print(f"  建议: {result['advice']}")
    print(f"  BUY加权: {result['weighted_buy']:.1f}, SELL加权: {result['weighted_sell']:.1f}")
    print("✅ 测试 4.1: SELL 生成正确")

    print("\n✅ 测试 4 完成：SELL 场景全部通过")


# ==================== 测试 5: STRONG_SELL 场景 ====================

def test_strong_sell():
    """测试 STRONG_SELL 建议生成"""
    print("\n" + "="*70)
    print("测试 5: STRONG_SELL 建议生成")
    print("="*70)

    advisor = BundleAdvisor()

    # 场景 5.1: 多个高质量 SELL vs 1 个低质量 BUY
    print("\n✓ 测试 5.1: 多个高质量 SELL 信号")
    signals = [
        create_signal('iceberg', 'WARNING', 'BUY', 0.150, 65.0),
        create_signal('liq', 'CRITICAL', 'SELL', 0.151, 90.0),
        create_signal('whale', 'CONFIRMED', 'SELL', 0.151, 85.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 80.0),
    ]

    result = advisor.generate_advice(signals)

    assert result['advice'] == 'STRONG_SELL', \
        f"测试 5.1: 应为 STRONG_SELL，实际为 {result['advice']}"
    assert result['buy_count'] == 1, "测试 5.1: buy_count 应为 1"
    assert result['sell_count'] == 3, "测试 5.1: sell_count 应为 3"
    assert result['weighted_sell'] > result['weighted_buy'] * 1.5, \
        "测试 5.1: weighted_sell 应 > weighted_buy * 1.5"
    assert result['confidence'] > 0.0, \
        "测试 5.1: 置信度应 > 0"
    assert result['confidence'] <= 1.0, \
        "测试 5.1: 置信度应 <= 1.0"

    print(f"  建议: {result['advice']}")
    print(f"  BUY加权: {result['weighted_buy']:.1f}, SELL加权: {result['weighted_sell']:.1f}")
    print(f"  置信度: {result['confidence']*100:.1f}%")
    print("✅ 测试 5.1: STRONG_SELL 生成正确")

    # 场景 5.2: 单个 CRITICAL liq SELL
    print("\n✓ 测试 5.2: 单个 CRITICAL SELL 信号")
    signals2 = [
        create_signal('liq', 'CRITICAL', 'SELL', 0.150, 95.0),
    ]

    result2 = advisor.generate_advice(signals2)
    assert result2['advice'] == 'STRONG_SELL', \
        f"测试 5.2: 单个 CRITICAL SELL 应为 STRONG_SELL"

    print(f"  建议: {result2['advice']}")
    print("✅ 测试 5.2: 单个 CRITICAL SELL 正确")

    print("\n✅ 测试 5 完成：STRONG_SELL 场景全部通过")


# ==================== 测试 6: 加权计算验证 ====================

def test_weighted_calculation():
    """测试加权计算逻辑"""
    print("\n" + "="*70)
    print("测试 6: 加权计算验证")
    print("="*70)

    advisor = BundleAdvisor()

    # 测试 6.1: 类型权重（liq:3, whale:2, iceberg:1）
    print("\n✓ 测试 6.1: 类型权重验证")
    signals = [
        create_signal('liq', 'CONFIRMED', 'BUY', 0.150, 80.0),      # 3 * 2.0 * 80 = 480
        create_signal('whale', 'CONFIRMED', 'BUY', 0.150, 80.0),    # 2 * 2.0 * 80 = 320
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0),  # 1 * 2.0 * 80 = 160
    ]

    result = advisor.generate_advice(signals)

    # 总加权: 480 + 320 + 160 = 960
    expected_weighted = 480 + 320 + 160
    assert result['weighted_buy'] == expected_weighted, \
        f"测试 6.1: 加权应为 {expected_weighted}，实际为 {result['weighted_buy']}"

    print(f"  BUY加权: {result['weighted_buy']:.1f}")
    print("✅ 测试 6.1: 类型权重正确")

    # 测试 6.2: 级别权重（CRITICAL:3, CONFIRMED:2, WARNING:1.5, ACTIVITY:1, INFO:0.5）
    print("\n✓ 测试 6.2: 级别权重验证")
    signals2 = [
        create_signal('iceberg', 'CRITICAL', 'BUY', 0.150, 80.0),   # 1 * 3.0 * 80 = 240
        create_signal('iceberg', 'CONFIRMED', 'BUY', 0.150, 80.0),  # 1 * 2.0 * 80 = 160
        create_signal('iceberg', 'WARNING', 'BUY', 0.150, 80.0),    # 1 * 1.5 * 80 = 120
        create_signal('iceberg', 'ACTIVITY', 'BUY', 0.150, 80.0),   # 1 * 1.0 * 80 = 80
        create_signal('iceberg', 'INFO', 'BUY', 0.150, 80.0),       # 1 * 0.5 * 80 = 40
    ]

    result2 = advisor.generate_advice(signals2)

    # 总加权: 240 + 160 + 120 + 80 + 40 = 640
    expected_weighted2 = 240 + 160 + 120 + 80 + 40
    assert result2['weighted_buy'] == expected_weighted2, \
        f"测试 6.2: 加权应为 {expected_weighted2}，实际为 {result2['weighted_buy']}"

    print(f"  BUY加权: {result2['weighted_buy']:.1f}")
    print("✅ 测试 6.2: 级别权重正确")

    print("\n✅ 测试 6 完成：加权计算验证通过")


# ==================== 测试 7: 告警格式化 ====================

def test_alert_formatting():
    """测试告警消息格式化"""
    print("\n" + "="*70)
    print("测试 7: 告警格式化")
    print("="*70)

    advisor = BundleAdvisor()

    signals = [
        create_signal('liq', 'CRITICAL', 'BUY', 0.150, 90.0),
        create_signal('whale', 'CONFIRMED', 'BUY', 0.150, 85.0),
        create_signal('iceberg', 'CONFIRMED', 'SELL', 0.151, 75.0),
    ]

    advice = advisor.generate_advice(signals)
    message = advisor.format_bundle_alert(advice, signals)

    # 验证消息包含关键信息
    assert 'STRONG_BUY' in message, "消息应包含建议级别"
    assert 'TEST_USDT' in message, "消息应包含交易对"
    assert 'BUY' in message and 'SELL' in message, "消息应包含方向"
    assert '0.150' in message or '0.151' in message, "消息应包含价格"
    assert len(message) > 100, "消息长度应足够详细"

    print("\n格式化消息预览:")
    print("-" * 70)
    print(message[:500])  # 只显示前 500 字符
    print("-" * 70)
    print("✅ 测试 7.1: 告警格式化正确")

    print("\n✅ 测试 7 完成：告警格式化通过")


# ==================== 测试 8: 边界情况 ====================

def test_edge_cases():
    """测试边界情况"""
    print("\n" + "="*70)
    print("测试 8: 边界情况处理")
    print("="*70)

    advisor = BundleAdvisor()

    # 测试 8.1: 空信号列表
    print("\n✓ 测试 8.1: 空信号列表")
    result1 = advisor.generate_advice([])

    assert result1['advice'] == 'WATCH', \
        "测试 8.1: 空列表应返回 WATCH"
    assert result1['buy_count'] == 0, "测试 8.1: buy_count 应为 0"
    assert result1['sell_count'] == 0, "测试 8.1: sell_count 应为 0"
    assert result1['confidence'] == 0.0, "测试 8.1: 置信度应为 0"

    print(f"  建议: {result1['advice']}")
    print("✅ 测试 8.1: 空列表处理正确")

    # 测试 8.2: 单个 INFO 级别信号
    print("\n✓ 测试 8.2: 单个低级别信号")
    signals2 = [
        create_signal('iceberg', 'INFO', 'BUY', 0.150, 50.0),
    ]

    result2 = advisor.generate_advice(signals2)
    # 应返回某个建议（不是 None）
    assert result2['advice'] in ['STRONG_BUY', 'BUY', 'WATCH', 'SELL', 'STRONG_SELL'], \
        "测试 8.2: 应返回有效的建议级别"
    assert result2['buy_count'] == 1 and result2['sell_count'] == 0, \
        "测试 8.2: 计数应正确"

    print(f"  建议: {result2['advice']}")
    print("✅ 测试 8.2: 低级别信号处理正确")

    # 测试 8.3: 极端置信度（0 和 100）
    print("\n✓ 测试 8.3: 极端置信度")
    signals3 = [
        create_signal('liq', 'CRITICAL', 'BUY', 0.150, 100.0),
        create_signal('iceberg', 'INFO', 'SELL', 0.151, 0.0),
    ]

    result3 = advisor.generate_advice(signals3)
    assert result3['advice'] in ['STRONG_BUY', 'BUY'], \
        "测试 8.3: 极端置信度应处理正确"

    print(f"  建议: {result3['advice']}")
    print("✅ 测试 8.3: 极端置信度处理正确")

    print("\n✅ 测试 8 完成：边界情况全部通过")


# ==================== 主测试函数 ====================

def main():
    """运行所有测试"""
    print("="*70)
    print("BundleAdvisor 单元测试")
    print("="*70)

    try:
        # 运行所有测试
        test_strong_buy()           # 测试 1: STRONG_BUY
        test_buy()                  # 测试 2: BUY
        test_watch()                # 测试 3: WATCH
        test_sell()                 # 测试 4: SELL
        test_strong_sell()          # 测试 5: STRONG_SELL
        test_weighted_calculation() # 测试 6: 加权计算
        test_alert_formatting()     # 测试 7: 告警格式
        test_edge_cases()           # 测试 8: 边界情况

        # 汇总
        print("\n" + "="*70)
        print("测试汇总")
        print("="*70)
        print("总测试数: 8")
        print("通过: 8")
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
