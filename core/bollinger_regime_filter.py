"""
布林带×订单流环境过滤器 - 核心逻辑
Bollinger Regime Filter - Core Module

第三十四轮三方共识
功能:
- 5种环境状态识别 (SQUEEZE, EXPANSION, UPPER_TOUCH, LOWER_TOUCH, WALKING_BAND)
- 4种共振场景检测 (absorption_reversal, imbalance_reversal, iceberg_defense, walkband_risk)
- acceptance_time 追踪机制
- 置信度乘法调整
- 与 KGodRadar 集成

作者: Claude Code
日期: 2026-01-10
版本: v2.0 (第三十四轮)
"""

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum

# 复用现有模块
from core.kgod_radar import RollingBB, OrderFlowSnapshot

# 导入配置
from config import bollinger_settings as bsettings


# ==================== 枚举定义 ====================

class RegimeState(Enum):
    """布林带环境状态"""
    SQUEEZE = "SQUEEZE"              # 收口
    EXPANSION = "EXPANSION"          # 扩张
    UPPER_TOUCH = "UPPER_TOUCH"      # 触上轨
    LOWER_TOUCH = "LOWER_TOUCH"      # 触下轨
    WALKING_BAND = "WALKING_BAND"    # 走轨
    NEUTRAL = "NEUTRAL"              # 中性（带内）


class DecisionType(Enum):
    """判定结果类型"""
    ALLOW_LONG = "ALLOW_LONG"        # 允许做多
    ALLOW_SHORT = "ALLOW_SHORT"      # 允许做空
    BAN_LONG = "BAN_LONG"            # 禁止做多
    BAN_SHORT = "BAN_SHORT"          # 禁止做空
    NEUTRAL = "NEUTRAL"              # 中性（无操作）


# ==================== 数据结构 ====================

@dataclass
class RegimeDecision:
    """
    环境判定结果（GPT 建议的接口）

    字段说明:
    - decision: 决策类型 (ALLOW_LONG / ALLOW_SHORT / BAN_LONG / BAN_SHORT / NEUTRAL)
    - confidence_boost: 置信度增强系数 (0.15 = +15%)
    - reasons: 触发原因列表
    - meta: 元数据字典，包含:
        - acceptance_time: 带外停留时间（秒）
        - bandwidth: 当前带宽
        - state: 环境状态 (RegimeState)
        - scenario: 匹配的场景编号 (1-4)
        - bands: 布林带数据 {upper, mid, lower, bandwidth, z}
    """
    decision: DecisionType
    confidence_boost: float = 0.0  # 0.15 表示 +15%
    reasons: List[str] = field(default_factory=list)
    meta: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'decision': self.decision.value,
            'confidence_boost': self.confidence_boost,
            'reasons': self.reasons,
            'meta': self.meta
        }


# ==================== 核心过滤器 ====================

