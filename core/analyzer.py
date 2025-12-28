"""
Shell Market Watcher - Signal Analyzer
信号分析器

职责: 信号生成、衰减管理、优先级排序
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import logging
from pathlib import Path

from config.settings import CONFIG_COMMAND, SIGNAL_TYPES, SIGNAL_DIR


logger = logging.getLogger('Analyzer')


class SignalPriority(Enum):
    """信号优先级"""
    P1 = 1  # 最高优先级
    P2 = 2
    P3 = 3
    P4 = 4  # 最低优先级


class SignalStatus(Enum):
    """信号状态"""
    ACTIVE = "active"
    DECAYING = "decaying"
    EXPIRED = "expired"
    CONFIRMED = "confirmed"
    INVALIDATED = "invalidated"


@dataclass
class Signal:
    """交易信号"""
    id: str
    signal_type: str
    direction: str                      # 'LONG', 'SHORT', 'NEUTRAL'
    source: str                         # 'M', 'I', 'A', 'C'
    priority: SignalPriority
    strength: float                     # 0-100
    confidence: float                   # 0-100
    timestamp: datetime
    price_at_signal: float
    details: Dict = field(default_factory=dict)
    status: SignalStatus = SignalStatus.ACTIVE
    decay_factor: float = 1.0
    confirmations: int = 0
    invalidations: int = 0

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.timestamp).total_seconds()

    @property
    def effective_strength(self) -> float:
        """考虑衰减的有效强度"""
        return self.strength * self.decay_factor

    @property
    def effective_confidence(self) -> float:
        """考虑确认/失效的有效置信度"""
        base = self.confidence * self.decay_factor
        # 每次确认增加5%，每次失效减少10%
        adjustment = self.confirmations * 5 - self.invalidations * 10
        return max(0, min(100, base + adjustment))

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'signal_type': self.signal_type,
            'direction': self.direction,
            'source': self.source,
            'priority': self.priority.value,
            'strength': self.strength,
            'confidence': self.confidence,
            'timestamp': self.timestamp.isoformat(),
            'price_at_signal': self.price_at_signal,
            'details': self.details,
            'status': self.status.value,
            'decay_factor': self.decay_factor,
            'effective_strength': self.effective_strength,
            'effective_confidence': self.effective_confidence
        }


class SignalDecayManager:
    """信号衰减管理器"""

    def __init__(self, decay_window: int = 300):
        self.decay_window = decay_window  # 默认5分钟

    def calculate_decay(self, age_seconds: float) -> float:
        """
        计算衰减因子
        使用指数衰减: decay = e^(-age/window)
        """
        import math
        if age_seconds <= 0:
            return 1.0
        decay = math.exp(-age_seconds / self.decay_window)
        return max(0.0, min(1.0, decay))

    def update_signal_decay(self, signal: Signal) -> Signal:
        """更新信号的衰减状态"""
        signal.decay_factor = self.calculate_decay(signal.age_seconds)

        # 更新状态
        if signal.decay_factor < 0.1:
            signal.status = SignalStatus.EXPIRED
        elif signal.decay_factor < 0.5:
            signal.status = SignalStatus.DECAYING

        return signal


class SignalAnalyzer:
    """信号分析器"""

    def __init__(self):
        self.signals: List[Signal] = []
        self.decay_manager = SignalDecayManager(CONFIG_COMMAND['signal_decay_window'])
        self.signal_counter = 0

    def _generate_id(self) -> str:
        """生成信号ID"""
        self.signal_counter += 1
        return f"SIG_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self.signal_counter:04d}"

    def create_signal(
        self,
        signal_type: str,
        source: str,
        strength: float,
        price: float,
        details: Dict = None
    ) -> Signal:
        """创建新信号"""
        signal_config = SIGNAL_TYPES.get(signal_type, {})

        signal = Signal(
            id=self._generate_id(),
            signal_type=signal_type,
            direction=signal_config.get('direction', 'NEUTRAL'),
            source=source,
            priority=SignalPriority(signal_config.get('priority', 2)),
            strength=strength,
            confidence=self._calculate_initial_confidence(signal_type, strength),
            timestamp=datetime.now(),
            price_at_signal=price,
            details=details or {}
        )

        self.signals.append(signal)
        logger.info(f"新信号: {signal.signal_type} | 方向: {signal.direction} | 强度: {signal.strength:.1f}")

        return signal

    def _calculate_initial_confidence(self, signal_type: str, strength: float) -> float:
        """计算初始置信度"""
        # 基础置信度 = 强度 * 0.6 + 信号类型基准
        base_confidence = {
            'WHALE_BUY': 55,
            'WHALE_SELL': 55,
            'ICEBERG_BUY': 60,
            'ICEBERG_SELL': 60,
            'STRONG_BULLISH': 50,
            'STRONG_BEARISH': 50,
            'SYMMETRY_BREAK_UP': 70,
            'SYMMETRY_BREAK_DOWN': 70,
            'LIQUIDITY_GRAB': 75,
            'CHAIN_INFLOW': 45,
            'CHAIN_OUTFLOW': 45,
        }.get(signal_type, 50)

        return min(95, base_confidence + (strength - 50) * 0.4)

    def update_all_signals(self) -> List[Signal]:
        """更新所有信号的衰减状态"""
        for signal in self.signals:
            self.decay_manager.update_signal_decay(signal)
        return self.signals

    def get_active_signals(self, direction: str = None, min_confidence: float = 0) -> List[Signal]:
        """获取活跃信号"""
        active = [
            s for s in self.signals
            if s.status in [SignalStatus.ACTIVE, SignalStatus.DECAYING, SignalStatus.CONFIRMED]
            and s.effective_confidence >= min_confidence
        ]

        if direction:
            active = [s for s in active if s.direction == direction]

        # 按优先级和有效强度排序
        active.sort(key=lambda s: (s.priority.value, -s.effective_strength))

        return active

    def confirm_signal(self, signal_id: str):
        """确认信号"""
        for signal in self.signals:
            if signal.id == signal_id:
                signal.confirmations += 1
                signal.status = SignalStatus.CONFIRMED
                logger.info(f"信号确认: {signal_id} | 确认次数: {signal.confirmations}")
                break

    def invalidate_signal(self, signal_id: str, reason: str = ""):
        """失效信号"""
        for signal in self.signals:
            if signal.id == signal_id:
                signal.invalidations += 1
                if signal.invalidations >= 2:
                    signal.status = SignalStatus.INVALIDATED
                logger.info(f"信号失效: {signal_id} | 原因: {reason}")
                break

    def cleanup_expired(self):
        """清理过期信号"""
        before_count = len(self.signals)
        self.signals = [
            s for s in self.signals
            if s.status not in [SignalStatus.EXPIRED, SignalStatus.INVALIDATED]
            or s.age_seconds < 3600  # 保留1小时内的记录用于分析
        ]
        cleaned = before_count - len(self.signals)
        if cleaned > 0:
            logger.debug(f"清理了 {cleaned} 个过期信号")

    def get_signal_summary(self) -> Dict:
        """获取信号摘要"""
        self.update_all_signals()

        active = [s for s in self.signals if s.status == SignalStatus.ACTIVE]
        decaying = [s for s in self.signals if s.status == SignalStatus.DECAYING]
        confirmed = [s for s in self.signals if s.status == SignalStatus.CONFIRMED]

        long_signals = [s for s in active + confirmed if s.direction == 'LONG']
        short_signals = [s for s in active + confirmed if s.direction == 'SHORT']

        return {
            'total': len(self.signals),
            'active': len(active),
            'decaying': len(decaying),
            'confirmed': len(confirmed),
            'long_count': len(long_signals),
            'short_count': len(short_signals),
            'avg_long_confidence': sum(s.effective_confidence for s in long_signals) / len(long_signals) if long_signals else 0,
            'avg_short_confidence': sum(s.effective_confidence for s in short_signals) / len(short_signals) if short_signals else 0,
            'dominant_direction': 'LONG' if len(long_signals) > len(short_signals) else 'SHORT' if len(short_signals) > len(long_signals) else 'NEUTRAL'
        }

    def detect_conflicting_signals(self) -> List[Tuple[Signal, Signal]]:
        """检测冲突信号"""
        conflicts = []
        active = self.get_active_signals()

        for i, s1 in enumerate(active):
            for s2 in active[i + 1:]:
                # 同源但方向相反的信号
                if s1.source == s2.source and s1.direction != s2.direction:
                    if s1.direction != 'NEUTRAL' and s2.direction != 'NEUTRAL':
                        conflicts.append((s1, s2))

        return conflicts

    def save_signals(self, filename: str = None):
        """保存信号到文件"""
        if filename is None:
            filename = f"signals_{datetime.now().strftime('%Y%m%d')}.json"

        filepath = SIGNAL_DIR / filename

        data = {
            'saved_at': datetime.now().isoformat(),
            'signals': [s.to_dict() for s in self.signals]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"信号已保存到: {filepath}")

    def load_signals(self, filename: str) -> int:
        """从文件加载信号"""
        filepath = SIGNAL_DIR / filename

        if not filepath.exists():
            logger.warning(f"信号文件不存在: {filepath}")
            return 0

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        loaded = 0
        for s_data in data.get('signals', []):
            try:
                signal = Signal(
                    id=s_data['id'],
                    signal_type=s_data['signal_type'],
                    direction=s_data['direction'],
                    source=s_data['source'],
                    priority=SignalPriority(s_data['priority']),
                    strength=s_data['strength'],
                    confidence=s_data['confidence'],
                    timestamp=datetime.fromisoformat(s_data['timestamp']),
                    price_at_signal=s_data['price_at_signal'],
                    details=s_data.get('details', {}),
                    status=SignalStatus(s_data.get('status', 'expired')),
                    decay_factor=s_data.get('decay_factor', 0)
                )
                self.signals.append(signal)
                loaded += 1
            except Exception as e:
                logger.warning(f"加载信号失败: {e}")

        logger.info(f"从 {filepath} 加载了 {loaded} 个信号")
        return loaded


class TrapDetector:
    """陷阱检测器 - 识别诱多/诱空"""

    def __init__(self):
        self.price_history: List[float] = []
        self.signal_history: List[Signal] = []

    def add_price(self, price: float):
        """添加价格"""
        self.price_history.append(price)
        if len(self.price_history) > 100:
            self.price_history = self.price_history[-100:]

    def add_signal(self, signal: Signal):
        """添加信号"""
        self.signal_history.append(signal)
        if len(self.signal_history) > 50:
            self.signal_history = self.signal_history[-50:]

    def detect_bull_trap(self, current_price: float, recent_high: float) -> Optional[Dict]:
        """
        检测诱多陷阱
        特征: 价格突破前高后快速回落
        """
        if len(self.price_history) < 20:
            return None

        max_20 = max(self.price_history[-20:])
        max_5 = max(self.price_history[-5:])

        # 刚创新高后回落
        if max_5 >= max_20 * 0.995 and current_price < max_5 * 0.98:
            # 检查是否有大量多头信号后反转
            recent_long_signals = [
                s for s in self.signal_history
                if s.direction == 'LONG' and s.age_seconds < 300
            ]

            if len(recent_long_signals) >= 2:
                return {
                    'type': 'BULL_TRAP',
                    'confidence': 70,
                    'breakout_price': max_5,
                    'current_price': current_price,
                    'signal_count': len(recent_long_signals)
                }

        return None

    def detect_bear_trap(self, current_price: float, recent_low: float) -> Optional[Dict]:
        """
        检测诱空陷阱
        特征: 价格跌破前低后快速反弹
        """
        if len(self.price_history) < 20:
            return None

        min_20 = min(self.price_history[-20:])
        min_5 = min(self.price_history[-5:])

        # 刚创新低后反弹
        if min_5 <= min_20 * 1.005 and current_price > min_5 * 1.02:
            # 检查是否有大量空头信号后反转
            recent_short_signals = [
                s for s in self.signal_history
                if s.direction == 'SHORT' and s.age_seconds < 300
            ]

            if len(recent_short_signals) >= 2:
                return {
                    'type': 'BEAR_TRAP',
                    'confidence': 70,
                    'breakdown_price': min_5,
                    'current_price': current_price,
                    'signal_count': len(recent_short_signals)
                }

        return None
