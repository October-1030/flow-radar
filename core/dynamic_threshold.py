#!/usr/bin/env python3
"""
Flow Radar - Dynamic Threshold Engine
流动性雷达 - 动态阈值引擎

解决 $10,000 鲸鱼阈值跨币种不可迁移的问题
使用滚动分位数自动调整阈值
"""

import time
from collections import deque
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class ThresholdSnapshot:
    """阈值快照"""
    whale_threshold: float
    iceberg_intensity: float
    sample_count: int
    timestamp: float


class DynamicThresholdEngine:
    """
    动态阈值引擎

    - 鲸鱼阈值: 基于单笔成交额 P99 分位数
    - 冰山强度阈值: 基于波动率调整
    """

    def __init__(
        self,
        window_hours: int = 24,
        min_samples: int = 100,
        min_whale_usd: float = 5000,
        min_iceberg_intensity: float = 1.5
    ):
        """
        Args:
            window_hours: 滚动窗口时长 (小时)
            min_samples: 计算分位数所需最小样本数
            min_whale_usd: 鲸鱼阈值下限 (USD)
            min_iceberg_intensity: 冰山强度阈值下限
        """
        self.window_hours = window_hours
        self.min_samples = min_samples
        self.min_whale_usd = min_whale_usd
        self.min_iceberg_intensity = min_iceberg_intensity

        # 存储 (timestamp, notional_usd)
        self.trade_notionals = deque(maxlen=100000)

        # 波动率追踪
        self.price_changes = deque(maxlen=1000)
        self.last_price = None
        self.base_atr = None  # 基准 ATR

        # 缓存
        self._cached_whale_threshold = min_whale_usd
        self._cache_time = 0
        self._cache_ttl = 60  # 缓存60秒

    def add_trade(self, notional_usd: float, timestamp: float = None):
        """
        记录每笔成交金额

        Args:
            notional_usd: 成交金额 (USD)
            timestamp: 时间戳 (秒)
        """
        if timestamp is None:
            timestamp = time.time()

        self.trade_notionals.append((timestamp, notional_usd))
        self._cleanup_old_trades(timestamp)

    def add_price(self, price: float, timestamp: float = None):
        """
        记录价格用于计算波动率

        Args:
            price: 当前价格
            timestamp: 时间戳
        """
        if self.last_price is not None and self.last_price > 0:
            change = abs(price - self.last_price) / self.last_price
            self.price_changes.append(change)

        self.last_price = price

        # 更新基准 ATR (使用最近的平均波动)
        if len(self.price_changes) >= 100 and self.base_atr is None:
            self.base_atr = sum(self.price_changes) / len(self.price_changes)

    def _cleanup_old_trades(self, current_time: float):
        """清理超出窗口的旧数据"""
        cutoff = current_time - self.window_hours * 3600
        while self.trade_notionals and self.trade_notionals[0][0] < cutoff:
            self.trade_notionals.popleft()

    def get_whale_threshold(self) -> float:
        """
        获取鲸鱼阈值 (稳健版 - 抗极端值)

        使用 GPT 推荐方案：min(P99, P95*3, median*50)
        防止单笔超大交易污染阈值

        Returns:
            float: 鲸鱼交易阈值 (USD)
        """
        # 检查缓存
        now = time.time()
        if now - self._cache_time < self._cache_ttl:
            return self._cached_whale_threshold

        # 样本不足时返回默认值
        if len(self.trade_notionals) < self.min_samples:
            return self.min_whale_usd

        # 计算分位数
        notionals = sorted([t[1] for t in self.trade_notionals])
        n = len(notionals)

        p99 = notionals[int(n * 0.99)]
        p95 = notionals[int(n * 0.95)]
        median = notionals[n // 2]

        # 稳健阈值：取 min(P99, P95*3, median*50)
        # 这样即使有 100x 的异常大单，也不会让阈值"失明"
        robust_threshold = min(p99, p95 * 3, median * 50)

        # 更新缓存
        self._cached_whale_threshold = max(self.min_whale_usd, robust_threshold)
        self._cache_time = now

        return self._cached_whale_threshold

    def get_dual_thresholds(self) -> dict:
        """
        获取双阈值 (Gemini 建议：区分大户和巨鲸)

        Returns:
            dict: {'active_whale': P95, 'mega_whale': P99}
        """
        if len(self.trade_notionals) < self.min_samples:
            return {
                'active_whale': self.min_whale_usd,
                'mega_whale': self.min_whale_usd * 2
            }

        notionals = sorted([t[1] for t in self.trade_notionals])
        n = len(notionals)

        return {
            'active_whale': notionals[int(n * 0.95)],  # P95 - 活跃大户
            'mega_whale': notionals[int(n * 0.99)]     # P99 - 巨鲸
        }

    def get_iceberg_intensity_threshold(self) -> float:
        """
        获取冰山强度阈值 (根据波动率调整)

        波动率高时提高阈值，避免将正常波动误判为冰山

        Returns:
            float: 冰山强度阈值
        """
        if self.base_atr is None or len(self.price_changes) < 20:
            return 2.0  # 默认阈值

        # 计算当前 ATR
        recent_changes = list(self.price_changes)[-20:]
        current_atr = sum(recent_changes) / len(recent_changes)

        # ATR 比率
        atr_ratio = current_atr / self.base_atr if self.base_atr > 0 else 1.0

        # 波动率高时提高阈值
        # 例如: 波动率是基准的2倍 -> 阈值变为 2 * 2 = 4
        adjusted_threshold = 2.0 * max(1.0, atr_ratio)

        return max(self.min_iceberg_intensity, adjusted_threshold)

    def get_thresholds(self) -> Tuple[float, float]:
        """
        获取所有阈值

        Returns:
            Tuple[float, float]: (鲸鱼阈值, 冰山强度阈值)
        """
        return (
            self.get_whale_threshold(),
            self.get_iceberg_intensity_threshold()
        )

    def get_snapshot(self) -> ThresholdSnapshot:
        """获取当前阈值快照"""
        return ThresholdSnapshot(
            whale_threshold=self.get_whale_threshold(),
            iceberg_intensity=self.get_iceberg_intensity_threshold(),
            sample_count=len(self.trade_notionals),
            timestamp=time.time()
        )

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            dict: 统计数据
        """
        if not self.trade_notionals:
            return {
                "sample_count": 0,
                "whale_threshold": self.min_whale_usd,
                "message": "等待数据..."
            }

        notionals = [t[1] for t in self.trade_notionals]

        # 计算分位数
        sorted_notionals = sorted(notionals)
        n = len(sorted_notionals)

        stats = {
            "sample_count": n,
            "window_hours": self.window_hours,
            "min": sorted_notionals[0],
            "max": sorted_notionals[-1],
            "median": sorted_notionals[n // 2],
            "p90": sorted_notionals[int(n * 0.90)],
            "p95": sorted_notionals[int(n * 0.95)],
            "p99": sorted_notionals[int(n * 0.99)],
            "whale_threshold": self.get_whale_threshold(),
            "iceberg_intensity": self.get_iceberg_intensity_threshold()
        }

        if self.base_atr:
            recent_changes = list(self.price_changes)[-20:] if self.price_changes else []
            current_atr = sum(recent_changes) / len(recent_changes) if recent_changes else 0
            stats["base_atr"] = self.base_atr
            stats["current_atr"] = current_atr
            stats["atr_ratio"] = current_atr / self.base_atr if self.base_atr > 0 else 1.0

        return stats


# 全局实例 (可选)
_default_engine: Optional[DynamicThresholdEngine] = None


def get_threshold_engine() -> DynamicThresholdEngine:
    """获取默认阈值引擎实例"""
    global _default_engine
    if _default_engine is None:
        _default_engine = DynamicThresholdEngine()
    return _default_engine


def reset_threshold_engine():
    """重置默认阈值引擎"""
    global _default_engine
    _default_engine = None
