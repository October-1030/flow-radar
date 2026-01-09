#!/usr/bin/env python3
"""
Flow Radar - Unified PriceLevel Module
流动性雷达 - 统一价格层级模块

P1-1: 单一来源的 PriceLevel 类
P1-Config: 配置外部化
"""

from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# 从 settings 导入配置
try:
    from config.settings import CONFIG_ICEBERG
except ImportError:
    CONFIG_ICEBERG = {
        'intensity_threshold': 2.0,
        'min_cumulative_volume': 500,
        'min_refill_count': 2,
    }


# ==================== P1-Config: 价格层级配置 ====================
CONFIG_PRICE_LEVEL = {
    # 迟滞阈值 (P0-1)
    "depletion_ratio": 0.2,             # 耗尽阈值: 剩余 < 20%
    "recovery_ratio": 0.5,              # 恢复阈值: 恢复到 > 50%
    "refill_time_limit": 30.0,          # 补单时间窗口 (秒)

    # 强度衰减 (P0-1)
    "strength_decay": 0.95,             # 强度衰减系数 (每次更新)
    "strength_boost": 0.3,              # 每次有效补单增加的强度
    "strength_threshold": 0.5,          # 强度阈值 (用于 is_iceberg 判断)

    # Spoofing 检测 (P0-3)
    "spoofing_threshold": 0.3,          # 低于此比例视为可疑
    "min_quantity_for_spoofing_check": 100.0,  # 至少消失量才检查

    # 置信度惩罚 (P1-2)
    "confidence_cap_suspicious": 60.0,  # 可疑信号的置信度上限
    "penalty_tiers": {
        # explanation_ratio 区间 -> 置信度乘数
        "high": {"min_ratio": 0.7, "multiplier": 1.0},
        "medium": {"min_ratio": 0.3, "multiplier": 0.6},
        "low": {"min_ratio": 0.0, "multiplier": 0.3},
    },

    # IcebergLevel 判断阈值
    "confirmed_absorption": 3.0,        # 确认冰山的吸收度阈值
    "confirmed_refill_count": 3,        # 确认冰山的补单次数阈值
}


class IcebergLevel(Enum):
    """
    冰山信号级别

    区分噪音与真实信号:
    - NONE: 无冰山活动
    - ACTIVITY: 有补单活动，可能是做市噪音
    - CONFIRMED: 满足吸收度和补单阈值，确认是冰山单
    """
    NONE = 0
    ACTIVITY = 1
    CONFIRMED = 2


