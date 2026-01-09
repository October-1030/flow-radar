#!/usr/bin/env python3
"""
Unit Tests for IncrementalBollingerBands
布林带增量计算引擎单元测试

测试覆盖:
- 基础功能: 更新、计算、状态检查
- 边界条件: 数据不足、极值、零值
- 扩展指标: bandwidth, percent_b, z_score
- 性能测试: 1000 次更新 < 10ms
- 辅助函数: band_position, bandwidth_expanding, squeeze

作者: Claude Code (三方共识)
日期: 2026-01-09
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import time
from collections import deque

from core.bollinger_engine import (
    IncrementalBollingerBands,
    calculate_band_position,
    is_bandwidth_expanding,
    is_bandwidth_squeezing,
    detect_bollinger_squeeze
)


class TestIncrementalBollingerBands:
    """测试 IncrementalBollingerBands 类"""

    def test_initialization(self):
        """测试初始化"""
        bb = IncrementalBollingerBands(period=20, std_dev=2.0)

        assert bb.period == 20
        assert bb.std_dev == 2.0
        assert len(bb.prices) == 0
        assert not bb.is_ready()

    def test_invalid_parameters(self):
        """测试无效参数"""
        # period < 2
        with pytest.raises(ValueError, match="period must be >= 2"):
            IncrementalBollingerBands(period=1)

        # std_dev <= 0
        with pytest.raises(ValueError, match="std_dev must be > 0"):
            IncrementalBollingerBands(period=20, std_dev=0)

        with pytest.raises(ValueError, match="std_dev must be > 0"):
            IncrementalBollingerBands(period=20, std_dev=-1)

    def test_invalid_price(self):
        """测试无效价格"""
        bb = IncrementalBollingerBands(period=20)

        # 负价格
        with pytest.raises(ValueError, match="price must be > 0"):
            bb.update(-100)

        # 零价格
        with pytest.raises(ValueError, match="price must be > 0"):
            bb.update(0)

    def test_data_insufficient(self):
        """测试数据不足时返回 None"""
        bb = IncrementalBollingerBands(period=20)

        # 添加 19 个价格（不足 20）
        for i in range(19):
            result = bb.update(100.0 + i * 0.1)
            assert result is None
            assert not bb.is_ready()

        # 第 20 个价格，应该返回结果
        result = bb.update(100.0)
        assert result is not None
        assert bb.is_ready()

    def test_basic_calculation(self):
        """测试基本计算"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 添加 5 个价格: [100, 101, 102, 101, 100]
        prices = [100.0, 101.0, 102.0, 101.0, 100.0]
        result = None

        for price in prices:
            result = bb.update(price)

        assert result is not None

        # 手工验证: mean = 100.8, std ≈ 0.748
        mean = sum(prices) / len(prices)
        assert abs(result['middle'] - mean) < 0.01

        # 上下轨应该对称
        assert result['upper'] > result['middle']
        assert result['lower'] < result['middle']
        assert abs((result['upper'] - result['middle']) -
                   (result['middle'] - result['lower'])) < 0.01

    def test_sliding_window(self):
        """测试滑动窗口（移除最老价格）"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 添加 10 个价格（窗口会滑动）
        prices = [100 + i for i in range(10)]

        for price in prices:
            bb.update(price)

        # 窗口应该只保留最后 5 个: [105, 106, 107, 108, 109]
        assert len(bb.prices) == 5
        assert list(bb.prices) == [105, 106, 107, 108, 109]

    def test_bandwidth_calculation(self):
        """测试带宽计算"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 低波动率: [100, 100, 100, 100, 100]
        for _ in range(5):
            bb.update(100.0)

        result_low_vol = bb.get_current_bands()
        assert result_low_vol is not None

        # 重置
        bb.reset()

        # 高波动率: [90, 95, 100, 105, 110]
        for price in [90, 95, 100, 105, 110]:
            bb.update(price)

        result_high_vol = bb.get_current_bands()
        assert result_high_vol is not None

        # 高波动率 bandwidth > 低波动率 bandwidth
        assert result_high_vol['bandwidth'] > result_low_vol['bandwidth']

    def test_percent_b(self):
        """测试 %b 指标"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 添加 5 个价格
        for price in [98, 99, 100, 101, 102]:
            bb.update(price)

        # 测试不同价格位置的 %b
        # 触上轨: %b ≈ 1.0
        result_upper = bb.update(105)
        assert result_upper is not None
        assert result_upper['percent_b'] > 0.8  # 接近上轨

        # 触下轨: %b ≈ 0.0
        bb.reset()
        for price in [98, 99, 100, 101, 102]:
            bb.update(price)
        result_lower = bb.update(95)
        assert result_lower is not None
        assert result_lower['percent_b'] < 0.2  # 接近下轨

        # 中轨: %b ≈ 0.5
        bb.reset()
        for price in [98, 99, 100, 101, 102]:
            bb.update(price)
        result_middle = bb.update(100)
        assert result_middle is not None
        assert 0.4 < result_middle['percent_b'] < 0.6  # 接近中轨

    def test_z_score(self):
        """测试 Z 分数"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 添加 5 个价格: [100] * 5 (无波动)
        for _ in range(5):
            bb.update(100.0)

        result = bb.get_current_bands()
        assert result is not None

        # 价格 = 均值，Z 分数 ≈ 0
        assert abs(result['z_score']) < 0.01

        # 添加偏离均值的价格
        result = bb.update(110.0)  # 偏离 +10
        assert result is not None
        assert result['z_score'] > 0  # 正 Z 分数

    def test_get_current_bands(self):
        """测试获取当前布林带（不更新）"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 数据不足
        assert bb.get_current_bands() is None

        # 添加足够数据
        for price in [98, 99, 100, 101, 102]:
            bb.update(price)

        # 获取当前值（不更新）
        bands1 = bb.get_current_bands()
        bands2 = bb.get_current_bands()

        assert bands1 is not None
        assert bands2 is not None
        assert bands1['middle'] == bands2['middle']  # 值不变

    def test_reset(self):
        """测试重置功能"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 添加数据
        for price in [98, 99, 100, 101, 102]:
            bb.update(price)

        assert bb.is_ready()
        assert len(bb.prices) == 5

        # 重置
        bb.reset()

        assert not bb.is_ready()
        assert len(bb.prices) == 0
        assert bb._sum == 0.0
        assert bb._sum_sq == 0.0
        assert bb._update_count == 0

    def test_stats(self):
        """测试统计信息"""
        bb = IncrementalBollingerBands(period=20, std_dev=2.5)

        stats = bb.get_stats()

        assert stats['period'] == 20
        assert stats['std_dev'] == 2.5
        assert stats['data_points'] == 0
        assert stats['is_ready'] is False
        assert stats['update_count'] == 0

        # 添加数据
        for i in range(25):
            bb.update(100 + i * 0.1)

        stats = bb.get_stats()
        assert stats['data_points'] == 20  # maxlen = period
        assert stats['is_ready'] is True
        assert stats['update_count'] == 25

    def test_repr(self):
        """测试字符串表示"""
        bb = IncrementalBollingerBands(period=20, std_dev=2.0)

        repr_str = repr(bb)

        assert "IncrementalBollingerBands" in repr_str
        assert "period=20" in repr_str
        assert "std_dev=2.0" in repr_str
        assert "0/20" in repr_str  # 数据点

    def test_performance(self):
        """测试性能（1000 次更新 < 10ms）"""
        bb = IncrementalBollingerBands(period=20)

        # 生成测试数据
        prices = [100 + i * 0.01 for i in range(1000)]

        start = time.perf_counter()
        for price in prices:
            bb.update(price)
        elapsed = time.perf_counter() - start

        # 断言: 1000 次更新 < 10ms
        assert elapsed < 0.01, f"Performance test failed: {elapsed*1000:.2f}ms > 10ms"

        # 输出性能指标
        print(f"\n  Performance: {elapsed*1000:.2f}ms for 1000 updates")
        print(f"  Avg: {elapsed*1000000/len(prices):.2f} μs per update")


