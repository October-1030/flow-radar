"""
Flow Radar - 优先级配置外部化
Priority Configuration for Signal Ranking and Sorting

本模块定义信号优先级映射和排序工具，用于多信号融合系统的排序和筛选。

设计原则：
    - 配置外部化（可热更新，无需重启）
    - 数值越小优先级越高（1 = 最高优先，99 = 降级/未知）
    - 优先级排序：level_rank > type_rank > timestamp（层次化）
    - UI 层应单独处理 BAN 状态（无视 rank 进行置顶）

优先级调整策略：
    - 根据实战效果调整 rank 数值
    - 如：若 K神信号 频繁误报，可调低其 type_rank（增大数值）
    - 如：若 清算信号 需更高优先，保持 type_rank = 1

作者: Claude Code
日期: 2026-01-10
版本: v2.0 (工作编号 2.3 - 优先级系统重构)
参考: core/signal_schema.py (SignalLevel, SignalType 枚举)
"""

from typing import Tuple, Dict, Any, Union
from enum import Enum


# ==================== 优先级映射定义 ====================

# 信号级别优先级（Level Rank）
# 数值越小优先级越高，99 表示未知/降级
LEVEL_RANK: Dict[str, int] = {
    "CRITICAL": 1,    # 最高优先 - 临界事件（大额清算、连锁风险）
    "CONFIRMED": 2,   # 已确认 - 高置信度信号（多次验证、强度高）
    "WARNING": 3,     # 警告级 - 中等风险（单笔清算、价格异常）
    "ACTIVITY": 4,    # 观察级 - 低置信度（单次出现、待确认）
}

# 默认 Level Rank（用于未知级别的降级）
DEFAULT_LEVEL_RANK: int = 99


# 信号类型优先级（Type Rank）
# 数值越小优先级越高，99 表示未知/降级
TYPE_RANK: Dict[str, int] = {
    "liq": 1,         # 清算 - 最高（已发生的强制平仓事件）
    "whale": 2,       # 大单 - 已确认的市场行为（真实资金流）
    "iceberg": 3,     # 冰山 - 推测性检测（挂单意图，可能撤单）
    "kgod": 4,        # K神 - 环境过滤器（技术指标信号，可调整）
}

# 默认 Type Rank（用于未知类型的降级）
DEFAULT_TYPE_RANK: int = 99


# ==================== 优先级说明文档 ====================

LEVEL_PRIORITY_DOC = """
信号级别优先级说明（Level Rank）

CRITICAL (1) - 临界级事件
    定义：市场发生重大风险事件，需立即响应
    触发条件：
        - 大额清算（单笔 > 100万 USDT）
        - 连锁清算（短时间内多笔强平）
        - 价格剧烈波动（触及熔断或极端行情）
    排序优先级：最高
    告警策略：立即推送，不节流

CONFIRMED (2) - 已确认信号
    定义：经过多次验证的高置信度信号
    触发条件：
        - 冰山订单：refill_count ≥ 3, confidence ≥ 65%
        - 巨鲸成交：5分钟内多笔大额成交聚合
        - K神信号：z-score ≥ 2.0 + MACD + 订单流确认
    排序优先级：高
    告警策略：30分钟节流，可合并同类信号

WARNING (3) - 警告级信号
    定义：中等风险事件，需要关注但不紧急
    触发条件：
        - 单笔清算（10万-100万 USDT）
        - 价格异常波动（未触发熔断）
        - 订单簿异常（疑似洗盘）
    排序优先级：中等
    告警策略：1小时节流，可降噪

ACTIVITY (4) - 观察级信号
    定义：单次出现的行为，待进一步确认
    触发条件：
        - 冰山订单：refill_count = 1-2（初次检测）
        - 单笔大额成交（未聚合）
        - K神预警信号：z-score < 1.8
    排序优先级：最低
    告警策略：不主动推送，仅记录
"""