@dataclass
class PriceLevel:
    """
    价格层级追踪 - 统一版本

    整合 P0 改进:
    - P0-1: 迟滞阈值检测补单 (Hysteresis)
    - P0-3: Spoofing 过滤 (explanation_ratio)

    整合 P1 改进:
    - P1-2: 置信度计算增强
    - P1-Config: 配置外部化
    """
    price: float
    side: str = 'bid'                           # 'bid' 或 'ask'
    visible_quantity: float = 0.0               # 当前可见挂单量
    cumulative_filled: float = 0.0              # 累计成交量
    fill_count: int = 0                         # 成交次数
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    refill_count: int = 0                       # 补单次数
    previous_visible: float = 0.0               # 上次可见量

    # P0-1: 迟滞检测相关字段
    peak_quantity: float = 0.0                  # 历史峰值挂单量
    max_visible: float = 0.0                    # 历史最大可见量 (兼容旧代码)
    is_depleted: bool = False                   # 是否处于耗尽状态
    depletion_time: Optional[datetime] = None   # 耗尽发生时间
    iceberg_strength: float = 0.0               # 连续冰山强度值 (0.0 - 2.0)

    # P0-3: Spoofing 检测相关字段
    disappeared_quantity: float = 0.0           # 订单簿消失量
    explained_quantity: float = 0.0             # 被实际成交解释的量
    explanation_ratio: float = 1.0              # 解释比例
    is_suspicious: bool = False                 # 是否可疑

    def update(self, new_visible: float, filled: float = 0) -> None:
        """
        更新价格层级

        使用迟滞阈值(Hysteresis)检测补单行为：
        - 耗尽阈值: 当可见量降至峰值的 20% 以下时，标记为"耗尽"
        - 恢复阈值: 当可见量恢复到峰值的 50% 以上时，确认为"补单"
        - 时间约束: 补单必须在耗尽后 30 秒内发生

        Args:
            new_visible: 新的可见挂单量
            filled: 本次成交量
        """
        cfg = CONFIG_PRICE_LEVEL
        now = datetime.now()

        # 更新历史最大值 (兼容旧代码)
        self.max_visible = max(self.max_visible, new_visible)

        # 更新峰值（只在非耗尽状态下更新）
        if not self.is_depleted and new_visible > self.peak_quantity:
            self.peak_quantity = new_visible

        # 初始化峰值
        if self.peak_quantity == 0:
            self.peak_quantity = max(new_visible, self.visible_quantity, 1.0)

        # 计算当前量相对于峰值的比例
        current_ratio = new_visible / self.peak_quantity if self.peak_quantity > 0 else 0

        # === 迟滞状态机 ===
        if not self.is_depleted:
            # 状态: 正常 -> 检测是否耗尽
            if current_ratio < cfg['depletion_ratio']:
                self.is_depleted = True
                self.depletion_time = now
                # 耗尽时轻微增加强度（表示有大单在吃）
                self.iceberg_strength += 0.1
        else:
            # 状态: 已耗尽 -> 检测是否补单
            time_since_depletion = (
                (now - self.depletion_time).total_seconds()
                if self.depletion_time else float('inf')
            )

            if current_ratio >= cfg['recovery_ratio']:
                # 恢复到阈值以上
                if time_since_depletion <= cfg['refill_time_limit']:
                    # 有效补单！在时间窗口内恢复
                    self.refill_count += 1
                    self.iceberg_strength += cfg['strength_boost']
                    # 重置峰值为当前值
                    self.peak_quantity = new_visible

                # 退出耗尽状态
                self.is_depleted = False
                self.depletion_time = None

            elif time_since_depletion > cfg['refill_time_limit']:
                # 超时未补单，重置状态
                self.is_depleted = False
                self.depletion_time = None
                self.peak_quantity = new_visible if new_visible > 0 else self.peak_quantity

        # 强度自然衰减
        self.iceberg_strength *= cfg['strength_decay']

        # 更新基础字段
        self.previous_visible = self.visible_quantity
        self.visible_quantity = new_visible
        self.cumulative_filled += filled
        if filled > 0:
            self.fill_count += 1
        self.last_updated = now

    @property
    def intensity(self) -> float:
        """
        计算冰山强度 (基于成交量/可见量比值)

        使用历史最大值避免除零
        """
        base = max(self.visible_quantity, self.max_visible, self.peak_quantity, 1)
        return self.cumulative_filled / base

    @property
    def is_iceberg(self) -> bool:
        """
        判断是否为冰山单

        条件:
        1. 强度超过阈值
        2. 累计成交量超过最小值
        3. 补单次数超过阈值 或 iceberg_strength 超过阈值
        4. P0-3: 不能是可疑的 spoofing
        """
        cfg = CONFIG_PRICE_LEVEL
        strength_qualified = self.iceberg_strength >= cfg['strength_threshold']
        refill_qualified = self.refill_count >= CONFIG_ICEBERG['min_refill_count']

        return (
            self.intensity >= CONFIG_ICEBERG['intensity_threshold'] and
            self.cumulative_filled >= CONFIG_ICEBERG['min_cumulative_volume'] and
            (refill_qualified or strength_qualified) and
            not self.is_suspicious  # P0-3: 排除可疑 spoofing
        )

    def get_iceberg_level(self) -> IcebergLevel:
        """
        获取冰山信号级别

        - NONE: 无冰山活动
        - ACTIVITY: 有补单活动，可能是做市噪音
        - CONFIRMED: 满足吸收度 >= 3 且补单 >= 3，确认是冰山单

        Returns:
            IcebergLevel: 冰山信号级别
        """
        cfg = CONFIG_PRICE_LEVEL

        # 计算吸收度
        absorption = self.cumulative_filled / max(self.max_visible, self.peak_quantity, 1)

        # 确认冰山
        if (absorption >= cfg['confirmed_absorption'] and
                self.refill_count >= cfg['confirmed_refill_count']):
            return IcebergLevel.CONFIRMED

        # 有活动
        if self.refill_count >= 1:
            return IcebergLevel.ACTIVITY

        return IcebergLevel.NONE

    # ==================== P0-3: Spoofing 检测方法 ====================

    def record_disappeared(self, amount: float) -> None:
        """
        P0-3: 记录订单簿消失量

        当订单簿的可见量减少时调用。
        消失可能是成交，也可能是撤单（spoofing）。

        Args:
            amount: 消失的数量
        """
        if amount > 0:
            self.disappeared_quantity += amount

    def explain_with_trade(self, trade_quantity: float) -> None:
        """
        P0-3: 用实际成交解释消失量

        当有实际成交匹配到此价格层级时调用。

        Args:
            trade_quantity: 实际成交量
        """
        if trade_quantity > 0:
            self.explained_quantity += trade_quantity
            self._update_explanation_ratio()

    def _update_explanation_ratio(self) -> None:
        """
        P0-3: 更新解释比例并判断是否可疑
        """
        cfg = CONFIG_PRICE_LEVEL

        if self.disappeared_quantity > 0:
            self.explanation_ratio = min(
                1.0, self.explained_quantity / self.disappeared_quantity
            )
        else:
            self.explanation_ratio = 1.0

        # 只有在有足够的消失量时才判断
        if self.disappeared_quantity >= cfg['min_quantity_for_spoofing_check']:
            self.is_suspicious = self.explanation_ratio < cfg['spoofing_threshold']
        else:
            self.is_suspicious = False

    # ==================== P1-2: 置信度计算 ====================

    def get_confidence_penalty(self) -> float:
        """
        P0-3: 获取置信度惩罚值 (扣除值)

        基于 explanation_ratio 计算置信度惩罚。
        比例越低，惩罚越大。

        Returns:
            惩罚值 (0.0 - 30.0)，用于从置信度中扣除
        """
        if self.explanation_ratio >= 0.7:
            return 0.0   # 无惩罚
        elif self.explanation_ratio >= 0.5:
            return 10.0  # 轻微惩罚
        elif self.explanation_ratio >= 0.3:
            return 20.0  # 中等惩罚
        else:
            return 30.0  # 严重惩罚

    def get_confidence_multiplier(self) -> float:
        """
        P1-2: 获取置信度乘数

        基于 explanation_ratio 返回置信度乘数。
        用于 _calculate_confidence() 中的惩罚计算。

        Returns:
            乘数 (0.3 - 1.0)
        """
        cfg = CONFIG_PRICE_LEVEL['penalty_tiers']

        if self.explanation_ratio >= cfg['high']['min_ratio']:
            return cfg['high']['multiplier']      # 1.0
        elif self.explanation_ratio >= cfg['medium']['min_ratio']:
            return cfg['medium']['multiplier']    # 0.6
        else:
            return cfg['low']['multiplier']       # 0.3

    def calculate_confidence(self) -> float:
        """
        P1-2: 计算置信度 (含 spoofing 惩罚)

        基础置信度计算 + spoofing 惩罚

        Returns:
            置信度 (0.0 - 95.0)
        """
        cfg = CONFIG_PRICE_LEVEL

        # 基础置信度
        confidence = 50.0

        # 基于强度加分
        if self.intensity >= 10:
            confidence += 20
        elif self.intensity >= 5:
            confidence += 10

        # 基于补单次数加分
        if self.refill_count >= 10:
            confidence += 15
        elif self.refill_count >= 5:
            confidence += 10

        # 基于累计成交加分
        if self.cumulative_filled >= 5000:
            confidence += 15
        elif self.cumulative_filled >= 2000:
            confidence += 10

        # P1-2: 应用 spoofing 惩罚
        multiplier = self.get_confidence_multiplier()
        confidence *= multiplier

        # P1-2: 可疑信号的置信度上限
        if self.is_suspicious:
            confidence = min(confidence, cfg['confidence_cap_suspicious'])

        return min(95.0, confidence)
