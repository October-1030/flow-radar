#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - 置信度调整器

功能：
1. 计算信号置信度调整值（confidence_modifier）
2. 同向共振检测（+0 ~ +25）
3. 反向冲突检测（-5 ~ -10）
4. 类型组合奖励（iceberg+whale=+10 等）
5. 应用调整到信号对象

算法：
- 共振增强 = min(同向信号数 * 5, 25)
- 冲突惩罚 = -min(反向信号数 * 5, 10)
- 类型奖励 = TYPE_COMBO_BONUS 查表
- 最终置信度 = clamp(base + boost + penalty + bonus, 0, 100)

作者：Claude Code
日期：2026-01-09
版本：v2.0（Phase 2）
"""

from typing import List, Dict
from collections import Counter

from core.signal_schema import SignalEvent
from config.p3_fusion_config import (
    RESONANCE_BOOST_PER_SIGNAL,
    RESONANCE_BOOST_MAX,
    CONFLICT_PENALTY_PER_SIGNAL,
    CONFLICT_PENALTY_MAX,
    CONFIDENCE_MIN,
    CONFIDENCE_MAX,
    get_type_combo_bonus,
    TYPE_TRIPLE_COMBO_BONUS,
)


class ConfidenceModifier:
    """
    置信度调整器

    负责根据关联信号计算置信度调整值，填充 confidence_modifier 字段
    """

    def __init__(self, config=None):
        """
        初始化置信度调整器

        Args:
            config: 配置模块（默认使用 p3_fusion_config）
        """
        if config is None:
            from config import p3_fusion_config as config

        self.config = config
        self.boost_per_signal = RESONANCE_BOOST_PER_SIGNAL
        self.boost_max = RESONANCE_BOOST_MAX
        self.penalty_per_signal = CONFLICT_PENALTY_PER_SIGNAL
        self.penalty_max = CONFLICT_PENALTY_MAX

    def calculate_modifier(
        self,
        signal: SignalEvent,
        related_signals: List[SignalEvent]
    ) -> Dict[str, float]:
        """
        计算信号置信度调整值

        Args:
            signal: 目标信号
            related_signals: 关联信号列表（完整对象，非 key）

        Returns:
            Dict[str, float]: 置信度调整明细
            {
                'base': 65.0,              # 原始置信度
                'resonance_boost': 15.0,   # 共振增强
                'conflict_penalty': -5.0,  # 冲突惩罚
                'type_bonus': 10.0,        # 类型组合奖励
                'time_decay': 0.0,         # 时间衰减（Phase 2 暂不实现）
                'final': 85.0              # 最终置信度
            }

        Example:
            >>> modifier = ConfidenceModifier()
            >>> signal = IcebergSignal(confidence=75, side='BUY', ...)
            >>> related = [
            ...     IcebergSignal(confidence=80, side='BUY', ...),  # 同向
            ...     WhaleSignal(confidence=85, side='BUY', ...),    # 同向，且类型不同
            ...     IcebergSignal(confidence=70, side='SELL', ...),  # 反向
            ... ]
            >>> modifier_dict = modifier.calculate_modifier(signal, related)
            >>> print(modifier_dict)
            {
                'base': 75.0,
                'resonance_boost': 10.0,  # 2 个同向信号 * 5
                'conflict_penalty': -5.0,  # 1 个反向信号 * -5
                'type_bonus': 10.0,        # iceberg + whale 组合
                'time_decay': 0.0,
                'final': 90.0              # 75 + 10 - 5 + 10
            }
        """
        modifier = {
            'base': signal.confidence,
            'resonance_boost': 0.0,
            'conflict_penalty': 0.0,
            'type_bonus': 0.0,
            'time_decay': 0.0,
            'final': signal.confidence
        }

        # 如果没有关联信号，直接返回基础值
        if not related_signals:
            return modifier

        # 1. 计算同向共振增强
        modifier['resonance_boost'] = self._calculate_resonance_boost(signal, related_signals)

        # 2. 计算反向冲突惩罚
        modifier['conflict_penalty'] = self._calculate_conflict_penalty(signal, related_signals)

        # 3. 计算类型组合奖励
        modifier['type_bonus'] = self._calculate_type_bonus(signal, related_signals)

        # 4. 计算时间衰减（Phase 2 暂不实现，保留接口）
        modifier['time_decay'] = self._calculate_time_decay(signal, related_signals)

        # 5. 计算最终置信度（限制在 [0, 100]）
        final = (
            modifier['base']
            + modifier['resonance_boost']
            + modifier['conflict_penalty']
            + modifier['type_bonus']
            + modifier['time_decay']
        )
        modifier['final'] = self._clamp_confidence(final)

        return modifier

    def _calculate_resonance_boost(
        self,
        signal: SignalEvent,
        related_signals: List[SignalEvent]
    ) -> float:
        """
        计算同向共振增强（+0 ~ +25）

        算法：
        - 同向信号数量 = len([s for s in related if s.side == signal.side])
        - 增强值 = min(同向信号数 * RESONANCE_BOOST_PER_SIGNAL, RESONANCE_BOOST_MAX)

        Args:
            signal: 目标信号
            related_signals: 关联信号列表

        Returns:
            共振增强值（0 ~ 25）

        Example:
            >>> # 3 个同向信号
            >>> boost = modifier._calculate_resonance_boost(signal, related)
            >>> print(boost)
            15.0  # 3 * 5 = 15
        """
        # 筛选同向信号
        same_direction = [
            s for s in related_signals
            if s.side == signal.side
        ]

        if not same_direction:
            return 0.0

        # 计算增强值（上限 RESONANCE_BOOST_MAX）
        boost = min(
            len(same_direction) * self.boost_per_signal,
            self.boost_max
        )

        return float(boost)

    def _calculate_conflict_penalty(
        self,
        signal: SignalEvent,
        related_signals: List[SignalEvent]
    ) -> float:
        """
        计算反向冲突惩罚（-5 ~ -10）

        算法：
        - 反向信号数量 = len([s for s in related if s.side != signal.side])
        - 惩罚值 = -min(反向信号数 * CONFLICT_PENALTY_PER_SIGNAL, CONFLICT_PENALTY_MAX)

        Args:
            signal: 目标信号
            related_signals: 关联信号列表

        Returns:
            冲突惩罚值（-10 ~ 0）

        Example:
            >>> # 2 个反向信号
            >>> penalty = modifier._calculate_conflict_penalty(signal, related)
            >>> print(penalty)
            -10.0  # -(2 * 5) = -10 (达到上限)
        """
        # 筛选反向信号
        opposite_direction = [
            s for s in related_signals
            if s.side != signal.side
        ]

        if not opposite_direction:
            return 0.0

        # 计算惩罚值（上限 CONFLICT_PENALTY_MAX）
        penalty = -min(
            len(opposite_direction) * self.penalty_per_signal,
            self.penalty_max
        )

        return float(penalty)

    def _calculate_type_bonus(
        self,
        signal: SignalEvent,
        related_signals: List[SignalEvent]
    ) -> float:
        """
        计算类型组合奖励

        奖励规则：
        - iceberg + whale = +10
        - iceberg + liq = +15
        - whale + liq = +20
        - iceberg + whale + liq = +30 (三类型齐全)

        Args:
            signal: 目标信号
            related_signals: 关联信号列表

        Returns:
            类型组合奖励值

        Example:
            >>> # 目标信号是 iceberg，关联信号中有 whale
            >>> bonus = modifier._calculate_type_bonus(iceberg_signal, [whale_signal])
            >>> print(bonus)
            10.0  # iceberg + whale = +10
        """
        # 统计关联信号的类型
        related_types = {s.signal_type for s in related_signals}

        # 加上目标信号自己的类型
        all_types = related_types | {signal.signal_type}

        # 检查三类型齐全（最高奖励）
        if len(all_types) >= 3 and {'iceberg', 'whale', 'liq'}.issubset(all_types):
            return TYPE_TRIPLE_COMBO_BONUS

        # 检查两类型组合
        max_bonus = 0.0
        target_type = signal.signal_type

        for related_type in related_types:
            if related_type == target_type:
                continue  # 同类型不算组合

            # 查询组合奖励
            combo_bonus = get_type_combo_bonus(target_type, related_type)
            max_bonus = max(max_bonus, combo_bonus)

        return max_bonus

    def _calculate_time_decay(
        self,
        signal: SignalEvent,
        related_signals: List[SignalEvent]
    ) -> float:
        """
        计算时间衰减（Phase 2 暂不实现，预留接口）

        未来可能的实现：
        - 关联信号越旧，贡献的增强/惩罚越小
        - 使用指数衰减函数

        Args:
            signal: 目标信号
            related_signals: 关联信号列表

        Returns:
            时间衰减值（Phase 2 始终返回 0）
        """
        return 0.0

    def _clamp_confidence(self, confidence: float) -> float:
        """
        将置信度限制在 [CONFIDENCE_MIN, CONFIDENCE_MAX] 范围内

        Args:
            confidence: 原始置信度

        Returns:
            限制后的置信度

        Example:
            >>> modifier._clamp_confidence(105)
            100.0
            >>> modifier._clamp_confidence(-5)
            0.0
            >>> modifier._clamp_confidence(75)
            75.0
        """
        return max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, confidence))

    def apply_modifier(self, signal: SignalEvent, related_signals: List[SignalEvent]):
        """
        计算并应用置信度调整到信号对象

        修改信号的以下字段：
        - signal.confidence_modifier (Dict)
        - signal.confidence (float)

        Args:
            signal: 目标信号（会被修改）
            related_signals: 关联信号列表

        Example:
            >>> modifier = ConfidenceModifier()
            >>> signal = IcebergSignal(confidence=75, ...)
            >>> related = [...]
            >>> modifier.apply_modifier(signal, related)
            >>> print(signal.confidence)
            85.0  # 已更新
            >>> print(signal.confidence_modifier)
            {'base': 75.0, 'resonance_boost': 10.0, ...}
        """
        # 计算调整值
        modifier_dict = self.calculate_modifier(signal, related_signals)

        # 应用到信号对象
        signal.confidence_modifier = modifier_dict
        signal.confidence = modifier_dict['final']

    def batch_apply_modifiers(
        self,
        signals: List[SignalEvent],
        relations: Dict[str, List[str]]
    ):
        """
        批量应用置信度调整

        Args:
            signals: 信号列表
            relations: 关联关系字典 {signal_key: [related_keys]}

        Example:
            >>> modifier = ConfidenceModifier()
            >>> relations = {
            ...     'signal1': ['signal2', 'signal3'],
            ...     'signal2': ['signal1'],
            ...     'signal3': ['signal1'],
            ... }
            >>> modifier.batch_apply_modifiers(signals, relations)
        """
        # 构建 key -> signal 映射
        signal_map = {s.key: s for s in signals}

        # 对每个信号应用调整
        for signal in signals:
            # 获取关联信号的 key 列表
            related_keys = relations.get(signal.key, [])

            # 将 key 转换为完整对象
            related_objects = [
                signal_map[key]
                for key in related_keys
                if key in signal_map
            ]

            # 应用调整
            self.apply_modifier(signal, related_objects)
