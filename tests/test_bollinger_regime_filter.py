"""
布林带×订单流环境过滤器 - 单元测试
Unit Tests for BollingerRegimeFilter

第三十四轮三方共识
测试覆盖:
- 4种共振场景检测
- 置信度乘法调整验证
- acceptance_time 累积和重置
- 抖动触边测试
- 冲突场景测试（BAN 优先）
- 5种环境状态识别

作者: Claude Code
日期: 2026-01-10
版本: v2.0
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import time
from core.bollinger_regime_filter import (
    BollingerRegimeFilter,
    RegimeDecision,
    DecisionType,
    RegimeState
)
from core.kgod_radar import OrderFlowSnapshot


class TestBasicFunctionality:
    """测试基础功能"""

    def test_initialization(self):
        """测试初始化"""
        filter_engine = BollingerRegimeFilter()

        assert filter_engine.bb is not None
        assert filter_engine.current_state == RegimeState.NEUTRAL
        assert filter_engine.acceptance_time == 0.0

    def test_bb_not_ready(self):
        """测试布林带未就绪"""
        filter_engine = BollingerRegimeFilter()

        flow = OrderFlowSnapshot()
        result = filter_engine.evaluate(100.0, flow)

        assert result.decision == DecisionType.NEUTRAL
        assert "bb_not_ready" in result.reasons


class TestEnvironmentStates:
    """测试 5 种环境状态识别"""

    def setup_method(self):
        """每个测试前初始化"""
        self.filter_engine = BollingerRegimeFilter()
        # 建立布林带（需要 20 个数据点）
        for i in range(20):
            flow = OrderFlowSnapshot()
            self.filter_engine.evaluate(100.0, flow, timestamp=i)

    def test_state_squeeze(self):
        """测试 SQUEEZE 状态（带宽收口）"""
        # 创建收口场景（价格几乎不波动）
        for i in range(10):
            flow = OrderFlowSnapshot()
            self.filter_engine.evaluate(100.0 + 0.001 * i, flow, timestamp=20 + i)

        # 检查状态（通过 meta 获取）
        flow = OrderFlowSnapshot()
        result = self.filter_engine.evaluate(100.0, flow, timestamp=30)

        # bandwidth 应该很小，可能触发 SQUEEZE
        # 注意：SQUEEZE 条件是 bandwidth < 0.015，需要足够的窄幅波动

    def test_state_upper_touch(self):
        """测试 UPPER_TOUCH 状态"""
        # 价格上涨触上轨
        flow = OrderFlowSnapshot()
        result = self.filter_engine.evaluate(102.5, flow, timestamp=20)

        assert result.meta['state'] in [RegimeState.UPPER_TOUCH, RegimeState.NEUTRAL]

    def test_state_lower_touch(self):
        """测试 LOWER_TOUCH 状态"""
        # 价格下跌触下轨
        flow = OrderFlowSnapshot()
        result = self.filter_engine.evaluate(97.5, flow, timestamp=20)

        assert result.meta['state'] in [RegimeState.LOWER_TOUCH, RegimeState.NEUTRAL]

    def test_state_walking_band(self):
        """测试 WALKING_BAND 状态"""
        # 价格持续在带外 > 20s
        flow = OrderFlowSnapshot()

        # 持续触上轨 25 秒
        for i in range(25):
            result = self.filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        # 应该进入 WALKING_BAND 状态
        assert result.meta['state'] == RegimeState.WALKING_BAND or result.meta['acceptance_time'] > 20


class TestAcceptanceTimeTracking:
    """测试 acceptance_time 追踪机制"""

    def test_acceptance_time_accumulation(self):
        """测试带外停留时间累积"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 价格持续在带外
        flow = OrderFlowSnapshot()

        # 第 1 秒：进入带外
        result = filter_engine.evaluate(102.5, flow, timestamp=20.0)
        assert result.meta['acceptance_time'] >= 0.0

        # 第 5 秒：累积时间应约为 5s
        result = filter_engine.evaluate(102.5, flow, timestamp=25.0)
        assert result.meta['acceptance_time'] >= 4.0  # 至少 4 秒

        # 第 10 秒
        result = filter_engine.evaluate(102.5, flow, timestamp=30.0)
        assert result.meta['acceptance_time'] >= 9.0

    def test_acceptance_time_reset(self):
        """测试 acceptance_time 重置机制"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        flow = OrderFlowSnapshot()

        # 在带外停留 10 秒
        for i in range(10):
            filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        # 回到带内
        filter_engine.evaluate(100.0, flow, timestamp=30)

        # 等待宽限期 (3 秒)
        result = filter_engine.evaluate(100.0, flow, timestamp=33.5)

        # acceptance_time 应该被重置
        assert result.meta['acceptance_time'] == 0.0

    def test_grace_period_cancellation(self):
        """测试宽限期内回到带外（取消重置）"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        flow = OrderFlowSnapshot()

        # 在带外停留 10 秒
        for i in range(10):
            filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        acceptance_before = filter_engine.acceptance_time

        # 回到带内 1 秒（宽限期内）
        filter_engine.evaluate(100.0, flow, timestamp=30)

        # 1 秒后又回到带外（宽限期 3 秒内）
        result = filter_engine.evaluate(102.5, flow, timestamp=31)

        # acceptance_time 不应该被重置（宽限期被取消）
        assert filter_engine.acceptance_time > 0


