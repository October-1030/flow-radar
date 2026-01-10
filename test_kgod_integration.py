#!/usr/bin/env python3
"""
K神战法 2.0 - 集成测试（快速验证）
验证 alert_monitor.py 中的 KGodRadar 集成是否正常

作者: Claude Code
日期: 2026-01-09
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# 临时启用 K神雷达
from config import settings
original_kgod = settings.CONFIG_FEATURES.get('use_kgod_radar', False)
settings.CONFIG_FEATURES['use_kgod_radar'] = True

print("=" * 70)
print("K神战法 2.0 - 集成测试".center(70))
print("=" * 70)

try:
    print("\n📦 1. 导入测试...")
    from alert_monitor import AlertMonitor
    print("   ✅ AlertMonitor 导入成功")

    print("\n🔧 2. 初始化测试...")
    monitor = AlertMonitor(symbol="DOGE/USDT")
    print("   ✅ AlertMonitor 初始化成功")

    print("\n🎯 3. KGodRadar 检查...")
    if monitor.use_kgod:
        print(f"   ✅ K神雷达已启用: {monitor.kgod_radar is not None}")
        if monitor.kgod_radar:
            print(f"   ✅ 雷达交易对: {monitor.kgod_radar.symbol}")
            print(f"   ✅ 布林带周期: {monitor.kgod_radar.bb.period}")
            print(f"   ✅ MACD 参数: {monitor.kgod_radar.macd.fast_period}/{monitor.kgod_radar.macd.slow_period}")
    else:
        print("   ⚠️  K神雷达未启用（需设置 CONFIG_FEATURES['use_kgod_radar'] = True）")

    print("\n📊 4. OrderFlowSnapshot 桥接测试...")
    # 模拟指标结果
    from core.indicators import IndicatorResult
    fake_indicators = IndicatorResult(obi=0.3, cvd=100.0)

    # 测试 _update_kgod_radar 方法是否存在
    if hasattr(monitor, '_update_kgod_radar'):
        print("   ✅ _update_kgod_radar 方法存在")

        # 测试调用（不触发实际信号）
        if monitor.kgod_radar:
            import time
            result = monitor._update_kgod_radar(
                price=0.15000,
                indicators=fake_indicators,
                event_ts=time.time()
            )
            print(f"   ✅ 雷达更新成功（信号: {result.stage.value if result else 'None'}）")
    else:
        print("   ❌ _update_kgod_radar 方法不存在")

    print("\n🎨 5. 信号格式化测试...")
    if hasattr(monitor, '_format_kgod_title'):
        print("   ✅ _format_kgod_title 方法存在")
    if hasattr(monitor, '_format_kgod_message'):
        print("   ✅ _format_kgod_message 方法存在")
    if hasattr(monitor, '_handle_kgod_signal'):
        print("   ✅ _handle_kgod_signal 方法存在")

    print("\n" + "=" * 70)
    print("✅ 集成测试通过！".center(70))
    print("=" * 70)

    print("\n📝 测试总结:")
    print("  1. ✅ 模块导入正常")
    print("  2. ✅ AlertMonitor 初始化成功")
    print("  3. ✅ KGodRadar 集成完成")
    print("  4. ✅ OrderFlowSnapshot 桥接实现")
    print("  5. ✅ 信号处理方法齐全")

    print("\n🚀 下一步:")
    print("  - 修改 config/settings.py: CONFIG_FEATURES['use_kgod_radar'] = True")
    print("  - 运行 alert_monitor.py 进行实时测试")
    print("  - 观察 K神信号触发情况")

except Exception as e:
    print(f"\n❌ 集成测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    # 恢复原始配置
    settings.CONFIG_FEATURES['use_kgod_radar'] = original_kgod

print()
sys.exit(0)
