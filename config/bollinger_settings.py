"""
布林带×订单流环境过滤器 - 配置参数
Bollinger Regime Filter Configuration

第三十四轮三方共识
设计原则:
- 所有阈值外部化，禁止硬编码
- 配置参数清晰命名，便于回测调优
- 遵循 GPT + Gemini 三方共识的参数定义

作者: Claude Code
日期: 2026-01-10
版本: v2.0 (第三十四轮)
"""

# ==================== 布林带基础参数 ====================

# 布林带计算参数（复用 RollingBB）
BOLLINGER_PERIOD = 20  # 周期
BOLLINGER_STD_DEV = 2.0  # 标准差倍数


# ==================== 环境状态识别参数 ====================

# 带宽阈值（用于 SQUEEZE / EXPANSION 判定）
BANDWIDTH_SQUEEZE_THRESHOLD = 0.015  # 1.5% - 带宽收口判定（低于此值为 SQUEEZE）
BANDWIDTH_EXPANSION_THRESHOLD = 0.035  # 3.5% - 带宽扩张判定（高于此值为 EXPANSION）

# 触轨判定缓冲区（状态平滑，防止抖动）
TOUCH_BUFFER = 0.0002  # 0.02% - 价格在 [upper - buffer, upper] 视为 UPPER_TOUCH
                        #         价格在 [lower, lower + buffer] 视为 LOWER_TOUCH

# 走轨判定参数
WALKBAND_MIN_ACCEPTANCE_TIME = 20.0  # 秒 - 最小带外停留时间才认定为 WALKING_BAND


# ==================== acceptance_time 参数（核心机制）====================

# acceptance_time 定义：价格在布林带外"连续"停留的累计秒数

# 阈值
ACCEPTANCE_TIME_WARNING = 30.0  # 秒 - 预警阈值（风险开始升高）
ACCEPTANCE_TIME_BAN = 60.0  # 秒 - 封禁阈值（强走轨 BAN 的第一条件）

# 重置条件
RESET_GRACE_PERIOD = 3.0  # 秒 - 回到带内后需保持此时间才重置 acceptance_time
                           # 防止短暂回调立即重置计时器

# 强走轨 BAN 双条件（两个条件必须同时满足）
# 条件 1: acceptance_time > ACCEPTANCE_TIME_BAN（60秒）
# 条件 2: 动力确认（以下任一满足）：
#   - Delta 加速（delta_slope > DELTA_SLOPE_THRESHOLD）
#   - 扫单确认（sweep_score > SWEEP_SCORE_THRESHOLD）
#   - 失衡持续（imbalance > IMBALANCE_THRESHOLD 持续 3 个周期）


# ==================== 订单流共振参数 ====================

# 失衡度阈值
IMBALANCE_THRESHOLD = 0.6  # 买卖失衡度阈值（abs > 0.6 为显著失衡）
IMBALANCE_STRONG_THRESHOLD = 0.75  # 强失衡阈值（用于高置信度场景）

# 吸收量阈值
ABSORPTION_SCORE_THRESHOLD = 2.5  # 吸收强度阈值（> 2.5 为显著吸收）

# 扫单量阈值
SWEEP_SCORE_THRESHOLD = 2.0  # 扫单强度阈值（> 2.0 为显著扫单）

# 冰山检测阈值
ICEBERG_INTENSITY_THRESHOLD = 2.0  # 冰山强度阈值（> 2.0 为显著冰山活动）

# Delta 斜率阈值（用于动力确认）
DELTA_SLOPE_THRESHOLD = 0.3  # Delta 加速度阈值（绝对值 > 0.3 为加速）


# ==================== 共振场景置信度增强参数 ====================

# 置信度提升系数（使用乘法增强）
# 公式: new_confidence = min(100, base_confidence * (1 + boost))

BOOST_ABSORPTION_REVERSAL = 0.15  # +15% - 吸收型回归（场景 1）
BOOST_IMBALANCE_REVERSAL = 0.20  # +20% - 失衡确认回归（场景 2）
BOOST_ICEBERG_DEFENSE = 0.25  # +25% - 冰山护盘回归（场景 3，最高）

# 置信度上限
MAX_CONFIDENCE = 100.0  # 最终置信度不超过 100


# ==================== KGodRadar 集成参数 ====================

# 增强阶段控制（仅在这些阶段应用置信度加成）
BOOST_ALLOWED_STAGES = ["EARLY_CONFIRM", "KGOD_CONFIRM"]
# PRE_ALERT 阶段不加分

# 冲突处理优先级
BAN_OVERRIDES_BOOST = True  # BAN 优先于 boost
# 即：走轨风险高时，即使检测到共振，也忽略增强，优先 BAN


# ==================== 状态平滑参数 ====================

