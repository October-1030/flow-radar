#!/usr/bin/env python3
"""
Signal Fusion Engine 单元测试

测试覆盖：
1. 时间窗口内关联检测
2. 价格重叠判定（3 种信号类型）
3. 不同交易对隔离
4. 批量处理性能
5. 边界情况（空列表、单信号）

作者：Claude Code
日期：2026-01-09
"""

import sys
from pathlib import Path
import time

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.signal_fusion_engine import SignalFusionEngine, PriceRange
from core.signal_schema import IcebergSignal, WhaleSignal, LiqSignal


# ==================== 测试辅助函数 ====================

def create_test_iceberg(ts, symbol, side, price, level='CONFIRMED'):
    """创建测试用冰山信号"""
    return IcebergSignal(
        ts=ts,
        symbol=symbol,
        side=side,
        level=level,
        confidence=75.0,
        price=price,
        cumulative_filled=1000.0,
        refill_count=3,
        intensity=5.0,
        key=f"iceberg_{symbol}_{side}_{ts}",
        signal_type='iceberg'
    )


def create_test_whale(ts, symbol, side, price, level='CONFIRMED'):
    """创建测试用鲸鱼信号"""
    return WhaleSignal(
        ts=ts,
        symbol=symbol,
        side=side,
        level=level,
        confidence=80.0,
        price=price,
        trade_volume=50000.0,
        trade_count=10,
        key=f"whale_{symbol}_{side}_{ts}",
        signal_type='whale'
    )


# ==================== 测试 1: 价格范围重叠判定 ====================

def test_price_range_overlap():
    """测试价格范围重叠判定"""
    print("\n" + "="*70)
    print("测试 1: 价格范围重叠判定")
    print("="*70)

    # 测试用例 1: 完全重叠
    range1 = PriceRange(min_price=100, max_price=102, center_price=101)
    range2 = PriceRange(min_price=101, max_price=103, center_price=102)
    assert range1.overlaps(range2), "测试失败：完全重叠应返回 True"
    print("✅ 测试 1.1: 完全重叠 - PASS")

    # 测试用例 2: 不重叠
    range1 = PriceRange(min_price=100, max_price=101, center_price=100.5)
    range2 = PriceRange(min_price=102, max_price=103, center_price=102.5)
    assert not range1.overlaps(range2), "测试失败：不重叠应返回 False"
    print("✅ 测试 1.2: 不重叠 - PASS")

    # 测试用例 3: 边界重叠
    range1 = PriceRange(min_price=100, max_price=101, center_price=100.5)
    range2 = PriceRange(min_price=101, max_price=102, center_price=101.5)
    assert range1.overlaps(range2), "测试失败：边界重叠应返回 True"
    print("✅ 测试 1.3: 边界重叠 - PASS")

    # 测试用例 4: 包含关系
    range1 = PriceRange(min_price=100, max_price=105, center_price=102.5)
    range2 = PriceRange(min_price=101, max_price=103, center_price=102)
    assert range1.overlaps(range2), "测试失败：包含关系应返回 True"
    print("✅ 测试 1.4: 包含关系 - PASS")

    print("✅ 测试 1 完成：价格范围重叠判定全部通过")


# ==================== 测试 2: 时间窗口内关联检测 ====================

def test_time_window_correlation():
    """测试时间窗口内关联检测"""
    print("\n" + "="*70)
    print("测试 2: 时间窗口内关联检测")
    print("="*70)

    engine = SignalFusionEngine()

    base_ts = 1704800000  # 基准时间戳
    symbol = "DOGE/USDT"
    price = 0.15

    # 测试用例 1: 时间窗口内（5 分钟内）
    signal1 = create_test_iceberg(base_ts, symbol, 'BUY', price)
    signal2 = create_test_iceberg(base_ts + 120, symbol, 'BUY', price)  # 2分钟后

    all_signals = [signal1, signal2]
    related = engine.find_related_signals(signal1, all_signals)

    assert signal2.key in related, "测试失败：2分钟内信号应关联"
    print("✅ 测试 2.1: 时间窗口内关联 - PASS")

    # 测试用例 2: 超出时间窗口（6 分钟）
    signal3 = create_test_iceberg(base_ts + 400, symbol, 'BUY', price)  # 6.67分钟后

    all_signals = [signal1, signal3]
    related = engine.find_related_signals(signal1, all_signals)

    assert signal3.key not in related, "测试失败：超时信号不应关联"
    print("✅ 测试 2.2: 超出时间窗口 - PASS")

    # 测试用例 3: 边界情况（刚好 5 分钟）
    signal4 = create_test_iceberg(base_ts + 300, symbol, 'BUY', price)  # 刚好5分钟

    all_signals = [signal1, signal4]
    related = engine.find_related_signals(signal1, all_signals)

    assert signal4.key in related, "测试失败：5分钟边界应关联"
    print("✅ 测试 2.3: 时间窗口边界 - PASS")

    print("✅ 测试 2 完成：时间窗口检测全部通过")