class TestBandPositionHelper:
    """测试 calculate_band_position 辅助函数"""

    def test_above_upper(self):
        """测试超过上轨"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(101.0, bands) == "above_upper"

    def test_at_upper(self):
        """测试触上轨"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(100.0, bands) == "upper"

    def test_at_middle(self):
        """测试触中轨"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(98.0, bands) == "middle"

    def test_at_lower(self):
        """测试触下轨"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(96.0, bands) == "lower"

    def test_below_lower(self):
        """测试低于下轨"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(95.0, bands) == "below_lower"

    def test_upper_half(self):
        """测试上半区"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(99.0, bands) == "upper_half"

    def test_lower_half(self):
        """测试下半区"""
        bands = {
            "upper": 100.0,
            "middle": 98.0,
            "lower": 96.0
        }

        assert calculate_band_position(97.0, bands) == "lower_half"

    def test_none_bands(self):
        """测试 None 输入"""
        assert calculate_band_position(100.0, None) == "unknown"


class TestBandwidthExpanding:
    """测试 is_bandwidth_expanding"""

    def test_expanding(self):
        """测试带宽扩张"""
        assert is_bandwidth_expanding(1.1, 1.0, threshold=0.05) is True

    def test_not_expanding(self):
        """测试带宽未扩张"""
        assert is_bandwidth_expanding(1.02, 1.0, threshold=0.05) is False

    def test_zero_prev_bandwidth(self):
        """测试之前带宽为 0"""
        assert is_bandwidth_expanding(1.0, 0.0, threshold=0.05) is False


