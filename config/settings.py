"""
Flow Radar - Configuration Settings
流动性雷达 - 全局配置文件

微观结构量化交易系统配置参数
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 存储路径
STORAGE_DIR = BASE_DIR / "storage"
LOG_DIR = STORAGE_DIR / "logs"
SIGNAL_DIR = STORAGE_DIR / "signals"
BACKTEST_DIR = STORAGE_DIR / "backtest"

# 确保目录存在
for dir_path in [LOG_DIR, SIGNAL_DIR, BACKTEST_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# ==================== System M - 盘面监控配置 ====================
CONFIG_MARKET = {
    "symbol": "DOGE/USDT",                 # 默认交易对（可通过命令行参数修改）
    "refresh_interval": 5,                  # 刷新频率（秒）
    "whale_threshold_usd": 5000,            # 大额成交阈值（美元）
    "volume_spike_multiplier": 3,           # 成交量异动倍数
    "rsi_period": 14,                       # RSI 周期
    "atr_period": 14,                       # ATR 周期
    "log_path": str(LOG_DIR / "market.log"),
    "exchange": "okx",                      # 交易所
    "orderbook_depth": 20,                  # 订单簿深度
}

# ==================== System I - 冰山单检测配置 ====================
CONFIG_ICEBERG = {
    "detection_window": 60,                 # 检测窗口（秒）
    "intensity_threshold": 2.0,             # 强度阈值（降低以更容易检测）
    "min_cumulative_volume": 500,           # 最小累计成交量（U）
    "price_tolerance": 0.0001,              # 价格容差
    "min_refill_count": 2,                  # 最小补单次数
    "log_path": str(LOG_DIR / "iceberg.log"),
}

# ==================== System A - 链上分析配置 ====================
CONFIG_CHAIN = {
    "large_transfer_threshold": 100000,     # 大额转账阈值
    "small_flow_threshold": 50000,          # 小额流动阈值
    "monitoring_interval": 30,              # 监控间隔（秒）
    "exchange_wallets": [],                 # 已知交易所钱包列表
    "log_path": str(LOG_DIR / "chain.log"),
    # 链上数据API配置（需要配置）
    "api_endpoint": "",
    "api_key": "",
}

# ==================== System C - 战情指挥配置 ====================
CONFIG_COMMAND = {
    "resonance_weights": {
        "market": 0.35,
        "iceberg": 0.35,
        "chain": 0.30
    },
    "min_confidence_to_alert": 50,          # 最小警报置信度
    "min_confidence_to_trade": 70,          # 最小交易置信度
    "signal_decay_window": 300,             # 信号衰减窗口（秒）
    "log_path": str(LOG_DIR / "command.log"),
}

# ==================== 风险管理配置 ====================
CONFIG_RISK = {
    # 单笔风险控制
    "max_risk_per_trade": 0.02,             # 单笔最大风险 2%
    "max_position_size": 0.10,              # 最大仓位 10%
    "default_stop_loss_pct": 0.02,          # 默认止损 2%
    "max_leverage": 5,                      # 最大杠杆

    # 账户风险控制
    "max_daily_loss": 0.05,                 # 单日最大亏损 5%
    "max_drawdown": 0.15,                   # 最大回撤 15%
    "margin_call_threshold": 0.80,          # 保证金预警阈值 80%
    "force_close_threshold": 0.90,          # 强平阈值 90%

    # 连续亏损控制
    "max_consecutive_losses": 3,            # 最大连续亏损次数
    "cooldown_after_loss_streak": 3600,     # 连续亏损后冷却时间（秒）

    # R倍数追踪
    "target_r_multiple": 2.0,               # 目标盈亏比
    "min_r_multiple": 1.5,                  # 最小盈亏比

    # 熔断机制
    "circuit_breaker_enabled": True,
    "circuit_breaker_loss_pct": 0.05,       # 触发熔断的亏损百分比
    "circuit_breaker_duration": 3600,       # 熔断持续时间（秒）
}

# ==================== 多时间框架配置 ====================
CONFIG_MTF = {
    "timeframes": ["1D", "4H", "15M"],
    "weights": {
        "1D": 0.50,                         # 日线权重
        "4H": 0.30,                         # 4小时权重
        "15M": 0.20                         # 15分钟权重
    },
    "trend_thresholds": {
        "strong_up": 0.6,
        "up": 0.3,
        "neutral": -0.3,
        "down": -0.6,
        # < -0.6: strong_down
    }
}

# 时间框架秒数映射
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "15M": 900,
    "30m": 1800,
    "1h": 3600,
    "1H": 3600,
    "4h": 14400,
    "4H": 14400,
    "1d": 86400,
    "1D": 86400,
}

# ==================== 信号类型配置 ====================
SIGNAL_TYPES = {
    "WHALE_BUY": {"name": "巨鲸买入", "direction": "LONG", "priority": 1},
    "WHALE_SELL": {"name": "巨鲸卖出", "direction": "SHORT", "priority": 1},
    "ICEBERG_BUY": {"name": "冰山买单", "direction": "LONG", "priority": 2},
    "ICEBERG_SELL": {"name": "冰山卖单", "direction": "SHORT", "priority": 2},
    "STRONG_BULLISH": {"name": "强势看多", "direction": "LONG", "priority": 2},
    "STRONG_BEARISH": {"name": "强势看空", "direction": "SHORT", "priority": 2},
    "SYMMETRY_BREAK_UP": {"name": "对称性破坏(上)", "direction": "LONG", "priority": 1},
    "SYMMETRY_BREAK_DOWN": {"name": "对称性破坏(下)", "direction": "SHORT", "priority": 1},
    "LIQUIDITY_GRAB": {"name": "流动性猎杀", "direction": "REVERSE", "priority": 1},
    "CHAIN_INFLOW": {"name": "链上流入", "direction": "SHORT", "priority": 3},
    "CHAIN_OUTFLOW": {"name": "链上流出", "direction": "LONG", "priority": 3},
}

# ==================== BTC 联动配置 ====================
CONFIG_BTC = {
    "correlation_window": 100,              # 相关性计算窗口
    "high_correlation_threshold": 0.7,      # 高相关性阈值
    "low_correlation_threshold": 0.3,       # 低相关性阈值
    "btc_dominance_weight": 0.3,            # BTC走势权重
}

# ==================== 执行环境配置 ====================
CONFIG_EXECUTION = {
    "check_margin_availability": True,       # 检查借币可用性
    "max_slippage_pct": 0.005,              # 最大滑点 0.5%
    "order_timeout": 30,                     # 订单超时（秒）
    "data_source_check": True,              # 数据源对齐检查
    "min_liquidity_usd": 10000,             # 最小流动性要求
}

# ==================== 显示配置 ====================
CONFIG_DISPLAY = {
    "use_colors": True,
    "show_timestamp": True,
    "show_extreme_state": True,
    "show_chain_state": True,
    "show_countdown": True,
    "decimal_places": {
        "price": 6,
        "volume": 2,
        "percentage": 2,
        "score": 0,
    }
}

# ==================== API 密钥（从环境变量读取）====================
class Secrets:
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    CHAIN_API_KEY = os.getenv("CHAIN_API_KEY", "")

    @classmethod
    def validate(cls) -> bool:
        """验证必要的API密钥是否已配置"""
        return bool(cls.BINANCE_API_KEY and cls.BINANCE_API_SECRET)
