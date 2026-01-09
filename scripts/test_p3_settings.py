#!/usr/bin/env python3
"""
P3 优先级配置验证脚本

验证内容：
1. 配置导入成功
2. 优先级计算正确性
3. 信号排序功能
4. 工具函数正确性

作者：Claude Code
日期：2026-01-08
"""

import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.p3_settings import (
    LEVEL_PRIORITY, TYPE_PRIORITY,
    CONFIDENCE_THRESHOLDS, DEDUP_WINDOWS, ALERT_THROTTLE,
    get_signal_priority, compare_signals, sort_signals_by_priority,
    is_high_priority, get_dedup_window, get_alert_throttle,
    should_alert, validate_config
)


def test_config_import():
    """测试 1: 配置导入"""
    print("\n" + "="*60)
    print("测试 1: 配置导入")
    print("="*60)

    print(f"✅ LEVEL_PRIORITY: {LEVEL_PRIORITY}")
    print(f"✅ TYPE_PRIORITY: {TYPE_PRIORITY}")
    print(f"✅ CONFIDENCE_THRESHOLDS: {CONFIDENCE_THRESHOLDS}")

    # 验证配置完整性
    try:
        validate_config()
        print("\n✅ 配置验证通过")
        return True
    except AssertionError as e:
        print(f"\n❌ 配置验证失败: {e}")
        return False


def test_priority_calculation():
    """测试 2: 优先级计算"""
    print("\n" + "="*60)
    print("测试 2: 优先级计算")
    print("="*60)

    test_cases = [
        ('CRITICAL', 'liq', (1, 1), "最高优先级"),
        ('CRITICAL', 'whale', (1, 2), "CRITICAL + whale"),
        ('CONFIRMED', 'liq', (2, 1), "CONFIRMED + liq"),
        ('CONFIRMED', 'iceberg', (2, 3), "CONFIRMED + iceberg"),
        ('ACTIVITY', 'iceberg', (4, 3), "较低优先级"),
        ('INFO', 'iceberg', (5, 3), "最低优先级"),
    ]

    all_passed = True
    for level, signal_type, expected, desc in test_cases:
        result = get_signal_priority(level, signal_type)
        status = "✅" if result == expected else "❌"
        print(f"{status} {desc}: {level} + {signal_type} = {result}")

        if result != expected:
            print(f"   期望: {expected}, 实际: {result}")
            all_passed = False

    return all_passed


def test_signal_comparison():
    """测试 3: 信号比较"""
    print("\n" + "="*60)
    print("测试 3: 信号比较")
    print("="*60)

    # 测试用例
    signal1 = {'level': 'CRITICAL', 'signal_type': 'liq'}
    signal2 = {'level': 'CONFIRMED', 'signal_type': 'whale'}
    signal3 = {'level': 'CONFIRMED', 'signal_type': 'iceberg'}
    signal4 = {'level': 'CRITICAL', 'signal_type': 'liq'}

    # signal1 vs signal2: CRITICAL > CONFIRMED
    result = compare_signals(signal1, signal2)
    if result == -1:
        print("✅ CRITICAL/liq > CONFIRMED/whale")
    else:
        print(f"❌ 比较错误: {result}")
        return False

    # signal2 vs signal3: CONFIRMED + whale > CONFIRMED + iceberg
    result = compare_signals(signal2, signal3)
    if result == -1:
        print("✅ CONFIRMED/whale > CONFIRMED/iceberg")
    else:
        print(f"❌ 比较错误: {result}")
        return False

    # signal1 vs signal4: 相同优先级
    result = compare_signals(signal1, signal4)
    if result == 0:
        print("✅ CRITICAL/liq == CRITICAL/liq")
    else:
        print(f"❌ 比较错误: {result}")
        return False

    return True


def test_signal_sorting():
    """测试 4: 信号排序"""
    print("\n" + "="*60)
    print("测试 4: 信号排序")
    print("="*60)

    # 创建测试信号（故意乱序）
    signals = [
        {'level': 'ACTIVITY', 'signal_type': 'iceberg', 'name': 'S1'},
        {'level': 'CRITICAL', 'signal_type': 'liq', 'name': 'S2'},
        {'level': 'CONFIRMED', 'signal_type': 'whale', 'name': 'S3'},
        {'level': 'WARNING', 'signal_type': 'iceberg', 'name': 'S4'},
        {'level': 'CONFIRMED', 'signal_type': 'iceberg', 'name': 'S5'},
    ]

    print("排序前:")
    for s in signals:
        priority = get_signal_priority(s['level'], s['signal_type'])
        print(f"  {s['name']}: {s['level']}/{s['signal_type']} → {priority}")

    # 排序
    sorted_signals = sort_signals_by_priority(signals)

    print("\n排序后:")
    for s in sorted_signals:
        priority = get_signal_priority(s['level'], s['signal_type'])
        print(f"  {s['name']}: {s['level']}/{s['signal_type']} → {priority}")

    # 验证排序正确性
    expected_order = ['S2', 'S3', 'S5', 'S4', 'S1']
    actual_order = [s['name'] for s in sorted_signals]

    if actual_order == expected_order:
        print(f"\n✅ 排序正确: {actual_order}")
        return True
    else:
        print(f"\n❌ 排序错误:")
        print(f"   期望: {expected_order}")
        print(f"   实际: {actual_order}")
        return False


