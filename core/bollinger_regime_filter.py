#!/usr/bin/env python3
"""
Bollinger Bands Regime Filter - 布林带环境过滤器
流动性雷达 - 融合订单流的布林带判定系统

核心功能:
- 三态判定: ALLOW_REVERSION / BAN_REVERSION / NO_TRADE
- 走轨风险检测（6个维度）
- 回归信号识别（5个维度）
- 冰山信号融合
- 连续亏损保护

作者: Claude Code (三方共识)
日期: 2026-01-09
版本: v1.0
参考: 第二十五轮三方共识
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict
import time

from core.bollinger_engine import IncrementalBollingerBands
from config.bollinger_settings import CONFIG_BOLLINGER_REGIME, CONFIG_BOLLINGER_BANDS


# ==================== 枚举定义 ====================

class RegimeSignal(Enum):
    """环境信号类型"""
    ALLOW_REVERSION_SHORT = "allow_reversion_short"     # 允许做空回归
    ALLOW_REVERSION_LONG = "allow_reversion_long"       # 允许做多回归
    BAN_REVERSION = "ban_reversion"                     # 禁止回归（走轨风险）
    NO_TRADE = "no_trade"                               # 无交易（证据不足）


# ==================== 数据结构 ====================

@dataclass
class RegimeResult:
    """环境判定结果"""
    signal: RegimeSignal                # 信号类型
    confidence: float                   # 置信度 (0-1)
    triggers: List[str] = field(default_factory=list)  # 触发因素列表
    band_position: str = "middle"       # 价格位置: upper/lower/middle
    timestamp: float = 0.0              # 时间戳

    # 详细评分（调试用）
    ban_score: float = 0.0              # 走轨风险得分
    reversion_score: float = 0.0        # 回归信号得分

    # 额外信息
    bands: Optional[Dict] = None        # 布林带数据
    scenario: Optional[str] = None      # 匹配的场景（A/B/C/D/E/F）


# ==================== 核心过滤器 ====================

class BollingerRegimeFilter:
    """
    布林带环境过滤器 - 融合订单流判定

    工作流程:
    1. 更新布林带
    2. 检测价格位置（触轨？）
    3. 如果触轨:
       a. 评估走轨风险（BAN_REVERSION）
       b. 评估回归信号（ALLOW_REVERSION）
    4. 输出判定结果

    三方共识场景:
    - 场景 A: 衰竭性回归 (+15%)
    - 场景 B: 失衡确认回归 (+20%)
    - 场景 C: 冰山护盘回归 (+25%)
    - 场景 D: 挤压后触边界 (+12%)
    - 场景 E: 趋势性走轨 (禁止)
    - 场景 F: 冰山反向突破 (禁止)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化环境过滤器

        Args:
            config: 配置字典（可选，默认使用 bollinger_settings.py）
        """
        # 使用默认配置或用户提供的配置
        if config is None:
            self.config = CONFIG_BOLLINGER_REGIME
            bb_config = CONFIG_BOLLINGER_BANDS
        else:
            self.config = config
            bb_config = config.get("bollinger_bands", {})

        # 初始化布林带引擎
        self.bb = IncrementalBollingerBands(
            period=bb_config.get("period", 20),
            std_dev=bb_config.get("std_dev", 2.0)
        )

        # 提取阈值（避免重复查找）
        self._extract_thresholds()

        # 状态追踪
        self.consecutive_losses = 0
        self.last_loss_time = 0
        self.last_touch_time = {"upper": 0, "lower": 0}
        self.last_band_position = "middle"

        # 带宽历史（用于挤压检测）
        from collections import deque
        self.bandwidth_history = deque(
            maxlen=bb_config.get("bandwidth_window", 100)
        )

        # 统计信息
        self.stats = {
            "total_evaluations": 0,
            "allow_reversion_count": 0,
            "ban_reversion_count": 0,
            "no_trade_count": 0,
        }

    def _extract_thresholds(self):
        """提取配置阈值（性能优化）"""
        cfg = self.config

        # 走轨风险阈值
        self.delta_slope_threshold = cfg.get("delta_slope_threshold", 0.5)
        self.imbalance_threshold = cfg.get("imbalance_threshold", 0.6)
        self.sweep_score_threshold = cfg.get("sweep_score_threshold", 0.7)
        self.acceptance_time_threshold = cfg.get("acceptance_time_threshold", 30)
        self.bandwidth_expansion_threshold = cfg.get("bandwidth_expansion_threshold", 0.008)

        # 回归信号阈值
        self.delta_divergence_threshold = cfg.get("delta_divergence_threshold", -0.1)
        self.absorption_threshold = cfg.get("absorption_threshold", 0.5)
        self.depth_depletion_threshold = cfg.get("depth_depletion_threshold", 0.3)

        # 风控参数
        self.max_consecutive_losses = cfg.get("max_consecutive_losses", 3)
        self.cooldown_period = cfg.get("cooldown_period", 300)
        self.min_confidence = cfg.get("min_confidence", 0.6)

        # 权重
        self.ban_weights = cfg.get("ban_reversion_weights", {})
        self.ban_threshold = cfg.get("ban_reversion_threshold", 2.0)

        self.reversion_weights = cfg.get("allow_reversion_weights", {})
        self.reversion_threshold = cfg.get("allow_reversion_threshold", 2.0)

        # 置信度提升
        self.confidence_boost = cfg.get("confidence_boost", {})

        # 冰山权重
        self.iceberg_weight = cfg.get("iceberg_weight", {})

    def evaluate(
        self,
        price: float,
        delta_cumulative: float = 0.0,
        delta_slope: float = 0.0,
        absorption_ratio: float = 0.0,
        imbalance: Optional[Dict] = None,
        sweep_score: float = 0.0,
        iceberg_signals: Optional[List] = None,
        acceptance_time: float = 0.0,
        depth_depletion: float = 0.0
    ) -> RegimeResult:
        """
        核心评估：价格触边界时综合判定

        Args:
            price: 当前价格
            delta_cumulative: 累积 Delta (USDT)
            delta_slope: Delta 斜率 (USDT/s)
            absorption_ratio: 吸收率 (0-1)
            imbalance: 失衡字典 {"buy_ratio": 0.7, "sell_ratio": 0.3}
            sweep_score: 扫单得分 (0-1)
            iceberg_signals: 冰山信号列表
            acceptance_time: 价格在边界外持续时间（秒）
            depth_depletion: 深度耗尽比例 (0-1)

        Returns:
            RegimeResult: 判定结果
        """
        self.stats["total_evaluations"] += 1

        # 默认值
        if imbalance is None:
            imbalance = {"buy_ratio": 0.5, "sell_ratio": 0.5}

        if iceberg_signals is None:
            iceberg_signals = []

        # 更新布林带
        bands = self.bb.update(price)

        # 数据不足
        if bands is None:
            return RegimeResult(
                signal=RegimeSignal.NO_TRADE,
                confidence=0.0,
                triggers=["insufficient_data"],
                band_position="unknown",
                timestamp=time.time()
            )

        # 更新带宽历史
        self.bandwidth_history.append(bands["bandwidth"])

        # 连续亏损保护（Gemini 建议）
        if self.consecutive_losses >= self.max_consecutive_losses:
            # 检查冷却期
            if time.time() - self.last_loss_time < self.cooldown_period:
                self.stats["no_trade_count"] += 1
                return RegimeResult(
                    signal=RegimeSignal.BAN_REVERSION,
                    confidence=0.9,
                    triggers=["max_consecutive_losses", "in_cooldown"],
                    band_position="middle",
                    timestamp=time.time(),
                    bands=bands
                )

        # 检测价格位置
        band_position = self._get_band_position(price, bands)
        self.last_band_position = band_position

        # === 触上轨逻辑 ===
        if band_position in ["upper", "above_upper"]:
            self.last_touch_time["upper"] = time.time()
            result = self._evaluate_upper(
                price, bands, delta_cumulative, delta_slope,
                absorption_ratio, imbalance, sweep_score,
                iceberg_signals, acceptance_time, depth_depletion
            )
            result.bands = bands
            return result

        # === 触下轨逻辑（镜像）===
        elif band_position in ["lower", "below_lower"]:
            self.last_touch_time["lower"] = time.time()
            result = self._evaluate_lower(
                price, bands, delta_cumulative, delta_slope,
                absorption_ratio, imbalance, sweep_score,
                iceberg_signals, acceptance_time, depth_depletion
            )
            result.bands = bands
            return result

        # 价格在中间区域
        self.stats["no_trade_count"] += 1
        return RegimeResult(
            signal=RegimeSignal.NO_TRADE,
            confidence=0.0,
            triggers=[],
            band_position=band_position,
            timestamp=time.time(),
            bands=bands
        )

    def _evaluate_upper(
        self, price, bands, delta_cum, delta_slope,
        absorption, imbalance, sweep_score, icebergs,
        acceptance_time, depth_depletion
    ) -> RegimeResult:
        """触上轨时的判定逻辑"""
        triggers = []
        ban_score = 0.0
        reversion_score = 0.0
        base_confidence = 0.5
        scenario = None

        # ===  走轨风险检测（BAN_REVERSION）===

        # 1. 带宽扩张
        if bands["bandwidth"] > self.bandwidth_expansion_threshold:
            weight = self.ban_weights.get("bandwidth_expanding", 1.0)
            ban_score += weight
            triggers.append("bandwidth_expanding")

        # 2. Delta 加速（GPT 强调）
        if delta_slope > self.delta_slope_threshold:
            weight = self.ban_weights.get("delta_accelerating", 1.5)
            ban_score += weight
            triggers.append("delta_accelerating")

        # 3. 扫单得分高
        if sweep_score > self.sweep_score_threshold:
            weight = self.ban_weights.get("aggressive_sweeping", 1.2)
            ban_score += weight
            triggers.append("aggressive_sweeping")

        # 4. 持续买方失衡
        buy_ratio = imbalance.get("buy_ratio", 0.5)
        if buy_ratio > self.imbalance_threshold:
            weight = self.ban_weights.get("persistent_imbalance", 1.0)
            ban_score += weight
            triggers.append("persistent_buy_imbalance")

        # 5. 价格接受时间过长（GPT 独有）
        if acceptance_time > self.acceptance_time_threshold:
            weight = self.ban_weights.get("price_accepted", 1.0)
            ban_score += weight
            triggers.append("price_accepted_above_band")

        # 6. 买方冰山 = 突破风险（场景 F）
        buy_iceberg = self._check_iceberg_side(icebergs, "BUY", min_level="CONFIRMED")
        if buy_iceberg:
            weight = self.ban_weights.get("iceberg_opposite", 2.0)
            ban_score += weight
            triggers.append("buy_iceberg_at_upper")
            scenario = "F"  # 场景 F: 冰山反向突破

        # 走轨判定（场景 E）
        if ban_score >= self.ban_threshold:
            if scenario is None:
                scenario = "E"  # 场景 E: 趋势性走轨

            self.stats["ban_reversion_count"] += 1
            return RegimeResult(
                signal=RegimeSignal.BAN_REVERSION,
                confidence=0.8,
                triggers=triggers,
                band_position="upper",
                timestamp=time.time(),
                ban_score=ban_score,
                scenario=scenario
            )

        # === 回归信号检测（ALLOW_REVERSION）===
        triggers_reversion = []

        # 1. Delta 背离/衰减（场景 A）
        if delta_slope < self.delta_divergence_threshold or delta_cum < 0:
            weight = self.reversion_weights.get("delta_divergence", 1.0)
            reversion_score += weight
            boost = self.confidence_boost.get("delta_divergence", 0.10)
            base_confidence += boost
            triggers_reversion.append("delta_divergence")

        # 2. 吸收率高（买盘被吸收）（场景 A）
        if absorption > self.absorption_threshold:
            weight = self.reversion_weights.get("high_absorption", 1.0)
            reversion_score += weight
            boost = self.confidence_boost.get("high_absorption", 0.10)
            base_confidence += boost
            triggers_reversion.append("high_absorption")

        # 3. 卖方失衡（场景 B）
        sell_ratio = imbalance.get("sell_ratio", 0.5)
        if sell_ratio > self.imbalance_threshold:
            weight = self.reversion_weights.get("imbalance_reversal", 1.2)
            reversion_score += weight
            boost = self.confidence_boost.get("sell_imbalance", 0.15)
            base_confidence += boost
            triggers_reversion.append("sell_imbalance")
            if scenario is None:
                scenario = "B"  # 场景 B: 失衡确认回归

        # 4. 卖方冰山护盘（场景 C，Gemini +25%）
        sell_iceberg = self._check_iceberg_side(icebergs, "SELL", min_level="CONFIRMED")
        if sell_iceberg:
            weight = self.reversion_weights.get("iceberg_defense", 2.0)
            reversion_score += weight
            boost = self.confidence_boost.get("iceberg_defense", 0.25)
            base_confidence += boost
            triggers_reversion.append("sell_iceberg_defense")
            scenario = "C"  # 场景 C: 冰山护盘回归

        # 5. 深度耗尽
        if depth_depletion > self.depth_depletion_threshold:
            weight = self.reversion_weights.get("depth_depletion", 0.8)
            reversion_score += weight
            boost = self.confidence_boost.get("depth_depletion", 0.08)
            base_confidence += boost
            triggers_reversion.append("depth_depletion")

        # 回归判定
        if reversion_score >= self.reversion_threshold:
            # 确定场景
            if scenario is None:
                if len(triggers_reversion) >= 2:
                    scenario = "A"  # 场景 A: 衰竭性回归

            # 置信度限制
            final_confidence = min(base_confidence, 0.95)

            # 最低置信度检查
            if final_confidence < self.min_confidence:
                self.stats["no_trade_count"] += 1
                return RegimeResult(
                    signal=RegimeSignal.NO_TRADE,
                    confidence=final_confidence,
                    triggers=triggers_reversion + ["confidence_too_low"],
                    band_position="upper",
                    timestamp=time.time(),
                    reversion_score=reversion_score
                )

            self.stats["allow_reversion_count"] += 1
            return RegimeResult(
                signal=RegimeSignal.ALLOW_REVERSION_SHORT,
                confidence=final_confidence,
                triggers=triggers_reversion,
                band_position="upper",
                timestamp=time.time(),
                reversion_score=reversion_score,
                scenario=scenario
            )

        # 证据不足
        self.stats["no_trade_count"] += 1
        return RegimeResult(
            signal=RegimeSignal.NO_TRADE,
            confidence=0.0,
            triggers=[],
            band_position="upper",
            timestamp=time.time(),
            ban_score=ban_score,
            reversion_score=reversion_score
        )

    def _evaluate_lower(
        self, price, bands, delta_cum, delta_slope,
        absorption, imbalance, sweep_score, icebergs,
        acceptance_time, depth_depletion
    ) -> RegimeResult:
        """触下轨时的判定逻辑（镜像）"""
        triggers = []
        ban_score = 0.0
        reversion_score = 0.0
        base_confidence = 0.5
        scenario = None

        # === 走轨风险检测（BAN_REVERSION）===

        # 1. 带宽扩张
        if bands["bandwidth"] > self.bandwidth_expansion_threshold:
            weight = self.ban_weights.get("bandwidth_expanding", 1.0)
            ban_score += weight
            triggers.append("bandwidth_expanding")

        # 2. Delta 加速（负方向）
        if delta_slope < -self.delta_slope_threshold:
            weight = self.ban_weights.get("delta_accelerating", 1.5)
            ban_score += weight
            triggers.append("delta_decelerating")

        # 3. 扫单得分高
        if sweep_score > self.sweep_score_threshold:
            weight = self.ban_weights.get("aggressive_sweeping", 1.2)
            ban_score += weight
            triggers.append("aggressive_sweeping")

        # 4. 持续卖方失衡
        sell_ratio = imbalance.get("sell_ratio", 0.5)
        if sell_ratio > self.imbalance_threshold:
            weight = self.ban_weights.get("persistent_imbalance", 1.0)
            ban_score += weight
            triggers.append("persistent_sell_imbalance")

        # 5. 价格接受时间过长
        if acceptance_time > self.acceptance_time_threshold:
            weight = self.ban_weights.get("price_accepted", 1.0)
            ban_score += weight
            triggers.append("price_accepted_below_band")

        # 6. 卖方冰山 = 突破风险（镜像场景 F）
        sell_iceberg = self._check_iceberg_side(icebergs, "SELL", min_level="CONFIRMED")
        if sell_iceberg:
            weight = self.ban_weights.get("iceberg_opposite", 2.0)
            ban_score += weight
            triggers.append("sell_iceberg_at_lower")
            scenario = "F_mirror"

        # 走轨判定
        if ban_score >= self.ban_threshold:
            if scenario is None:
                scenario = "E_mirror"

            self.stats["ban_reversion_count"] += 1
            return RegimeResult(
                signal=RegimeSignal.BAN_REVERSION,
                confidence=0.8,
                triggers=triggers,
                band_position="lower",
                timestamp=time.time(),
                ban_score=ban_score,
                scenario=scenario
            )

        # === 回归信号检测（ALLOW_REVERSION）===
        triggers_reversion = []

        # 1. Delta 背离/转正
        if delta_slope > -self.delta_divergence_threshold or delta_cum > 0:
            weight = self.reversion_weights.get("delta_divergence", 1.0)
            reversion_score += weight
            boost = self.confidence_boost.get("delta_divergence", 0.10)
            base_confidence += boost
            triggers_reversion.append("delta_divergence")

        # 2. 吸收率高（卖盘被吸收）
        if absorption > self.absorption_threshold:
            weight = self.reversion_weights.get("high_absorption", 1.0)
            reversion_score += weight
            boost = self.confidence_boost.get("high_absorption", 0.10)
            base_confidence += boost
            triggers_reversion.append("high_absorption")

        # 3. 买方失衡（镜像场景 B）
        buy_ratio = imbalance.get("buy_ratio", 0.5)
        if buy_ratio > self.imbalance_threshold:
            weight = self.reversion_weights.get("imbalance_reversal", 1.2)
            reversion_score += weight
            boost = self.confidence_boost.get("buy_imbalance", 0.15)
            base_confidence += boost
            triggers_reversion.append("buy_imbalance")
            if scenario is None:
                scenario = "B_mirror"

        # 4. 买方冰山托底（镜像场景 C）
        buy_iceberg = self._check_iceberg_side(icebergs, "BUY", min_level="CONFIRMED")
        if buy_iceberg:
            weight = self.reversion_weights.get("iceberg_defense", 2.0)
            reversion_score += weight
            boost = self.confidence_boost.get("iceberg_defense", 0.25)
            base_confidence += boost
            triggers_reversion.append("buy_iceberg_defense")
            scenario = "C_mirror"

        # 5. 深度耗尽
        if depth_depletion > self.depth_depletion_threshold:
            weight = self.reversion_weights.get("depth_depletion", 0.8)
            reversion_score += weight
            boost = self.confidence_boost.get("depth_depletion", 0.08)
            base_confidence += boost
            triggers_reversion.append("depth_depletion")

        # 回归判定
        if reversion_score >= self.reversion_threshold:
            if scenario is None:
                scenario = "A_mirror"

            final_confidence = min(base_confidence, 0.95)

            if final_confidence < self.min_confidence:
                self.stats["no_trade_count"] += 1
                return RegimeResult(
                    signal=RegimeSignal.NO_TRADE,
                    confidence=final_confidence,
                    triggers=triggers_reversion + ["confidence_too_low"],
                    band_position="lower",
                    timestamp=time.time(),
                    reversion_score=reversion_score
                )

            self.stats["allow_reversion_count"] += 1
            return RegimeResult(
                signal=RegimeSignal.ALLOW_REVERSION_LONG,
                confidence=final_confidence,
                triggers=triggers_reversion,
                band_position="lower",
                timestamp=time.time(),
                reversion_score=reversion_score,
                scenario=scenario
            )

        # 证据不足
        self.stats["no_trade_count"] += 1
        return RegimeResult(
            signal=RegimeSignal.NO_TRADE,
            confidence=0.0,
            triggers=[],
            band_position="lower",
            timestamp=time.time(),
            ban_score=ban_score,
            reversion_score=reversion_score
        )

    def _get_band_position(self, price: float, bands: Dict) -> str:
        """获取价格在布林带中的位置"""
        upper = bands["upper"]
        middle = bands["middle"]
        lower = bands["lower"]

        # 距离阈值（0.05%）
        threshold = middle * 0.0005

        if price > upper + threshold:
            return "above_upper"
        elif abs(price - upper) <= threshold:
            return "upper"
        elif price > middle + threshold:
            return "upper_half"
        elif abs(price - middle) <= threshold:
            return "middle"
        elif price > lower + threshold:
            return "lower_half"
        elif abs(price - lower) <= threshold:
            return "lower"
        else:
            return "below_lower"

    def _check_iceberg_side(self, icebergs: List, side: str, min_level: str = "CONFIRMED") -> bool:
        """
        检查是否有指定方向的冰山信号

        Args:
            icebergs: 冰山信号列表
            side: "BUY" 或 "SELL"
            min_level: 最低级别（默认 CONFIRMED）

        Returns:
            True 如果存在符合条件的冰山信号
        """
        level_priority = {"CRITICAL": 1, "CONFIRMED": 2, "WARNING": 3, "ACTIVITY": 4}
        min_priority = level_priority.get(min_level, 2)

        for signal in icebergs:
            # 检查方向
            if hasattr(signal, 'side') and signal.side == side:
                # 检查级别
                if hasattr(signal, 'level'):
                    signal_priority = level_priority.get(signal.level, 999)
                    if signal_priority <= min_priority:
                        return True

        return False

    def record_trade_result(self, is_win: bool):
        """
        记录交易结果（Gemini 建议）

        Args:
            is_win: 是否盈利
        """
        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.last_loss_time = time.time()

    def reset_loss_counter(self):
        """手动重置亏损计数器"""
        self.consecutive_losses = 0
        self.last_loss_time = 0

    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = self.stats["total_evaluations"]
        if total == 0:
            return self.stats

        return {
            **self.stats,
            "allow_reversion_pct": self.stats["allow_reversion_count"] / total * 100,
            "ban_reversion_pct": self.stats["ban_reversion_count"] / total * 100,
            "no_trade_pct": self.stats["no_trade_count"] / total * 100,
            "consecutive_losses": self.consecutive_losses,
            "bb_data_points": len(self.bb.prices),
            "bb_is_ready": self.bb.is_ready(),
        }

    def __repr__(self) -> str:
        return (
            f"BollingerRegimeFilter("
            f"period={self.bb.period}, "
            f"std_dev={self.bb.std_dev}, "
            f"evaluations={self.stats['total_evaluations']})"
        )


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("="*60)
    print("Bollinger Regime Filter - 测试")
    print("="*60)

    # 创建过滤器
    filter_engine = BollingerRegimeFilter()

    # 模拟价格序列（触上轨场景）
    import random
    base_price = 100.0
    prices = []

    # 前20个价格正常波动
    for i in range(20):
        prices.append(base_price + random.gauss(0, 0.5))

    # 接下来价格上涨，触上轨
    for i in range(10):
        prices.append(base_price + 1.5 + i * 0.1 + random.gauss(0, 0.2))

    print("\n测试 1: 回归信号检测（卖方冰山+失衡）")
    print("-" * 60)

    # 模拟冰山信号
    from dataclasses import dataclass as dc

    @dc
    class MockIcebergSignal:
        side: str
        level: str

    for i, price in enumerate(prices):
        # 模拟订单流数据
        delta_slope = random.gauss(0.2, 0.1) if i < 25 else -0.15  # 后期Delta转负
        absorption = 0.3 if i < 25 else 0.6  # 后期吸收率高
        imbalance = {"buy_ratio": 0.7, "sell_ratio": 0.3} if i < 25 else {"buy_ratio": 0.3, "sell_ratio": 0.7}

        # 最后触上轨时出现卖方冰山
        icebergs = []
        if i >= 28:
            icebergs = [MockIcebergSignal(side="SELL", level="CONFIRMED")]

        result = filter_engine.evaluate(
            price=price,
            delta_slope=delta_slope,
            absorption_ratio=absorption,
            imbalance=imbalance,
            iceberg_signals=icebergs
        )

        # 只打印关键时刻
        if result.signal != RegimeSignal.NO_TRADE or i >= 28:
            print(f"\n[{i+1:2d}] 价格: {price:.2f}")
            if result.bands:
                print(f"     上轨: {result.bands['upper']:.2f}, 中轨: {result.bands['middle']:.2f}")
            print(f"     信号: {result.signal.value}")
            print(f"     置信度: {result.confidence:.2%}")
            print(f"     位置: {result.band_position}")
            if result.triggers:
                print(f"     触发: {', '.join(result.triggers)}")
            if result.scenario:
                print(f"     场景: {result.scenario}")
            if result.reversion_score > 0:
                print(f"     回归得分: {result.reversion_score:.2f}")

    print("\n测试 2: 统计信息")
    print("-" * 60)
    stats = filter_engine.get_stats()
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    print(f"\n✅ 测试完成！")
