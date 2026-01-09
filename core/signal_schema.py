#!/usr/bin/env python3
"""
信号数据结构定义 - SignalEvent Schema

功能：
1. SignalEvent 基础数据类（通用信号字段）
2. 信号子类：IcebergSignal, WhaleSignal, LiqSignal
3. JSON 序列化/反序列化（无损存储到 .jsonl.gz）
4. 预留扩展接口（confidence_modifier, related_signals）

设计原则：
- 纯定义，无副作用（import 时不做初始化）
- 向后兼容（可扩展字段）
- 类型安全（使用 dataclass + Optional）

作者：Claude Code
日期：2026-01-08
版本：v1.0（三方会谈第二十二轮共识 - 工作 2.2）
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime


# ==================== 基础 SignalEvent ====================

@dataclass
class SignalEvent:
    """
    信号事件基础类

    适用于所有信号类型（iceberg/whale/liq）的通用字段
    """

    # 核心字段（所有信号必需）
    ts: float                           # Unix 时间戳
    symbol: str                         # 交易对（如 "DOGE/USDT"）
    side: str                           # 方向："BUY" | "SELL"
    level: str                          # 级别："ACTIVITY" | "CONFIRMED" | "WARNING" | "CRITICAL"
    signal_type: str                    # 信号类型："iceberg" | "whale" | "liq"

    # 置信度字段
    confidence: float = 0.0             # 置信度（0-100）

    # 价格字段（可选，某些信号类型可能没有价格）
    price: Optional[float] = None       # 价格

    # 唯一标识和追溯字段
    key: str = ""                       # 信号唯一标识（格式见 P3-2 文档）
    snippet_path: str = ""              # 原始数据文件路径（用于回溯）
    offset: int = 0                     # 文件行号（用于定位）

    # 预留扩展字段（P3-2 Phase 2+）
    confidence_modifier: Dict[str, float] = field(default_factory=dict)  # 置信度调整明细
    related_signals: List[str] = field(default_factory=list)             # 关联信号 key 列表

    # 元数据字段（可选）
    data: Dict[str, Any] = field(default_factory=dict)  # 额外数据（用于扩展）


    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典（用于 JSON 序列化）

        Returns:
            字典表示，可直接 json.dumps()
        """
        result = asdict(self)

        # 移除空字段（减少存储空间）
        result = {k: v for k, v in result.items() if v or k in ['ts', 'confidence', 'offset']}

        return result


    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SignalEvent':
        """
        从字典创建信号对象（用于 JSON 反序列化）

        Args:
            data: 字典数据（来自 json.loads()）

        Returns:
            SignalEvent 对象
        """
        # 提取已知字段
        known_fields = {
            'ts', 'symbol', 'side', 'level', 'signal_type',
            'confidence', 'price', 'key', 'snippet_path', 'offset',
            'confidence_modifier', 'related_signals', 'data'
        }

        # 构建参数字典
        kwargs = {k: v for k, v in data.items() if k in known_fields}

        # 未知字段存入 data
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}
        if extra_fields:
            kwargs.setdefault('data', {}).update(extra_fields)

        return cls(**kwargs)


    def get_readable_time(self) -> str:
        """
        获取可读时间字符串（UTC+8 北京时间）

        Returns:
            格式化时间字符串（YYYY-MM-DD HH:MM:SS）
        """
        dt = datetime.fromtimestamp(self.ts)
        return dt.strftime('%Y-%m-%d %H:%M:%S')


    def __repr__(self) -> str:
        """字符串表示（调试用）"""
        return (
            f"{self.__class__.__name__}("
            f"type={self.signal_type}, "
            f"side={self.side}, "
            f"level={self.level}, "
            f"confidence={self.confidence:.1f}%, "
            f"price={self.price}, "
            f"ts={self.get_readable_time()})"
        )


# ==================== 冰山信号 ====================

@dataclass
class IcebergSignal(SignalEvent):
    """
    冰山订单信号

    特有字段：
    - cumulative_filled: 累计成交量
    - refill_count: 补单次数
    - intensity: 强度
    """

    # 冰山特有字段
    cumulative_filled: float = 0.0      # 累计成交量（USDT）
    refill_count: int = 0               # 补单次数
    intensity: float = 0.0              # 强度（用于排序和过滤）

    # 默认 signal_type
    signal_type: str = "iceberg"


    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IcebergSignal':
        """
        从字典创建冰山信号对象

        Args:
            data: 字典数据

        Returns:
            IcebergSignal 对象
        """
        # 提取冰山特有字段
        known_fields = {
            'ts', 'symbol', 'side', 'level', 'signal_type',
            'confidence', 'price', 'key', 'snippet_path', 'offset',
            'confidence_modifier', 'related_signals', 'data',
            'cumulative_filled', 'refill_count', 'intensity'
        }

        kwargs = {k: v for k, v in data.items() if k in known_fields}

        # 未知字段存入 data
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}
        if extra_fields:
            kwargs.setdefault('data', {}).update(extra_fields)

        # 确保 signal_type 正确
        kwargs.setdefault('signal_type', 'iceberg')

        return cls(**kwargs)


    def __repr__(self) -> str:
        """字符串表示（调试用）"""
        return (
            f"IcebergSignal("
            f"side={self.side}, "
            f"level={self.level}, "
            f"price={self.price}, "
            f"confidence={self.confidence:.1f}%, "
            f"refill_count={self.refill_count}, "
            f"intensity={self.intensity:.2f}, "
            f"ts={self.get_readable_time()})"
        )