# 防止状态快速切换（抖动过滤）
STATE_MIN_DURATION = 2.0  # 秒 - 状态至少持续此时间才生效


# ==================== 场景定义（三方共识）====================

# 场景 1: 吸收型回归（触轨 + 吸收强 + Delta 背离）
SCENARIO_ABSORPTION_REVERSAL = {
    "name": "吸收型回归",
    "conditions": {
        "touch_band": True,  # 触及布林带边界
        "absorption_score": ABSORPTION_SCORE_THRESHOLD,  # 吸收强度 > 2.5
        "delta_divergence": True,  # Delta 开始转负或衰减
    },
    "boost": BOOST_ABSORPTION_REVERSAL,  # +15%
    "description": "价格触及边界但被吸收，Delta 背离，预期回归",
}

# 场景 2: 失衡确认回归（触轨 + 失衡反转 + Delta 转负）
SCENARIO_IMBALANCE_REVERSAL = {
    "name": "失衡确认回归",
    "conditions": {
        "touch_band": True,  # 触及布林带边界
        "imbalance_reversal": IMBALANCE_THRESHOLD,  # 失衡度 > 0.6 且反转
        "delta_turn_negative": True,  # Delta 转负
    },
    "boost": BOOST_IMBALANCE_REVERSAL,  # +20%
    "description": "触轨后失衡反转，Delta 转负，强回归信号",
}

# 场景 3: 冰山护盘回归（触轨 + 反向冰山单）
SCENARIO_ICEBERG_DEFENSE = {
    "name": "冰山护盘回归",
    "conditions": {
        "touch_band": True,  # 触及布林带边界
        "iceberg_opposite_direction": ICEBERG_INTENSITY_THRESHOLD,  # 反向冰山 > 2.0
        "iceberg_level": ["CONFIRMED", "CRITICAL"],  # 至少 CONFIRMED 级别
    },
    "boost": BOOST_ICEBERG_DEFENSE,  # +25% (最高)
    "description": "触上轨遇卖方冰山护盘，或触下轨遇买方冰山支撑",
}

# 场景 4: 走轨风险 BAN（acceptance_time > 60s + 动力确认）
SCENARIO_WALKBAND_RISK = {
    "name": "走轨风险 BAN",
    "conditions": {
        "acceptance_time": ACCEPTANCE_TIME_BAN,  # > 60秒
        "momentum_confirmed": True,  # Delta 加速 或 扫单 或 失衡持续
    },
    "decision": "BAN",
    "description": "价格在边界外停留过久且有动力确认，禁止回归交易",
}


# ==================== 调试和日志参数 ====================

# 日志控制
VERBOSE_LOGGING = False  # 默认关闭详细日志，回测时可开启
LOG_LEVEL = "INFO"  # DEBUG / INFO / WARNING / ERROR

# 日志详细度
LOG_ALL_EVALUATIONS = False  # 是否记录所有评估（调试用）
LOG_STATE_TRANSITIONS = True  # 是否记录状态切换


# ==================== 参数验证 ====================

def validate_config() -> bool:
    """验证配置参数合法性"""
    errors = []

    # 带宽阈值检查
    if BANDWIDTH_SQUEEZE_THRESHOLD >= BANDWIDTH_EXPANSION_THRESHOLD:
        errors.append("BANDWIDTH_SQUEEZE_THRESHOLD 必须小于 BANDWIDTH_EXPANSION_THRESHOLD")

    # acceptance_time 阈值检查
    if ACCEPTANCE_TIME_WARNING >= ACCEPTANCE_TIME_BAN:
        errors.append("ACCEPTANCE_TIME_WARNING 必须小于 ACCEPTANCE_TIME_BAN")

    if RESET_GRACE_PERIOD <= 0:
        errors.append("RESET_GRACE_PERIOD 必须大于 0")

    # 失衡阈值检查
    if not (0 < IMBALANCE_THRESHOLD < 1):
        errors.append("IMBALANCE_THRESHOLD 必须在 (0, 1) 范围内")

    if not (0 < IMBALANCE_STRONG_THRESHOLD < 1):
        errors.append("IMBALANCE_STRONG_THRESHOLD 必须在 (0, 1) 范围内")

    if IMBALANCE_THRESHOLD >= IMBALANCE_STRONG_THRESHOLD:
        errors.append("IMBALANCE_THRESHOLD 必须小于 IMBALANCE_STRONG_THRESHOLD")

    # 置信度增强检查
    if not (0 <= BOOST_ABSORPTION_REVERSAL <= 1):
        errors.append("BOOST_ABSORPTION_REVERSAL 必须在 [0, 1] 范围内")

    if not (0 <= BOOST_IMBALANCE_REVERSAL <= 1):
        errors.append("BOOST_IMBALANCE_REVERSAL 必须在 [0, 1] 范围内")

    if not (0 <= BOOST_ICEBERG_DEFENSE <= 1):
        errors.append("BOOST_ICEBERG_DEFENSE 必须在 [0, 1] 范围内")

    # 阈值正值检查
    if ABSORPTION_SCORE_THRESHOLD <= 0:
        errors.append("ABSORPTION_SCORE_THRESHOLD 必须大于 0")

    if SWEEP_SCORE_THRESHOLD <= 0:
        errors.append("SWEEP_SCORE_THRESHOLD 必须大于 0")

    if ICEBERG_INTENSITY_THRESHOLD <= 0:
        errors.append("ICEBERG_INTENSITY_THRESHOLD 必须大于 0")

    if DELTA_SLOPE_THRESHOLD <= 0:
        errors.append("DELTA_SLOPE_THRESHOLD 必须大于 0")

    # 布林带参数检查
    if BOLLINGER_PERIOD < 2:
        errors.append("BOLLINGER_PERIOD 必须 >= 2")

    if BOLLINGER_STD_DEV <= 0:
        errors.append("BOLLINGER_STD_DEV 必须大于 0")

    if errors:
        raise ValueError(f"配置参数验证失败:\n" + "\n".join(f"  - {e}" for e in errors))

    return True


