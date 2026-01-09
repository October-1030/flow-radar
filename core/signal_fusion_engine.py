#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - 信号融合引擎

功能：
1. 基于时间窗口和价格重叠检测信号关联
2. 填充 SignalEvent.related_signals 字段
3. 支持三种信号类型（iceberg/whale/liq）
4. 性能优化（价格分桶、时间索引）

算法：
- 时间条件：abs(ts1 - ts2) <= SIGNAL_CORRELATION_WINDOW
- 交易对条件：symbol1 == symbol2
- 价格条件：price_range1 与 price_range2 重叠

作者：Claude Code
日期：2026-01-09
版本：v2.0（Phase 2）
"""

import time
from typing import List, Tuple, Dict, Optional, Set
from collections import defaultdict
from dataclasses import dataclass

from core.signal_schema import SignalEvent
from config.p3_fusion_config import (
    SIGNAL_CORRELATION_WINDOW,
    PRICE_OVERLAP_THRESHOLD,
    get_price_expansion,
    PRICE_BUCKET_PRECISION,
    ENABLE_PRICE_RANGE_CACHE,
)


@dataclass
class PriceRange:
    """价格范围数据类"""
    min_price: float
    max_price: float
    center_price: float

    def overlaps(self, other: 'PriceRange') -> bool:
        """
        判断两个价格范围是否重叠

        Args:
            other: 另一个价格范围

        Returns:
            True: 重叠
            False: 不重叠
        """
        return not (self.max_price < other.min_price or self.min_price > other.max_price)


class SignalFusionEngine:
    """
    信号融合引擎

    负责检测信号之间的关联关系，填充 related_signals 字段
    """

    def __init__(self, config=None):
        """
        初始化信号融合引擎

        Args:
            config: 配置模块（默认使用 p3_fusion_config）
        """
        if config is None:
            from config import p3_fusion_config as config

        self.config = config
        self.correlation_window = SIGNAL_CORRELATION_WINDOW
        self.price_threshold = PRICE_OVERLAP_THRESHOLD

        # 缓存
        self._price_range_cache: Dict[str, PriceRange] = {} if ENABLE_PRICE_RANGE_CACHE else None

        # 统计
        self.stats = {
            'total_checks': 0,
            'time_filtered': 0,
            'symbol_filtered': 0,
            'price_filtered': 0,
            'relations_found': 0,
        }

    def find_related_signals(self, signal: SignalEvent, all_signals: List[SignalEvent]) -> List[str]:
        """
        查找与目标信号关联的其他信号

        关联条件（必须全部满足）:
        1. 时间窗口内（abs(ts1 - ts2) <= SIGNAL_CORRELATION_WINDOW）
        2. 同交易对（symbol1 == symbol2）
        3. 价格范围重叠

        Args:
            signal: 目标信号
            all_signals: 所有信号列表

        Returns:
            关联信号的 key 列表

        Example:
            >>> engine = SignalFusionEngine()
            >>> signal = IcebergSignal(...)
            >>> related = engine.find_related_signals(signal, all_signals)
            >>> print(related)
            ['iceberg_BTC_USDT_BUY_1704800000_0', 'iceberg_BTC_USDT_BUY_1704800120_0']
        """
        related_keys = []

        # 获取目标信号的价格范围
        target_range = self._get_price_range(signal)

        for other in all_signals:
            self.stats['total_checks'] += 1

            # 跳过自己
            if signal.key == other.key:
                continue

            # 条件 1: 时间窗口检查
            time_diff = abs(signal.ts - other.ts)
            if time_diff > self.correlation_window:
                self.stats['time_filtered'] += 1
                continue

            # 条件 2: 同交易对检查
            if signal.symbol != other.symbol:
                self.stats['symbol_filtered'] += 1
                continue

            # 条件 3: 价格重叠检查
            other_range = self._get_price_range(other)
            if not self._has_price_overlap(target_range, other_range):
                self.stats['price_filtered'] += 1
                continue

            # 满足所有条件，建立关联
            related_keys.append(other.key)
            self.stats['relations_found'] += 1

        return related_keys

    def _has_price_overlap(self, range1: PriceRange, range2: PriceRange) -> bool:
        """
        判断两个价格范围是否重叠

        Args:
            range1: 价格范围 1
            range2: 价格范围 2

        Returns:
            True: 重叠
            False: 不重叠

        Example:
            >>> r1 = PriceRange(min_price=100, max_price=101, center_price=100.5)
            >>> r2 = PriceRange(min_price=100.5, max_price=101.5, center_price=101)
            >>> engine._has_price_overlap(r1, r2)
            True
        """
        return range1.overlaps(range2)

    def _get_price_range(self, signal: SignalEvent) -> PriceRange:
        """
        获取信号的价格范围

        根据信号类型使用不同的价格扩展系数:
        - iceberg: price ± 0.1%
        - whale: avg_price ± 0.05% (或使用 price)
        - liq: liquidation_price ± 0.2% (或使用 price)

        Args:
            signal: 信号对象

        Returns:
            PriceRange 对象

        Example:
            >>> signal = IcebergSignal(price=100, signal_type='iceberg', ...)
            >>> range = engine._get_price_range(signal)
            >>> print(range)
            PriceRange(min_price=99.9, max_price=100.1, center_price=100)
        """
        # 检查缓存
        if self._price_range_cache is not None and signal.key in self._price_range_cache:
            return self._price_range_cache[signal.key]

        # 获取中心价格
        center_price = self._get_center_price(signal)

        # 获取价格扩展系数
        expansion = get_price_expansion(signal.signal_type)

        # 计算价格范围
        min_price = center_price * (1 - expansion)
        max_price = center_price * (1 + expansion)

        price_range = PriceRange(
            min_price=min_price,
            max_price=max_price,
            center_price=center_price
        )

        # 缓存结果
        if self._price_range_cache is not None:
            self._price_range_cache[signal.key] = price_range

        return price_range

    def _get_center_price(self, signal: SignalEvent) -> float:
        """
        获取信号的中心价格

        优先级:
        1. 特定字段（avg_price, liquidation_price）
        2. 通用 price 字段
        3. 从 data 字典提取

        Args:
            signal: 信号对象

        Returns:
            中心价格

        Raises:
            ValueError: 无法获取价格
        """
        # 优先使用通用 price 字段
        if signal.price is not None:
            return signal.price

        # 从 data 字典提取
        if signal.data:
            # 尝试常见价格字段
            for price_field in ['price', 'avg_price', 'liquidation_price', 'entry_price']:
                if price_field in signal.data:
                    price = signal.data[price_field]
                    if price is not None and price > 0:
                        return price

        raise ValueError(f"无法获取信号 {signal.key} 的价格")

    def batch_find_relations(self, signals: List[SignalEvent]) -> Dict[str, List[str]]:
        """
        批量处理所有信号的关联关系（性能优化版）

        使用优化策略：
        1. 价格分桶 - 只在相邻价格桶中查找
        2. 时间排序 - 使用滑动窗口
        3. 符号分组 - 先按交易对分组

        Args:
            signals: 信号列表

        Returns:
            Dict[signal_key, List[related_keys]]

        Example:
            >>> engine = SignalFusionEngine()
            >>> relations = engine.batch_find_relations(signals)
            >>> print(relations['iceberg_BTC_USDT_BUY_1704800000_0'])
            ['iceberg_BTC_USDT_BUY_1704800120_0', 'whale_BTC_USDT_BUY_1704800150_0']
        """
        start_time = time.time()

        # 重置统计
        self.stats = {
            'total_checks': 0,
            'time_filtered': 0,
            'symbol_filtered': 0,
            'price_filtered': 0,
            'relations_found': 0,
            'processing_time': 0,
        }

        # 结果字典
        relations: Dict[str, List[str]] = {sig.key: [] for sig in signals}

        # 步骤 1: 按交易对分组（减少跨交易对比较）
        symbol_groups = self._group_by_symbol(signals)

        # 步骤 2: 对每个交易对组，使用优化算法
        for symbol, group_signals in symbol_groups.items():
            if len(group_signals) < 2:
                # 单信号组，无需查找关联
                continue

            # 步骤 2.1: 按时间排序
            sorted_signals = sorted(group_signals, key=lambda s: s.ts)

            # 步骤 2.2: 价格分桶
            price_buckets = self._build_price_buckets(sorted_signals)

            # 步骤 2.3: 查找关联（使用滑动窗口 + 价格桶）
            for i, signal in enumerate(sorted_signals):
                # 获取时间窗口内的候选信号
                candidates = self._get_time_window_candidates(
                    signal, sorted_signals, i
                )

                # 进一步使用价格桶过滤
                price_filtered_candidates = self._filter_by_price_bucket(
                    signal, candidates, price_buckets
                )

                # 精确价格重叠检查
                signal_range = self._get_price_range(signal)
                for candidate in price_filtered_candidates:
                    if candidate.key == signal.key:
                        continue

                    candidate_range = self._get_price_range(candidate)
                    if self._has_price_overlap(signal_range, candidate_range):
                        relations[signal.key].append(candidate.key)
                        self.stats['relations_found'] += 1

        # 统计处理时间
        self.stats['processing_time'] = time.time() - start_time

        return relations

    def _group_by_symbol(self, signals: List[SignalEvent]) -> Dict[str, List[SignalEvent]]:
        """
        按交易对分组信号

        Args:
            signals: 信号列表

        Returns:
            Dict[symbol, List[signals]]
        """
        groups = defaultdict(list)
        for signal in signals:
            groups[signal.symbol].append(signal)
        return dict(groups)

    def _build_price_buckets(self, signals: List[SignalEvent]) -> Dict[int, List[SignalEvent]]:
        """
        构建价格分桶索引

        将信号按价格分桶（精度由 PRICE_BUCKET_PRECISION 控制）

        Args:
            signals: 信号列表

        Returns:
            Dict[bucket_key, List[signals]]

        Example:
            价格 100.123 -> 桶 100 (precision=0)
            价格 100.123 -> 桶 1001 (precision=1, 即 100.1)
            价格 100.123 -> 桶 10012 (precision=2, 即 100.12)
        """
        buckets = defaultdict(list)

        for signal in signals:
            try:
                center_price = self._get_center_price(signal)
                # 计算桶键（根据精度）
                bucket_key = int(round(center_price * (10 ** PRICE_BUCKET_PRECISION)))
                buckets[bucket_key].append(signal)
            except ValueError:
                # 无法获取价格，跳过
                continue

        return dict(buckets)

    def _get_time_window_candidates(
        self,
        signal: SignalEvent,
        sorted_signals: List[SignalEvent],
        current_index: int
    ) -> List[SignalEvent]:
        """
        获取时间窗口内的候选信号（滑动窗口）

        Args:
            signal: 目标信号
            sorted_signals: 按时间排序的信号列表
            current_index: 目标信号在列表中的索引

        Returns:
            时间窗口内的候选信号列表
        """
        candidates = []
        window_start = signal.ts - self.correlation_window
        window_end = signal.ts + self.correlation_window

        # 向前查找
        for i in range(current_index - 1, -1, -1):
            other = sorted_signals[i]
            if other.ts < window_start:
                break  # 超出窗口，停止
            candidates.append(other)

        # 向后查找
        for i in range(current_index + 1, len(sorted_signals)):
            other = sorted_signals[i]
            if other.ts > window_end:
                break  # 超出窗口，停止
            candidates.append(other)

        self.stats['total_checks'] += len(candidates)
        return candidates

    def _filter_by_price_bucket(
        self,
        signal: SignalEvent,
        candidates: List[SignalEvent],
        price_buckets: Dict[int, List[SignalEvent]]
    ) -> List[SignalEvent]:
        """
        使用价格桶过滤候选信号

        只保留价格桶相邻的候选信号（相邻 = 当前桶 ± 1）

        Args:
            signal: 目标信号
            candidates: 候选信号列表
            price_buckets: 价格桶索引

        Returns:
            过滤后的候选信号列表
        """
        try:
            center_price = self._get_center_price(signal)
            signal_bucket = int(round(center_price * (10 ** PRICE_BUCKET_PRECISION)))

            # 获取相邻桶（包括当前桶）
            adjacent_buckets = {signal_bucket - 1, signal_bucket, signal_bucket + 1}

            # 过滤候选信号
            filtered = []
            for candidate in candidates:
                try:
                    cand_center = self._get_center_price(candidate)
                    cand_bucket = int(round(cand_center * (10 ** PRICE_BUCKET_PRECISION)))

                    if cand_bucket in adjacent_buckets:
                        filtered.append(candidate)
                    else:
                        self.stats['price_filtered'] += 1
                except ValueError:
                    continue

            return filtered

        except ValueError:
            # 无法获取价格，返回全部候选
            return candidates

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计字典
        """
        return self.stats.copy()

    def clear_cache(self):
        """清空缓存"""
        if self._price_range_cache is not None:
            self._price_range_cache.clear()
