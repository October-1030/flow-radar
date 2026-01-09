#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - 冲突解决器

功能：
1. 检测 BUY vs SELL 信号冲突
2. 应用 6 场景冲突解决矩阵
3. 标记失败者（降低置信度）
4. 返回解决后的信号列表

冲突解决优先级：
1. 类型优先（liq > whale > iceberg）
2. 级别优先（CRITICAL > CONFIRMED > ...）
3. 置信度优先（高置信度胜出）
4. 同级同类 → 都保留但降低置信度

作者：Claude Code
日期：2026-01-09
版本：v2.0（Phase 2）
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from core.signal_schema import SignalEvent
from core.signal_fusion_engine import SignalFusionEngine
from config.p3_settings import LEVEL_PRIORITY, TYPE_PRIORITY, get_signal_priority
from config.p3_fusion_config import (
    CONFLICT_DETECTION_WINDOW,
    CONFLICT_PRICE_THRESHOLD,
    SAME_LEVEL_TYPE_CONFLICT_PENALTY,
)


class ConflictResolver:
    """
    冲突解决器

    负责检测和解决信号冲突（BUY vs SELL）
    """

    def __init__(self, config=None):
        """
        初始化冲突解决器

        Args:
            config: 配置模块（默认使用 p3_fusion_config）
        """
        if config is None:
            from config import p3_fusion_config as config

        self.config = config
        self.fusion_engine = SignalFusionEngine(config)

        # 统计
        self.stats = {
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'signals_penalized': 0,
        }

    def resolve_conflicts(self, signals: List[SignalEvent]) -> List[SignalEvent]:
        """
        解决信号冲突（BUY vs SELL）

        流程:
        1. 检测冲突组（同时间窗口 + 价格重叠 + 方向相反）
        2. 应用优先级规则（6 场景矩阵）
        3. 标记失败者（降低置信度）
        4. 返回所有信号（包括胜出者和失败者）

        Args:
            signals: 信号列表

        Returns:
            List[SignalEvent]: 处理后的信号列表（冲突已解决）

        Example:
            >>> resolver = ConflictResolver()
            >>> signals = [buy_signal, sell_signal]  # 有冲突
            >>> resolved = resolver.resolve_conflicts(signals)
            >>> # buy_signal 胜出，sell_signal 被标记降低置信度
        """
        # 重置统计
        self.stats = {
            'conflicts_detected': 0,
            'conflicts_resolved': 0,
            'signals_penalized': 0,
        }

        # 步骤 1: 检测冲突组
        conflict_groups = self._detect_conflicts(signals)

        if not conflict_groups:
            # 无冲突，直接返回
            return signals

        # 步骤 2: 解决每个冲突组
        for conflict_group in conflict_groups:
            self._resolve_conflict_group(conflict_group)

        return signals

    def _detect_conflicts(self, signals: List[SignalEvent]) -> List[List[SignalEvent]]:
        """
        检测冲突信号组

        冲突定义：
        1. 时间窗口内（abs(ts1 - ts2) <= CONFLICT_DETECTION_WINDOW）
        2. 同交易对（symbol1 == symbol2）
        3. 价格范围重叠
        4. 方向相反（BUY vs SELL）

        Returns:
            List[List[SignalEvent]]: 冲突组列表
            例: [[buy1, sell1], [buy2, buy3, sell2]]

        Example:
            >>> groups = resolver._detect_conflicts(signals)
            >>> print(len(groups))
            2  # 2 个冲突组
        """
        conflict_groups = []

        # 按交易对分组
        symbol_groups = defaultdict(list)
        for signal in signals:
            symbol_groups[signal.symbol].append(signal)

        # 对每个交易对，检测冲突
        for symbol, group_signals in symbol_groups.items():
            # 分离 BUY 和 SELL
            buy_signals = [s for s in group_signals if s.side == 'BUY']
            sell_signals = [s for s in group_signals if s.side == 'SELL']

            if not buy_signals or not sell_signals:
                # 无对立信号，跳过
                continue

            # 检测每对 BUY-SELL 是否冲突
            for buy in buy_signals:
                for sell in sell_signals:
                    if self._is_conflicting(buy, sell):
                        # 找到冲突，创建冲突组
                        conflict_group = [buy, sell]

                        # 检查是否已在其他冲突组中
                        merged = False
                        for existing_group in conflict_groups:
                            if buy in existing_group or sell in existing_group:
                                # 合并到现有冲突组
                                if buy not in existing_group:
                                    existing_group.append(buy)
                                if sell not in existing_group:
                                    existing_group.append(sell)
                                merged = True
                                break

                        if not merged:
                            conflict_groups.append(conflict_group)
                            self.stats['conflicts_detected'] += 1

        return conflict_groups

    def _is_conflicting(self, signal1: SignalEvent, signal2: SignalEvent) -> bool:
        """
        判断两个信号是否冲突

        Args:
            signal1: 信号1
            signal2: 信号2

        Returns:
            True: 冲突
            False: 不冲突
        """
        # 条件 1: 方向相反
        if signal1.side == signal2.side:
            return False

        # 条件 2: 时间窗口内
        time_diff = abs(signal1.ts - signal2.ts)
        if time_diff > CONFLICT_DETECTION_WINDOW:
            return False

        # 条件 3: 同交易对
        if signal1.symbol != signal2.symbol:
            return False

        # 条件 4: 价格重叠
        range1 = self.fusion_engine._get_price_range(signal1)
        range2 = self.fusion_engine._get_price_range(signal2)
        if not range1.overlaps(range2):
            return False

        return True

    def _resolve_conflict_group(self, conflict_group: List[SignalEvent]):
        """
        解决一个冲突组

        应用 6 场景优先级规则：
        1. 类型优先（liq > whale > iceberg）
        2. 级别优先（CRITICAL > CONFIRMED > ...）
        3. 置信度优先（高置信度胜出）
        4. 同级同类 → 都保留但降低置信度

        Args:
            conflict_group: 冲突组（会被修改，失败者置信度降低）
        """
        # 分离 BUY 和 SELL
        buy_signals = [s for s in conflict_group if s.side == 'BUY']
        sell_signals = [s for s in conflict_group if s.side == 'SELL']

        if not buy_signals or not sell_signals:
            return  # 无冲突，不处理

        # 应用优先级规则
        winners, losers = self._apply_priority_rules(buy_signals, sell_signals)

        # 标记失败者
        for loser in losers:
            self._penalize_signal(loser, 'conflict')
            self.stats['signals_penalized'] += 1

        self.stats['conflicts_resolved'] += 1

    def _apply_priority_rules(
        self,
        buy_signals: List[SignalEvent],
        sell_signals: List[SignalEvent]
    ) -> Tuple[List[SignalEvent], List[SignalEvent]]:
        """
        应用 6 场景优先级规则

        规则顺序:
        1. 类型优先（liq > whale > iceberg）
        2. 级别优先（CRITICAL > CONFIRMED > ...）
        3. 置信度优先（高置信度胜出）
        4. 同级同类 → 都保留但降低置信度

        Args:
            buy_signals: BUY 信号列表
            sell_signals: SELL 信号列表

        Returns:
            (winners, losers): 胜出信号列表, 失败信号列表
        """
        # 选出最高优先级的 BUY 和 SELL
        best_buy = max(buy_signals, key=lambda s: self._get_priority_score(s))
        best_sell = max(sell_signals, key=lambda s: self._get_priority_score(s))

        # 比较优先级
        buy_priority = get_signal_priority(best_buy.level, best_buy.signal_type)
        sell_priority = get_signal_priority(best_sell.level, best_sell.signal_type)

        if buy_priority < sell_priority:
            # BUY 优先级更高
            winners = [best_buy]
            losers = sell_signals
        elif sell_priority < buy_priority:
            # SELL 优先级更高
            winners = [best_sell]
            losers = buy_signals
        else:
            # 优先级相同（同级同类），比较置信度
            if best_buy.confidence > best_sell.confidence:
                winners = [best_buy]
                losers = sell_signals
            elif best_sell.confidence > best_buy.confidence:
                winners = [best_sell]
                losers = buy_signals
            else:
                # 置信度也相同，都保留但都降低置信度
                winners = []
                losers = buy_signals + sell_signals

        return winners, losers

    def _get_priority_score(self, signal: SignalEvent) -> Tuple:
        """
        获取信号的优先级分数（用于排序）

        返回元组：(level_priority, type_priority, confidence)
        - level_priority: 级别优先级（越小越优先）
        - type_priority: 类型优先级（越小越优先）
        - confidence: 置信度（越大越优先）

        Args:
            signal: 信号对象

        Returns:
            优先级元组（用于比较）
        """
        level_priority = LEVEL_PRIORITY.get(signal.level, 999)
        type_priority = TYPE_PRIORITY.get(signal.signal_type, 999)
        confidence = signal.confidence

        # 返回元组（level 和 type 越小越优先，confidence 越大越优先）
        # 注意：由于使用 max() 选择最大值，需要反转 level 和 type
        return (-level_priority, -type_priority, confidence)

    def _penalize_signal(self, signal: SignalEvent, reason: str = 'conflict'):
        """
        标记失败信号（降低置信度）

        Args:
            signal: 失败信号（会被修改）
            reason: 惩罚原因
        """
        # 如果 confidence_modifier 尚未初始化，初始化它
        if not signal.confidence_modifier:
            signal.confidence_modifier = {
                'base': signal.confidence,
                'resonance_boost': 0.0,
                'conflict_penalty': 0.0,
                'type_bonus': 0.0,
                'time_decay': 0.0,
                'final': signal.confidence
            }

        # 应用同级同类冲突惩罚
        signal.confidence_modifier['conflict_penalty'] -= SAME_LEVEL_TYPE_CONFLICT_PENALTY

        # 重新计算最终置信度
        final = (
            signal.confidence_modifier['base']
            + signal.confidence_modifier['resonance_boost']
            + signal.confidence_modifier['conflict_penalty']
            + signal.confidence_modifier['type_bonus']
            + signal.confidence_modifier['time_decay']
        )

        # 限制在 [0, 100]
        signal.confidence = max(0.0, min(100.0, final))
        signal.confidence_modifier['final'] = signal.confidence

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计字典
        """
        return self.stats.copy()