TYPE_PRIORITY_DOC = """
信号类型优先级说明（Type Rank）

liq (1) - 清算信号
    定义：已发生的强制平仓事件（市场确定性事件）
    优先级理由：
        - 清算是已发生的损失事件（不可撤销）
        - 直接影响价格（市价单吃掉流动性）
        - 可能触发连锁清算（系统性风险）
    市场影响：立即、直接、不可逆
    排序优先级：最高

whale (2) - 巨鲸成交信号
    定义：大额市价单成交记录（真实资金流动）
    优先级理由：
        - 成交是已确认事件（不可撤销）
        - 直接消耗流动性（短期价格冲击）
        - 大户意图已执行（不是假象）
    市场影响：立即、直接、可持续
    排序优先级：高

iceberg (3) - 冰山订单信号
    定义：限价单挂单行为（意图信号，可能撤单）
    优先级理由：
        - 挂单可以撤销（不一定成交）
        - 影响价格的不确定性高
        - 大户意图（但可能是诱多/诱空）
    市场影响：间接、推测性、可撤销
    排序优先级：中等

kgod (4) - K神战法信号
    定义：技术指标信号（环境过滤器，辅助判断）
    优先级理由：
        - 基于历史数据的统计信号（滞后性）
        - 不直接反映资金流（间接指标）
        - 作为环境过滤器使用（辅助决策）
    市场影响：间接、统计性、辅助性
    排序优先级：最低（可根据实战效果调整）

注意：
    - K神信号的 type_rank 可根据实战效果调整
    - 如频繁误报，可降低其优先级（增大 rank 数值）
    - 如与其他信号配合效果好，可保持当前 rank
"""


# ==================== 优先级计算工具 ====================

def get_sort_key(signal: Union[Dict[str, Any], Any]) -> Tuple[int, int, float]:
    """
    获取信号的排序键（Sort Key）

    排序规则：
        1. 优先按 level_rank 排序（数值越小越靠前）
        2. 其次按 type_rank 排序（数值越小越靠前）
        3. 最后按 timestamp 排序（时间越新越靠前）

    参数：
        signal: 信号对象（支持字典或 SignalEvent 对象）
                需包含字段：level, signal_type (或 type), ts

    返回：
        (level_rank, type_rank, -ts) 元组
        - level_rank: 级别优先级（1-4, 99=未知）
        - type_rank: 类型优先级（1-4, 99=未知）
        - -ts: 负时间戳（越新越小，排序时越靠前）

    示例：
        >>> signal = {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758400.0}
        >>> get_sort_key(signal)
        (1, 1, -1704758400.0)  # 最高优先级

        >>> signal2 = {"level": "ACTIVITY", "signal_type": "iceberg", "ts": 1704758500.0}
        >>> get_sort_key(signal2)
        (4, 3, -1704758500.0)  # 较低优先级

    用法：
        >>> signals = [signal1, signal2, signal3]
        >>> sorted_signals = sorted(signals, key=get_sort_key)  # 优先级排序
    """
    # 兼容字典和对象
    if isinstance(signal, dict):
        level = signal.get("level", "ACTIVITY")
        signal_type = signal.get("signal_type") or signal.get("type", "iceberg")
        ts = signal.get("ts", 0.0)
    else:
        # SignalEvent 对象或其他类（支持 .level, .signal_type, .ts 属性）
        level = getattr(signal, "level", "ACTIVITY")
        signal_type = getattr(signal, "signal_type", None) or getattr(signal, "type", "iceberg")
        ts = getattr(signal, "ts", 0.0)

    # 处理枚举类型（如 SignalLevel.CRITICAL 或 SignalType.LIQ）
    if hasattr(level, "value"):
        level = level.value
    if hasattr(signal_type, "value"):
        signal_type = signal_type.value

    # 获取优先级数值（使用 .get(x, 99) 处理未知类型）
    level_rank = LEVEL_RANK.get(level, DEFAULT_LEVEL_RANK)
    type_rank = TYPE_RANK.get(signal_type, DEFAULT_TYPE_RANK)

    # 返回排序键（负时间戳：越新越小）
    return (level_rank, type_rank, -ts)