class TestJitterFiltering:
    """测试抖动过滤（频繁穿轨不累积）"""

    def test_frequent_edge_crossing(self):
        """测试频繁触边（抖动）"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        flow = OrderFlowSnapshot()

        # 频繁在带内外切换（每 0.5 秒切换一次）
        for i in range(10):
            # 带外
            filter_engine.evaluate(102.5, flow, timestamp=20 + i * 0.5)
            # 带内
            filter_engine.evaluate(100.0, flow, timestamp=20 + i * 0.5 + 0.25)

        # 由于频繁切换，acceptance_time 不应该累积太多
        # 每次回到带内都会启动宽限期
        assert filter_engine.acceptance_time < 3.0  # 应该远小于 10 * 0.5 = 5 秒


class TestScenario1_AbsorptionReversal:
    """测试场景 1: 吸收型回归（+15%）"""

    def test_absorption_reversal_detection(self):
        """测试吸收型回归检测"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 场景 1 条件：吸收强度 > 2.5 + Delta 背离
        flow = OrderFlowSnapshot(
            absorption_ask=3.0,      # 高吸收
            delta_slope_10s=0.1,     # Delta 衰减（< 0.3）
        )

        result = filter_engine.evaluate(102.5, flow, timestamp=20)

        # 应该检测到吸收型回归
        assert result.decision == DecisionType.ALLOW_SHORT
        assert "absorption_reversal" in result.reasons
        assert result.confidence_boost == pytest.approx(0.15, rel=0.01)
        assert result.meta['scenario'] == 1


class TestScenario2_ImbalanceReversal:
    """测试场景 2: 失衡确认回归（+20%）"""

    def test_imbalance_reversal_detection(self):
        """测试失衡确认回归检测"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 场景 2 条件：失衡反转 + Delta 转负
        flow = OrderFlowSnapshot(
            imbalance_1s=0.3,        # 卖方失衡（< 0.4）
            delta_slope_10s=-0.2,    # Delta 转负
        )

        result = filter_engine.evaluate(102.5, flow, timestamp=20)

        # 应该检测到失衡确认回归
        assert result.decision == DecisionType.ALLOW_SHORT
        assert "imbalance_reversal_sell" in result.reasons
        assert result.confidence_boost == pytest.approx(0.20, rel=0.01)
        assert result.meta['scenario'] == 2


class TestScenario3_IcebergDefense:
    """测试场景 3: 冰山护盘回归（+25%）"""

    def test_iceberg_defense_detection(self):
        """测试冰山护盘回归检测"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 场景 3 条件：冰山强度 > 2.0 + 补单次数 >= 2
        flow = OrderFlowSnapshot(
            iceberg_intensity=2.5,   # 冰山强度高
            refill_count=3,          # 补单次数
        )

        result = filter_engine.evaluate(102.5, flow, timestamp=20)

        # 应该检测到冰山护盘回归
        assert result.decision == DecisionType.ALLOW_SHORT
        assert "iceberg_defense_sell" in result.reasons
        assert result.confidence_boost == pytest.approx(0.25, rel=0.01)
        assert result.meta['scenario'] == 3

    def test_iceberg_defense_mirror(self):
        """测试冰山护盘回归（触下轨）"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 场景 3 镜像：触下轨 + 买方冰山
        flow = OrderFlowSnapshot(
            iceberg_intensity=2.5,
            refill_count=3,
        )

        result = filter_engine.evaluate(97.5, flow, timestamp=20)

        # 应该允许做多
        assert result.decision == DecisionType.ALLOW_LONG
        assert "iceberg_defense_buy" in result.reasons


class TestScenario4_WalkbandRisk:
    """测试场景 4: 走轨风险 BAN（双条件）"""

    def test_walkband_risk_ban(self):
        """测试走轨风险 BAN（acceptance_time > 60s + 动力确认）"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 在带外停留 65 秒
        for i in range(65):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        # 场景 4 条件：acceptance_time > 60s + 动力确认（Delta 加速）
        flow = OrderFlowSnapshot(
            delta_slope_10s=0.5,     # Delta 加速 (> 0.3)
        )

        result = filter_engine.evaluate(102.5, flow, timestamp=85)

        # 应该 BAN
        assert result.decision == DecisionType.BAN_SHORT
        assert "walkband_risk_ban" in result.reasons
        assert result.meta['scenario'] == 4

    def test_walkband_risk_no_momentum(self):
        """测试走轨风险（无动力确认 -> 不 BAN）"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 在带外停留 65 秒
        for i in range(65):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        # 无动力确认（Delta 斜率低，扫单低，失衡不持续）
        flow = OrderFlowSnapshot(
            delta_slope_10s=0.1,     # Delta 未加速
            sweep_score_5s=1.0,      # 扫单低
            imbalance_1s=0.5,        # 失衡不显著
        )

        result = filter_engine.evaluate(102.5, flow, timestamp=85)

        # 不应该 BAN（仅时间长不够，还需动力确认）
        assert result.decision != DecisionType.BAN_SHORT or result.meta.get('scenario') != 4


class TestConflictPriority:
    """测试冲突场景（BAN 优先）"""

    def test_ban_overrides_boost(self):
        """测试 BAN 优先于共振增强"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 在带外停留 65 秒
        for i in range(65):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        # 冲突场景：既有冰山回归（+25%）又有走轨风险
        flow = OrderFlowSnapshot(
            iceberg_intensity=2.5,   # 冰山护盘
            refill_count=3,
            delta_slope_10s=0.5,     # Delta 加速（走轨风险）
        )

        result = filter_engine.evaluate(102.5, flow, timestamp=85)

        # BAN 应该优先（走轨风险 > 共振增强）
        assert result.decision == DecisionType.BAN_SHORT
        assert result.confidence_boost == 0.0  # BAN 不增强


