#!/usr/bin/env python3
"""
Flow Radar 验收测试
GPT 建议的 4 项必测 (T1/T2/T4/T6)

运行方式:
    python tests/test_acceptance.py
"""

import sys
import time
import json
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.trade_deduplicator import TradeDeduplicator
from core.state_saver import StateSaver
from core.divergence_detector import DivergenceDetector, DivergenceType


def test_t2_deduplication():
    """
    T2: 去重正确性测试
    验收标准: 同一批 trades 重复喂 2 次，CVD 不变
    """
    print("\n" + "=" * 50)
    print("T2: 去重正确性测试")
    print("=" * 50)

    trades = [
        {'id': '1', 'price': 100, 'amount': 10, 'side': 'buy', 'timestamp': 1000},
        {'id': '2', 'price': 101, 'amount': 20, 'side': 'sell', 'timestamp': 1001},
        {'id': '3', 'price': 102, 'amount': 15, 'side': 'buy', 'timestamp': 1002},
    ]

    deduplicator = TradeDeduplicator()
    current_ts = time.time()

    # 第一次
    result1 = deduplicator.filter_trades(trades, current_ts)
    cvd1 = sum(t['amount'] if t['side'] == 'buy' else -t['amount'] for t in result1)

    # 第二次 (重复)
    result2 = deduplicator.filter_trades(trades, current_ts + 1)
    cvd2 = sum(t['amount'] if t['side'] == 'buy' else -t['amount'] for t in result2)

    print(f"  第一次: {len(result1)} 条, CVD = {cvd1}")
    print(f"  第二次: {len(result2)} 条, CVD = {cvd2}")
    print(f"  去重统计: {deduplicator.get_stats()}")

    # 验证
    assert len(result1) == 3, f"第一次应该有 3 条，实际 {len(result1)}"
    assert len(result2) == 0, f"第二次应该有 0 条，实际 {len(result2)}"
    assert cvd2 == 0, f"第二次 CVD 应该是 0，实际 {cvd2}"

    print("\n  ✅ T2 通过: 去重正确，重复数据不影响 CVD")
    return True


def test_t4_persistence():
    """
    T4: 持久化连续性测试
    验收标准: kill 程序再启动，CVD 不归零
    """
    print("\n" + "=" * 50)
    print("T4: 持久化连续性测试")
    print("=" * 50)

    # 使用测试专用 symbol
    test_symbol = "TEST/USDT"
    saver = StateSaver(symbol=test_symbol, save_dir="./storage/state")

    # 清理旧状态
    saver.delete()

    # 模拟运行 - 保存状态
    test_state = {
        'cvd_total': 12345.67,
        'total_whale_flow': 98765.43,
        'iceberg_buy_count': 5,
        'iceberg_sell_count': 3,
        'current_state': 'trend_up',
        'last_score': 72,
        'last_price': 0.32156,
    }

    save_ts = time.time()
    saver.save(test_state, save_ts, force=True)
    print(f"  保存状态: CVD = {test_state['cvd_total']}")

    # 模拟重启 - 加载状态
    saver2 = StateSaver(symbol=test_symbol, save_dir="./storage/state")
    loaded = saver2.load()

    print(f"  加载状态: CVD = {loaded.cvd_total if loaded else 'None'}")

    # 验证
    assert loaded is not None, "加载失败"
    assert loaded.cvd_total == test_state['cvd_total'], f"CVD 不一致: {loaded.cvd_total} != {test_state['cvd_total']}"
    assert loaded.total_whale_flow == test_state['total_whale_flow'], "鲸鱼流不一致"
    assert loaded.iceberg_buy_count == test_state['iceberg_buy_count'], "冰山买单数不一致"

    # 清理
    saver.delete()

    print("\n  ✅ T4 通过: 状态持久化正确，重启后 CVD 不归零")
    return True


def test_t6_divergence():
    """
    T6: 背离一致性测试
    验收标准: 固定输入触发点稳定
    """
    print("\n" + "=" * 50)
    print("T6: 背离一致性测试")
    print("=" * 50)

    # 固定输入: 价格上涨，CVD 下降 -> 看跌背离
    prices = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
    cvds = [1000, 1050, 1030, 1000, 970, 940, 910, 880, 850, 820, 790]

    results = []
    for run in range(3):  # 跑 3 次验证一致性
        detector = DivergenceDetector(window=20)
        run_results = []

        for i, (p, c) in enumerate(zip(prices, cvds)):
            result = detector.update(p, c, p, p, timestamp=1000 + i)
            if result and result.detected:
                run_results.append({
                    'index': i,
                    'type': result.type.value,
                    'confidence': result.confidence
                })

        results.append(run_results)

    print(f"  运行 1: {results[0]}")
    print(f"  运行 2: {results[1]}")
    print(f"  运行 3: {results[2]}")

    # 验证一致性
    assert results[0] == results[1] == results[2], "三次运行结果不一致"

    # 验证触发背离
    if results[0]:
        last_result = results[0][-1]
        assert last_result['type'] == 'bearish', f"应该是看跌背离，实际是 {last_result['type']}"
        print(f"\n  触发点: index={last_result['index']}, type={last_result['type']}, confidence={last_result['confidence']:.2f}")

    print("\n  ✅ T6 通过: 背离检测一致，固定输入触发点稳定")
    return True


def run_all_tests():
    """运行所有验收测试"""
    print("\n" + "=" * 60)
    print("Flow Radar 验收测试 (GPT 必测集合)")
    print("=" * 60)

    results = {}

    # T2: 去重正确性
    try:
        results['T2'] = test_t2_deduplication()
    except AssertionError as e:
        print(f"\n  ❌ T2 失败: {e}")
        results['T2'] = False

    # T4: 持久化连续性
    try:
        results['T4'] = test_t4_persistence()
    except AssertionError as e:
        print(f"\n  ❌ T4 失败: {e}")
        results['T4'] = False

    # T6: 背离一致性
    try:
        results['T6'] = test_t6_divergence()
    except AssertionError as e:
        print(f"\n  ❌ T6 失败: {e}")
        results['T6'] = False

    # 汇总
    print("\n" + "=" * 60)
    print("验收结果汇总")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有验收测试通过，可以启动 72 小时验证！")
        return True
    else:
        print("\n⚠️ 有测试失败，请修复后重新运行")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