class TestBandwidthSqueezing:
    """测试 is_bandwidth_squeezing"""

    def test_squeezing(self):
        """测试带宽收缩"""
        assert is_bandwidth_squeezing(0.4, 1.0, threshold=0.5) is True

    def test_not_squeezing(self):
        """测试带宽未收缩"""
        assert is_bandwidth_squeezing(0.6, 1.0, threshold=0.5) is False

    def test_zero_historical_avg(self):
        """测试历史平均为 0"""
        assert is_bandwidth_squeezing(0.4, 0.0, threshold=0.5) is False


class TestBollingerSqueeze:
    """测试 detect_bollinger_squeeze"""

    def test_squeeze_detected(self):
        """测试检测到挤压"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 建立布林带（横盘）
        for _ in range(5):
            bb.update(100.0)

        # 获取当前带宽（会非常小，接近 0）
        current_bands = bb.get_current_bands()
        current_bandwidth = current_bands['bandwidth']

        # 建立带宽历史（高波动 → 当前带宽）
        bandwidth_history = deque([0.05, 0.04, 0.03, 0.02, current_bandwidth], maxlen=5)

        # 当前带宽是最小值 → 检测到挤压
        assert detect_bollinger_squeeze(bb, bandwidth_history, window=5) is True

    def test_squeeze_not_detected(self):
        """测试未检测到挤压"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 建立布林带（高波动）
        for price in [95, 100, 105, 100, 95]:
            bb.update(price)

        # 建立带宽历史（低波动 → 高波动）
        bandwidth_history = deque([0.01, 0.02, 0.03, 0.04, 0.05], maxlen=5)

        # 当前带宽不是最小值 → 未检测到挤压
        assert detect_bollinger_squeeze(bb, bandwidth_history, window=5) is False

    def test_insufficient_data(self):
        """测试数据不足"""
        bb = IncrementalBollingerBands(period=5, std_dev=2.0)

        # 不足 5 个数据点
        for _ in range(4):
            bb.update(100.0)

        bandwidth_history = deque([0.05, 0.04, 0.03], maxlen=5)

        assert detect_bollinger_squeeze(bb, bandwidth_history, window=5) is False


# ==================== pytest 配置 ====================

def pytest_configure(config):
    """pytest 配置"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "-s"])
