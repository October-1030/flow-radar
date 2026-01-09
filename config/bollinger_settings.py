#!/usr/bin/env python3
"""
Bollinger Bands Regime Filter Configuration
布林带环境过滤器配置

设计原则:
- 所有阈值外部化，禁止硬编码
- 配置分组清晰（布林带参数 / 走轨风险阈值 / 回归信号阈值 / 风控参数）
- 提供默认值和推荐范围

作者: Claude Code (三方共识)
日期: 2026-01-09
版本: v1.0
参考: 第二十五轮三方共识
"""

# ==================== 布林带参数 ====================

CONFIG_BOLLINGER_BANDS = {
    # 基础参数
    "period": 20,               # 周期（推荐范围: 10-30）
    "std_dev": 2.0,             # 标准差倍数（推荐范围: 1.5-2.5）

    # 扩展参数
    "bandwidth_window": 100,    # 带宽历史窗口（用于检测挤压）
    "squeeze_threshold": 0.5,   # 挤压阈值（当前带宽 < 平均值 * 0.5）
}


# ==================== 环境过滤器配置 ====================

CONFIG_BOLLINGER_REGIME = {
    # === 走轨风险阈值（BAN_REVERSION 判定）===

    # Delta 相关
    "delta_slope_threshold": 0.5,           # Delta 斜率阈值（单位: USDT/s）
                                            # 推荐范围: 0.3-1.0
                                            # 说明: Delta 加速超过此值 = 趋势加速

    "delta_acceleration_threshold": 0.2,    # Delta 二阶导数阈值
                                            # 推荐范围: 0.1-0.5
                                            # 说明: 加速度指标，捕捉动量变化

    # 失衡相关
    "imbalance_threshold": 0.6,             # 失衡阈值（0-1）
                                            # 推荐范围: 0.55-0.7
                                            # 说明: buy_ratio 或 sell_ratio 超过此值

    "persistent_imbalance_periods": 3,      # 持续失衡周期数
                                            # 推荐范围: 2-5
                                            # 说明: 连续 N 个周期保持失衡

    # 扫单相关
    "sweep_score_threshold": 0.7,           # 扫单得分阈值（0-1）
                                            # 推荐范围: 0.6-0.8
                                            # 说明: 激进扫单 = 突破意图

    # 价格接受度
    "acceptance_time_threshold": 30,        # 价格接受时间阈值（秒）
                                            # 推荐范围: 15-60
                                            # 说明: 价格在边界外持续时间

    "acceptance_distance_threshold": 0.002, # 价格接受距离阈值（比例）
                                            # 推荐范围: 0.001-0.005
                                            # 说明: 价格超出边界的距离

    # 带宽相关
    "bandwidth_expansion_threshold": 0.008, # 带宽扩张阈值（比例）
                                            # 推荐范围: 0.005-0.015
                                            # 说明: 带宽超过此值 = 波动率扩张

    "bandwidth_expansion_rate": 0.05,       # 带宽扩张速率阈值（5%）
                                            # 推荐范围: 0.03-0.10
                                            # 说明: 带宽变化率超过此值

    # === 回归信号阈值（ALLOW_REVERSION 判定）===

    # Delta 相关
    "delta_divergence_threshold": -0.1,     # Delta 背离阈值
                                            # 推荐范围: -0.2 ~ 0
                                            # 说明: Delta 转负或衰减

    "delta_reversal_ratio": 0.5,            # Delta 反转比例阈值
                                            # 推荐范围: 0.3-0.7
                                            # 说明: Delta 衰减到峰值的比例

    # 吸收率相关
    "absorption_threshold": 0.5,            # 吸收率阈值（0-1）
                                            # 推荐范围: 0.4-0.7
                                            # 说明: 买盘/卖盘被吸收的比例

    "absorption_window": 5,                 # 吸收率计算窗口（周期数）
                                            # 推荐范围: 3-10

    # 深度相关
    "depth_depletion_threshold": 0.3,       # 深度耗尽阈值（比例）
                                            # 推荐范围: 0.2-0.5
                                            # 说明: 盘口深度被消耗的比例

    # === 冰山信号权重 ===

    "iceberg_weight": {
        "CRITICAL": 3.0,        # 冰山 CRITICAL 信号权重
        "CONFIRMED": 2.0,       # 冰山 CONFIRMED 信号权重
        "WARNING": 1.0,         # 冰山 WARNING 信号权重
        "ACTIVITY": 0.5,        # 冰山 ACTIVITY 信号权重
    },

    # === 走轨风险评分权重 ===

    "ban_reversion_weights": {
        "bandwidth_expanding": 1.0,             # 带宽扩张权重
        "delta_accelerating": 1.5,              # Delta 加速权重（GPT 强调）
        "aggressive_sweeping": 1.2,             # 扫单权重
        "persistent_imbalance": 1.0,            # 持续失衡权重
        "price_accepted": 1.0,                  # 价格接受权重（GPT 独有）
        "iceberg_opposite": 2.0,                # 反向冰山权重（最高）
    },

    "ban_reversion_threshold": 2.0,             # 走轨风险总分阈值
                                                # 推荐范围: 1.5-3.0

    # === 回归信号评分权重 ===

    "allow_reversion_weights": {
        "delta_divergence": 1.0,                # Delta 背离权重
        "high_absorption": 1.0,                 # 高吸收率权重
        "imbalance_reversal": 1.2,              # 失衡反转权重
        "iceberg_defense": 2.0,                 # 冰山防守权重（Gemini +25%）
        "depth_depletion": 0.8,                 # 深度耗尽权重
    },

    "allow_reversion_threshold": 2.0,           # 回归信号总分阈值
                                                # 推荐范围: 1.5-3.0

    # === 置信度提升（Gemini 量化）===

    "confidence_boost": {
        "delta_divergence": 0.10,               # Delta 背离 +10%
        "high_absorption": 0.10,                # 高吸收率 +10%
        "sell_imbalance": 0.15,                 # 卖方失衡 +15%
        "buy_imbalance": 0.15,                  # 买方失衡 +15%
        "iceberg_defense": 0.25,                # 冰山防守 +25%（最高）
        "depth_depletion": 0.08,                # 深度耗尽 +8%
        "squeeze_breakout": 0.12,               # 挤压突破 +12%
    },

    # === 风控参数 ===

    "max_consecutive_losses": 3,                # 最大连续亏损次数
                                                # 推荐范围: 2-5
                                                # 说明: 达到此值后暂停回归交易

    "cooldown_period": 300,                     # 冷却期（秒）
                                                # 推荐范围: 180-600
                                                # 说明: 连续亏损后的冷却时间

    "min_confidence": 0.6,                      # 最低置信度阈值
                                                # 推荐范围: 0.5-0.7
                                                # 说明: 低于此值不发出信号

    "max_holding_time": 3600,                   # 最大持仓时间（秒）
                                                # 推荐范围: 1800-7200
                                                # 说明: 超时未回归则止损

    # === 调试和日志 ===

    "enable_logging": True,                     # 是否启用日志
    "log_level": "INFO",                        # 日志级别: DEBUG/INFO/WARNING
    "log_all_evaluations": False,               # 是否记录所有评估（调试用）
}


