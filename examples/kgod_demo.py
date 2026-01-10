#!/usr/bin/env python3
"""
K神战法 2.0 - 演示脚本
K-God Strategy 2.0 - Demo Script

展示 KGodRadar 的基本用法和四层信号识别

作者: 三方共识（Claude + GPT + Gemini）
日期: 2026-01-09
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
from core.kgod_radar import (
    create_kgod_radar,
    OrderFlowSnapshot,
    SignalStage,
    SignalSide
)


def print_section(title):
    """打印分节标题"""
    print(f"\n{'='*70}")
    print(f"{title:^70}")
    print(f"{'='*70}\n")


def demo_basic_usage():
    """演示基本用法"""
    print_section("演示 1: 基本用法")

    # 创建雷达
    radar = create_kgod_radar(symbol="DOGE_USDT")
    print(f"✅ 创建雷达: {radar.symbol}")
    print(f"   布林带周期: {radar.bb.period}")
    print(f"   MACD 参数: {radar.macd.fast_period}/{radar.macd.slow_period}/{radar.macd.signal_period}")

    # 填充初始数据（布林带需要至少 20 个价格）
    print("\n📊 填充初始数据...")
    base_price = 0.15000
    for i in range(30):
        flow = OrderFlowSnapshot(iceberg_intensity=1.0)
        radar.update(price=base_price, order_flow=flow, ts=time.time() + i)

    print(f"   已更新 30 个价格点")
    print(f"   布林带就绪: {radar.bb.is_ready()}")
    print(f"   MACD 就绪: {radar.macd.is_ready()}")


def demo_pre_alert():
    """演示 PRE_ALERT 信号"""
    print_section("演示 2: PRE_ALERT 预警信号（z ≥ 1.4）")

    radar = create_kgod_radar(symbol="DOGE_USDT")

    # 填充稳定价格
    base_price = 0.15000
    for i in range(30):
        flow = OrderFlowSnapshot(iceberg_intensity=1.0)
        radar.update(price=base_price, order_flow=flow, ts=time.time() + i)

    # 突然上涨，触发 PRE_ALERT
    print("💡 价格突然上涨...")
    flow = OrderFlowSnapshot(
        delta_5s=100.0,
        imbalance_1s=0.6,
        iceberg_intensity=1.0
    )
    signal = radar.update(price=0.15100, order_flow=flow, ts=time.time() + 30)

    if signal:
        print(f"\n🔔 信号触发!")
        print(f"   级别: {signal.stage.value}")
        print(f"   方向: {signal.side.value}")
        print(f"   置信度: {signal.confidence:.1f}%")
        print(f"   原因:")
        for reason in signal.reasons:
            print(f"     - {reason}")
    else:
        print("   未触发信号（可能需要更大的价格变化）")


def demo_kgod_confirm():
    """演示 KGOD_CONFIRM 信号"""
    print_section("演示 3: KGOD_CONFIRM K神确认信号（最高级别）")

    radar = create_kgod_radar(symbol="DOGE_USDT")

    # 填充上涨趋势
    print("📈 构建上涨趋势...")
    base_price = 0.15000
    for i in range(30):
        price = base_price + i * 0.00005
        flow = OrderFlowSnapshot(
            delta_5s=200.0,
            imbalance_1s=0.65,
            iceberg_intensity=2.0,
            refill_count=2
        )
        radar.update(price=price, order_flow=flow, ts=time.time() + i)

    # 强信号：z ≥ 2.0 + 强订单流 + 带宽扩张
    print("🚀 强势突破...")
    flow = OrderFlowSnapshot(
        delta_5s=800.0,           # Delta 强
        imbalance_1s=0.82,        # 失衡强
        sweep_score_5s=4.0,       # 扫单强
        iceberg_intensity=3.5,    # 冰山存在
        refill_count=5
    )
    signal = radar.update(price=0.15250, order_flow=flow, ts=time.time() + 30)

    if signal and signal.stage == SignalStage.KGOD_CONFIRM:
        print(f"\n🎯 K神确认信号触发!")
        print(f"   级别: {signal.stage.value}")
        print(f"   方向: {signal.side.value}")
        print(f"   置信度: {signal.confidence:.1f}%")
        print(f"   原因:")
        for reason in signal.reasons:
            print(f"     - {reason}")

        # 调试信息
        print(f"\n   调试信息:")
        print(f"     z-score: {signal.debug['bb']['z']:.2f}")
        print(f"     MACD hist: {signal.debug['macd']['hist']:.5f}")
        print(f"     带宽斜率: {signal.debug['bb']['bw_slope']:.6f}")
    else:
        if signal:
            print(f"   触发了 {signal.stage.value} 信号（置信度: {signal.confidence:.1f}%）")
        else:
            print("   未触发信号（可能需要更强的突破）")


def demo_ban_detection():
    """演示 BAN 信号（走轨风险）"""
    print_section("演示 4: BAN 走轨风险检测")

    radar = create_kgod_radar(symbol="DOGE_USDT")

    # 填充数据
    base_price = 0.15000
    for i in range(30):
        flow = OrderFlowSnapshot(iceberg_intensity=1.0)
        radar.update(price=base_price, order_flow=flow, ts=time.time() + i)

    # 触发 BAN 信号（价格持续在上轨上方）
    print("⚠️  价格持续在上轨上方...")
    flow = OrderFlowSnapshot(
        acceptance_above_upper_s=35.0,  # 在上轨上方 35 秒
        iceberg_intensity=0.5           # 冰山弱化
    )
    signal = radar.update(price=0.15200, order_flow=flow, ts=time.time() + 30)

    if signal and signal.stage == SignalStage.BAN:
        print(f"\n🚫 BAN 信号触发!")
        print(f"   方向: {signal.side.value}")
        print(f"   BAN 原因:")
        for reason in signal.reasons:
            print(f"     - {reason}")

        print(f"\n   当前 BAN 累计: {radar.get_ban_count()} 条")
        print(f"   禁止开仓: {radar.should_ban_entry()}")
        print(f"   强制平仓: {radar.should_force_exit()}")
    else:
        print("   未触发 BAN 信号")

    # 累计更多 BAN 信号
    print("\n   继续累计 BAN 信号...")
    for i in range(2):
        flow = OrderFlowSnapshot(acceptance_above_upper_s=40.0, iceberg_intensity=0.3)
        signal = radar.update(price=0.15200, order_flow=flow, ts=time.time() + 30 + i)
        if signal and signal.stage == SignalStage.BAN:
            print(f"     - 触发第 {radar.get_ban_count()} 条 BAN")

    print(f"\n   ⚠️  当前 BAN 累计: {radar.get_ban_count()} 条")
    print(f"   🚫 禁止开仓: {radar.should_ban_entry()}")
    print(f"   ⛔ 强制平仓: {radar.should_force_exit()}")


def demo_statistics():
    """演示统计信息"""
    print_section("演示 5: 统计信息")

    radar = create_kgod_radar(symbol="DOGE_USDT")

    # 模拟一系列价格更新
    print("📊 模拟价格序列...")
    base_price = 0.15000
    for i in range(50):
        price = base_price + (i % 10) * 0.0001
        flow = OrderFlowSnapshot(
            delta_5s=(i % 5 - 2) * 100.0,
            imbalance_1s=0.5 + (i % 3) * 0.1,
            iceberg_intensity=1.0 + (i % 2)
        )
        signal = radar.update(price=price, order_flow=flow, ts=time.time() + i)

        if signal:
            print(f"   更新 {i+1}: {signal.stage.value} (置信度: {signal.confidence:.0f}%)")

    # 获取统计信息
    stats = radar.get_stats()
    print(f"\n📈 统计汇总:")
    print(f"   总更新次数: {stats['total_updates']}")
    print(f"   PRE_ALERT: {stats['pre_alert_count']} 次")
    print(f"   EARLY_CONFIRM: {stats['early_confirm_count']} 次")
    print(f"   KGOD_CONFIRM: {stats['kgod_confirm_count']} 次")
    print(f"   BAN: {stats['ban_count']} 次")


def main():
    """主函数"""
    print("="*70)
    print("K神战法 2.0 - 演示脚本".center(70))
    print("="*70)
    print("\n基于布林带 + MACD + 订单流的四层信号识别系统")
    print("PRE_ALERT → EARLY_CONFIRM → KGOD_CONFIRM → BAN")

    try:
        demo_basic_usage()
        demo_pre_alert()
        demo_kgod_confirm()
        demo_ban_detection()
        demo_statistics()

        print_section("所有演示完成")
        print("✅ K神战法 2.0 核心模块运行正常")
        print("\n核心特性:")
        print("  1. ✅ O(1) 复杂度增量计算（RollingBB + MACD）")
        print("  2. ✅ 四层信号识别（PRE/EARLY/KGOD/BAN）")
        print("  3. ✅ 走轨风险管理（≥2 禁入，≥3 强平）")
        print("  4. ✅ 置信度评分（0-100）")
        print("  5. ✅ 详细触发原因记录")

        print("\n下一步:")
        print("  - 集成到 alert_monitor.py（实时监控）")
        print("  - 历史数据回测（验证有效性）")
        print("  - 参数调优（提高准确率）")

    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
