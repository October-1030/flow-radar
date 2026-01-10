#!/usr/bin/env python3
"""
P3 优先级配置集成测试
Integration Test for P3 Priority Configuration

测试内容：
    1. 与 SignalEvent 对象的兼容性
    2. 枚举类型的正确处理
    3. 字典和对象混合排序
    4. 边界情况（未知类型的降级）

作者: Claude Code
日期: 2026-01-10
"""

import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.signal_schema import (
    SignalEvent, SignalLevel, SignalType, SignalSide
)
from config.p3_settings import (
    get_sort_key, compare_signals, get_level_rank, get_type_rank,
    validate_priority_config, LEVEL_RANK, TYPE_RANK
)
import time


def test_signal_event_compatibility():
    """测试与 SignalEvent 对象的兼容性"""
    print("\n" + "=" * 70)
    print("测试 1: SignalEvent 对象兼容性")
    print("=" * 70)

    # 创建 SignalEvent 对象
    signals = [
        SignalEvent(
            ts=time.time(),
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.ACTIVITY,
            confidence=40.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key="iceberg:DOGE/USDT:BUY:ACTIVITY:price_0.15068"
        ),
        SignalEvent(
            ts=time.time() + 1,
            symbol="BTC/USDT",
            side=SignalSide.SELL,
            level=SignalLevel.CRITICAL,
            confidence=95.0,
            price=42000.0,
            signal_type=SignalType.LIQ,
            key="liq:BTC/USDT:SELL:CRITICAL:price_42000"
        ),
        SignalEvent(
            ts=time.time() + 2,
            symbol="ETH/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=75.0,
            price=2200.0,
            signal_type=SignalType.WHALE,
            key="whale:ETH/USDT:BUY:CONFIRMED:price_2200"
        ),
        SignalEvent(
            ts=time.time() + 3,
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=70.0,
            price=0.15100,
            signal_type=SignalType.KGOD,
            key="kgod:DOGE/USDT:BUY:CONFIRMED:time_08:30"
        ),
    ]

    print("\n原始信号（SignalEvent 对象）：")
    for i, sig in enumerate(signals, 1):
        print(f"  {i}. [{sig.level.value:9}] {sig.signal_type.value:8} "
              f"@ {sig.symbol} | confidence={sig.confidence}%")

    # 使用 get_sort_key 排序
    sorted_signals = sorted(signals, key=get_sort_key)

    print("\n排序后：")
    for i, sig in enumerate(sorted_signals, 1):
        level_rank, type_rank, neg_ts = get_sort_key(sig)
        print(f"  {i}. [{sig.level.value:9}] {sig.signal_type.value:8} "
              f"| rank=({level_rank}, {type_rank}) | confidence={sig.confidence}%")

    # 验证排序正确性
    assert sorted_signals[0].signal_type == SignalType.LIQ, "LIQ 应排在最前"
    assert sorted_signals[0].level == SignalLevel.CRITICAL, "CRITICAL 应排在最前"
    print("\n✅ SignalEvent 对象兼容性测试通过")


def test_enum_handling():
    """测试枚举类型的正确处理"""
    print("\n" + "=" * 70)
    print("测试 2: 枚举类型处理")
    print("=" * 70)

    # 测试 get_level_rank
    print("\nLevel Rank 测试：")
    test_levels = [
        SignalLevel.CRITICAL,
        "CONFIRMED",
        SignalLevel.WARNING,
        "ACTIVITY",
    ]
    for level in test_levels:
        rank = get_level_rank(level)
        level_str = level.value if hasattr(level, "value") else level
        print(f"  {level_str:9} -> rank={rank}")

    # 测试 get_type_rank
    print("\nType Rank 测试：")
    test_types = [
        SignalType.LIQ,
        "whale",
        SignalType.ICEBERG,
        "kgod",
    ]
    for signal_type in test_types:
        rank = get_type_rank(signal_type)
        type_str = signal_type.value if hasattr(signal_type, "value") else signal_type
        print(f"  {type_str:8} -> rank={rank}")

    # 验证枚举和字符串返回相同 rank
    assert get_level_rank(SignalLevel.CRITICAL) == get_level_rank("CRITICAL")
    assert get_type_rank(SignalType.LIQ) == get_type_rank("liq")
    print("\n✅ 枚举类型处理测试通过")


