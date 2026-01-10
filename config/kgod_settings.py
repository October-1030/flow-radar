"""
K神战法 2.0 - 配置参数
K-God Strategy 2.0 Configuration

基于布林带 + MACD + 订单流的四层信号识别系统

作者: 三方共识（Claude + GPT + Gemini）
日期: 2026-01-09
版本: v2.0
参考: 第二十七轮、第二十八轮三方共识
"""

# ==================== 布林带参数 ====================
CONFIG_BOLLINGER = {
    # 基础参数
    "period": 20,                    # 周期（默认 20）
    "num_std": 2.0,                  # 标准差倍数（默认 2.0）

    # 预警区 z-score 阈值
    "z_pre_alert": 1.4,              # 预警区：1.4 ≤ |z| < 1.8
    "z_early_confirm": 1.8,          # 早期确认：1.8 ≤ |z| < 2.0
    "z_kgod_confirm": 2.0,           # K神确认：|z| ≥ 2.0

    # 带宽相关
    "bw_expand_min": 0.0005,         # 带宽扩张最小阈值（0.05%）
    "bw_expand_strong": 0.001,       # 带宽强扩张阈值（0.1%）
    "bw_slope_window": 5,            # 带宽斜率计算窗口（5 tick）
}

# ==================== MACD 参数 ====================
CONFIG_MACD = {
    # EMA 参数
    "fast_period": 12,               # 快线周期
    "slow_period": 26,               # 慢线周期
    "signal_period": 9,              # 信号线周期

    # 柱状图斜率
    "hist_slope_window": 3,          # 柱状图斜率窗口（3 tick）

    # MACD 确认阈值
    "hist_min_confirm": 0.00001,     # 柱状图最小确认值
    "hist_slope_min": 0.000005,      # 柱状图斜率最小值
}

# ==================== 订单流参数 ====================
CONFIG_ORDER_FLOW = {
    # Delta 相关
    "delta_5s_strong": 500.0,        # 5秒 Delta 强信号阈值（USDT）
    "delta_5s_weak": 200.0,          # 5秒 Delta 弱信号阈值
    "delta_slope_10s_strong": 50.0,  # 10秒 Delta 斜率强阈值
    "delta_slope_10s_weak": 20.0,    # 10秒 Delta 斜率弱阈值

    # 失衡相关
    "imbalance_1s_strong": 0.75,     # 1秒失衡强信号（75%）
    "imbalance_1s_weak": 0.60,       # 1秒失衡弱信号（60%）

    # 吸收率
    "absorption_ask_high": 0.70,     # 卖方吸收率高（70%）- 看涨
    "absorption_bid_high": 0.70,     # 买方吸收率高（70%）- 看跌

    # 扫单相关
    "sweep_score_5s_strong": 3.0,    # 5秒扫单得分强阈值
    "sweep_score_5s_weak": 1.5,      # 5秒扫单得分弱阈值

    # 冰山相关
    "iceberg_intensity_min": 2.0,    # 冰山强度最小值
    "refill_count_min": 2,           # 最小补单次数
}

# ==================== 价格接受参数 ====================
CONFIG_ACCEPTANCE = {
    # 价格在布林带轨道附近的接受时间阈值
    "acceptance_above_upper_s": 30.0,    # 价格在上轨上方接受时间（秒）
    "acceptance_below_lower_s": 30.0,    # 价格在下轨下方接受时间（秒）
    "acceptance_tolerance": 0.0002,      # 接受判定容差（0.02%）
}