def test_utility_functions():
    """测试 5: 工具函数"""
    print("\n" + "="*60)
    print("测试 5: 工具函数")
    print("="*60)

    # 测试 is_high_priority
    if is_high_priority('CRITICAL', 'liq'):
        print("✅ is_high_priority('CRITICAL', 'liq') = True")
    else:
        print("❌ is_high_priority 判断错误")
        return False

    if not is_high_priority('ACTIVITY', 'iceberg'):
        print("✅ is_high_priority('ACTIVITY', 'iceberg') = False")
    else:
        print("❌ is_high_priority 判断错误")
        return False

    # 测试 get_dedup_window
    window = get_dedup_window('CONFIRMED')
    if window == 1800:
        print(f"✅ get_dedup_window('CONFIRMED') = {window} 秒 (30分钟)")
    else:
        print(f"❌ get_dedup_window 返回错误: {window}")
        return False

    # 测试 get_alert_throttle
    throttle = get_alert_throttle('CRITICAL')
    if throttle == 0:
        print(f"✅ get_alert_throttle('CRITICAL') = {throttle} (不节流)")
    else:
        print(f"❌ get_alert_throttle 返回错误: {throttle}")
        return False

    # 测试 should_alert
    if should_alert('CONFIRMED'):
        print("✅ should_alert('CONFIRMED') = True")
    else:
        print("❌ should_alert 判断错误")
        return False

    if not should_alert('ACTIVITY'):
        print("✅ should_alert('ACTIVITY') = False")
    else:
        print("❌ should_alert 判断错误")
        return False

    return True


def test_priority_rules():
    """测试 6: 优先级规则验证"""
    print("\n" + "="*60)
    print("测试 6: 优先级规则验证（P3-2 v1.2 规范）")
    print("="*60)

    print("\n规则 1: level 优先于 type")
    # CRITICAL + iceberg 应该优先于 CONFIRMED + liq
    s1 = {'level': 'CRITICAL', 'signal_type': 'iceberg'}
    s2 = {'level': 'CONFIRMED', 'signal_type': 'liq'}

    if compare_signals(s1, s2) == -1:
        print("✅ CRITICAL/iceberg > CONFIRMED/liq (level 优先)")
    else:
        print("❌ level 优先级规则失败")
        return False

    print("\n规则 2: 相同 level 时，type 决定优先级")
    # CONFIRMED + liq 应该优先于 CONFIRMED + iceberg
    s1 = {'level': 'CONFIRMED', 'signal_type': 'liq'}
    s2 = {'level': 'CONFIRMED', 'signal_type': 'iceberg'}

    if compare_signals(s1, s2) == -1:
        print("✅ CONFIRMED/liq > CONFIRMED/iceberg (type 决定)")
    else:
        print("❌ type 优先级规则失败")
        return False

    print("\n规则 3: liq > whale > iceberg")
    priorities = [
        get_signal_priority('CONFIRMED', 'liq'),
        get_signal_priority('CONFIRMED', 'whale'),
        get_signal_priority('CONFIRMED', 'iceberg'),
    ]

    if priorities == sorted(priorities):
        print(f"✅ 类型优先级正确: liq{priorities[0]} < whale{priorities[1]} < iceberg{priorities[2]}")
    else:
        print(f"❌ 类型优先级错误: {priorities}")
        return False

    return True


def main():
    """主函数"""
    print("="*60)
    print("P3 优先级配置验证")
    print("="*60)

    tests = [
        ("配置导入", test_config_import),
        ("优先级计算", test_priority_calculation),
        ("信号比较", test_signal_comparison),
        ("信号排序", test_signal_sorting),
        ("工具函数", test_utility_functions),
        ("优先级规则验证", test_priority_rules),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ 测试 '{name}' 抛出异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # 汇总结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    passed = sum(1 for _, success in results if success)
    total = len(results)

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        print("\n✅ P3 优先级配置符合 P3-2 v1.2 规范")
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
