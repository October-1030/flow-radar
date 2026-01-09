#!/usr/bin/env python3
"""
SignalEvent 数据结构验证脚本

验证内容：
1. CSV 数据加载（从 iceberg_annotation_samples.csv）
2. JSON 序列化/反序列化可逆性
3. 数据字段完整性
4. 工厂函数正确性

作者：Claude Code
日期：2026-01-08
"""

import json
import csv
from pathlib import Path
import sys

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.signal_schema import (
    SignalEvent, IcebergSignal, WhaleSignal, LiqSignal,
    create_signal_from_dict, from_csv_row, to_csv_row,
    signals_to_dicts, dicts_to_signals
)


def test_csv_loading():
    """测试 1: CSV 数据加载"""
    print("\n" + "="*60)
    print("测试 1: CSV 数据加载")
    print("="*60)

    csv_path = Path("docs/iceberg_annotation_samples.csv")

    if not csv_path.exists():
        print(f"❌ CSV 文件不存在: {csv_path}")
        return False

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"✅ 成功读取 {len(rows)} 行 CSV 数据")

    # 转换为信号对象
    signals = []
    for i, row in enumerate(rows[:3], 1):  # 测试前 3 行
        try:
            signal = from_csv_row(row)
            signals.append(signal)
            print(f"  ✅ 行 {i}: {signal}")
        except Exception as e:
            print(f"  ❌ 行 {i} 转换失败: {e}")
            return False

    print(f"\n✅ 成功转换 {len(signals)} 个信号对象")
    return True


def test_json_serialization():
    """测试 2: JSON 序列化/反序列化"""
    print("\n" + "="*60)
    print("测试 2: JSON 序列化/反序列化")
    print("="*60)

    # 创建测试信号
    original = IcebergSignal(
        ts=1767775139.597447,
        symbol="DOGE/USDT",
        side="BUY",
        level="CONFIRMED",
        confidence=65.0,
        price=0.15068,
        cumulative_filled=0.0,
        refill_count=3,
        intensity=3.78,
        key="iceberg:DOGE/USDT:BUY:CONFIRMED:0.1507",
        snippet_path="storage/events/DOGE_USDT_2026-01-07.jsonl.gz",
        offset=17
    )

    print(f"原始信号: {original}")

    # 序列化
    signal_dict = original.to_dict()
    print(f"\n✅ 序列化为字典: {json.dumps(signal_dict, indent=2)[:200]}...")

    # 反序列化
    restored = IcebergSignal.from_dict(signal_dict)
    print(f"\n✅ 反序列化为对象: {restored}")

    # 验证一致性
    errors = []
    if restored.ts != original.ts:
        errors.append(f"ts 不一致: {restored.ts} != {original.ts}")
    if restored.symbol != original.symbol:
        errors.append(f"symbol 不一致")
    if restored.confidence != original.confidence:
        errors.append(f"confidence 不一致")
    if restored.refill_count != original.refill_count:
        errors.append(f"refill_count 不一致")

    if errors:
        print(f"\n❌ 序列化/反序列化不一致:")
        for err in errors:
            print(f"  - {err}")
        return False

    print("\n✅ 序列化/反序列化可逆，所有字段一致")
    return True


