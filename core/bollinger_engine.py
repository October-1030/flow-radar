#!/usr/bin/env python3
"""
Bollinger Bands Engine - 增量布林带计算器
流动性雷达 - O(1) 复杂度布林带计算

设计原则:
- O(1) 更新复杂度（增量计算）
- 避免重复计算整个窗口
- 提供 percent_b、z_score 等扩展指标

作者: Claude Code (三方共识)
日期: 2026-01-09
版本: v1.0
参考: 第二十五轮三方共识
"""

from collections import deque
from typing import Optional, Dict
import math


class IncrementalBollingerBands:
    """
    增量布林带计算器 - O(1) 更新复杂度

    算法:
    - 使用 deque 维护滑动窗口
    - 维护 sum 和 sum_sq 两个累积值
    - 新数据到来时: O(1) 更新均值和方差

    公式:
    - mean = sum / n
    - variance = sum_sq / n - mean^2
    - std = sqrt(variance)
    - upper = mean + k * std
    - lower = mean - k * std

    扩展指标:
    - bandwidth = (upper - lower) / mean
    - percent_b = (price - lower) / (upper - lower)
    - z_score = (price - mean) / std
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        """
        初始化布林带计算器

        Args:
            period: 周期（默认 20）
            std_dev: 标准差倍数（默认 2.0）
        """
        if period < 2:
            raise ValueError(f"period must be >= 2, got {period}")
        if std_dev <= 0:
            raise ValueError(f"std_dev must be > 0, got {std_dev}")

        self.period = period
        self.std_dev = std_dev

        # 价格窗口
        self.prices = deque(maxlen=period)

        # 增量统计量
        self._sum = 0.0
        self._sum_sq = 0.0

        # 统计信息
        self._update_count = 0

    def update(self, price: float) -> Optional[Dict[str, float]]:
        """
        更新布林带（O(1) 复杂度）

        Args:
            price: 新价格

        Returns:
            布林带指标字典，如果数据不足返回 None
            {
                "middle": 中轨,
                "upper": 上轨,
                "lower": 下轨,
                "bandwidth": 带宽,
                "percent_b": %b (0-1),
                "z_score": Z分数,
                "std": 标准差,
                "price": 当前价格
            }
        """
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")

        # 移除最老价格（如果窗口已满）
        if len(self.prices) == self.period:
            old_price = self.prices[0]
            self._sum -= old_price
            self._sum_sq -= old_price ** 2

        # 添加新价格
        self.prices.append(price)
        self._sum += price
        self._sum_sq += price ** 2
        self._update_count += 1

        # 数据不足，返回 None
        if len(self.prices) < self.period:
            return None

        # 计算均值
        mean = self._sum / self.period

        # 计算方差（避免负数）
        variance = max(self._sum_sq / self.period - mean ** 2, 1e-12)
        std = math.sqrt(variance)

        # 计算上下轨
        upper = mean + self.std_dev * std
        lower = mean - self.std_dev * std

        # 计算扩展指标
        bandwidth = (upper - lower) / mean if mean > 0 else 0

        # percent_b: 价格在布林带中的位置 (0 = 下轨, 1 = 上轨, 0.5 = 中轨)
        if upper != lower:
            percent_b = (price - lower) / (upper - lower)
        else:
            percent_b = 0.5

        # z_score: 价格相对均值的标准差倍数
        z_score = (price - mean) / std if std > 0 else 0

        return {
            "middle": round(mean, 8),
            "upper": round(upper, 8),
            "lower": round(lower, 8),
            "bandwidth": round(bandwidth, 6),
            "percent_b": round(percent_b, 4),
            "z_score": round(z_score, 4),
            "std": round(std, 8),
            "price": price,
            "period": self.period,
            "std_dev": self.std_dev
        }

    def is_ready(self) -> bool:
        """检查是否有足够数据"""
        return len(self.prices) >= self.period

    def get_current_bands(self) -> Optional[Dict[str, float]]:
        """
        获取当前布林带值（不更新）

        Returns:
            当前布林带值，如果数据不足返回 None
        """
        if not self.is_ready():
            return None

        mean = self._sum / self.period
        variance = max(self._sum_sq / self.period - mean ** 2, 1e-12)
        std = math.sqrt(variance)

        upper = mean + self.std_dev * std
        lower = mean - self.std_dev * std

        current_price = self.prices[-1]
        bandwidth = (upper - lower) / mean if mean > 0 else 0

        if upper != lower:
            percent_b = (current_price - lower) / (upper - lower)
        else:
            percent_b = 0.5

        z_score = (current_price - mean) / std if std > 0 else 0

        return {
            "middle": round(mean, 8),
            "upper": round(upper, 8),
            "lower": round(lower, 8),
            "bandwidth": round(bandwidth, 6),
            "percent_b": round(percent_b, 4),
            "z_score": round(z_score, 4),
            "std": round(std, 8),
            "price": current_price,
            "period": self.period,
            "std_dev": self.std_dev
        }

    def reset(self):
        """重置计算器"""
        self.prices.clear()
        self._sum = 0.0
        self._sum_sq = 0.0
        self._update_count = 0

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "period": self.period,
            "std_dev": self.std_dev,
            "data_points": len(self.prices),
            "is_ready": self.is_ready(),
            "update_count": self._update_count
        }

    def __repr__(self) -> str:
        return (
            f"IncrementalBollingerBands("
            f"period={self.period}, "
            f"std_dev={self.std_dev}, "
            f"data_points={len(self.prices)}/{self.period})"
        )


# ==================== 辅助函数 ====================

def calculate_band_position(price: float, bands: Dict[str, float]) -> str:
    """
    计算价格在布林带中的位置

    Args:
        price: 当前价格
        bands: 布林带字典

    Returns:
        位置描述: "above_upper" / "upper" / "middle" / "lower" / "below_lower"
    """
    if bands is None:
        return "unknown"

    upper = bands["upper"]
    middle = bands["middle"]
    lower = bands["lower"]

    # 距离阈值（0.1%）
    threshold = middle * 0.001

    if price > upper + threshold:
        return "above_upper"
    elif abs(price - upper) <= threshold:
        return "upper"
    elif abs(price - middle) <= threshold:
        return "middle"
    elif abs(price - lower) <= threshold:
        return "lower"
    elif price < lower - threshold:
        return "below_lower"
    else:
        # 在上下轨之间
        if price > middle:
            return "upper_half"
        else:
            return "lower_half"


def is_bandwidth_expanding(current_bandwidth: float,
                           prev_bandwidth: float,
                           threshold: float = 0.05) -> bool:
    """
    判断带宽是否扩张

    Args:
        current_bandwidth: 当前带宽
        prev_bandwidth: 之前带宽
        threshold: 扩张阈值（默认 5%）

    Returns:
        True 如果带宽扩张超过阈值
    """
    if prev_bandwidth == 0:
        return False

    change_pct = (current_bandwidth - prev_bandwidth) / prev_bandwidth
    return change_pct > threshold


def is_bandwidth_squeezing(bandwidth: float,
                           historical_avg: float,
                           threshold: float = 0.5) -> bool:
    """
    判断带宽是否收缩（挤压）

    Args:
        bandwidth: 当前带宽
        historical_avg: 历史平均带宽
        threshold: 收缩阈值（默认低于平均值 50%）

    Returns:
        True 如果带宽收缩到阈值以下
    """
    if historical_avg == 0:
        return False

    return bandwidth < historical_avg * threshold


def detect_bollinger_squeeze(bb_engine: IncrementalBollingerBands,
                             bandwidth_history: deque,
                             window: int = 100) -> bool:
    """
    检测布林带挤压（Bollinger Squeeze）

    当前带宽是过去 N 期中最小的，表示波动率压缩

    Args:
        bb_engine: 布林带引擎
        bandwidth_history: 带宽历史（deque）
        window: 比较窗口（默认 100 期）

    Returns:
        True 如果检测到挤压
    """
    if not bb_engine.is_ready():
        return False

    if len(bandwidth_history) < window:
        return False

    current = bb_engine.get_current_bands()
    if current is None:
        return False

    current_bandwidth = current["bandwidth"]

    # 当前带宽是最小值？
    return current_bandwidth == min(bandwidth_history)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("="*60)
    print("Incremental Bollinger Bands - 测试")
    print("="*60)

    # 创建实例
    bb = IncrementalBollingerBands(period=20, std_dev=2.0)

    # 测试数据（模拟价格序列）
    import random
    base_price = 100.0
    prices = [base_price + random.gauss(0, 2) for _ in range(50)]

    print(f"\n测试 1: 增量更新 {len(prices)} 个价格")
    print("-" * 60)

    for i, price in enumerate(prices):
        result = bb.update(price)

        if result is not None and i % 10 == 0:
            print(f"\n[{i+1:2d}] 价格: {price:.2f}")
            print(f"     中轨: {result['middle']:.2f}")
            print(f"     上轨: {result['upper']:.2f}")
            print(f"     下轨: {result['lower']:.2f}")
            print(f"     带宽: {result['bandwidth']:.4f}")
            print(f"     %b:   {result['percent_b']:.2f}")
            print(f"     Z分数: {result['z_score']:.2f}")
            print(f"     位置: {calculate_band_position(price, result)}")

    print(f"\n测试 2: 统计信息")
    print("-" * 60)
    stats = bb.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print(f"\n测试 3: 性能测试（1000 次更新）")
    print("-" * 60)
    import time

    bb_perf = IncrementalBollingerBands(period=20)
    test_prices = [100 + random.gauss(0, 1) for _ in range(1000)]

    start = time.perf_counter()
    for price in test_prices:
        bb_perf.update(price)
    elapsed = time.perf_counter() - start

    print(f"  总时间: {elapsed*1000:.2f} ms")
    print(f"  每次更新: {elapsed*1000000/len(test_prices):.2f} μs")
    print(f"  更新频率: {len(test_prices)/elapsed:.0f} updates/s")

    print(f"\n✅ 所有测试完成！")
