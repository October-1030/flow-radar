#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - 优先级配置

功能：
1. 定义信号级别优先级（LEVEL_PRIORITY）
2. 定义信号类型优先级（TYPE_PRIORITY）
3. 提供优先级比较工具函数

设计原则：
- 配置外部化（不硬编码在业务逻辑中）
- 优先级排序规则：(level_rank, type_rank) - level 优先于 type
- 数值越小优先级越高（1 最高，5 最低）

作者：Claude Code
日期：2026-01-08
版本：v1.0（三方会谈第二十二轮共识 - 工作 2.3）
参考：docs/P3-2_multi_signal_design.md v1.2
"""

from typing import Tuple, Optional


# ==================== 信号级别优先级 ====================

LEVEL_PRIORITY = {
    'CRITICAL': 1,   # 最高优先 - 严重事件（大额清算、连锁反应）
    'CONFIRMED': 2,  # 已确认信号（多次验证、置信度高）
    'WARNING': 3,    # 警告级别（中等风险、需关注）
    'ACTIVITY': 4,   # 观察级别（单次出现、待确认）
    'INFO': 5,       # 最低优先 - 信息记录（仅统计、不告警）
}

"""
级别说明：

CRITICAL (1) - 严重事件
    定义：市场发生重大风险事件，需立即关注
    触发条件：
        - 大额清算（单笔 > 100万 USDT）
        - 连锁清算（短时间内多笔清算）
        - 鲸鱼异常行为（与冰山信号反向共振）
    告警策略：立即推送，不降噪

CONFIRMED (2) - 已确认信号
    定义：经过多次验证的高置信度信号
    触发条件：
        - 冰山订单：refill_count ≥ 3, confidence ≥ 65%
        - 鲸鱼成交：5分钟内多笔大额成交
        - 清算聚合：中等规模清算
    告警策略：30分钟节流，可合并同类信号

WARNING (3) - 警告级别
    定义：中等风险事件，需要关注但不紧急
    触发条件：
        - 单笔清算（10万-100万 USDT）
        - 价格异常波动
        - 疑似洗盘行为
    告警策略：1小时节流，可降噪

ACTIVITY (4) - 观察级别
    定义：单次出现的行为，待进一步确认
    触发条件：
        - 冰山订单：refill_count = 1-2
        - 单笔大额成交（但未聚合）
        - 订单簿异常
    告警策略：不主动推送，仅记录

INFO (5) - 信息级别
    定义：纯统计信息，不触发告警
    触发条件：
        - 市场状态变化记录
        - CVD 统计
        - 流量统计
    告警策略：不推送，仅日志记录
"""


# ==================== 信号类型优先级 ====================

TYPE_PRIORITY = {
    'liq': 1,        # 清算 - 市场风险最高（已发生强平）
    'whale': 2,      # 鲸鱼成交 - 真实资金流（已成交订单）
    'iceberg': 3,    # 冰山订单 - 需验证确认（挂单意图）
}

"""
类型说明：

liq (1) - 清算信号
    定义：已发生的强制平仓事件
    风险等级：最高（已经发生损失）
    市场影响：
        - 直接影响价格（市价单吃掉流动性）
        - 可能触发连锁清算
        - 情绪指标（多空力量失衡）
    优先级理由：
        清算 > 成交 > 挂单
        （已发生 > 正在发生 > 可能发生）

whale (2) - 鲸鱼成交
    定义：大额市价单成交记录
    风险等级：高（真实资金流动）
    市场影响：
        - 直接消耗流动性
        - 短期价格冲击
        - 大户意图确认（已下手）
    优先级理由：
        成交是确定事件，比挂单更可靠

iceberg (3) - 冰山订单
    定义：限价单挂单行为（可能撤单）
    风险等级：中（意图信号）
    市场影响：
        - 可能影响价格（如果不撤单）
        - 支撑/阻力位参考
        - 大户意图（但可能是假象）
    优先级理由：
        挂单可以撤销，不如成交可靠
        但仍有参考价值（尤其是 CONFIRMED 级别）
