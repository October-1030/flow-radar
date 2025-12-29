#!/usr/bin/env python3
"""
Flow Radar - Hysteresis State Machine
流动性雷达 - 滞回状态机

解决分数在阈值附近反复横跳导致的告警风暴问题
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


class MarketState(Enum):
    """市场状态枚举"""
    NEUTRAL = "neutral"                      # 中性观望
    ACCUMULATING = "accumulating"            # 暗中吸筹
    DISTRIBUTING = "distributing"            # 暗中出货
    TREND_UP = "trend_up"                    # 真实上涨
    TREND_DOWN = "trend_down"                # 真实下跌
    WASH_ACCUMULATE = "wash_accumulate"      # 洗盘吸筹
    TRAP_DISTRIBUTION = "trap_distribution"  # 诱多出货


# 状态中文映射
STATE_NAMES = {
    MarketState.NEUTRAL: "多空博弈",
    MarketState.ACCUMULATING: "暗中吸筹",
    MarketState.DISTRIBUTING: "暗中出货",
    MarketState.TREND_UP: "真实上涨",
    MarketState.TREND_DOWN: "真实下跌",
    MarketState.WASH_ACCUMULATE: "洗盘吸筹",
    MarketState.TRAP_DISTRIBUTION: "诱多出货",
}

# 状态对应的建议
STATE_RECOMMENDATIONS = {
    MarketState.NEUTRAL: ("观望", "等待方向明确"),
    MarketState.ACCUMULATING: ("可以关注", "大户在悄悄建仓"),
    MarketState.DISTRIBUTING: ("小心", "大户在悄悄出货"),
    MarketState.TREND_UP: ("可以买入", "表面+暗盘都确认上涨"),
    MarketState.TREND_DOWN: ("不要抄底", "表面+暗盘都在卖"),
    MarketState.WASH_ACCUMULATE: ("可以关注", "表面打压，暗盘吸货"),
    MarketState.TRAP_DISTRIBUTION: ("不要追高", "表面拉升，暗盘出货"),
}


@dataclass
class SignalOutput:
    """信号输出"""
    state: MarketState
    state_name: str
    confidence: float  # 0-100
    reason: str
    recommendation: str
    detail: str
    cooldown_remaining: int = 0
    state_changed: bool = False
    previous_state: Optional[MarketState] = None


class HysteresisStateMachine:
    """
    滞回状态机

    使用滞回阈值避免在边界反复切换：
    - 多头进入: 65, 退出: 55
    - 空头进入: 30, 退出: 40
    """

    # 表面信号滞回阈值
    LONG_ENTRY = 65      # 分数高于此进入多头状态
    LONG_EXIT = 55       # 分数低于此退出多头状态
    SHORT_ENTRY = 30     # 分数低于此进入空头状态
    SHORT_EXIT = 40      # 分数高于此退出空头状态

    # 暗盘信号阈值
    ICEBERG_BULLISH = 0.55       # 暗盘偏多
    ICEBERG_BEARISH = 0.45       # 暗盘偏空
    ICEBERG_STRONG_BULLISH = 0.65  # 暗盘强多
    ICEBERG_STRONG_BEARISH = 0.35  # 暗盘强空

    # 冷却时间 (秒)
    DEFAULT_COOLDOWN = 30

    def __init__(self, cooldown_seconds: int = 30):
        self.current_state = MarketState.NEUTRAL
        self.cooldown = 0
        self.cooldown_seconds = cooldown_seconds
        self.last_score = 50
        self.last_iceberg_ratio = 0.5
        self.last_update_ts = 0.0  # 使用时间戳而非 datetime
        self.last_state_change_ts = 0.0  # 上次状态变化时间

        # 内部状态追踪
        self._is_surface_bullish = False
        self._is_surface_bearish = False

    def update(self, score: float, iceberg_ratio: float,
               ice_buy_vol: float = 0, ice_sell_vol: float = 0,
               event_ts: float = None) -> SignalOutput:
        """
        更新状态机

        Args:
            score: 综合分数 (0-100)
            iceberg_ratio: 冰山买单比例 (0-1)
            ice_buy_vol: 冰山买单累计量
            ice_sell_vol: 冰山卖单累计量
            event_ts: 事件时间戳 (秒)，用于回放确定性

        Returns:
            SignalOutput: 信号输出
        """
        import time
        # 使用 event_ts 保证回放确定性，如果没有则用当前时间
        if event_ts is None:
            event_ts = time.time()

        time_elapsed = event_ts - self.last_update_ts if self.last_update_ts > 0 else 0
        self.last_update_ts = event_ts

        # 更新冷却 (基于 event_ts，保证回放确定性)
        if self.cooldown > 0:
            self.cooldown = max(0, self.cooldown - time_elapsed)

        # 确定新状态
        new_state = self._determine_state(score, iceberg_ratio)

        # 状态变化检测
        state_changed = False
        previous_state = None

        if new_state != self.current_state:
            if self.cooldown <= 0:
                # 冷却结束，允许状态切换
                state_changed = True
                previous_state = self.current_state
                self.current_state = new_state
                self.cooldown = self.cooldown_seconds
                self.last_state_change_ts = event_ts  # 记录状态变化时间
            # else: 冷却中，保持原状态

        # 计算置信度
        confidence = self._calculate_confidence(score, iceberg_ratio)

        # 生成原因说明
        reason = self._generate_reason(score, iceberg_ratio, ice_buy_vol, ice_sell_vol)

        # 获取建议
        rec_short, rec_detail = STATE_RECOMMENDATIONS[self.current_state]

        # 记录历史
        self.last_score = score
        self.last_iceberg_ratio = iceberg_ratio

        return SignalOutput(
            state=self.current_state,
            state_name=STATE_NAMES[self.current_state],
            confidence=confidence,
            reason=reason,
            recommendation=rec_short,
            detail=rec_detail,
            cooldown_remaining=int(self.cooldown),
            state_changed=state_changed,
            previous_state=previous_state
        )

    def _determine_state(self, score: float, iceberg_ratio: float) -> MarketState:
        """确定市场状态 (带滞回)"""

        # === 表面信号判断 (带滞回) ===
        # 如果当前已经是多头相关状态，用更宽松的退出阈值
        if self._is_surface_bullish:
            surface_bullish = score >= self.LONG_EXIT
        else:
            surface_bullish = score >= self.LONG_ENTRY

        # 如果当前已经是空头相关状态，用更宽松的退出阈值
        if self._is_surface_bearish:
            surface_bearish = score <= self.SHORT_EXIT
        else:
            surface_bearish = score <= self.SHORT_ENTRY

        # 更新内部状态
        self._is_surface_bullish = surface_bullish
        self._is_surface_bearish = surface_bearish

        # === 暗盘信号判断 ===
        hidden_bullish = iceberg_ratio >= self.ICEBERG_BULLISH
        hidden_bearish = iceberg_ratio <= self.ICEBERG_BEARISH

        # === 综合判断矩阵 ===
        # 表面空 + 暗盘多 = 洗盘吸筹
        if surface_bearish and hidden_bullish:
            return MarketState.WASH_ACCUMULATE

        # 表面多 + 暗盘空 = 诱多出货
        if surface_bullish and hidden_bearish:
            return MarketState.TRAP_DISTRIBUTION

        # 表面空 + 暗盘空 = 真实下跌
        if surface_bearish and hidden_bearish:
            return MarketState.TREND_DOWN

        # 表面多 + 暗盘多 = 真实上涨
        if surface_bullish and hidden_bullish:
            return MarketState.TREND_UP

        # 表面中性的情况
        if not surface_bullish and not surface_bearish:
            if hidden_bullish:
                return MarketState.ACCUMULATING
            elif hidden_bearish:
                return MarketState.DISTRIBUTING

        return MarketState.NEUTRAL

    def _calculate_confidence(self, score: float, iceberg_ratio: float) -> float:
        """计算置信度 (0-100)"""
        # 分数偏离度 (离50越远越确定)
        score_deviation = abs(score - 50) / 50  # 0-1

        # 暗盘偏离度 (离0.5越远越确定)
        iceberg_deviation = abs(iceberg_ratio - 0.5) * 2  # 0-1

        # 综合置信度 (分数权重60%, 暗盘权重40%)
        confidence = (score_deviation * 0.6 + iceberg_deviation * 0.4) * 100

        return min(100, max(0, confidence))

    def _generate_reason(self, score: float, iceberg_ratio: float,
                         ice_buy_vol: float, ice_sell_vol: float) -> str:
        """生成原因说明"""
        parts = []

        # 分数描述
        if score >= 70:
            parts.append(f"分数{score:.0f}(强多)")
        elif score >= 60:
            parts.append(f"分数{score:.0f}(偏多)")
        elif score <= 25:
            parts.append(f"分数{score:.0f}(强空)")
        elif score <= 35:
            parts.append(f"分数{score:.0f}(偏空)")
        else:
            parts.append(f"分数{score:.0f}(中性)")

        # 暗盘描述
        if iceberg_ratio >= 0.65:
            parts.append(f"暗盘{iceberg_ratio:.2f}(强多)")
        elif iceberg_ratio >= 0.55:
            parts.append(f"暗盘{iceberg_ratio:.2f}(偏多)")
        elif iceberg_ratio <= 0.35:
            parts.append(f"暗盘{iceberg_ratio:.2f}(强空)")
        elif iceberg_ratio <= 0.45:
            parts.append(f"暗盘{iceberg_ratio:.2f}(偏空)")
        else:
            parts.append(f"暗盘{iceberg_ratio:.2f}(中性)")

        # 净额
        ice_diff = ice_buy_vol - ice_sell_vol
        if abs(ice_diff) >= 10000:
            net_str = f"净{'买' if ice_diff > 0 else '卖'}{abs(ice_diff)/10000:.0f}万"
            parts.append(net_str)

        return " | ".join(parts)

    def force_state(self, state: MarketState):
        """强制设置状态 (用于测试或特殊情况)"""
        self.current_state = state
        self.cooldown = 0

    def reset(self):
        """重置状态机"""
        self.current_state = MarketState.NEUTRAL
        self.cooldown = 0
        self._is_surface_bullish = False
        self._is_surface_bearish = False
        self.last_score = 50
        self.last_iceberg_ratio = 0.5


# 便捷函数
def is_bullish_state(state: MarketState) -> bool:
    """是否为看多状态"""
    return state in [
        MarketState.TREND_UP,
        MarketState.ACCUMULATING,
        MarketState.WASH_ACCUMULATE
    ]


def is_bearish_state(state: MarketState) -> bool:
    """是否为看空状态"""
    return state in [
        MarketState.TREND_DOWN,
        MarketState.DISTRIBUTING,
        MarketState.TRAP_DISTRIBUTION
    ]


def is_danger_state(state: MarketState) -> bool:
    """是否为危险状态 (不应买入)"""
    return state in [
        MarketState.TREND_DOWN,
        MarketState.DISTRIBUTING,
        MarketState.TRAP_DISTRIBUTION
    ]


def is_opportunity_state(state: MarketState) -> bool:
    """是否为机会状态 (可以考虑买入)"""
    return state in [
        MarketState.TREND_UP,
        MarketState.ACCUMULATING,
        MarketState.WASH_ACCUMULATE
    ]
