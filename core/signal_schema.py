"""
Flow Radar - Signal Event Schema
流动性雷达 - 信号事件数据结构

统一的信号事件数据模型，支持多种信号类型（iceberg/whale/liq/kgod）

作者: Claude Code
日期: 2026-01-09
工作编号: 2.2
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from enum import Enum
import time
import copy


# ==================== 枚举定义 ====================

class SignalSide(str, Enum):
    """信号方向"""
    BUY = "BUY"
    SELL = "SELL"


class SignalLevel(str, Enum):
    """信号级别（优先级从高到低）"""
    CRITICAL = "CRITICAL"      # 临界级（清算聚集等）
    CONFIRMED = "CONFIRMED"    # 确认级（高置信度信号）
    WARNING = "WARNING"        # 警告级（中等置信度）
    ACTIVITY = "ACTIVITY"      # 活动级（低置信度观察）


class SignalType(str, Enum):
    """信号类型"""
    ICEBERG = "iceberg"        # 冰山单信号
    WHALE = "whale"            # 巨鲸成交信号
    LIQ = "liq"                # 清算信号
    KGOD = "kgod"              # K神战法信号


class BucketType(str, Enum):
    """Key bucket 类型"""
    MARKET = "market"          # 市场级别（全局）
    TIME_BUCKET = "time"       # 时间分桶（5分钟等）
    PRICE_BUCKET = "price"     # 价格分桶（价格区间）


# ==================== SignalEvent 基础类 ====================

@dataclass
class SignalEvent:
    """
    信号事件基础类

    所有信号类型的统一数据结构，支持扩展字段和元数据。

    字段说明：
        ts: 信号时间戳（Unix timestamp，秒）
        symbol: 交易对（如 "DOGE/USDT"）
        side: 信号方向（BUY/SELL）
        level: 信号级别（CRITICAL/CONFIRMED/WARNING/ACTIVITY）
        confidence: 置信度（0-100）
        price: 信号触发价格
        signal_type: 信号类型（iceberg/whale/liq/kgod）
        key: 唯一标识符（格式: {type}:{symbol}:{side}:{level}:{bucket}）
        data: 扩展数据字典（类型特定字段）
        metadata: 元数据字典（调试信息、原始数据等）
        confidence_modifier: 置信度调整记录（Phase 3 预留）
        related_signals: 关联信号 key 列表（Phase 3 预留）

    示例：
        >>> signal = SignalEvent(
        ...     ts=1704758400.0,
        ...     symbol="DOGE/USDT",
        ...     side=SignalSide.BUY,
        ...     level=SignalLevel.CONFIRMED,
        ...     confidence=85.0,
        ...     price=0.15068,
        ...     signal_type=SignalType.ICEBERG,
        ...     key="iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068"
        ... )
    """

    # ========== 必填字段 ==========
    ts: float                          # 信号时间戳
    symbol: str                        # 交易对
    side: SignalSide                   # 信号方向
    level: SignalLevel                 # 信号级别
    confidence: float                  # 置信度 (0-100)
    price: float                       # 信号价格
    signal_type: SignalType            # 信号类型
    key: str                           # 唯一标识符

    # ========== 扩展字段（可变默认值使用 field(default_factory)） ==========
    data: Dict[str, Any] = field(default_factory=dict)            # 扩展数据
    metadata: Dict[str, Any] = field(default_factory=dict)        # 元数据
    confidence_modifier: List[Dict[str, Any]] = field(default_factory=list)  # 置信度调整记录
    related_signals: List[str] = field(default_factory=list)      # 关联信号 keys

    def to_dict(self) -> Dict[str, Any]:
        """
        序列化为字典（JSON 兼容）

        注意：
        - 输出字段名使用 `type`（非 `signal_type`）
        - 枚举值转为字符串
        - 保留所有字段（包括 extras）

        Returns:
            Dict: JSON 兼容的字典
        """
        result = {
            "ts": self.ts,
            "symbol": self.symbol,
            "side": self.side.value if isinstance(self.side, SignalSide) else self.side,
            "level": self.level.value if isinstance(self.level, SignalLevel) else self.level,
            "confidence": self.confidence,
            "price": self.price,
            "type": self.signal_type.value if isinstance(self.signal_type, SignalType) else self.signal_type,
            "key": self.key,
            "data": self.data,
            "metadata": self.metadata,
            "confidence_modifier": self.confidence_modifier,
            "related_signals": self.related_signals,
        }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalEvent':
        """
        从字典反序列化

        注意：
        - 字段名 `type` 映射到 `signal_type`
        - 未知字段存入 `data` 或 `metadata.extras`
        - 枚举字段自动转换

        Args:
            data: 包含信号数据的字典

        Returns:
            SignalEvent: 信号事件实例
        """
        # 映射字段名：type -> signal_type
        signal_type = data.get("type", data.get("signal_type", "iceberg"))

        # 枚举转换
        side = SignalSide(data["side"]) if isinstance(data["side"], str) else data["side"]
        level = SignalLevel(data["level"]) if isinstance(data["level"], str) else data["level"]
        signal_type_enum = SignalType(signal_type) if isinstance(signal_type, str) else signal_type

        # 已知字段
        known_fields = {
            "ts", "symbol", "side", "level", "confidence", "price",
            "type", "signal_type", "key", "data", "metadata",
            "confidence_modifier", "related_signals"
        }

        # 提取已知字段（使用 deepcopy 避免嵌套字典共享引用）
        event_data = copy.deepcopy(data.get("data", {})) if "data" in data else {}
        event_metadata = copy.deepcopy(data.get("metadata", {})) if "metadata" in data else {}

        # 未知字段存入 metadata.extras
        extras = {}
        for k, v in data.items():
            if k not in known_fields:
                extras[k] = v

        if extras:
            event_metadata["extras"] = extras

        return cls(
            ts=data["ts"],
            symbol=data["symbol"],
            side=side,
            level=level,
            confidence=data["confidence"],
            price=data["price"],
            signal_type=signal_type_enum,
            key=data["key"],
            data=event_data,
            metadata=event_metadata,
            confidence_modifier=data.get("confidence_modifier", []),
            related_signals=data.get("related_signals", []),
        )

    def validate(self) -> bool:
        """
        轻量级校验

        校验内容：
        1. 必填字段非空
        2. 枚举字段合法性
        3. key 格式正确
        4. 置信度范围 [0, 100]

        Returns:
            bool: 校验是否通过

        Raises:
            ValueError: 校验失败时抛出异常
        """
        # 1. 必填字段校验
        if not self.symbol or not self.key:
            raise ValueError("symbol and key are required fields")

        # 2. 枚举合法性
        if not isinstance(self.side, SignalSide):
            raise ValueError(f"Invalid side: {self.side}, must be BUY or SELL")
        if not isinstance(self.level, SignalLevel):
            raise ValueError(f"Invalid level: {self.level}")
        if not isinstance(self.signal_type, SignalType):
            raise ValueError(f"Invalid signal_type: {self.signal_type}")

        # 3. 置信度范围
        if not (0 <= self.confidence <= 100):
            raise ValueError(f"Invalid confidence: {self.confidence}, must be in [0, 100]")

        # 4. key 格式校验（最小格式：{type}:{symbol}:{side}:{level}:{bucket}）
        key_parts = self.key.split(":")
        if len(key_parts) < 5:
            raise ValueError(f"Invalid key format: {self.key}, expected at least 5 parts separated by ':'")

        # 5. key 字段一致性检查
        expected_type = self.signal_type.value
        expected_symbol = self.symbol
        expected_side = self.side.value
        expected_level = self.level.value

        if key_parts[0] != expected_type:
            raise ValueError(f"Key type mismatch: {key_parts[0]} != {expected_type}")
        if key_parts[1] != expected_symbol:
            raise ValueError(f"Key symbol mismatch: {key_parts[1]} != {expected_symbol}")
        if key_parts[2] != expected_side:
            raise ValueError(f"Key side mismatch: {key_parts[2]} != {expected_side}")
        if key_parts[3] != expected_level:
            raise ValueError(f"Key level mismatch: {key_parts[3]} != {expected_level}")

        return True

    @staticmethod
    def generate_key(
        signal_type: SignalType,
        symbol: str,
        side: SignalSide,
        level: SignalLevel,
        bucket: str,
        bucket_type: BucketType = BucketType.PRICE_BUCKET
    ) -> str:
        """
        生成标准 key 格式

        格式：{type}:{symbol}:{side}:{level}:{bucket}

        Args:
            signal_type: 信号类型
            symbol: 交易对
            side: 方向
            level: 级别
            bucket: 分桶标识（如 "price_0.15068", "time_08:30", "market"）
            bucket_type: 分桶类型（可选，用于未来扩展）

        Returns:
            str: 标准 key

        Example:
            >>> SignalEvent.generate_key(
            ...     SignalType.ICEBERG, "DOGE/USDT", SignalSide.BUY,
            ...     SignalLevel.CONFIRMED, "price_0.15068"
            ... )
            'iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068'
        """
        type_str = signal_type.value if isinstance(signal_type, SignalType) else signal_type
        side_str = side.value if isinstance(side, SignalSide) else side
        level_str = level.value if isinstance(level, SignalLevel) else level

        return f"{type_str}:{symbol}:{side_str}:{level_str}:{bucket}"


# ==================== 信号子类 ====================

@dataclass
class IcebergSignal(SignalEvent):
    """
    冰山单信号（扩展字段）

    继承自 SignalEvent，添加冰山单特定字段：
        cumulative_filled: 累计成交量（USDT）
        refill_count: 补单次数
        intensity: 强度值

    示例：
        >>> signal = IcebergSignal(
        ...     ts=1704758400.0,
        ...     symbol="DOGE/USDT",
        ...     side=SignalSide.BUY,
        ...     level=SignalLevel.CONFIRMED,
        ...     confidence=85.0,
        ...     price=0.15068,
        ...     signal_type=SignalType.ICEBERG,
        ...     key="iceberg:DOGE/USDT:BUY:CONFIRMED:price_0.15068",
        ...     cumulative_filled=5000.0,
        ...     refill_count=3,
        ...     intensity=3.41
        ... )
    """

    cumulative_filled: float = 0.0     # 累计成交量（USDT）
    refill_count: int = 0              # 补单次数
    intensity: float = 0.0             # 强度值

    def to_dict(self) -> Dict[str, Any]:
        """序列化，包含冰山单特定字段"""
        result = super().to_dict()
        result["cumulative_filled"] = self.cumulative_filled
        result["refill_count"] = self.refill_count
        result["intensity"] = self.intensity
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IcebergSignal':
        """从字典反序列化"""
        # 先调用父类 from_dict 提取通用字段
        base_data = {k: v for k, v in data.items()
                     if k not in ["cumulative_filled", "refill_count", "intensity"]}
        base_signal = SignalEvent.from_dict(base_data)

        # 构造冰山单信号
        return cls(
            ts=base_signal.ts,
            symbol=base_signal.symbol,
            side=base_signal.side,
            level=base_signal.level,
            confidence=base_signal.confidence,
            price=base_signal.price,
            signal_type=base_signal.signal_type,
            key=base_signal.key,
            data=base_signal.data,
            metadata=base_signal.metadata,
            confidence_modifier=base_signal.confidence_modifier,
            related_signals=base_signal.related_signals,
            cumulative_filled=data.get("cumulative_filled", 0.0),
            refill_count=data.get("refill_count", 0),
            intensity=data.get("intensity", 0.0),
        )


@dataclass
class WhaleSignal(SignalEvent):
    """
    巨鲸成交信号（预留结构）

    未来扩展字段：
        - trade_volume: 成交量
        - avg_price: 平均成交价
        - maker_taker_ratio: Maker/Taker 比例
    """

    trade_volume: float = 0.0          # 成交量（USDT）
    avg_price: float = 0.0             # 平均成交价
    maker_taker_ratio: float = 0.5     # Maker/Taker 比例

    def to_dict(self) -> Dict[str, Any]:
        """序列化"""
        result = super().to_dict()
        result["trade_volume"] = self.trade_volume
        result["avg_price"] = self.avg_price
        result["maker_taker_ratio"] = self.maker_taker_ratio
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WhaleSignal':
        """从字典反序列化"""
        base_data = {k: v for k, v in data.items()
                     if k not in ["trade_volume", "avg_price", "maker_taker_ratio"]}
        base_signal = SignalEvent.from_dict(base_data)

        return cls(
            ts=base_signal.ts,
            symbol=base_signal.symbol,
            side=base_signal.side,
            level=base_signal.level,
            confidence=base_signal.confidence,
            price=base_signal.price,
            signal_type=base_signal.signal_type,
            key=base_signal.key,
            data=base_signal.data,
            metadata=base_signal.metadata,
            confidence_modifier=base_signal.confidence_modifier,
            related_signals=base_signal.related_signals,
            trade_volume=data.get("trade_volume", 0.0),
            avg_price=data.get("avg_price", 0.0),
            maker_taker_ratio=data.get("maker_taker_ratio", 0.5),
        )


@dataclass
class LiqSignal(SignalEvent):
    """
    清算信号（预留结构）

    未来扩展字段：
        - liquidation_volume: 清算量
        - liquidation_price: 清算价格
        - cascade_risk: 连锁清算风险
    """

    liquidation_volume: float = 0.0    # 清算量（USDT）
    liquidation_price: float = 0.0     # 清算价格
    cascade_risk: float = 0.0          # 连锁清算风险 (0-1)

    def to_dict(self) -> Dict[str, Any]:
        """序列化"""
        result = super().to_dict()
        result["liquidation_volume"] = self.liquidation_volume
        result["liquidation_price"] = self.liquidation_price
        result["cascade_risk"] = self.cascade_risk
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LiqSignal':
        """从字典反序列化"""
        base_data = {k: v for k, v in data.items()
                     if k not in ["liquidation_volume", "liquidation_price", "cascade_risk"]}
        base_signal = SignalEvent.from_dict(base_data)

        return cls(
            ts=base_signal.ts,
            symbol=base_signal.symbol,
            side=base_signal.side,
            level=base_signal.level,
            confidence=base_signal.confidence,
            price=base_signal.price,
            signal_type=base_signal.signal_type,
            key=base_signal.key,
            data=base_signal.data,
            metadata=base_signal.metadata,
            confidence_modifier=base_signal.confidence_modifier,
            related_signals=base_signal.related_signals,
            liquidation_volume=data.get("liquidation_volume", 0.0),
            liquidation_price=data.get("liquidation_price", 0.0),
            cascade_risk=data.get("cascade_risk", 0.0),
        )


# ==================== 工厂函数 ====================

def create_signal_from_dict(data: Dict[str, Any]) -> SignalEvent:
    """
    根据字典创建对应类型的信号实例

    根据 `type` 字段自动选择正确的子类。

    Args:
        data: 信号数据字典

    Returns:
        SignalEvent: 对应类型的信号实例

    Example:
        >>> data = {"type": "iceberg", "ts": 1704758400.0, ...}
        >>> signal = create_signal_from_dict(data)
        >>> isinstance(signal, IcebergSignal)
        True
    """
    signal_type = data.get("type", data.get("signal_type", "iceberg"))

    type_to_class = {
        "iceberg": IcebergSignal,
        SignalType.ICEBERG.value: IcebergSignal,
        "whale": WhaleSignal,
        SignalType.WHALE.value: WhaleSignal,
        "liq": LiqSignal,
        SignalType.LIQ.value: LiqSignal,
        "kgod": SignalEvent,  # K神信号暂用基类（保持隔离）
        SignalType.KGOD.value: SignalEvent,
    }

    signal_class = type_to_class.get(signal_type, SignalEvent)
    return signal_class.from_dict(data)


# ==================== 示例数据（用于测试） ====================

def get_example_signals() -> List[SignalEvent]:
    """
    获取示例信号（用于测试和文档）

    Returns:
        List[SignalEvent]: 4 个示例信号（iceberg/whale/liq/kgod）
    """
    ts = time.time()

    examples = [
        # 1. 冰山单信号
        IcebergSignal(
            ts=ts,
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=85.0,
            price=0.15068,
            signal_type=SignalType.ICEBERG,
            key=SignalEvent.generate_key(
                SignalType.ICEBERG, "DOGE/USDT", SignalSide.BUY,
                SignalLevel.CONFIRMED, "price_0.15068"
            ),
            cumulative_filled=5000.0,
            refill_count=3,
            intensity=3.41,
        ),

        # 2. 巨鲸成交信号
        WhaleSignal(
            ts=ts,
            symbol="BTC/USDT",
            side=SignalSide.SELL,
            level=SignalLevel.WARNING,
            confidence=70.0,
            price=42000.0,
            signal_type=SignalType.WHALE,
            key=SignalEvent.generate_key(
                SignalType.WHALE, "BTC/USDT", SignalSide.SELL,
                SignalLevel.WARNING, "price_42000"
            ),
            trade_volume=50000.0,
            avg_price=42100.0,
            maker_taker_ratio=0.7,
        ),

        # 3. 清算信号
        LiqSignal(
            ts=ts,
            symbol="ETH/USDT",
            side=SignalSide.SELL,
            level=SignalLevel.CRITICAL,
            confidence=95.0,
            price=2200.0,
            signal_type=SignalType.LIQ,
            key=SignalEvent.generate_key(
                SignalType.LIQ, "ETH/USDT", SignalSide.SELL,
                SignalLevel.CRITICAL, "price_2200"
            ),
            liquidation_volume=100000.0,
            liquidation_price=2200.0,
            cascade_risk=0.8,
        ),

        # 4. K神信号（使用基类）
        SignalEvent(
            ts=ts,
            symbol="DOGE/USDT",
            side=SignalSide.BUY,
            level=SignalLevel.CONFIRMED,
            confidence=75.0,
            price=0.15100,
            signal_type=SignalType.KGOD,
            key=SignalEvent.generate_key(
                SignalType.KGOD, "DOGE/USDT", SignalSide.BUY,
                SignalLevel.CONFIRMED, "time_08:30"
            ),
            data={
                "stage": "KGOD_CONFIRM",
                "z_score": 2.1,
                "macd_hist": 0.00015,
            },
            metadata={
                "bb_bandwidth": 0.002,
                "order_flow_score": 0.85,
            }
        ),
    ]

    return examples


if __name__ == "__main__":
    # 快速测试
    print("=" * 70)
    print("SignalEvent Schema - Quick Test".center(70))
    print("=" * 70)

    # 测试示例信号
    signals = get_example_signals()

    for i, signal in enumerate(signals, 1):
        print(f"\n{i}. {signal.signal_type.value.upper()} Signal:")
        print(f"   Key: {signal.key}")
        print(f"   Side: {signal.side.value}, Level: {signal.level.value}")
        print(f"   Confidence: {signal.confidence}%")

        # 测试序列化
        data = signal.to_dict()
        print(f"   Serialized: {len(data)} fields")

        # 测试反序列化
        restored = create_signal_from_dict(data)
        print(f"   Deserialized: {type(restored).__name__}")

        # 测试校验
        try:
            restored.validate()
            print(f"   Validation: ✅ PASS")
        except ValueError as e:
            print(f"   Validation: ❌ FAIL - {e}")

    print("\n" + "=" * 70)
    print("✅ Quick Test Complete".center(70))
    print("=" * 70)