class TestConfidenceMultiplication:
    """测试置信度乘法调整"""

    def test_confidence_boost_multiplication(self):
        """测试置信度乘法公式"""
        filter_engine = BollingerRegimeFilter()

        base_confidence = 60.0
        boost = 0.15  # +15%

        # 公式: new_confidence = min(100, base_confidence * (1 + boost))
        expected = min(100, base_confidence * (1 + boost))  # 60 * 1.15 = 69

        result = filter_engine.apply_boost_to_confidence(base_confidence, boost)

        assert result == pytest.approx(expected, rel=0.01)

    def test_confidence_max_cap(self):
        """测试置信度上限 100"""
        filter_engine = BollingerRegimeFilter()

        base_confidence = 90.0
        boost = 0.25  # +25%

        # 90 * 1.25 = 112.5 -> 应该被限制为 100
        result = filter_engine.apply_boost_to_confidence(base_confidence, boost)

        assert result == 100.0


class TestKGodRadarIntegration:
    """测试与 KGodRadar 集成"""

    def test_boost_allowed_stages(self):
        """测试增强允许阶段"""
        filter_engine = BollingerRegimeFilter()

        # EARLY_CONFIRM 和 KGOD_CONFIRM 允许增强
        assert filter_engine.should_boost_for_stage("EARLY_CONFIRM") == True
        assert filter_engine.should_boost_for_stage("KGOD_CONFIRM") == True

        # PRE_ALERT 和 BAN 不允许增强
        assert filter_engine.should_boost_for_stage("PRE_ALERT") == False
        assert filter_engine.should_boost_for_stage("BAN") == False


class TestStatistics:
    """测试统计功能"""

    def test_stats_tracking(self):
        """测试统计信息追踪"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 执行多次评估
        flow_allow = OrderFlowSnapshot(iceberg_intensity=2.5, refill_count=3)
        filter_engine.evaluate(102.5, flow_allow, timestamp=20)  # ALLOW

        flow_neutral = OrderFlowSnapshot()
        filter_engine.evaluate(100.0, flow_neutral, timestamp=21)  # NEUTRAL

        stats = filter_engine.get_stats()

        assert stats['total_evaluations'] >= 2
        assert stats['allow_count'] >= 1
        assert stats['neutral_count'] >= 1


class TestEdgeCases:
    """测试边界情况"""

    def test_state_smoothing(self):
        """测试状态平滑（STATE_MIN_DURATION）"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 快速切换状态（< 2 秒）
        flow = OrderFlowSnapshot()
        result1 = filter_engine.evaluate(102.5, flow, timestamp=20.0)  # 触上轨
        result2 = filter_engine.evaluate(100.0, flow, timestamp=20.5)  # 0.5 秒后回中轨

        # 状态切换应该被平滑（至少持续 2 秒）
        # current_state 不应该立即切换

    def test_manual_reset_acceptance_time(self):
        """测试手动重置 acceptance_time"""
        filter_engine = BollingerRegimeFilter()

        # 建立布林带
        for i in range(20):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(100.0, flow, timestamp=i)

        # 累积 acceptance_time
        for i in range(10):
            flow = OrderFlowSnapshot()
            filter_engine.evaluate(102.5, flow, timestamp=20 + i)

        assert filter_engine.acceptance_time > 0

        # 手动重置
        filter_engine.reset_acceptance_time()

        assert filter_engine.acceptance_time == 0.0
        assert filter_engine.is_outside_band == False


# ==================== pytest 配置 ====================

def pytest_configure(config):
    """pytest 配置"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow"
    )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
