#!/usr/bin/env python3
"""
Flow Radar - Divergence Detector
流动性雷达 - 背离检测器

检测价格与 CVD 的背离，用于确认诱多出货信号
"""

from collections import deque
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class DivergenceType(Enum):
    """背离类型"""
    NONE = "none"
    BEARISH = "bearish"   # 看跌背离：价格新高但 CVD 下降
    BULLISH = "bullish"   # 看涨背离：价格新低但 CVD 上升


@dataclass
class DivergenceSignal:
    """背离信号"""
    detected: bool
    type: DivergenceType
    description: str
    confidence: float       # 0-1
    price_change: float     # 价格变化幅度
    cvd_change: float       # CVD 变化幅度


class DivergenceDetector:
    """
    背离检测器

    Gemini 建议：背离是二阶确认信号，比加阈值更有价值

    使用方法：
    - 价格创新高但 CVD 下降 = 看跌背离 → 确认诱多出货
    - 价格创新低但 CVD 上升 = 看涨背离 → 确认洗盘吸筹
    """

    def __init__(self, window: int = 20):
        """
        Args:
            window: 检测窗口大小
        """
        self.window = window
        self.prices = deque(maxlen=window)
        self.cvd_values = deque(maxlen=window)
        self.highs = deque(maxlen=window)
        self.lows = deque(maxlen=window)
        self.timestamps = deque(maxlen=window)

    def update(self, price: float, cvd: float,
               high: float = None, low: float = None,
               timestamp: float = None) -> Optional[DivergenceSignal]:
        """
        更新数据并检测背离

        Args:
            price: 当前价格
            cvd: 当前 CVD 值
            high: 当前高点 (如果没有则用 price)
            low: 当前低点 (如果没有则用 price)
            timestamp: 时间戳

        Returns:
            Optional[DivergenceSignal]: 检测到的背离信号
        """
        if high is None:
            high = price
        if low is None:
            low = price

        self.prices.append(price)
        self.cvd_values.append(cvd)
        self.highs.append(high)
        self.lows.append(low)
        if timestamp:
            self.timestamps.append(timestamp)

        # 数据不足
        if len(self.prices) < 10:
            return None

        return self._detect_divergence()

    def _detect_divergence(self) -> Optional[DivergenceSignal]:
        """内部背离检测逻辑"""
        recent_highs = list(self.highs)[-10:]
        recent_lows = list(self.lows)[-10:]
        recent_cvd = list(self.cvd_values)[-10:]
        recent_prices = list(self.prices)[-10:]

        # === 看跌背离：价格创新高但 CVD 下降 ===
        if recent_highs[-1] >= max(recent_highs):
            cvd_start = recent_cvd[0]
            cvd_end = recent_cvd[-1]

            if cvd_start != 0 and cvd_end < cvd_start:
                cvd_decline = (cvd_start - cvd_end) / abs(cvd_start)
                price_rise = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]

                # 背离强度：CVD 下降越多，价格上涨越多，背离越强
                confidence = min(1.0, cvd_decline * 2)

                if cvd_decline > 0.1:  # CVD 下降超过 10%
                    return DivergenceSignal(
                        detected=True,
                        type=DivergenceType.BEARISH,
                        description=f"价格新高但买盘动能衰竭 (CVD下降{cvd_decline*100:.1f}%)",
                        confidence=confidence,
                        price_change=price_rise,
                        cvd_change=-cvd_decline
                    )

        # === 看涨背离：价格创新低但 CVD 上升 ===
        if recent_lows[-1] <= min(recent_lows):
            cvd_start = recent_cvd[0]
            cvd_end = recent_cvd[-1]

            if cvd_start != 0 and cvd_end > cvd_start:
                cvd_rise = (cvd_end - cvd_start) / abs(cvd_start)
                price_drop = (recent_prices[0] - recent_prices[-1]) / recent_prices[0]

                confidence = min(1.0, cvd_rise * 2)

                if cvd_rise > 0.1:  # CVD 上升超过 10%
                    return DivergenceSignal(
                        detected=True,
                        type=DivergenceType.BULLISH,
                        description=f"价格新低但卖压减弱 (CVD上升{cvd_rise*100:.1f}%)",
                        confidence=confidence,
                        price_change=-price_drop,
                        cvd_change=cvd_rise
                    )

        return None

    def check_bearish(self) -> bool:
        """快速检查是否有看跌背离"""
        signal = self._detect_divergence()
        return signal is not None and signal.type == DivergenceType.BEARISH

    def check_bullish(self) -> bool:
        """快速检查是否有看涨背离"""
        signal = self._detect_divergence()
        return signal is not None and signal.type == DivergenceType.BULLISH

    def get_recent_trend(self) -> dict:
        """获取近期趋势信息"""
        if len(self.prices) < 5:
            return {"price_trend": "unknown", "cvd_trend": "unknown"}

        recent_prices = list(self.prices)[-5:]
        recent_cvd = list(self.cvd_values)[-5:]

        price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
        cvd_change = recent_cvd[-1] - recent_cvd[0]

        return {
            "price_trend": "up" if price_change > 0.001 else "down" if price_change < -0.001 else "flat",
            "cvd_trend": "up" if cvd_change > 0 else "down" if cvd_change < 0 else "flat",
            "price_change_pct": price_change * 100,
            "cvd_change": cvd_change,
            "diverging": (price_change > 0 and cvd_change < 0) or (price_change < 0 and cvd_change > 0)
        }

    def reset(self):
        """重置检测器"""
        self.prices.clear()
        self.cvd_values.clear()
        self.highs.clear()
        self.lows.clear()
        self.timestamps.clear()