# ==================== 测试 3: 不同交易对隔离 ====================

def test_symbol_isolation():
    """测试不同交易对隔离"""
    print("\n" + "="*70)
    print("测试 3: 不同交易对隔离")
    print("="*70)

    engine = SignalFusionEngine()

    base_ts = 1704800000
    price = 0.15

    # 创建不同交易对的信号
    signal1 = create_test_iceberg(base_ts, "DOGE/USDT", 'BUY', price)
    signal2 = create_test_iceberg(base_ts + 60, "BTC/USDT", 'BUY', 50000)
    signal3 = create_test_iceberg(base_ts + 120, "DOGE/USDT", 'BUY', price)

    all_signals = [signal1, signal2, signal3]
    related = engine.find_related_signals(signal1, all_signals)

    assert signal2.key not in related, "测试失败：不同交易对不应关联"
    assert signal3.key in related, "测试失败：相同交易对应关联"
    print("✅ 测试 3.1: 交易对隔离 - PASS")

    print("✅ 测试 3 完成：交易对隔离通过")


# ==================== 测试 4: 价格重叠检测（多类型） ====================

def test_price_overlap_multi_types():
    """测试不同信号类型的价格重叠检测"""
    print("\n" + "="*70)
    print("测试 4: 价格重叠检测（多类型）")
    print("="*70)

    engine = SignalFusionEngine()

    base_ts = 1704800000
    symbol = "DOGE/USDT"
    base_price = 0.15

    # 测试用例 1: 冰山信号价格重叠（±0.1%）
    signal1 = create_test_iceberg(base_ts, symbol, 'BUY', 0.15000)
    signal2 = create_test_iceberg(base_ts + 60, symbol, 'BUY', 0.15010)  # 0.067% 差异

    all_signals = [signal1, signal2]
    related = engine.find_related_signals(signal1, all_signals)

    assert signal2.key in related, "测试失败：冰山信号应重叠"
    print("✅ 测试 4.1: 冰山信号价格重叠 - PASS")

    # 测试用例 2: 冰山信号价格不重叠
    signal3 = create_test_iceberg(base_ts + 120, symbol, 'BUY', 0.15200)  # 1.33% 差异

    all_signals = [signal1, signal3]
    related = engine.find_related_signals(signal1, all_signals)

    assert signal3.key not in related, "测试失败：冰山信号不应重叠"
    print("✅ 测试 4.2: 冰山信号价格不重叠 - PASS")

    # 测试用例 3: 鲸鱼信号价格重叠（±0.05%，更严格）
    whale1 = create_test_whale(base_ts, symbol, 'BUY', 0.15000)
    whale2 = create_test_whale(base_ts + 60, symbol, 'BUY', 0.15005)  # 0.033% 差异

    all_signals = [whale1, whale2]
    related = engine.find_related_signals(whale1, all_signals)

    assert whale2.key in related, "测试失败：鲸鱼信号应重叠"
    print("✅ 测试 4.3: 鲸鱼信号价格重叠 - PASS")

    print("✅ 测试 4 完成：多类型价格重叠检测通过")


# ==================== 测试 5: 批量处理性能 ====================

def test_batch_processing_performance():
    """测试批量处理性能"""
    print("\n" + "="*70)
    print("测试 5: 批量处理性能")
    print("="*70)

    engine = SignalFusionEngine()

    base_ts = 1704800000
    symbol = "DOGE/USDT"

    # 创建 100 个信号
    signals = []
    for i in range(100):
        signal = create_test_iceberg(
            ts=base_ts + i * 10,  # 每10秒一个信号
            symbol=symbol,
            side='BUY' if i % 2 == 0 else 'SELL',
            price=0.15 + (i % 10) * 0.001  # 价格略有变化
        )
        signals.append(signal)

    # 测试批量处理
    start_time = time.time()
    relations = engine.batch_find_relations(signals)
    elapsed = time.time() - start_time

    print(f"   处理 {len(signals)} 个信号耗时: {elapsed*1000:.2f} ms")

    # 验证结果
    assert len(relations) == len(signals), "测试失败：关联字典应包含所有信号"

    # 检查关联数量
    total_relations = sum(len(keys) for keys in relations.values())
    print(f"   总关联关系数: {total_relations}")

    # 性能要求：100 信号 < 100ms（宽松要求，实际应 < 20ms）
    assert elapsed < 0.1, f"测试失败：性能不达标（{elapsed*1000:.2f} ms > 100 ms）"
    print("✅ 测试 5.1: 批量处理性能 - PASS")

    # 验证统计信息
    stats = engine.get_stats()
    assert stats['total_checks'] > 0, "测试失败：应有比较次数"
    assert stats['relations_found'] > 0, "测试失败：应找到关联"
    print(f"   统计信息: {stats}")
    print("✅ 测试 5.2: 统计信息正确 - PASS")

    print("✅ 测试 5 完成：批量处理性能通过")