def test_factory_function():
    """测试 3: 工厂函数"""
    print("\n" + "="*60)
    print("测试 3: 工厂函数")
    print("="*60)

    # 测试冰山信号
    iceberg_data = {
        'signal_type': 'iceberg',
        'ts': 1767775139.0,
        'symbol': 'DOGE/USDT',
        'side': 'BUY',
        'level': 'CONFIRMED',
        'confidence': 65.0,
        'price': 0.15068,
        'cumulative_filled': 0.0,
        'refill_count': 3,
        'intensity': 3.78
    }

    signal = create_signal_from_dict(iceberg_data)

    if not isinstance(signal, IcebergSignal):
        print(f"❌ 工厂函数返回类型错误: {type(signal)}")
        return False

    print(f"✅ 冰山信号: {signal}")

    # 测试鲸鱼信号
    whale_data = {
        'signal_type': 'whale',
        'ts': 1767775139.0,
        'symbol': 'DOGE/USDT',
        'side': 'BUY',
        'level': 'CONFIRMED',
        'confidence': 75.0,
        'trade_volume': 100000.0
    }

    signal = create_signal_from_dict(whale_data)

    if not isinstance(signal, WhaleSignal):
        print(f"❌ 工厂函数返回类型错误: {type(signal)}")
        return False

    print(f"✅ 鲸鱼信号: {signal}")

    # 测试清算信号
    liq_data = {
        'signal_type': 'liq',
        'ts': 1767775139.0,
        'symbol': 'DOGE/USDT',
        'side': 'SELL',
        'level': 'CRITICAL',
        'confidence': 95.0,
        'liquidation_volume': 500000.0
    }

    signal = create_signal_from_dict(liq_data)

    if not isinstance(signal, LiqSignal):
        print(f"❌ 工厂函数返回类型错误: {type(signal)}")
        return False

    print(f"✅ 清算信号: {signal}")

    print("\n✅ 工厂函数正确识别所有信号类型")
    return True


def test_batch_conversion():
    """测试 4: 批量转换"""
    print("\n" + "="*60)
    print("测试 4: 批量转换")
    print("="*60)

    # 创建多个信号
    signals = [
        IcebergSignal(ts=1.0, symbol="A", side="BUY", level="CONFIRMED", confidence=65.0),
        WhaleSignal(ts=2.0, symbol="B", side="SELL", level="WARNING", confidence=75.0),
        LiqSignal(ts=3.0, symbol="C", side="BUY", level="CRITICAL", confidence=95.0),
    ]

    print(f"原始信号: {len(signals)} 个")

    # 批量转为字典
    dicts = signals_to_dicts(signals)
    print(f"✅ 批量序列化: {len(dicts)} 个字典")

    # 批量转回对象
    restored = dicts_to_signals(dicts)
    print(f"✅ 批量反序列化: {len(restored)} 个对象")

    # 验证类型
    if not isinstance(restored[0], IcebergSignal):
        print("❌ 第 1 个信号类型错误")
        return False
    if not isinstance(restored[1], WhaleSignal):
        print("❌ 第 2 个信号类型错误")
        return False
    if not isinstance(restored[2], LiqSignal):
        print("❌ 第 3 个信号类型错误")
        return False

    print("✅ 批量转换保持类型正确")
    return True


def test_csv_roundtrip():
    """测试 5: CSV 往返转换"""
    print("\n" + "="*60)
    print("测试 5: CSV 往返转换")
    print("="*60)

    # 创建信号
    original = IcebergSignal(
        ts=1767775139.597447,
        symbol="DOGE/USDT",
        side="BUY",
        level="CONFIRMED",
        confidence=65.0,
        price=0.15068,
        cumulative_filled=1000.0,
        refill_count=3,
        intensity=3.78,
        key="test_key",
        snippet_path="test_path",
        offset=17
    )

    print(f"原始信号: {original}")

    # 转为 CSV 行
    csv_row = to_csv_row(original)
    print(f"\n✅ 转为 CSV 行: {csv_row}")

    # 从 CSV 行恢复
    restored = from_csv_row(csv_row)
    print(f"\n✅ 从 CSV 恢复: {restored}")

    # 验证关键字段
    if abs(restored.ts - original.ts) > 0.001:
        print(f"❌ ts 不一致")
        return False
    if restored.refill_count != original.refill_count:
        print(f"❌ refill_count 不一致")
        return False
    if abs(restored.intensity - original.intensity) > 0.01:
        print(f"❌ intensity 不一致")
        return False

    print("\n✅ CSV 往返转换无损")
    return True


def main():
    """主函数"""
    print("="*60)
    print("SignalEvent 数据结构验证")
    print("="*60)

    tests = [
        ("CSV 数据加载", test_csv_loading),
        ("JSON 序列化/反序列化", test_json_serialization),
        ("工厂函数", test_factory_function),
        ("批量转换", test_batch_conversion),
        ("CSV 往返转换", test_csv_roundtrip),
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
        return 0
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit(main())