def test_mixed_sorting():
    """测试字典和对象混合排序"""
    print("\n" + "=" * 70)
    print("测试 3: 字典和对象混合排序")
    print("=" * 70)

    ts_base = time.time()

    # 混合信号列表（字典 + SignalEvent 对象）
    mixed_signals = [
        # 字典形式
        {"level": "ACTIVITY", "signal_type": "iceberg", "ts": ts_base},
        # SignalEvent 对象
        SignalEvent(
            ts=ts_base + 1,
            symbol="BTC/USDT",
            side=SignalSide.SELL,
            level=SignalLevel.CRITICAL,
            confidence=95.0,
            price=42000.0,
            signal_type=SignalType.LIQ,
            key="liq:BTC/USDT:SELL:CRITICAL:price_42000"
        ),
        # 字典形式（使用 type 字段而非 signal_type）
        {"level": "CONFIRMED", "type": "whale", "ts": ts_base + 2},
        # SignalEvent 对象
        SignalEvent(
            ts=ts_base + 3,
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.WARNING,
            confidence=60.0,
            price=0.15100,
            signal_type=SignalType.KGOD,
            key="kgod:DOGE/USDT:BUY:WARNING:time_08:30"
        ),
    ]

    print("\n原始混合信号列表：")
    for i, sig in enumerate(mixed_signals, 1):
        if isinstance(sig, dict):
            level = sig.get('level', 'N/A')
            sig_type = sig.get('signal_type') or sig.get('type', 'N/A')
            print(f"  {i}. [dict    ] {level:9} / {sig_type:8}")
        else:
            print(f"  {i}. [object  ] {sig.level.value:9} / {sig.signal_type.value:8}")

    # 排序
    sorted_mixed = sorted(mixed_signals, key=get_sort_key)

    print("\n排序后：")
    for i, sig in enumerate(sorted_mixed, 1):
        level_rank, type_rank, neg_ts = get_sort_key(sig)
        if isinstance(sig, dict):
            level = sig.get('level', 'N/A')
            sig_type = sig.get('signal_type') or sig.get('type', 'N/A')
            print(f"  {i}. [dict    ] {level:9} / {sig_type:8} | rank=({level_rank}, {type_rank})")
        else:
            print(f"  {i}. [object  ] {sig.level.value:9} / {sig.signal_type.value:8} "
                  f"| rank=({level_rank}, {type_rank})")

    # 验证排序正确性
    first_key = get_sort_key(sorted_mixed[0])
    assert first_key[0] == 1 and first_key[1] == 1, "CRITICAL + liq 应排在最前"
    print("\n✅ 混合排序测试通过")


def test_unknown_types():
    """测试未知类型的降级处理"""
    print("\n" + "=" * 70)
    print("测试 4: 未知类型降级处理")
    print("=" * 70)

    # 创建包含未知类型的信号
    signals = [
        {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758400.0},
        {"level": "UNKNOWN_LEVEL", "signal_type": "whale", "ts": 1704758500.0},
        {"level": "CONFIRMED", "signal_type": "unknown_type", "ts": 1704758600.0},
        {"level": "UNKNOWN", "signal_type": "unknown", "ts": 1704758700.0},
    ]

    print("\n信号排序（包含未知类型）：")
    sorted_signals = sorted(signals, key=get_sort_key)

    for i, sig in enumerate(sorted_signals, 1):
        level_rank, type_rank, neg_ts = get_sort_key(sig)
        level = sig.get('level', 'N/A')
        sig_type = sig.get('signal_type', 'N/A')
        print(f"  {i}. {level:15} / {sig_type:12} | rank=({level_rank:2}, {type_rank:2})")

    # 验证降级策略
    last_sig = sorted_signals[-1]
    last_key = get_sort_key(last_sig)
    assert last_key[0] == 99 and last_key[1] == 99, "未知类型应降级到 rank=99"
    print("\n✅ 未知类型降级测试通过")


def test_compare_signals_function():
    """测试 compare_signals 函数"""
    print("\n" + "=" * 70)
    print("测试 5: compare_signals 函数")
    print("=" * 70)

    ts = time.time()
    s1 = {"level": "CRITICAL", "signal_type": "liq", "ts": ts}
    s2 = {"level": "CONFIRMED", "signal_type": "whale", "ts": ts + 1}
    s3 = {"level": "CRITICAL", "signal_type": "liq", "ts": ts + 2}

    print("\n比较测试：")
    print(f"  s1: CRITICAL/liq @ ts={ts}")
    print(f"  s2: CONFIRMED/whale @ ts={ts+1}")
    print(f"  s3: CRITICAL/liq @ ts={ts+2}")

    result_1_2 = compare_signals(s1, s2)
    result_1_3 = compare_signals(s1, s3)
    result_2_3 = compare_signals(s2, s3)

    print(f"\n  compare(s1, s2) = {result_1_2:2} (s1 优先级更高)")
    print(f"  compare(s1, s3) = {result_1_3:2} (s3 时间更新，优先级更高)")
    print(f"  compare(s2, s3) = {result_2_3:2} (s3 优先级更高)")

    assert result_1_2 == -1, "s1 优先级应高于 s2"
    assert result_1_3 == 1, "s3 时间更新应高于 s1"
    assert result_2_3 == 1, "s3 优先级应高于 s2"
    print("\n✅ compare_signals 函数测试通过")


def test_config_validation():
    """测试配置验证"""
    print("\n" + "=" * 70)
    print("测试 6: 配置验证")
    print("=" * 70)

    try:
        validate_priority_config()
        print("\n✅ 配置验证通过")
        print(f"\n配置摘要：")
        print(f"  LEVEL_RANK: {LEVEL_RANK}")
        print(f"  TYPE_RANK: {TYPE_RANK}")
    except AssertionError as e:
        print(f"\n❌ 配置验证失败: {e}")
        return False

    return True


def run_all_tests():
    """运行所有测试"""
    print("=" * 70)
    print("P3 优先级配置 - 集成测试".center(70))
    print("=" * 70)

    tests = [
        ("SignalEvent 对象兼容性", test_signal_event_compatibility),
        ("枚举类型处理", test_enum_handling),
        ("字典和对象混合排序", test_mixed_sorting),
        ("未知类型降级处理", test_unknown_types),
        ("compare_signals 函数", test_compare_signals_function),
        ("配置验证", test_config_validation),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ 测试失败: {test_name}")
            print(f"   错误: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # 总结
    print("\n" + "=" * 70)
    print("测试总结".center(70))
    print("=" * 70)
    print(f"\n  通过: {passed}/{len(tests)}")
    print(f"  失败: {failed}/{len(tests)}")

    if failed == 0:
        print("\n  🎉 所有测试通过！")
        return True
    else:
        print("\n  ⚠️  部分测试失败，请检查错误信息")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