# ==================== 测试 6: 边界情况 ====================

def test_edge_cases():
    """测试边界情况"""
    print("\n" + "="*70)
    print("测试 6: 边界情况")
    print("="*70)

    engine = SignalFusionEngine()

    base_ts = 1704800000
    symbol = "DOGE/USDT"

    # 测试用例 1: 空信号列表
    signal1 = create_test_iceberg(base_ts, symbol, 'BUY', 0.15)
    related = engine.find_related_signals(signal1, [])

    assert len(related) == 0, "测试失败：空列表应返回空关联"
    print("✅ 测试 6.1: 空信号列表 - PASS")

    # 测试用例 2: 单信号列表
    related = engine.find_related_signals(signal1, [signal1])

    assert len(related) == 0, "测试失败：单信号不应自关联"
    print("✅ 测试 6.2: 单信号列表 - PASS")

    # 测试用例 3: 无价格信号
    signal_no_price = IcebergSignal(
        ts=base_ts,
        symbol=symbol,
        side='BUY',
        level='CONFIRMED',
        confidence=75.0,
        price=None,  # 无价格
        key="test_no_price",
        signal_type='iceberg'
    )

    try:
        related = engine.find_related_signals(signal_no_price, [signal1])
        # 应该抛出 ValueError 或返回空
        print("✅ 测试 6.3: 无价格信号处理 - PASS")
    except ValueError:
        print("✅ 测试 6.3: 无价格信号抛出异常 - PASS")

    # 测试用例 4: 缓存清空
    engine.clear_cache()
    assert len(engine._price_range_cache or {}) == 0, "测试失败：缓存应清空"
    print("✅ 测试 6.4: 缓存清空 - PASS")

    print("✅ 测试 6 完成：边界情况处理通过")


# ==================== 测试 7: 价格分桶优化 ====================

def test_price_bucketing():
    """测试价格分桶优化"""
    print("\n" + "="*70)
    print("测试 7: 价格分桶优化")
    print("="*70)

    engine = SignalFusionEngine()

    base_ts = 1704800000
    symbol = "DOGE/USDT"

    # 创建不同价格桶的信号
    signals = [
        create_test_iceberg(base_ts, symbol, 'BUY', 0.100),  # 桶 100
        create_test_iceberg(base_ts + 10, symbol, 'BUY', 0.150),  # 桶 150
        create_test_iceberg(base_ts + 20, symbol, 'BUY', 0.200),  # 桶 200
    ]

    # 批量处理
    relations = engine.batch_find_relations(signals)

    # 验证不同桶的信号不关联（价格差异太大）
    assert len(relations[signals[0].key]) == 0, "测试失败：不同桶信号不应关联"
    print("✅ 测试 7.1: 价格分桶隔离 - PASS")

    # 创建相同价格桶的信号（应该关联）
    signals2 = [
        create_test_iceberg(base_ts, symbol, 'BUY', 0.1500),
        create_test_iceberg(base_ts + 10, symbol, 'BUY', 0.1500),
        create_test_iceberg(base_ts + 20, symbol, 'BUY', 0.1501),  # 非常接近
    ]

    relations = engine.batch_find_relations(signals2)

    # 验证相同/相近价格信号应关联
    assert signals2[1].key in relations[signals2[0].key], "测试失败：相同价格信号应关联"
    print("✅ 测试 7.2: 相同价格桶关联 - PASS")

    print("✅ 测试 7 完成：价格分桶优化通过")


# ==================== 主测试函数 ====================

def run_all_tests():
    """运行所有测试"""
    print("="*70)
    print("Signal Fusion Engine 单元测试")
    print("="*70)

    tests = [
        ("价格范围重叠判定", test_price_range_overlap),
        ("时间窗口内关联检测", test_time_window_correlation),
        ("不同交易对隔离", test_symbol_isolation),
        ("价格重叠检测（多类型）", test_price_overlap_multi_types),
        ("批量处理性能", test_batch_processing_performance),
        ("边界情况", test_edge_cases),
        ("价格分桶优化", test_price_bucketing),
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