# ==================== 配置摘要输出 ====================

def print_config_summary():
    """打印配置摘要"""
    print("=" * 70)
    print("布林带×订单流环境过滤器 - 配置摘要")
    print("=" * 70)

    print("\n[布林带参数]")
    print(f"  周期: {BOLLINGER_PERIOD}")
    print(f"  标准差倍数: {BOLLINGER_STD_DEV}")

    print("\n[环境状态阈值]")
    print(f"  带宽收口阈值 (SQUEEZE): {BANDWIDTH_SQUEEZE_THRESHOLD:.3f}")
    print(f"  带宽扩张阈值 (EXPANSION): {BANDWIDTH_EXPANSION_THRESHOLD:.3f}")
    print(f"  触轨缓冲区 (TOUCH_BUFFER): {TOUCH_BUFFER:.4f}")
    print(f"  走轨最小时间: {WALKBAND_MIN_ACCEPTANCE_TIME:.1f}s")

    print("\n[acceptance_time 参数]")
    print(f"  预警阈值: {ACCEPTANCE_TIME_WARNING:.1f}s")
    print(f"  封禁阈值: {ACCEPTANCE_TIME_BAN:.1f}s")
    print(f"  重置宽限期: {RESET_GRACE_PERIOD:.1f}s")

    print("\n[订单流共振阈值]")
    print(f"  失衡度: {IMBALANCE_THRESHOLD:.2f}")
    print(f"  吸收强度: {ABSORPTION_SCORE_THRESHOLD:.2f}")
    print(f"  扫单强度: {SWEEP_SCORE_THRESHOLD:.2f}")
    print(f"  冰山强度: {ICEBERG_INTENSITY_THRESHOLD:.2f}")
    print(f"  Delta 斜率: {DELTA_SLOPE_THRESHOLD:.2f}")

    print("\n[置信度增强（乘法）]")
    print(f"  吸收型回归: +{BOOST_ABSORPTION_REVERSAL*100:.0f}%")
    print(f"  失衡确认回归: +{BOOST_IMBALANCE_REVERSAL*100:.0f}%")
    print(f"  冰山护盘回归: +{BOOST_ICEBERG_DEFENSE*100:.0f}%")

    print("\n[KGodRadar 集成]")
    print(f"  允许增强阶段: {', '.join(BOOST_ALLOWED_STAGES)}")
    print(f"  BAN 优先于 boost: {BAN_OVERRIDES_BOOST}")

    print("\n[场景定义]")
    for i, scenario in enumerate([
        SCENARIO_ABSORPTION_REVERSAL,
        SCENARIO_IMBALANCE_REVERSAL,
        SCENARIO_ICEBERG_DEFENSE,
        SCENARIO_WALKBAND_RISK,
    ], 1):
        print(f"  场景 {i}: {scenario['name']}")
        if 'boost' in scenario:
            print(f"    增强: +{scenario['boost']*100:.0f}%")
        if 'decision' in scenario:
            print(f"    决策: {scenario['decision']}")

    print("\n" + "=" * 70)


# ==================== 模块初始化验证 ====================

# 导入时自动验证配置
if __name__ != "__main__":
    try:
        validate_config()
    except ValueError as e:
        print(f"❌ {e}")
        raise


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print_config_summary()
    print()
    try:
        validate_config()
        print("✅ 配置验证通过")
    except ValueError as e:
        print(f"❌ {e}")