# ==================== 四层信号阈值 ====================
CONFIG_SIGNAL_STAGES = {
    # PRE_ALERT - 预警（低置信度）
    "pre_alert": {
        "z_min": 1.4,                    # z-score ≥ 1.4
        "confidence_base": 30,           # 基础置信度 30
        "confidence_max": 50,            # 最大置信度 50
    },

    # EARLY_CONFIRM - 早期确认（中置信度）
    "early_confirm": {
        "z_min": 1.8,                    # z-score ≥ 1.8
        "confidence_base": 50,           # 基础置信度 50
        "confidence_max": 70,            # 最大置信度 70
        "require_macd": True,            # 需要 MACD 确认
        "require_order_flow_weak": True, # 需要弱订单流确认
    },

    # KGOD_CONFIRM - K神确认（高置信度）
    "kgod_confirm": {
        "z_min": 2.0,                    # z-score ≥ 2.0
        "confidence_base": 70,           # 基础置信度 70
        "confidence_max": 95,            # 最大置信度 95
        "require_macd_strong": True,     # 需要 MACD 强确认
        "require_order_flow_strong": True,  # 需要强订单流确认
        "require_bandwidth_expand": True,   # 需要带宽扩张
    },

    # BAN - 禁入（走轨风险）
    "ban": {
        "ban_threshold_enter": 2,        # ≥2 条 BAN → 禁止开仓
        "ban_threshold_force_exit": 3,   # ≥3 条 BAN → 强制平仓
        "ban_reasons": [
            "价格持续在上轨上方 >30s",
            "价格持续在下轨下方 >30s",
            "带宽持续收缩",
            "MACD 柱状图反向",
            "订单流方向反转",
            "冰山信号消失",
        ]
    }
}

# ==================== 置信度加成 ====================
CONFIG_CONFIDENCE_BOOST = {
    # MACD 加成
    "macd_hist_positive": 5,         # MACD 柱状图同方向 +5
    "macd_slope_positive": 5,        # MACD 斜率同方向 +5

    # 订单流加成
    "delta_strong": 10,              # Delta 强信号 +10
    "delta_weak": 5,                 # Delta 弱信号 +5
    "imbalance_strong": 10,          # 失衡强信号 +10
    "imbalance_weak": 5,             # 失衡弱信号 +5
    "sweep_strong": 8,               # 扫单强信号 +8
    "sweep_weak": 4,                 # 扫单弱信号 +4
    "absorption_high": 8,            # 吸收率高 +8

    # 冰山加成
    "iceberg_present": 10,           # 冰山信号存在 +10
    "iceberg_refill_bonus": 2,       # 每次补单额外 +2

    # 带宽加成
    "bandwidth_expand_strong": 10,   # 带宽强扩张 +10
    "bandwidth_expand_weak": 5,      # 带宽弱扩张 +5
}

# ==================== 走轨风险检测 ====================
CONFIG_BAN_DETECTION = {
    # 价格接受检测
    "check_acceptance": True,        # 是否检测价格接受
    "acceptance_check_interval": 5.0,  # 检测间隔（秒）

    # 带宽检测
    "check_bandwidth_shrink": True,  # 是否检测带宽收缩
    "bw_shrink_threshold": -0.0003,  # 带宽收缩阈值（-0.03%）

    # MACD 反向检测
    "check_macd_reversal": True,     # 是否检测 MACD 反向
    "macd_reversal_threshold": 3,    # MACD 反向检测窗口（3 tick）

    # 订单流反向检测
    "check_flow_reversal": True,     # 是否检测订单流反向
    "flow_reversal_delta": -300.0,   # Delta 反向阈值（USDT）
    "flow_reversal_imbalance": -0.3, # 失衡反向阈值

    # 冰山消失检测
    "check_iceberg_loss": True,      # 是否检测冰山消失
    "iceberg_loss_timeout": 60.0,    # 冰山消失超时（秒）
}

# ==================== 性能参数 ====================
CONFIG_PERFORMANCE = {
    # 数据窗口大小
    "price_history_size": 50,        # 价格历史最大长度（50 tick）
    "macd_history_size": 30,         # MACD 历史最大长度（30 tick）
    "ban_history_size": 10,          # BAN 信号历史最大长度（10 条）

    # 计算优化
    "use_deque": True,               # 使用 deque 实现 O(1) 计算
    "lazy_calculation": False,       # 是否延迟计算（默认关闭）
}