def compare_signals(signal_a: Union[Dict[str, Any], Any],
                     signal_b: Union[Dict[str, Any], Any]) -> int:
    """
    比较两个信号的优先级

    基于 get_sort_key 的包装函数，符合 Python 比较函数规范。

    参数：
        signal_a: 信号 A
        signal_b: 信号 B

    返回：
        -1: signal_a 优先级高于 signal_b
         0: 优先级相同
        +1: signal_a 优先级低于 signal_b

    示例：
        >>> s1 = {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758400.0}
        >>> s2 = {"level": "CONFIRMED", "signal_type": "whale", "ts": 1704758500.0}
        >>> compare_signals(s1, s2)
        -1  # s1 优先级更高

        >>> s3 = {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758600.0}
        >>> compare_signals(s1, s3)
        1  # s3 更新（ts 更大），优先级更高

    注意：
        - 此函数可用于 sorted(signals, key=functools.cmp_to_key(compare_signals))
        - 但推荐直接使用 get_sort_key: sorted(signals, key=get_sort_key)
    """
    key_a = get_sort_key(signal_a)
    key_b = get_sort_key(signal_b)

    if key_a < key_b:
        return -1
    elif key_a > key_b:
        return 1
    else:
        return 0


def get_level_rank(level: Union[str, Enum]) -> int:
    """
    获取信号级别的优先级数值

    参数：
        level: 信号级别（字符串或枚举）

    返回：
        优先级数值（1-4, 99=未知）

    示例：
        >>> get_level_rank("CRITICAL")
        1
        >>> get_level_rank("UNKNOWN_LEVEL")
        99
    """
    if hasattr(level, "value"):
        level = level.value
    return LEVEL_RANK.get(level, DEFAULT_LEVEL_RANK)


def get_type_rank(signal_type: Union[str, Enum]) -> int:
    """
    获取信号类型的优先级数值

    参数：
        signal_type: 信号类型（字符串或枚举）

    返回：
        优先级数值（1-4, 99=未知）

    示例：
        >>> get_type_rank("liq")
        1
        >>> get_type_rank("unknown_type")
        99
    """
    if hasattr(signal_type, "value"):
        signal_type = signal_type.value
    return TYPE_RANK.get(signal_type, DEFAULT_TYPE_RANK)


# ==================== 优先级配置验证 ====================

def validate_priority_config() -> bool:
    """
    验证优先级配置的完整性和一致性

    校验内容：
        1. LEVEL_RANK 包含所有必需级别（CRITICAL/CONFIRMED/WARNING/ACTIVITY）
        2. TYPE_RANK 包含所有必需类型（liq/whale/iceberg/kgod）
        3. 优先级数值唯一性（无重复 rank）
        4. 优先级数值递增（符合语义顺序）

    返回：
        True: 配置有效

    异常：
        AssertionError: 配置验证失败
    """
    # 1. 检查 LEVEL_RANK 完整性
    required_levels = {"CRITICAL", "CONFIRMED", "WARNING", "ACTIVITY"}
    actual_levels = set(LEVEL_RANK.keys())
    assert required_levels == actual_levels, (
        f"LEVEL_RANK 缺少必需级别: {required_levels - actual_levels} "
        f"或包含额外级别: {actual_levels - required_levels}"
    )

    # 2. 检查 TYPE_RANK 完整性
    required_types = {"liq", "whale", "iceberg", "kgod"}
    actual_types = set(TYPE_RANK.keys())
    assert required_types == actual_types, (
        f"TYPE_RANK 缺少必需类型: {required_types - actual_types} "
        f"或包含额外类型: {actual_types - required_types}"
    )

    # 3. 检查优先级数值唯一性
    level_values = list(LEVEL_RANK.values())
    assert len(level_values) == len(set(level_values)), (
        "LEVEL_RANK 数值不唯一，存在重复 rank"
    )

    type_values = list(TYPE_RANK.values())
    assert len(type_values) == len(set(type_values)), (
        "TYPE_RANK 数值不唯一，存在重复 rank"
    )

    # 4. 检查优先级数值递增（按语义顺序）
    expected_level_order = ["CRITICAL", "CONFIRMED", "WARNING", "ACTIVITY"]
    level_ranks = [LEVEL_RANK[level] for level in expected_level_order]
    assert level_ranks == sorted(level_ranks), (
        f"LEVEL_RANK 数值顺序错误，应为递增序列: {level_ranks}"
    )

    expected_type_order = ["liq", "whale", "iceberg", "kgod"]
    type_ranks = [TYPE_RANK[t] for t in expected_type_order]
    assert type_ranks == sorted(type_ranks), (
        f"TYPE_RANK 数值顺序错误，应为递增序列: {type_ranks}"
    )

    # 5. 检查默认值合理性
    assert DEFAULT_LEVEL_RANK > max(LEVEL_RANK.values()), (
        f"DEFAULT_LEVEL_RANK ({DEFAULT_LEVEL_RANK}) 应大于所有已定义的 level_rank"
    )
    assert DEFAULT_TYPE_RANK > max(TYPE_RANK.values()), (
        f"DEFAULT_TYPE_RANK ({DEFAULT_TYPE_RANK}) 应大于所有已定义的 type_rank"
    )

    return True


