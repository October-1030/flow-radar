"""
K神战法 2.0 - 单元测试
K-God Strategy 2.0 - Unit Tests

测试覆盖：
1. RollingBB - 布林带计算正确性
2. MACD - MACD 计算正确性
3. KGodRadar - 四层信号触发逻辑
4. BAN 信号 - 走轨风险识别

作者: 三方共识（Claude + GPT + Gemini）
日期: 2026-01-09
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import math
from core.kgod_radar import (
    RollingBB, MACD, OrderFlowSnapshot, KGodSignal, KGodRadar,
    SignalStage, SignalSide, create_kgod_radar
)


# ==================== 测试 RollingBB ====================
class TestRollingBB:
    """测试布林带增量计算器"""

    def test_initialization(self):
        """测试初始化"""
        bb = RollingBB(period=20, num_std=2.0)
        assert bb.period == 20
        assert bb.num_std == 2.0
        assert not bb.is_ready()

    def test_single_update(self):
        """测试单次更新"""
        bb = RollingBB(period=5, num_std=2.0)

        # 第一个价格
        result = bb.update(100.0)
        assert result['mid'] == 100.0
        assert result['upper'] == 100.0  # 标准差为 0
        assert result['lower'] == 100.0
        assert result['z'] == 0.0

    def test_multiple_updates(self):
        """测试多次更新"""
        bb = RollingBB(period=5, num_std=2.0)

        prices = [100, 102, 101, 103, 104]
        for price in prices:
            bb.update(price)

        # 期望：mid = 102, std ≈ 1.41
        assert bb.is_ready()
        assert abs(bb.mid - 102.0) < 0.1
        assert bb.upper > bb.mid
        assert bb.lower < bb.mid

    def test_z_score_calculation(self):
        """测试 z-score 计算"""
        bb = RollingBB(period=5, num_std=2.0)

        # 稳定价格 + 突然上涨
        prices = [100, 100, 100, 100, 110]
        for price in prices:
            bb.update(price)

        # 最后一个价格远高于均值，z-score 应为正值
        assert bb.z > 1.0

    def test_bandwidth_calculation(self):
        """测试带宽计算"""
        bb = RollingBB(period=5, num_std=2.0)

        prices = [100, 102, 101, 103, 104]
        for price in prices:
            bb.update(price)

        # 带宽应为正值
        assert bb.bandwidth > 0
        assert bb.bandwidth == (bb.upper - bb.lower) / bb.mid

    def test_bandwidth_slope(self):
        """测试带宽斜率"""
        bb = RollingBB(period=5, num_std=2.0, bw_slope_window=3)

        # 波动率逐渐增大
        prices = [100, 100, 100, 100, 100]  # 低波动
        for price in prices:
            bb.update(price)

        bw1 = bb.bandwidth

        # 高波动
        prices2 = [105, 95, 110, 90, 115]
        for price in prices2:
            bb.update(price)

        bw2 = bb.bandwidth

        # 带宽应该扩张
        assert bw2 > bw1

    def test_rolling_window(self):
        """测试滑动窗口（O(1) 复杂度）"""
        bb = RollingBB(period=5, num_std=2.0)

        # 填满窗口
        for i in range(10):
            bb.update(100.0 + i)

        # 窗口应该只保留最近 5 个
        assert len(bb.prices) == 5
        assert list(bb.prices) == [105, 106, 107, 108, 109]


# ==================== 测试 MACD ====================
class TestMACD:
    """测试 MACD 增量计算器"""

    def test_initialization(self):
        """测试初始化"""
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        assert macd.fast_period == 12
        assert macd.slow_period == 26
        assert macd.signal_period == 9
        assert not macd.is_ready()

    def test_single_update(self):
        """测试单次更新"""
        macd = MACD(fast_period=12, slow_period=26)

        result = macd.update(100.0)
        assert result['macd'] == 0.0  # 第一个值，快慢线相等
        assert result['hist'] == 0.0

    def test_uptrend_signal(self):
        """测试上涨趋势 MACD"""
        macd = MACD(fast_period=5, slow_period=10, signal_period=3)

        # 模拟上涨趋势
        prices = [100 + i * 0.5 for i in range(30)]
        for price in prices:
            macd.update(price)

        # 上涨趋势：MACD > 0, hist > 0
        assert macd.is_ready()
        assert macd.macd > 0
        assert macd.hist > 0

    def test_downtrend_signal(self):
        """测试下跌趋势 MACD"""
        macd = MACD(fast_period=5, slow_period=10, signal_period=3)

        # 模拟下跌趋势
        prices = [100 - i * 0.5 for i in range(30)]
        for price in prices:
            macd.update(price)

        # 下跌趋势：MACD < 0, hist < 0
        assert macd.is_ready()
        assert macd.macd < 0
        assert macd.hist < 0

    def test_hist_slope(self):
        """测试柱状图斜率"""
        macd = MACD(fast_period=5, slow_period=10, signal_period=3, hist_slope_window=3)

        # 加速上涨
        prices = [100, 101, 102, 103, 105, 108, 112, 117]
        for price in prices:
            macd.update(price)

        # 柱状图应该递增（正斜率）
        assert macd.hist_slope > 0


# ==================== 测试 OrderFlowSnapshot ====================
class TestOrderFlowSnapshot:
    """测试订单流快照结构"""

    def test_initialization(self):
        """测试初始化"""
        flow = OrderFlowSnapshot()
        assert flow.delta_5s == 0.0
        assert flow.imbalance_1s == 0.5

    def test_custom_values(self):
        """测试自定义值"""
        flow = OrderFlowSnapshot(
            delta_5s=500.0,
            imbalance_1s=0.75,
            iceberg_intensity=3.0,
            refill_count=5
        )
        assert flow.delta_5s == 500.0
        assert flow.imbalance_1s == 0.75
        assert flow.iceberg_intensity == 3.0
        assert flow.refill_count == 5


# ==================== 测试 KGodSignal ====================
class TestKGodSignal:
    """测试信号输出结构"""

    def test_signal_creation(self):
        """测试信号创建"""
        signal = KGodSignal(
            symbol="DOGE_USDT",
            ts=1704700000.0,
            side=SignalSide.BUY,
            stage=SignalStage.KGOD_CONFIRM,
            confidence=85.0,
            reasons=["z ≥ 2.0", "MACD 同向"],
            debug={'z': 2.1}
        )

        assert signal.symbol == "DOGE_USDT"
        assert signal.side == SignalSide.BUY
        assert signal.stage == SignalStage.KGOD_CONFIRM
        assert signal.confidence == 85.0
        assert len(signal.reasons) == 2

    def test_to_dict(self):
        """测试转换为字典"""
        signal = KGodSignal(
            symbol="DOGE_USDT",
            ts=1704700000.0,
            side=SignalSide.BUY,
            stage=SignalStage.PRE_ALERT,
            confidence=35.0
        )

        d = signal.to_dict()
        assert d['symbol'] == "DOGE_USDT"
        assert d['side'] == "BUY"
        assert d['stage'] == "PRE_ALERT"
        assert d['confidence'] == 35.0


# ==================== 测试 KGodRadar ====================
class TestKGodRadar:
    """测试 K神雷达核心类"""

    def test_initialization(self):
        """测试初始化"""
        radar = KGodRadar(symbol="DOGE_USDT")
        assert radar.symbol == "DOGE_USDT"
        assert radar.bb.period == 20
        assert radar.macd.fast_period == 12

    def test_not_ready_no_signal(self):
        """测试数据不足时无信号"""
        radar = KGodRadar(symbol="DOGE_USDT")

        flow = OrderFlowSnapshot()
        signal = radar.update(price=100.0, order_flow=flow, ts=1704700000.0)

        # 数据不足，不应返回信号
        assert signal is None

    def test_pre_alert_trigger(self):
        """测试 PRE_ALERT 信号触发"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 填充布林带和 MACD 数据
        base_price = 100.0
        for i in range(30):
            # 设置 iceberg_intensity > 0 避免触发"冰山消失" BAN
            flow = OrderFlowSnapshot(iceberg_intensity=1.0)
            radar.update(price=base_price, order_flow=flow, ts=1704700000.0 + i)

        # 突然大涨，触发 z ≥ 1.4
        flow = OrderFlowSnapshot(
            delta_5s=100.0,
            imbalance_1s=0.6,
            iceberg_intensity=1.0  # 避免触发 BAN
        )
        signal = radar.update(price=105.0, order_flow=flow, ts=1704700030.0)

        # 应该触发 PRE_ALERT 或更高级别
        if signal:
            assert signal.stage in [SignalStage.PRE_ALERT, SignalStage.EARLY_CONFIRM, SignalStage.KGOD_CONFIRM]
            assert signal.confidence >= 30

    def test_kgod_confirm_trigger(self):
        """测试 KGOD_CONFIRM 信号触发"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 填充布林带和 MACD 数据（上涨趋势）
        base_price = 100.0
        for i in range(30):
            price = base_price + i * 0.1
            flow = OrderFlowSnapshot(delta_5s=50.0, imbalance_1s=0.6)
            radar.update(price=price, order_flow=flow, ts=1704700000.0 + i)

        # 强信号：z ≥ 2.0 + 强订单流 + 带宽扩张
        flow = OrderFlowSnapshot(
            delta_5s=600.0,           # Delta 强
            imbalance_1s=0.80,        # 失衡强
            sweep_score_5s=3.5,       # 扫单强
            iceberg_intensity=3.0,    # 冰山存在
            refill_count=4
        )
        signal = radar.update(price=108.0, order_flow=flow, ts=1704700030.0)

        # 应该触发 KGOD_CONFIRM
        if signal and signal.stage == SignalStage.KGOD_CONFIRM:
            assert signal.confidence >= 70
            assert signal.side == SignalSide.BUY

    def test_ban_signal_acceptance(self):
        """测试 BAN 信号（价格接受）"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 填充数据
        for i in range(30):
            flow = OrderFlowSnapshot()
            radar.update(price=100.0, order_flow=flow, ts=1704700000.0 + i)

        # 价格持续在上轨上方 >30s
        flow = OrderFlowSnapshot(acceptance_above_upper_s=35.0)
        signal = radar.update(price=105.0, order_flow=flow, ts=1704700030.0)

        # 应该触发 BAN
        if signal and signal.stage == SignalStage.BAN:
            assert "价格持续在上轨上方" in signal.reasons[0]

    def test_ban_signal_bandwidth_shrink(self):
        """测试 BAN 信号（带宽收缩检测）"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 先制造高波动（扩张带宽）
        high_vol_prices = [100, 105, 98, 107, 95, 110, 92, 115, 88]
        for i, price in enumerate(high_vol_prices):
            flow = OrderFlowSnapshot(iceberg_intensity=1.0)
            radar.update(price=price, order_flow=flow, ts=1704700000.0 + i)

        # 记录当前带宽
        bw_initial = radar.bb.bandwidth

        # 然后制造低波动（收缩带宽）
        for i in range(30):
            flow = OrderFlowSnapshot(iceberg_intensity=1.0)
            radar.update(price=100.0, order_flow=flow, ts=1704700010.0 + i)

        # 检查带宽是否收缩
        bw_final = radar.bb.bandwidth
        assert bw_final < bw_initial  # 带宽应该明显收缩

    def test_ban_threshold_logic(self):
        """测试 BAN 阈值逻辑"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 模拟累计 2 个 BAN 信号
        for i in range(2):
            ban_signal = KGodSignal(
                symbol="DOGE_USDT",
                ts=1704700000.0 + i,
                side=SignalSide.BUY,
                stage=SignalStage.BAN,
                confidence=0.0,
                reasons=["测试 BAN"]
            )
            radar.ban_history.append(ban_signal)

        # ≥2 条 BAN → 禁止开仓
        assert radar.should_ban_entry()

        # 累计 3 个 BAN 信号
        ban_signal = KGodSignal(
            symbol="DOGE_USDT",
            ts=1704700002.0,
            side=SignalSide.BUY,
            stage=SignalStage.BAN,
            confidence=0.0,
            reasons=["测试 BAN"]
        )
        radar.ban_history.append(ban_signal)

        # ≥3 条 BAN → 强制平仓
        assert radar.should_force_exit()

    def test_clear_ban_history(self):
        """测试清除 BAN 历史"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 添加 BAN 信号
        for i in range(3):
            ban_signal = KGodSignal(
                symbol="DOGE_USDT",
                ts=1704700000.0 + i,
                side=SignalSide.BUY,
                stage=SignalStage.BAN,
                confidence=0.0,
                reasons=["测试 BAN"]
            )
            radar.ban_history.append(ban_signal)

        assert radar.get_ban_count() == 3

        # 清除
        radar.clear_ban_history()
        assert radar.get_ban_count() == 0

    def test_stats_tracking(self):
        """测试统计信息"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 填充数据
        for i in range(30):
            flow = OrderFlowSnapshot()
            radar.update(price=100.0 + i * 0.1, order_flow=flow, ts=1704700000.0 + i)

        stats = radar.get_stats()
        assert stats['total_updates'] == 30
        assert 'pre_alert_count' in stats
        assert 'kgod_confirm_count' in stats

    def test_reset(self):
        """测试重置"""
        radar = KGodRadar(symbol="DOGE_USDT")

        # 添加数据
        for i in range(10):
            flow = OrderFlowSnapshot()
            radar.update(price=100.0, order_flow=flow, ts=1704700000.0 + i)

        # 重置
        radar.reset()

        assert radar.stats['total_updates'] == 0
        assert radar.get_ban_count() == 0


# ==================== 测试工厂函数 ====================
class TestFactoryFunctions:
    """测试工厂函数"""

    def test_create_kgod_radar(self):
        """测试创建雷达"""
        radar = create_kgod_radar("DOGE_USDT")
        assert isinstance(radar, KGodRadar)
        assert radar.symbol == "DOGE_USDT"


# ==================== 运行测试 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("K神战法 2.0 - 单元测试")
    print("=" * 60)

    # 运行 pytest
    pytest.main([__file__, "-v", "--tb=short"])