# ==================== 调试配置 ====================
CONFIG_DEBUG = {
    "enabled": False,                # 是否启用调试模式
    "log_all_signals": False,        # 是否记录所有信号（含未触发）
    "log_ban_details": True,         # 是否详细记录 BAN 原因
    "log_confidence_breakdown": True,  # 是否记录置信度分解
}


# ==================== 配置验证函数 ====================
def validate_kgod_config():
    """验证 K神战法配置参数的合理性"""
    issues = []

    # 验证布林带参数
    if CONFIG_BOLLINGER['period'] < 5:
        issues.append("布林带周期过短（< 5）")
    if CONFIG_BOLLINGER['num_std'] < 1.0:
        issues.append("布林带标准差倍数过小（< 1.0）")

    # 验证 z-score 阈值递增
    z_pre = CONFIG_BOLLINGER['z_pre_alert']
    z_early = CONFIG_BOLLINGER['z_early_confirm']
    z_kgod = CONFIG_BOLLINGER['z_kgod_confirm']
    if not (z_pre < z_early < z_kgod):
        issues.append(f"z-score 阈值未递增：{z_pre} < {z_early} < {z_kgod}")

    # 验证 MACD 参数
    if CONFIG_MACD['fast_period'] >= CONFIG_MACD['slow_period']:
        issues.append("MACD 快线周期 >= 慢线周期")

    # 验证置信度范围
    for stage_name, stage_cfg in CONFIG_SIGNAL_STAGES.items():
        if stage_name == 'ban':
            continue
        base = stage_cfg.get('confidence_base', 0)
        max_conf = stage_cfg.get('confidence_max', 100)
        if not (0 <= base <= max_conf <= 100):
            issues.append(f"{stage_name} 置信度范围不合法：{base} ~ {max_conf}")

    # 验证 BAN 阈值
    ban_enter = CONFIG_SIGNAL_STAGES['ban']['ban_threshold_enter']
    ban_exit = CONFIG_SIGNAL_STAGES['ban']['ban_threshold_force_exit']
    if ban_enter >= ban_exit:
        issues.append(f"BAN 阈值不合法：enter={ban_enter} >= exit={ban_exit}")

    return issues


# ==================== 配置导出 ====================
def get_kgod_config() -> dict:
    """获取完整的 K神战法配置（用于初始化 KGodRadar）"""
    return {
        'bollinger': CONFIG_BOLLINGER,
        'macd': CONFIG_MACD,
        'order_flow': CONFIG_ORDER_FLOW,
        'acceptance': CONFIG_ACCEPTANCE,
        'signal_stages': CONFIG_SIGNAL_STAGES,
        'confidence_boost': CONFIG_CONFIDENCE_BOOST,
        'ban_detection': CONFIG_BAN_DETECTION,
        'performance': CONFIG_PERFORMANCE,
        'debug': CONFIG_DEBUG,
    }


# ==================== 配置自检 ====================
if __name__ == "__main__":
    print("=" * 60)
    print("K神战法 2.0 - 配置验证")
    print("=" * 60)

    issues = validate_kgod_config()

    if issues:
        print("\n❌ 配置验证失败：")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\n✅ 配置验证通过")

        print("\n核心参数：")
        print(f"  布林带周期: {CONFIG_BOLLINGER['period']}")
        print(f"  z-score 阈值: PRE={CONFIG_BOLLINGER['z_pre_alert']}, "
              f"EARLY={CONFIG_BOLLINGER['z_early_confirm']}, "
              f"KGOD={CONFIG_BOLLINGER['z_kgod_confirm']}")
        print(f"  MACD 周期: {CONFIG_MACD['fast_period']}/{CONFIG_MACD['slow_period']}/{CONFIG_MACD['signal_period']}")
        print(f"  BAN 阈值: enter≥{CONFIG_SIGNAL_STAGES['ban']['ban_threshold_enter']}, "
              f"exit≥{CONFIG_SIGNAL_STAGES['ban']['ban_threshold_force_exit']}")