# ==================== 使用示例 ====================

def _example_usage():
    """优先级配置使用示例（供文档参考）"""
    print("=" * 70)
    print("优先级配置使用示例".center(70))
    print("=" * 70)

    # 示例 1：创建测试信号
    signals = [
        {"level": "ACTIVITY", "signal_type": "iceberg", "ts": 1704758400.0,
         "key": "iceberg:DOGE/USDT:BUY:ACTIVITY:price_0.15"},
        {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758500.0,
         "key": "liq:BTC/USDT:SELL:CRITICAL:price_42000"},
        {"level": "CONFIRMED", "signal_type": "whale", "ts": 1704758600.0,
         "key": "whale:ETH/USDT:BUY:CONFIRMED:price_2200"},
        {"level": "CONFIRMED", "signal_type": "kgod", "ts": 1704758700.0,
         "key": "kgod:DOGE/USDT:BUY:CONFIRMED:time_08:30"},
        {"level": "CRITICAL", "signal_type": "liq", "ts": 1704758800.0,
         "key": "liq:BTC/USDT:SELL:CRITICAL:price_41900"},
    ]

    print("\n原始信号列表：")
    for i, sig in enumerate(signals, 1):
        print(f"  {i}. [{sig['level']:9}] {sig['signal_type']:8} @ ts={sig['ts']}")

    # 示例 2：使用 get_sort_key 排序
    sorted_signals = sorted(signals, key=get_sort_key)

    print("\n排序后（按优先级）：")
    for i, sig in enumerate(sorted_signals, 1):
        level_rank, type_rank, neg_ts = get_sort_key(sig)
        print(f"  {i}. [{sig['level']:9}] {sig['signal_type']:8} "
              f"| rank=({level_rank}, {type_rank}) | ts={sig['ts']}")

    # 示例 3：使用 compare_signals 比较
    print("\n信号优先级比较：")
    sig1 = signals[0]  # ACTIVITY + iceberg
    sig2 = signals[1]  # CRITICAL + liq
    result = compare_signals(sig1, sig2)
    print(f"  compare({sig1['level']}/{sig1['signal_type']}, "
          f"{sig2['level']}/{sig2['signal_type']}) = {result}")
    print(f"  解释: {'sig2 优先级更高' if result > 0 else 'sig1 优先级更高'}")

    # 示例 4：获取单个信号的 rank
    print("\n单个信号 rank 查询：")
    for sig in signals[:3]:
        level_rank = get_level_rank(sig['level'])
        type_rank = get_type_rank(sig['signal_type'])
        print(f"  {sig['level']:9} / {sig['signal_type']:8} "
              f"-> level_rank={level_rank}, type_rank={type_rank}")

    # 示例 5：验证配置
    print("\n配置验证：")
    try:
        validate_priority_config()
        print("  ✅ 配置验证通过")
    except AssertionError as e:
        print(f"  ❌ 配置验证失败: {e}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # 手动运行配置验证（不在 import 时执行）
    print("=" * 70)
    print("P3 优先级配置 - 手动验证".center(70))
    print("=" * 70)

    try:
        validate_priority_config()
        print("\n✅ 配置验证通过")
        print("\n配置摘要：")
        print(f"  - Level Rank: {len(LEVEL_RANK)} 个级别")
        print(f"  - Type Rank: {len(TYPE_RANK)} 个类型")
        print(f"  - 默认降级: level={DEFAULT_LEVEL_RANK}, type={DEFAULT_TYPE_RANK}")
    except AssertionError as e:
        print(f"\n❌ 配置验证失败: {e}")
        import sys
        sys.exit(1)

    # 运行使用示例
    print("\n" + "=" * 70)
    _example_usage()