# ==================== 鲸鱼成交信号（预留） ====================

@dataclass
class WhaleSignal(SignalEvent):
    """
    大额成交信号（预留结构）

    Phase 1: 仅定义基础结构
    Phase 2+: 添加鲸鱼特有字段
    """

    # 鲸鱼特有字段（预留）
    trade_volume: float = 0.0           # 成交量（USDT）
    trade_count: int = 0                # 成交笔数
    time_window: int = 300              # 时间窗口（秒，默认 5 分钟）

    # 默认 signal_type
    signal_type: str = "whale"


    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WhaleSignal':
        """从字典创建鲸鱼信号对象"""
        known_fields = {
            'ts', 'symbol', 'side', 'level', 'signal_type',
            'confidence', 'price', 'key', 'snippet_path', 'offset',
            'confidence_modifier', 'related_signals', 'data',
            'trade_volume', 'trade_count', 'time_window'
        }

        kwargs = {k: v for k, v in data.items() if k in known_fields}
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}
        if extra_fields:
            kwargs.setdefault('data', {}).update(extra_fields)

        kwargs.setdefault('signal_type', 'whale')
        return cls(**kwargs)


# ==================== 清算信号（预留） ====================

@dataclass
class LiqSignal(SignalEvent):
    """
    清算信号（预留结构）

    Phase 1: 仅定义基础结构
    Phase 2+: 添加清算特有字段
    """

    # 清算特有字段（预留）
    liquidation_volume: float = 0.0     # 清算量（USDT）
    liquidation_count: int = 0          # 清算笔数
    is_cascade: bool = False            # 是否连锁清算

    # 默认 signal_type
    signal_type: str = "liq"


    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LiqSignal':
        """从字典创建清算信号对象"""
        known_fields = {
            'ts', 'symbol', 'side', 'level', 'signal_type',
            'confidence', 'price', 'key', 'snippet_path', 'offset',
            'confidence_modifier', 'related_signals', 'data',
            'liquidation_volume', 'liquidation_count', 'is_cascade'
        }

        kwargs = {k: v for k, v in data.items() if k in known_fields}
        extra_fields = {k: v for k, v in data.items() if k not in known_fields}
        if extra_fields:
            kwargs.setdefault('data', {}).update(extra_fields)

        kwargs.setdefault('signal_type', 'liq')
        return cls(**kwargs)


# ==================== 工厂函数 ====================

def create_signal_from_dict(data: Dict[str, Any]) -> SignalEvent:
    """
    工厂函数：根据 signal_type 创建对应的信号对象

    Args:
        data: 字典数据（必须包含 signal_type 字段）

    Returns:
        对应类型的信号对象

    Raises:
        ValueError: signal_type 不支持
    """
    signal_type = data.get('signal_type') or data.get('type')

    if signal_type == 'iceberg':
        return IcebergSignal.from_dict(data)
    elif signal_type == 'whale':
        return WhaleSignal.from_dict(data)
    elif signal_type == 'liq':
        return LiqSignal.from_dict(data)
    else:
        # 未知类型，使用基础 SignalEvent
        return SignalEvent.from_dict(data)


# ==================== 批量转换工具 ====================

def signals_to_dicts(signals: List[SignalEvent]) -> List[Dict[str, Any]]:
    """
    批量转换信号为字典列表

    Args:
        signals: 信号对象列表

    Returns:
        字典列表（可用于 JSON 序列化）
    """
    return [signal.to_dict() for signal in signals]


def dicts_to_signals(dicts: List[Dict[str, Any]]) -> List[SignalEvent]:
    """
    批量从字典列表创建信号对象

    Args:
        dicts: 字典列表

    Returns:
        信号对象列表
    """
    return [create_signal_from_dict(d) for d in dicts]


# ==================== 兼容性适配器 ====================

def from_csv_row(row: Dict[str, str]) -> IcebergSignal:
    """
    从 CSV 行（iceberg_annotation_samples.csv）创建冰山信号

    Args:
        row: CSV 行字典（pandas DataFrame row 或 csv.DictReader）

    Returns:
        IcebergSignal 对象
    """
    return IcebergSignal(
        ts=float(row.get('ts', 0)),
        symbol=row.get('symbol', ''),
        side=row.get('side', ''),
        level=row.get('level', ''),
        confidence=float(row.get('confidence', 0)),
        price=float(row.get('price', 0)) if row.get('price') else None,
        cumulative_filled=float(row.get('cumulative_filled', 0)),
        refill_count=int(row.get('refill_count', 0)),
        intensity=float(row.get('intensity', 0)),
        key=row.get('key', ''),
        snippet_path=row.get('snippet_path', ''),
        offset=int(row.get('offset', 0)),
        signal_type='iceberg'
    )


def to_csv_row(signal: IcebergSignal) -> Dict[str, Any]:
    """
    冰山信号转换为 CSV 行格式

    Args:
        signal: IcebergSignal 对象

    Returns:
        CSV 行字典
    """
    return {
        'ts': signal.ts,
        'symbol': signal.symbol,
        'side': signal.side,
        'level': signal.level,
        'confidence': signal.confidence,
        'price': signal.price or 0,
        'cumulative_filled': signal.cumulative_filled,
        'refill_count': signal.refill_count,
        'intensity': signal.intensity,
        'key': signal.key,
        'snippet_path': signal.snippet_path,
        'offset': signal.offset,
    }