class BollingerRegimeFilter:
    """
    布林带×订单流环境过滤器

    核心功能:
    1. 环境状态识别（5种状态）
    2. 共振场景检测（4种场景）
    3. acceptance_time 追踪
    4. 置信度乘法调整
    5. 与 KGodRadar 集成
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化过滤器

        Args:
            config: 配置字典（可选，默认使用 bollinger_settings.py）
        """
        # 初始化布林带引擎（复用 RollingBB）
        self.bb = RollingBB(
            period=bsettings.BOLLINGER_PERIOD,
            num_std=bsettings.BOLLINGER_STD_DEV
        )

        # 状态追踪
        self.current_state = RegimeState.NEUTRAL
        self.state_enter_time = 0.0  # 状态进入时间

        # acceptance_time 追踪机制
        self.acceptance_time = 0.0  # 带外停留累计时间（秒）
        self.last_update_ts = 0.0  # 上次更新时间戳
        self.is_outside_band = False  # 是否在带外
        self.outside_band_start_ts = 0.0  # 开始带外的时间戳
        self.grace_period_start = 0.0  # 宽限期开始时间

        # 失衡历史（用于检测持续失衡）
        self.imbalance_history = deque(maxlen=5)

        # 统计信息
        self.stats = {
            'total_evaluations': 0,
            'allow_count': 0,
            'ban_count': 0,
            'neutral_count': 0,
        }

    def evaluate(
        self,
        price: float,
        order_flow: OrderFlowSnapshot,
        timestamp: Optional[float] = None
    ) -> RegimeDecision:
        """
        核心评估方法

        Args:
            price: 当前价格
            order_flow: 订单流快照（OrderFlowSnapshot）
            timestamp: 时间戳（可选，默认使用 time.time()）

        Returns:
            RegimeDecision: 环境判定结果
        """
        self.stats['total_evaluations'] += 1

        if timestamp is None:
            timestamp = time.time()

        # 更新布林带
        self.bb.update(price)

        # 检查布林带是否就绪
        if not self.bb.is_ready():
            return RegimeDecision(
                decision=DecisionType.NEUTRAL,
                confidence_boost=0.0,
                reasons=["bb_not_ready"],
                meta={'state': RegimeState.NEUTRAL}
            )

        # 获取布林带数据
        bands = {
            'upper': self.bb.upper,
            'mid': self.bb.mid,
            'lower': self.bb.lower,
            'bandwidth': self.bb.bandwidth,
            'z': self.bb.z
        }

        # 1. 识别环境状态
        state = self._detect_state(price, bands, timestamp)

        # 2. 更新 acceptance_time
        self._update_acceptance_time(state, timestamp)

        # 3. 构建 meta 数据
        meta = {
            'acceptance_time': self.acceptance_time,
            'bandwidth': bands['bandwidth'],
            'state': state,
            'bands': bands,
            'timestamp': timestamp
        }

        # 4. 根据状态执行相应检测
        if state == RegimeState.UPPER_TOUCH:
            return self._handle_upper_touch(price, bands, order_flow, meta)

        elif state == RegimeState.LOWER_TOUCH:
            return self._handle_lower_touch(price, bands, order_flow, meta)

        elif state == RegimeState.WALKING_BAND:
            # 走轨状态直接 BAN
            decision = self._determine_ban_direction(price, bands)
            self.stats['ban_count'] += 1

            return RegimeDecision(
                decision=decision,
                confidence_boost=0.0,  # BAN 不增强
                reasons=["walking_band_detected"],
                meta={**meta, 'scenario': 4}
            )

        else:
            # NEUTRAL, SQUEEZE, EXPANSION 状态 -> 无操作
            self.stats['neutral_count'] += 1

            return RegimeDecision(
                decision=DecisionType.NEUTRAL,
                confidence_boost=0.0,
                reasons=[],
                meta=meta
            )

    def _detect_state(self, price: float, bands: Dict, timestamp: float) -> RegimeState:
        """
        检测当前环境状态（5种状态）

        状态优先级:
        1. WALKING_BAND（最高优先级）
        2. UPPER_TOUCH / LOWER_TOUCH
        3. EXPANSION / SQUEEZE
        4. NEUTRAL（默认）
        """
        # 提取布林带数据
        upper = bands['upper']
        lower = bands['lower']
        bandwidth = bands['bandwidth']

        # 状态 1: SQUEEZE（收口）
        if bandwidth < bsettings.BANDWIDTH_SQUEEZE_THRESHOLD:
            return self._set_state(RegimeState.SQUEEZE, timestamp)

        # 状态 2: EXPANSION（扩张）
        if bandwidth > bsettings.BANDWIDTH_EXPANSION_THRESHOLD:
            return self._set_state(RegimeState.EXPANSION, timestamp)

        # 状态 3: UPPER_TOUCH（触上轨，含缓冲区）
        touch_buffer = bsettings.TOUCH_BUFFER
        if upper - touch_buffer <= price <= upper + touch_buffer:
            return self._set_state(RegimeState.UPPER_TOUCH, timestamp)

        # 状态 4: LOWER_TOUCH（触下轨，含缓冲区）
        if lower - touch_buffer <= price <= lower + touch_buffer:
            return self._set_state(RegimeState.LOWER_TOUCH, timestamp)

        # 状态 5: WALKING_BAND（走轨）
        # 条件: acceptance_time > 20s 且价格仍在带外
        if self.acceptance_time > bsettings.WALKBAND_MIN_ACCEPTANCE_TIME:
            if price > upper or price < lower:
                return self._set_state(RegimeState.WALKING_BAND, timestamp)

        # 默认: NEUTRAL（带内）
        return self._set_state(RegimeState.NEUTRAL, timestamp)

    def _set_state(self, new_state: RegimeState, timestamp: float) -> RegimeState:
        """
        设置状态（含状态平滑处理）

        状态切换至少持续 STATE_MIN_DURATION 秒才生效
        """
        # 如果状态未改变，直接返回
        if new_state == self.current_state:
            return self.current_state

        # 计算状态持续时间
        duration = timestamp - self.state_enter_time

        # 状态平滑：至少持续 2 秒才切换
        if duration < bsettings.STATE_MIN_DURATION:
            return self.current_state  # 保持原状态

        # 切换到新状态
        self.current_state = new_state
        self.state_enter_time = timestamp

        return new_state

    def _update_acceptance_time(self, state: RegimeState, timestamp: float):
        """
        更新 acceptance_time（带外停留累计时间）

        核心逻辑:
        1. 如果在带外（UPPER_TOUCH, LOWER_TOUCH, WALKING_BAND）-> 累积时间
        2. 如果回到带内 -> 启动宽限期，持续 reset_grace 秒后重置
        3. 如果在宽限期内又回到带外 -> 取消重置，继续累积
        """
        # 初始化时间戳
        if self.last_update_ts == 0:
            self.last_update_ts = timestamp
            return

        # 计算时间差
        dt = timestamp - self.last_update_ts
        self.last_update_ts = timestamp

        # 判断是否在带外
        is_outside = state in [
            RegimeState.UPPER_TOUCH,
            RegimeState.LOWER_TOUCH,
            RegimeState.WALKING_BAND
        ]

        if is_outside:
            # 在带外 -> 累积时间
            if not self.is_outside_band:
                # 刚进入带外
                self.is_outside_band = True
                self.outside_band_start_ts = timestamp
                self.grace_period_start = 0.0  # 取消宽限期

            # 累积 acceptance_time
            self.acceptance_time += dt

        else:
            # 在带内
            if self.is_outside_band:
                # 刚回到带内 -> 启动宽限期
                self.is_outside_band = False
                self.grace_period_start = timestamp

            # 检查宽限期
            if self.grace_period_start > 0:
                grace_duration = timestamp - self.grace_period_start

                # 超过宽限期 -> 重置 acceptance_time
                if grace_duration > bsettings.RESET_GRACE_PERIOD:
                    self.acceptance_time = 0.0
                    self.grace_period_start = 0.0

    def _handle_upper_touch(
        self,
        price: float,
        bands: Dict,
        order_flow: OrderFlowSnapshot,
        meta: Dict
    ) -> RegimeDecision:
        """
        处理触上轨场景

        检测顺序（优先级）:
        1. check_walkband_risk() -> BAN
        2. check_iceberg_defense() -> ALLOW_SHORT (+25%)
        3. check_imbalance_reversal() -> ALLOW_SHORT (+20%)
        4. check_absorption_reversal() -> ALLOW_SHORT (+15%)
        5. 无匹配 -> NEUTRAL
        """
        # 场景 4: 走轨风险 BAN（最高优先级）
        if self.check_walkband_risk(order_flow):
            self.stats['ban_count'] += 1
            return RegimeDecision(
                decision=DecisionType.BAN_SHORT,
                confidence_boost=0.0,
                reasons=["walkband_risk_ban"],
                meta={**meta, 'scenario': 4}
            )

        # 场景 3: 冰山护盘回归（+25%）
        if self.check_iceberg_defense(order_flow, expected_side="SELL"):
            self.stats['allow_count'] += 1
            return RegimeDecision(
                decision=DecisionType.ALLOW_SHORT,
                confidence_boost=bsettings.BOOST_ICEBERG_DEFENSE,
                reasons=["iceberg_defense_sell"],
                meta={**meta, 'scenario': 3}
            )

        # 场景 2: 失衡确认回归（+20%）
        if self.check_imbalance_reversal(order_flow, expected_side="SELL"):
            self.stats['allow_count'] += 1
            return RegimeDecision(
                decision=DecisionType.ALLOW_SHORT,
                confidence_boost=bsettings.BOOST_IMBALANCE_REVERSAL,
                reasons=["imbalance_reversal_sell"],
                meta={**meta, 'scenario': 2}
            )

        # 场景 1: 吸收型回归（+15%）
        if self.check_absorption_reversal(order_flow):
            self.stats['allow_count'] += 1
            return RegimeDecision(
                decision=DecisionType.ALLOW_SHORT,
                confidence_boost=bsettings.BOOST_ABSORPTION_REVERSAL,
                reasons=["absorption_reversal"],
                meta={**meta, 'scenario': 1}
            )

        # 无匹配场景
        self.stats['neutral_count'] += 1
        return RegimeDecision(
            decision=DecisionType.NEUTRAL,
            confidence_boost=0.0,
            reasons=["no_scenario_matched"],
            meta=meta
        )

    def _handle_lower_touch(
        self,
        price: float,
        bands: Dict,
        order_flow: OrderFlowSnapshot,
        meta: Dict
    ) -> RegimeDecision:
        """
        处理触下轨场景（镜像逻辑）

        检测顺序（优先级）:
        1. check_walkband_risk() -> BAN
        2. check_iceberg_defense() -> ALLOW_LONG (+25%)
        3. check_imbalance_reversal() -> ALLOW_LONG (+20%)
        4. check_absorption_reversal() -> ALLOW_LONG (+15%)
        5. 无匹配 -> NEUTRAL
        """
        # 场景 4: 走轨风险 BAN
        if self.check_walkband_risk(order_flow):
            self.stats['ban_count'] += 1
            return RegimeDecision(
                decision=DecisionType.BAN_LONG,
                confidence_boost=0.0,
                reasons=["walkband_risk_ban"],
                meta={**meta, 'scenario': 4}
            )

        # 场景 3: 冰山护盘回归（+25%）
        if self.check_iceberg_defense(order_flow, expected_side="BUY"):
            self.stats['allow_count'] += 1
            return RegimeDecision(
                decision=DecisionType.ALLOW_LONG,
                confidence_boost=bsettings.BOOST_ICEBERG_DEFENSE,
                reasons=["iceberg_defense_buy"],
                meta={**meta, 'scenario': 3}
            )

        # 场景 2: 失衡确认回归（+20%）
        if self.check_imbalance_reversal(order_flow, expected_side="BUY"):
            self.stats['allow_count'] += 1
            return RegimeDecision(
                decision=DecisionType.ALLOW_LONG,
                confidence_boost=bsettings.BOOST_IMBALANCE_REVERSAL,
                reasons=["imbalance_reversal_buy"],
                meta={**meta, 'scenario': 2}
            )

        # 场景 1: 吸收型回归（+15%）
        if self.check_absorption_reversal(order_flow):
            self.stats['allow_count'] += 1
            return RegimeDecision(
                decision=DecisionType.ALLOW_LONG,
                confidence_boost=bsettings.BOOST_ABSORPTION_REVERSAL,
                reasons=["absorption_reversal"],
                meta={**meta, 'scenario': 1}
            )

        # 无匹配场景
        self.stats['neutral_count'] += 1
        return RegimeDecision(
            decision=DecisionType.NEUTRAL,
            confidence_boost=0.0,
            reasons=["no_scenario_matched"],
            meta=meta
        )

    # ==================== 4种共振场景检测方法 ====================

    def check_absorption_reversal(self, order_flow: OrderFlowSnapshot) -> bool:
        """
        场景 1: 吸收型回归（触轨 + 吸收强 + Delta 背离）

        条件:
        - absorption_ask > 2.5 或 absorption_bid > 2.5
        - delta_slope_10s 转负（或绝对值 < 阈值）

        Returns:
            True 如果检测到吸收型回归
        """
        # 条件 1: 吸收强度高
        absorption_strong = (
            order_flow.absorption_ask > bsettings.ABSORPTION_SCORE_THRESHOLD or
            order_flow.absorption_bid > bsettings.ABSORPTION_SCORE_THRESHOLD
        )

        # 条件 2: Delta 背离（斜率转负或接近0）
        delta_divergence = abs(order_flow.delta_slope_10s) < bsettings.DELTA_SLOPE_THRESHOLD

        return absorption_strong and delta_divergence

    def check_imbalance_reversal(
        self,
        order_flow: OrderFlowSnapshot,
        expected_side: str
    ) -> bool:
        """
        场景 2: 失衡确认回归（触轨 + 失衡反转 + Delta 转负）

        Args:
            expected_side: 预期方向 ("BUY" 或 "SELL")

        条件:
        - 触上轨时: 卖方失衡 > 0.6 且 Delta 转负
        - 触下轨时: 买方失衡 > 0.6 且 Delta 转正

        Returns:
            True 如果检测到失衡确认回归
        """
        imbalance = order_flow.imbalance_1s

        # 记录失衡历史
        self.imbalance_history.append(imbalance)

        if expected_side == "SELL":
            # 触上轨 -> 检测卖方失衡
            # 失衡反转：imbalance < 0.4（卖方占比 > 60%）
            imbalance_condition = imbalance < (1 - bsettings.IMBALANCE_THRESHOLD)

            # Delta 转负
            delta_condition = order_flow.delta_slope_10s < 0

        elif expected_side == "BUY":
            # 触下轨 -> 检测买方失衡
            # 失衡反转：imbalance > 0.6（买方占比 > 60%）
            imbalance_condition = imbalance > bsettings.IMBALANCE_THRESHOLD

            # Delta 转正
            delta_condition = order_flow.delta_slope_10s > 0

        else:
            return False

        return imbalance_condition and delta_condition

    def check_iceberg_defense(
        self,
        order_flow: OrderFlowSnapshot,
        expected_side: str
    ) -> bool:
        """
        场景 3: 冰山护盘回归（触轨 + 反向冰山单）

        Args:
            expected_side: 预期方向 ("BUY" 或 "SELL")

        条件:
        - 触上轨时: 检测到卖方冰山（iceberg_intensity > 2.0）
        - 触下轨时: 检测到买方冰山（iceberg_intensity > 2.0）

        Returns:
            True 如果检测到冰山护盘回归
        """
        # 检测冰山强度
        iceberg_detected = order_flow.iceberg_intensity > bsettings.ICEBERG_INTENSITY_THRESHOLD

        # 检测补单次数（额外确认）
        refill_confirmed = order_flow.refill_count >= 2

        return iceberg_detected and refill_confirmed

    def check_walkband_risk(self, order_flow: OrderFlowSnapshot) -> bool:
        """
        场景 4: 走轨风险 BAN（acceptance_time > 60s + 动力确认）

        强走轨 BAN 双条件（GPT 建议）:
        - 条件 1: acceptance_time > 60s
        - 条件 2: 动力确认（以下任一满足）:
            * Delta 加速（abs(delta_slope) > 0.3）
            * 扫单确认（sweep_score > 2.0）
            * 失衡持续（连续 3 个周期 imbalance > 0.6）

        Returns:
            True 如果检测到走轨风险
        """
        # 条件 1: acceptance_time 超过阈值
        if self.acceptance_time <= bsettings.ACCEPTANCE_TIME_BAN:
            return False

        # 条件 2: 动力确认（3选1）

        # 动力 1: Delta 加速
        delta_accelerating = abs(order_flow.delta_slope_10s) > bsettings.DELTA_SLOPE_THRESHOLD

        # 动力 2: 扫单确认
        sweep_confirmed = order_flow.sweep_score_5s > bsettings.SWEEP_SCORE_THRESHOLD

        # 动力 3: 失衡持续（检查历史）
        if len(self.imbalance_history) >= 3:
            recent_imbalances = list(self.imbalance_history)[-3:]
            # 检测持续失衡（买方或卖方）
            persistent_buy = all(im > bsettings.IMBALANCE_THRESHOLD for im in recent_imbalances)
            persistent_sell = all(im < (1 - bsettings.IMBALANCE_THRESHOLD) for im in recent_imbalances)
            imbalance_persistent = persistent_buy or persistent_sell
        else:
            imbalance_persistent = False

        # 任一动力确认即 BAN
        momentum_confirmed = delta_accelerating or sweep_confirmed or imbalance_persistent

        return momentum_confirmed

    # ==================== 辅助方法 ====================

    def _determine_ban_direction(self, price: float, bands: Dict) -> DecisionType:
        """
        根据价格位置确定 BAN 方向

        Args:
            price: 当前价格
            bands: 布林带数据

        Returns:
            DecisionType.BAN_SHORT (价格在上轨上方) 或 DecisionType.BAN_LONG (价格在下轨下方)
        """
        if price > bands['upper']:
            return DecisionType.BAN_SHORT  # 禁止做空回归
        elif price < bands['lower']:
            return DecisionType.BAN_LONG  # 禁止做多回归
        else:
            return DecisionType.BAN_SHORT  # 默认

    def apply_boost_to_confidence(
        self,
        base_confidence: float,
        boost: float
    ) -> float:
        """
        应用乘法增强到置信度（GPT 建议）

        公式: new_confidence = min(100, base_confidence * (1 + boost))

        Args:
            base_confidence: 基础置信度 (0-100)
            boost: 增强系数 (0.15 = +15%)

        Returns:
            增强后的置信度 (0-100)
        """
        new_confidence = base_confidence * (1 + boost)
        return min(bsettings.MAX_CONFIDENCE, new_confidence)

    def should_boost_for_stage(self, kgod_stage: str) -> bool:
        """
        判断是否允许在该 KGodRadar 阶段应用增强

        Args:
            kgod_stage: KGodRadar 信号阶段 ("PRE_ALERT" / "EARLY_CONFIRM" / "KGOD_CONFIRM" / "BAN")

        Returns:
            True 如果允许增强
        """
        return kgod_stage in bsettings.BOOST_ALLOWED_STAGES

    def reset_acceptance_time(self):
        """手动重置 acceptance_time（用于测试或特殊情况）"""
        self.acceptance_time = 0.0
        self.is_outside_band = False
        self.grace_period_start = 0.0

    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = self.stats['total_evaluations']
        if total == 0:
            return self.stats

        return {
            **self.stats,
            'allow_pct': self.stats['allow_count'] / total * 100,
            'ban_pct': self.stats['ban_count'] / total * 100,
            'neutral_pct': self.stats['neutral_count'] / total * 100,
            'current_state': self.current_state.value,
            'acceptance_time': self.acceptance_time,
            'bb_ready': self.bb.is_ready(),
        }

    def __repr__(self) -> str:
        return (
            f"BollingerRegimeFilter("
            f"state={self.current_state.value}, "
            f"acceptance_time={self.acceptance_time:.1f}s, "
            f"evals={self.stats['total_evaluations']})"
        )


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("=" * 70)
    print("布林带×订单流环境过滤器 - 单元测试")
    print("=" * 70)

    # 创建过滤器
    filter_engine = BollingerRegimeFilter()

    # 测试 1: 吸收型回归
    print("\n[测试 1] 吸收型回归检测")
    print("-" * 70)

    # 模拟价格序列（逐渐上涨触上轨）
    import random
    base_price = 100.0
    prices = [base_price + random.gauss(0, 0.3) for _ in range(20)]
    prices += [base_price + 1.5 + i * 0.05 for i in range(10)]

    for i, price in enumerate(prices):
        # 模拟订单流（后期吸收强 + Delta 背离）
        flow = OrderFlowSnapshot(
            delta_5s=100 if i < 25 else 20,
            delta_slope_10s=0.5 if i < 25 else 0.1,  # Delta 衰减
            imbalance_1s=0.7 if i < 25 else 0.4,
            absorption_ask=2.0 if i < 25 else 3.0,  # 吸收增强
            absorption_bid=2.0,
            sweep_score_5s=1.0,
            iceberg_intensity=0.5,
            refill_count=1
        )

        result = filter_engine.evaluate(price, flow, timestamp=i)

        # 打印关键结果
        if result.decision != DecisionType.NEUTRAL or i >= 28:
            print(f"\n[{i+1:2d}] 价格: {price:.2f} | 状态: {result.meta.get('state', 'N/A')}")
            print(f"     决策: {result.decision.value} | 增强: +{result.confidence_boost*100:.0f}%")
            if result.reasons:
                print(f"     原因: {', '.join(result.reasons)}")
            if 'scenario' in result.meta:
                print(f"     场景: {result.meta['scenario']}")

    print("\n" + "=" * 70)
    print("✅ 测试完成！")
    print("\n统计信息:")
    stats = filter_engine.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")
