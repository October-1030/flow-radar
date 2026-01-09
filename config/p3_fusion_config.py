#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - Phase 2 融合配置

功能：
1. 信号关联配置（时间窗口、价格重叠阈值）
2. 置信度调整参数（共振增强、冲突惩罚）
3. 类型组合奖励配置
4. Bundle 建议阈值
5. 配置验证函数

设计原则：
- 配置外部化（延续 Phase 1 范式）
- 参数可调整（便于优化）
- 类型安全（类型提示）
- 验证完整（启动时检查）

作者：Claude Code
日期：2026-01-09
版本：v2.0（Phase 2）
参考：docs/P3-2_multi_signal_design.md
"""

from typing import Dict, Tuple

# 继承 Phase 1 配置
from config.p3_settings import LEVEL_PRIORITY, TYPE_PRIORITY


# ==================== 信号关联配置 ====================

# 时间窗口（秒）- 在此窗口内的信号可建立关联
SIGNAL_CORRELATION_WINDOW = 300  # 5 分钟

# 价格重叠阈值（百分比）- 价格范围重叠判定
PRICE_OVERLAP_THRESHOLD = 0.001  # 0.1% (例: 价格 100 时，±0.1 视为重叠)

# 价格范围扩展系数（根据信号类型）
PRICE_RANGE_EXPANSION = {
    'iceberg': 0.001,    # 冰山订单 ±0.1%（挂单价格相对稳定）
    'whale': 0.0005,     # 鲸鱼成交 ±0.05%（成交价格精确）
    'liq': 0.002,        # 清算信号 ±0.2%（清算价格波动大）
}


# ==================== 置信度调整参数 ====================

# 同向共振增强（每个同向信号的增强值）
RESONANCE_BOOST_PER_SIGNAL = 5  # 每个同向关联信号 +5

# 共振增强上限
RESONANCE_BOOST_MAX = 25  # 最多 +25（即最多 5 个同向信号生效）

# 反向冲突惩罚（每个反向信号的惩罚值）
CONFLICT_PENALTY_PER_SIGNAL = 5  # 每个反向关联信号 -5

# 冲突惩罚上限
CONFLICT_PENALTY_MAX = 10  # 最多 -10（即最多 2 个反向信号生效）

# 置信度边界
CONFIDENCE_MIN = 0.0     # 最小置信度 0%
CONFIDENCE_MAX = 100.0   # 最大置信度 100%


# ==================== 类型组合奖励 ====================

# 特定类型组合的额外奖励（表示信号可靠性更高）
TYPE_COMBO_BONUS: Dict[Tuple[str, str], float] = {
    # 冰山挂单 + 鲸鱼成交 = 意图+执行确认 (+10)
    ('iceberg', 'whale'): 10.0,
    ('whale', 'iceberg'): 10.0,

    # 冰山挂单 + 清算 = 支撑/阻力位破位 (+15)
    ('iceberg', 'liq'): 15.0,
    ('liq', 'iceberg'): 15.0,

    # 鲸鱼成交 + 清算 = 大资金推动清算 (+20，最高奖励）
    ('whale', 'liq'): 20.0,
    ('liq', 'whale'): 20.0,
}

# 三类型组合特别奖励（冰山+鲸鱼+清算同时出现）
TYPE_TRIPLE_COMBO_BONUS = 30.0  # 三类型齐全 +30


# ==================== Bundle 建议阈值 ====================

# 强烈买入/卖出阈值（加权得分比）
STRONG_BUY_THRESHOLD = 1.5   # weighted_buy / weighted_sell > 1.5
STRONG_SELL_THRESHOLD = 1.5  # weighted_sell / weighted_buy > 1.5

# 类型权重（用于 Bundle 建议计算）
BUNDLE_TYPE_WEIGHTS = {
    'liq': 3,       # 清算权重最高（已发生事件）
    'whale': 2,     # 鲸鱼成交次之（真实资金流）
    'iceberg': 1,   # 冰山挂单权重最低（意图信号）
}

# 级别权重（用于 Bundle 建议计算）
BUNDLE_LEVEL_WEIGHTS = {
    'CRITICAL': 3.0,   # CRITICAL 级别信号权重 x3
    'CONFIRMED': 2.0,  # CONFIRMED 级别信号权重 x2
    'WARNING': 1.5,    # WARNING 级别信号权重 x1.5
    'ACTIVITY': 1.0,   # ACTIVITY 级别信号权重 x1
    'INFO': 0.5,       # INFO 级别信号权重 x0.5
}

# Bundle 建议最小信号数
MIN_SIGNALS_FOR_ADVICE = 1  # 至少 1 个信号才生成建议

# Bundle 建议置信度计算权重
ADVICE_CONFIDENCE_WEIGHT = 0.7  # 70% 权重来自信号置信度
ADVICE_COUNT_WEIGHT = 0.3       # 30% 权重来自信号数量


# ==================== 冲突解决配置 ====================

# 冲突检测时间窗口（与关联窗口相同）
CONFLICT_DETECTION_WINDOW = SIGNAL_CORRELATION_WINDOW

# 冲突检测价格重叠阈值（与关联阈值相同）
CONFLICT_PRICE_THRESHOLD = PRICE_OVERLAP_THRESHOLD

# 冲突解决优先级（继承自 Phase 1）
# 1. 类型优先：liq > whale > iceberg
# 2. 级别优先：CRITICAL > CONFIRMED > WARNING > ACTIVITY > INFO
# 3. 置信度优先：高置信度 > 低置信度

# 同级同类冲突处理
SAME_LEVEL_TYPE_CONFLICT_PENALTY = 10.0  # 同级同类冲突时，双方都 -10


# ==================== 性能优化配置 ====================

# 价格分桶精度（用于加速关联检测）
PRICE_BUCKET_PRECISION = 3  # 保留 3 位小数（例: 0.150 为一个桶）

# 批量处理大小
BATCH_PROCESSING_SIZE = 100  # 每批处理 100 个信号

# 缓存配置
ENABLE_PRICE_RANGE_CACHE = True  # 启用价格范围缓存
ENABLE_PRIORITY_CACHE = True     # 启用优先级缓存


# ==================== 配置验证函数 ====================

def validate_fusion_config() -> bool:
    """
    验证 Phase 2 融合配置的完整性和一致性

    Returns:
        True: 配置有效
        False: 配置无效

    Raises:
        AssertionError: 配置检查失败
    """
    # 检查时间窗口
    assert SIGNAL_CORRELATION_WINDOW > 0, \
        "SIGNAL_CORRELATION_WINDOW 必须 > 0"
    assert SIGNAL_CORRELATION_WINDOW <= 3600, \
        "SIGNAL_CORRELATION_WINDOW 不应超过 1 小时（3600秒）"

    # 检查价格阈值
    assert 0 < PRICE_OVERLAP_THRESHOLD < 0.1, \
        "PRICE_OVERLAP_THRESHOLD 应在 (0, 0.1) 范围内"

    # 检查价格范围扩展系数
    required_types = {'iceberg', 'whale', 'liq'}
    assert set(PRICE_RANGE_EXPANSION.keys()) == required_types, \
        f"PRICE_RANGE_EXPANSION 必须包含类型: {required_types}"

    for ptype, expansion in PRICE_RANGE_EXPANSION.items():
        assert 0 < expansion < 0.1, \
            f"PRICE_RANGE_EXPANSION[{ptype}] 应在 (0, 0.1) 范围内"

    # 检查置信度调整参数
    assert RESONANCE_BOOST_PER_SIGNAL > 0, \
        "RESONANCE_BOOST_PER_SIGNAL 必须 > 0"
    assert RESONANCE_BOOST_MAX > 0, \
        "RESONANCE_BOOST_MAX 必须 > 0"
    assert RESONANCE_BOOST_MAX >= RESONANCE_BOOST_PER_SIGNAL, \
        "RESONANCE_BOOST_MAX 应 >= RESONANCE_BOOST_PER_SIGNAL"

    assert CONFLICT_PENALTY_PER_SIGNAL > 0, \
        "CONFLICT_PENALTY_PER_SIGNAL 必须 > 0"
    assert CONFLICT_PENALTY_MAX > 0, \
        "CONFLICT_PENALTY_MAX 必须 > 0"
    assert CONFLICT_PENALTY_MAX >= CONFLICT_PENALTY_PER_SIGNAL, \
        "CONFLICT_PENALTY_MAX 应 >= CONFLICT_PENALTY_PER_SIGNAL"

    # 检查置信度边界
    assert CONFIDENCE_MIN == 0.0, "CONFIDENCE_MIN 应为 0.0"
    assert CONFIDENCE_MAX == 100.0, "CONFIDENCE_MAX 应为 100.0"

    # 检查类型组合奖励
    for combo, bonus in TYPE_COMBO_BONUS.items():
        assert len(combo) == 2, f"组合 {combo} 必须是 2 元组"
        assert combo[0] in required_types and combo[1] in required_types, \
            f"组合 {combo} 包含未知类型"
        assert bonus > 0, f"组合 {combo} 的奖励必须 > 0"

    assert TYPE_TRIPLE_COMBO_BONUS > 0, \
        "TYPE_TRIPLE_COMBO_BONUS 必须 > 0"

    # 检查 Bundle 阈值
    assert STRONG_BUY_THRESHOLD > 1.0, \
        "STRONG_BUY_THRESHOLD 必须 > 1.0"
    assert STRONG_SELL_THRESHOLD > 1.0, \
        "STRONG_SELL_THRESHOLD 必须 > 1.0"

    # 检查类型权重
    assert set(BUNDLE_TYPE_WEIGHTS.keys()) == required_types, \
        f"BUNDLE_TYPE_WEIGHTS 必须包含类型: {required_types}"

    for weight in BUNDLE_TYPE_WEIGHTS.values():
        assert weight > 0, "BUNDLE_TYPE_WEIGHTS 的值必须 > 0"

    # 检查级别权重
    required_levels = set(LEVEL_PRIORITY.keys())
    assert set(BUNDLE_LEVEL_WEIGHTS.keys()) == required_levels, \
        f"BUNDLE_LEVEL_WEIGHTS 必须包含级别: {required_levels}"

    for weight in BUNDLE_LEVEL_WEIGHTS.values():
        assert weight > 0, "BUNDLE_LEVEL_WEIGHTS 的值必须 > 0"

    # 检查建议参数
    assert MIN_SIGNALS_FOR_ADVICE >= 1, \
        "MIN_SIGNALS_FOR_ADVICE 必须 >= 1"

    assert 0 < ADVICE_CONFIDENCE_WEIGHT < 1, \
        "ADVICE_CONFIDENCE_WEIGHT 应在 (0, 1) 范围内"
    assert 0 < ADVICE_COUNT_WEIGHT < 1, \
        "ADVICE_COUNT_WEIGHT 应在 (0, 1) 范围内"
    assert abs(ADVICE_CONFIDENCE_WEIGHT + ADVICE_COUNT_WEIGHT - 1.0) < 0.001, \
        "ADVICE_CONFIDENCE_WEIGHT + ADVICE_COUNT_WEIGHT 应 = 1.0"

    # 检查冲突解决配置
    assert SAME_LEVEL_TYPE_CONFLICT_PENALTY > 0, \
        "SAME_LEVEL_TYPE_CONFLICT_PENALTY 必须 > 0"

    # 检查性能优化配置
    assert PRICE_BUCKET_PRECISION > 0, \
        "PRICE_BUCKET_PRECISION 必须 > 0"
    assert BATCH_PROCESSING_SIZE > 0, \
        "BATCH_PROCESSING_SIZE 必须 > 0"

    return True


# ==================== 辅助函数 ====================

def get_price_expansion(signal_type: str) -> float:
    """
    获取指定信号类型的价格范围扩展系数

    Args:
        signal_type: 信号类型（iceberg/whale/liq）

    Returns:
        价格扩展系数

    Example:
        >>> get_price_expansion('iceberg')
        0.001
    """
    return PRICE_RANGE_EXPANSION.get(signal_type, 0.001)


def get_type_combo_bonus(type1: str, type2: str) -> float:
    """
    获取两个信号类型组合的奖励值

    Args:
        type1: 信号类型 1
        type2: 信号类型 2

    Returns:
        组合奖励值，如果无匹配则返回 0

    Example:
        >>> get_type_combo_bonus('iceberg', 'whale')
        10.0
        >>> get_type_combo_bonus('iceberg', 'iceberg')
        0.0
    """
    if type1 == type2:
        return 0.0

    combo = (type1, type2)
    return TYPE_COMBO_BONUS.get(combo, 0.0)


def get_bundle_type_weight(signal_type: str) -> int:
    """
    获取信号类型的 Bundle 权重

    Args:
        signal_type: 信号类型

    Returns:
        类型权重

    Example:
        >>> get_bundle_type_weight('liq')
        3
    """
    return BUNDLE_TYPE_WEIGHTS.get(signal_type, 1)


def get_bundle_level_weight(level: str) -> float:
    """
    获取信号级别的 Bundle 权重

    Args:
        level: 信号级别

    Returns:
        级别权重

    Example:
        >>> get_bundle_level_weight('CRITICAL')
        3.0
    """
    return BUNDLE_LEVEL_WEIGHTS.get(level, 1.0)


# ==================== 模块初始化验证 ====================

# 导入时自动验证配置
try:
    validate_fusion_config()
except AssertionError as e:
    import sys
    print(f"❌ P3-2 Phase 2 配置验证失败: {e}", file=sys.stderr)
    sys.exit(1)