# ==================== 场景配置（三方共识）====================

# 场景 A: 衰竭性回归
SCENARIO_A_EXHAUSTION_REVERSION = {
    "name": "衰竭性回归",
    "conditions": [
        ("touch_upper_band", True),             # 触上轨
        ("delta_divergence", True),             # Delta 背离
        ("low_absorption", True),               # 吸收率低
    ],
    "output": "REVERSION_SHORT",
    "confidence_boost": 0.15,
    "source": "三方共识"
}

# 场景 B: 失衡确认回归
SCENARIO_B_IMBALANCE_REVERSION = {
    "name": "失衡确认回归",
    "conditions": [
        ("touch_upper_band", True),             # 触上轨
        ("sell_imbalance", "> 0.6"),            # Sell Imbalance > 60%
        ("delta_turn_negative", True),          # Delta 转负
    ],
    "output": "REVERSION_SHORT",
    "confidence_boost": 0.20,
    "source": "三方共识"
}

# 场景 C: 冰山护盘回归
SCENARIO_C_ICEBERG_DEFENSE = {
    "name": "冰山护盘回归",
    "conditions": [
        ("touch_upper_band", True),             # 触上轨
        ("sell_iceberg_confirmed", True),       # 卖方冰山 CONFIRMED
    ],
    "output": "STRONG_REVERSION_SHORT",
    "confidence_boost": 0.25,
    "source": "三方共识 (Gemini 强调)"
}

# 场景 D: 挤压后触边界
SCENARIO_D_SQUEEZE_BREAKOUT = {
    "name": "挤压后触边界",
    "conditions": [
        ("bandwidth_squeeze", True),            # Bandwidth 收缩
        ("touch_band", True),                   # 突然触轨
        ("order_flow_check", "required"),       # 需要订单流判定
    ],
    "output": "DEPENDS_ON_FLOW",                # 视订单流而定
    "confidence_boost": 0.12,
    "source": "GPT 独有"
}