"""


# ==================== 默认配置参数 ====================

# 置信度阈值
CONFIDENCE_THRESHOLDS = {
    'CRITICAL': 90.0,    # CRITICAL 级别需要 90%+ 置信度
    'CONFIRMED': 65.0,   # CONFIRMED 级别需要 65%+ 置信度
    'WARNING': 50.0,     # WARNING 级别需要 50%+ 置信度
    'ACTIVITY': 30.0,    # ACTIVITY 级别需要 30%+ 置信度
}

# 降噪时间窗口（秒）
DEDUP_WINDOWS = {
    'CRITICAL': 600,     # CRITICAL: 10 分钟内去重
    'CONFIRMED': 1800,   # CONFIRMED: 30 分钟内去重
    'WARNING': 3600,     # WARNING: 1 小时内去重
    'ACTIVITY': 7200,    # ACTIVITY: 2 小时内去重
}

# 告警节流配置（秒）
ALERT_THROTTLE = {
    'CRITICAL': 0,       # CRITICAL: 不节流，立即推送
    'CONFIRMED': 1800,   # CONFIRMED: 30 分钟节流
    'WARNING': 3600,     # WARNING: 1 小时节流
    'ACTIVITY': 0,       # ACTIVITY: 不推送告警
}

# 信号关联时间窗口（秒）
SIGNAL_CORRELATION_WINDOW = 300  # 5 分钟内的信号可建立关联

# 价格分桶精度
PRICE_BUCKET_PRECISION = 4  # 价格四舍五入到 4 位小数


# ==================== 优先级计算工具 ====================

def get_signal_priority(level: str, signal_type: str) -> Tuple[int, int]:
    """
    获取信号优先级元组

    Args:
        level: 信号级别（CRITICAL/CONFIRMED/WARNING/ACTIVITY/INFO）
        signal_type: 信号类型（liq/whale/iceberg）

    Returns:
        (level_rank, type_rank) 元组，用于排序
        数值越小优先级越高

    Example:
        >>> get_signal_priority('CRITICAL', 'liq')
        (1, 1)  # 最高优先级
        >>> get_signal_priority('ACTIVITY', 'iceberg')
        (4, 3)  # 较低优先级
    """
    level_rank = LEVEL_PRIORITY.get(level, 999)      # 未知级别排最后
    type_rank = TYPE_PRIORITY.get(signal_type, 999)   # 未知类型排最后

    return (level_rank, type_rank)


def compare_signals(signal1: dict, signal2: dict) -> int:
    """
    比较两个信号的优先级

    Args:
        signal1: 信号1（需包含 level 和 signal_type/type 字段）
        signal2: 信号2（需包含 level 和 signal_type/type 字段）

    Returns:
        -1: signal1 优先级高于 signal2
         0: 优先级相同
         1: signal1 优先级低于 signal2

    Example:
        >>> s1 = {'level': 'CRITICAL', 'signal_type': 'liq'}
        >>> s2 = {'level': 'CONFIRMED', 'signal_type': 'whale'}
        >>> compare_signals(s1, s2)
        -1  # s1 优先级更高
    """
    level1 = signal1.get('level', 'INFO')
    type1 = signal1.get('signal_type') or signal1.get('type', 'iceberg')

    level2 = signal2.get('level', 'INFO')
    type2 = signal2.get('signal_type') or signal2.get('type', 'iceberg')

    priority1 = get_signal_priority(level1, type1)
    priority2 = get_signal_priority(level2, type2)

    if priority1 < priority2:
        return -1
    elif priority1 > priority2:
        return 1
    else:
        return 0


def sort_signals_by_priority(signals: list) -> list:
    """
    按优先级排序信号列表（降序，优先级高的在前）

    Args:
        signals: 信号列表（每个信号需包含 level 和 signal_type/type 字段）

    Returns:
        排序后的信号列表（原地排序）

    Example:
        >>> signals = [
        ...     {'level': 'ACTIVITY', 'signal_type': 'iceberg'},
        ...     {'level': 'CRITICAL', 'signal_type': 'liq'},
        ...     {'level': 'CONFIRMED', 'signal_type': 'whale'},
        ... ]
        >>> sorted_signals = sort_signals_by_priority(signals)
        >>> sorted_signals[0]['level']
        'CRITICAL'
    """
    def _get_sort_key(signal):
        # 兼容字典和对象
        if isinstance(signal, dict):
            level = signal.get('level', 'INFO')
            signal_type = signal.get('signal_type') or signal.get('type', 'iceberg')
        else:
            # 对象（dataclass 或自定义类）
            level = getattr(signal, 'level', 'INFO')
            signal_type = getattr(signal, 'signal_type', None) or getattr(signal, 'type', 'iceberg')
        return get_signal_priority(level, signal_type)

    return sorted(signals, key=_get_sort_key)


def is_high_priority(level: str, signal_type: str) -> bool:
    """
    判断信号是否为高优先级（CRITICAL 级别或清算信号）

    Args:
        level: 信号级别
        signal_type: 信号类型

    Returns:
        True: 高优先级信号
        False: 普通优先级信号

    Example:
        >>> is_high_priority('CRITICAL', 'liq')
        True
        >>> is_high_priority('ACTIVITY', 'iceberg')
        False
    """
    return level == 'CRITICAL' or signal_type == 'liq'


def get_dedup_window(level: str) -> int:
    """
    获取指定级别的降噪时间窗口

    Args:
        level: 信号级别

    Returns:
        降噪时间窗口（秒）

    Example:
        >>> get_dedup_window('CONFIRMED')
        1800  # 30 分钟
    """
    return DEDUP_WINDOWS.get(level, 3600)  # 默认 1 小时


def get_alert_throttle(level: str) -> int:
    """
    获取指定级别的告警节流时间

    Args:
        level: 信号级别

    Returns:
        告警节流时间（秒），0 表示不节流

    Example:
        >>> get_alert_throttle('CRITICAL')
        0  # 立即推送
        >>> get_alert_throttle('CONFIRMED')
        1800  # 30 分钟节流
    """
    return ALERT_THROTTLE.get(level, 3600)  # 默认 1 小时


def should_alert(level: str) -> bool:
    """
    判断指定级别是否应该推送告警

    Args:
        level: 信号级别

    Returns:
        True: 应该推送告警
        False: 不推送告警（仅记录）

    Example:
        >>> should_alert('CRITICAL')
        True
        >>> should_alert('ACTIVITY')
        False
    """
    return level in ('CRITICAL', 'CONFIRMED', 'WARNING')


# ==================== 配置验证 ====================

def validate_config() -> bool:
    """
    验证配置完整性和一致性

    Returns:
        True: 配置有效
        False: 配置无效

    Raises:
        AssertionError: 配置检查失败
    """
    # 检查 LEVEL_PRIORITY 完整性
    required_levels = {'CRITICAL', 'CONFIRMED', 'WARNING', 'ACTIVITY', 'INFO'}
    assert set(LEVEL_PRIORITY.keys()) == required_levels, \
        f"LEVEL_PRIORITY 缺少必需级别: {required_levels - set(LEVEL_PRIORITY.keys())}"

    # 检查 TYPE_PRIORITY 完整性
    required_types = {'liq', 'whale', 'iceberg'}
    assert set(TYPE_PRIORITY.keys()) == required_types, \
        f"TYPE_PRIORITY 缺少必需类型: {required_types - set(TYPE_PRIORITY.keys())}"

    # 检查优先级数值唯一性
    level_values = list(LEVEL_PRIORITY.values())
    assert len(level_values) == len(set(level_values)), \
        "LEVEL_PRIORITY 数值不唯一"

    type_values = list(TYPE_PRIORITY.values())
    assert len(type_values) == len(set(type_values)), \
        "TYPE_PRIORITY 数值不唯一"

    # 检查优先级顺序（数值递增）
    assert level_values == sorted(level_values), \
        "LEVEL_PRIORITY 数值顺序错误"

    assert type_values == sorted(type_values), \
        "TYPE_PRIORITY 数值顺序错误"

    # 检查置信度阈值配置
    for level in CONFIDENCE_THRESHOLDS:
        assert level in LEVEL_PRIORITY, \
            f"CONFIDENCE_THRESHOLDS 中的 {level} 不在 LEVEL_PRIORITY 中"

    # 检查降噪窗口配置
    for level in DEDUP_WINDOWS:
        assert level in LEVEL_PRIORITY, \
            f"DEDUP_WINDOWS 中的 {level} 不在 LEVEL_PRIORITY 中"

    # 检查告警节流配置
    for level in ALERT_THROTTLE:
        assert level in LEVEL_PRIORITY, \
            f"ALERT_THROTTLE 中的 {level} 不在 LEVEL_PRIORITY 中"

    return True


# ==================== 模块初始化验证 ====================

# 导入时自动验证配置
try:
    validate_config()
except AssertionError as e:
    import sys
    print(f"❌ P3 配置验证失败: {e}", file=sys.stderr)
    sys.exit(1)