# 场景 E: 趋势性走轨
SCENARIO_E_TREND_WALKING = {
    "name": "趋势性走轨",
    "conditions": [
        ("touch_upper_band", True),             # 触上轨
        ("delta_accelerating", True),           # Delta 加速
        ("aggressive_sweeping", True),          # 扫单
        ("depth_depleted", True),               # 深度抽干
    ],
    "output": "BAN_REVERSION",
    "confidence_boost": 0.0,                    # 无增强，禁止操作
    "source": "三方共识"
}

# 场景 F: 冰山反向突破
SCENARIO_F_ICEBERG_BREAKOUT = {
    "name": "冰山反向突破",
    "conditions": [
        ("touch_upper_band", True),             # 触上轨
        ("buy_iceberg_confirmed", True),        # 买方冰山 CONFIRMED
    ],
    "output": "BAN_REVERSION",
    "confidence_boost": 0.0,                    # 无增强，禁止操作
    "source": "三方共识"
}


# ==================== 场景注册表 ====================

SCENARIOS = {
    "A": SCENARIO_A_EXHAUSTION_REVERSION,
    "B": SCENARIO_B_IMBALANCE_REVERSION,
    "C": SCENARIO_C_ICEBERG_DEFENSE,
    "D": SCENARIO_D_SQUEEZE_BREAKOUT,
    "E": SCENARIO_E_TREND_WALKING,
    "F": SCENARIO_F_ICEBERG_BREAKOUT,
}


# ==================== 验证函数 ====================

def validate_config() -> bool:
    """验证配置合法性"""
    errors = []

    # 检查布林带参数
    if CONFIG_BOLLINGER_BANDS["period"] < 2:
        errors.append("bb_period must be >= 2")

    if CONFIG_BOLLINGER_BANDS["std_dev"] <= 0:
        errors.append("bb_std must be > 0")

    # 检查阈值范围
    regime = CONFIG_BOLLINGER_REGIME

    if not (0 < regime["imbalance_threshold"] < 1):
        errors.append("imbalance_threshold must be in (0, 1)")

    if not (0 < regime["absorption_threshold"] < 1):
        errors.append("absorption_threshold must be in (0, 1)")

    if not (0 < regime["sweep_score_threshold"] < 1):
        errors.append("sweep_score_threshold must be in (0, 1)")

    if regime["max_consecutive_losses"] < 1:
        errors.append("max_consecutive_losses must be >= 1")

    # 检查置信度提升
    for key, value in regime["confidence_boost"].items():
        if not (0 <= value <= 1):
            errors.append(f"confidence_boost[{key}] must be in [0, 1], got {value}")

    if errors:
        print("❌ 配置验证失败:")
        for error in errors:
            print(f"  - {error}")
        return False

    print("✅ 配置验证通过")
    return True


# ==================== 配置导出 ====================

def get_config() -> dict:
    """获取完整配置"""
    return {
        "bollinger_bands": CONFIG_BOLLINGER_BANDS,
        "regime_filter": CONFIG_BOLLINGER_REGIME,
        "scenarios": SCENARIOS,
    }


def print_config_summary():
    """打印配置摘要"""
    print("="*60)
    print("Bollinger Regime Filter Configuration Summary")
    print("="*60)

    print("\n[布林带参数]")
    for key, value in CONFIG_BOLLINGER_BANDS.items():
        print(f"  {key:25s}: {value}")

    print("\n[走轨风险阈值]")
    risk_keys = [
        "delta_slope_threshold",
        "imbalance_threshold",
        "sweep_score_threshold",
        "acceptance_time_threshold",
        "bandwidth_expansion_threshold"
    ]
    for key in risk_keys:
        print(f"  {key:35s}: {CONFIG_BOLLINGER_REGIME[key]}")

    print("\n[回归信号阈值]")
    reversion_keys = [
        "delta_divergence_threshold",
        "absorption_threshold",
        "depth_depletion_threshold"
    ]
    for key in reversion_keys:
        print(f"  {key:35s}: {CONFIG_BOLLINGER_REGIME[key]}")

    print("\n[风控参数]")
    risk_control_keys = [
        "max_consecutive_losses",
        "cooldown_period",
        "min_confidence"
    ]
    for key in risk_control_keys:
        print(f"  {key:35s}: {CONFIG_BOLLINGER_REGIME[key]}")

    print("\n[置信度提升]")
    for key, value in CONFIG_BOLLINGER_REGIME["confidence_boost"].items():
        print(f"  {key:25s}: +{value*100:.0f}%")

    print("\n[场景定义]")
    for scenario_id, scenario in SCENARIOS.items():
        print(f"  场景 {scenario_id}: {scenario['name']}")
        print(f"    输出: {scenario['output']}")
        print(f"    置信度: +{scenario['confidence_boost']*100:.0f}%")


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print_config_summary()
    print()
    validate_config()
