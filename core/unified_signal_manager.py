"""
Flow Radar - Unified Signal Manager
流动性雷达 - 统一信号管理器

统一管理多来源信号（iceberg/whale/liq/kgod），实现优先级排序、去重、升级覆盖。

核心功能：
    - 多信号收集（线程安全）
    - 基于优先级排序（level_rank > type_rank > timestamp）
    - Key-based 去重（时间窗口内同 key 只保留最高优先级）
    - 升级覆盖规则（低优先级信号被高优先级替换）
    - 统计信息查询

作者: Claude Code
日期: 2026-01-10
工作编号: 2.4
依赖模块:
    - core/signal_schema.py (SignalEvent 数据结构)
    - config/p3_settings.py (优先级配置)
"""

from collections import deque
from typing import Dict, List, Any, Optional, Tuple
import threading
import time

from core.signal_schema import SignalEvent, SignalSide, SignalLevel, SignalType
from config.p3_settings import get_sort_key


class UnifiedSignalManager:
    """
    统一信号管理器

    职责：
        - 收集多来源信号（iceberg/whale/liq/kgod）
        - 基于 priority (level_rank, type_rank) 排序
        - Key-based 去重（时间窗口内同 key 只保留优先级最高的）
        - 升级覆盖规则：低优先级信号被高优先级替换
        - 线程安全操作

    内部数据结构：
        _signals: deque[SignalEvent] - 有序信号队列（最多 maxlen 个）
        _signal_index: Dict[str, Dict] - 快速查找索引（key -> 信号元数据）
        _lock: threading.Lock - 线程锁（保证并发安全）

    使用示例：
        >>> manager = UnifiedSignalManager(maxlen=1000)
        >>> signal = SignalEvent(...)
        >>> manager.add_signal(signal)
        >>> top_signals = manager.get_top_signals(n=5)
        >>> stats = manager.get_stats()
    """

    def __init__(self, maxlen: int = 1000):
        """
        初始化信号管理器

        Args:
            maxlen: 信号队列最大长度（超过时自动删除最旧信号）
        """
        # 有序信号队列（按添加顺序）
        self._signals: deque[SignalEvent] = deque(maxlen=maxlen)

        # 信号索引（key -> 元数据）
        # value = {
        #     'signal': SignalEvent,       # 信号对象
        #     'last_ts': float,            # 最后更新时间
        #     'suppressed_count': int      # 被抑制的同 key 信号数量
        # }
        self._signal_index: Dict[str, Dict[str, Any]] = {}

        # 线程锁
        self._lock: threading.Lock = threading.Lock()

        # 配置
        self._maxlen = maxlen

    def add_signal(self, signal: SignalEvent) -> None:
        """
        添加信号到管理器

        逻辑：
            1. 验证信号（signal.validate()）
            2. 检查是否存在同 key 信号
            3. 应用升级覆盖规则：
               - if new.sort_key < old.sort_key: 替换 old
               - elif sort_key 相同 and new.confidence > old.confidence: 替换 old
               - else: 保留 old，suppressed_count += 1
            4. 添加到 deque 和 index

        Args:
            signal: SignalEvent 对象

        Raises:
            ValueError: 如果信号验证失败
        """
        # 1. 验证信号
        try:
            signal.validate()
        except ValueError as e:
            raise ValueError(f"Signal validation failed: {e}")

        # 2. 获取信号的 sort_key
        new_sort_key = get_sort_key(signal)
        signal_key = signal.key

        with self._lock:
            # 3. 检查是否存在同 key 信号
            if signal_key in self._signal_index:
                old_entry = self._signal_index[signal_key]
                old_signal = old_entry['signal']
                old_sort_key = get_sort_key(old_signal)

                # 4. 应用升级覆盖规则
                should_replace = False

                # 规则 1: 新信号优先级更高（sort_key 更小）
                if new_sort_key < old_sort_key:
                    should_replace = True
                # 规则 2: 同优先级，新信号置信度更高
                elif new_sort_key == old_sort_key and signal.confidence > old_signal.confidence:
                    should_replace = True

                if should_replace:
                    # 替换旧信号
                    self._replace_signal(old_signal, signal)
                    self._signal_index[signal_key] = {
                        'signal': signal,
                        'last_ts': signal.ts,
                        'suppressed_count': old_entry.get('suppressed_count', 0)
                    }
                else:
                    # 保留旧信号，增加抑制计数
                    old_entry['suppressed_count'] = old_entry.get('suppressed_count', 0) + 1
            else:
                # 5. 新 key，直接添加
                old_len = len(self._signals)
                self._signals.append(signal)
                self._signal_index[signal_key] = {
                    'signal': signal,
                    'last_ts': signal.ts,
                    'suppressed_count': 0
                }

                # 检测 deque 溢出，清理 index（Critical Bug Fix）
                if len(self._signals) == old_len and old_len == self._maxlen:
                    # deque 满了，最旧信号被淘汰，需要同步清理 index
                    valid_keys = {sig.key for sig in self._signals}
                    for key in list(self._signal_index.keys()):
                        if key not in valid_keys:
                            del self._signal_index[key]

    def _replace_signal(self, old_signal: SignalEvent, new_signal: SignalEvent) -> None:
        """
        替换 deque 中的旧信号（优化版本）

        Args:
            old_signal: 旧信号对象
            new_signal: 新信号对象
        """
        # 重建 deque（对于 maxlen=1000，性能可接受，避免 O(n) 修改）
        new_signals = deque(maxlen=self._maxlen)
        replaced = False

        for sig in self._signals:
            if sig.key == old_signal.key and not replaced:
                new_signals.append(new_signal)
                replaced = True
            else:
                new_signals.append(sig)

        # 如果未找到（可能被 deque 淘汰），追加到末尾
        if not replaced:
            new_signals.append(new_signal)

        self._signals = new_signals

    def get_top_signals(self, n: int = 5) -> List[SignalEvent]:
        """
        获取优先级最高的 N 个信号

        排序规则：
            1. level_rank 升序（CRITICAL=1 最高）
            2. type_rank 升序（liq=1 最高）
            3. ts 降序（新信号优先）

        Args:
            n: 返回信号数量，默认 5

        Returns:
            排序后的信号列表（最多 n 个）

        Raises:
            ValueError: 如果 n <= 0
        """
        if n <= 0:
            raise ValueError(f"n must be positive, got {n}")

        with self._lock:
            # 复制信号列表（避免锁期间排序）
            signals = list(self._signals)

        # 按优先级排序
        sorted_signals = sorted(signals, key=get_sort_key)

        # 返回 top N
        return sorted_signals[:n]

    def flush(self) -> List[SignalEvent]:
        """
        清空并返回所有信号

        Returns:
            所有信号的列表（排序后）
        """
        with self._lock:
            # 复制信号列表
            signals = list(self._signals)

            # 清空队列和索引
            self._signals.clear()
            self._signal_index.clear()

        # 排序后返回
        return sorted(signals, key=get_sort_key)

    def dedupe_by_key(self, window_seconds: float = 60) -> None:
        """
        按 key 去重（时间窗口内）

        逻辑：
            1. 遍历 _signal_index
            2. 如果 last_ts < (now - window_seconds)：从 index 中移除
            3. 同时从 deque 中移除过期信号

        Args:
            window_seconds: 时间窗口（秒），默认 60

        Raises:
            ValueError: 如果 window_seconds <= 0
        """
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be positive, got {window_seconds}")

        now = time.time()
        cutoff_time = now - window_seconds

        with self._lock:
            # 1. 找出过期的 key
            expired_keys = []
            for key, entry in self._signal_index.items():
                if entry['last_ts'] < cutoff_time:
                    expired_keys.append(key)

            # 2. 从 index 中移除过期 key
            for key in expired_keys:
                del self._signal_index[key]

            # 3. 从 deque 中移除过期信号
            if expired_keys:
                # 创建新 deque，只保留未过期信号
                new_signals = deque(maxlen=self._maxlen)
                for signal in self._signals:
                    if signal.key not in expired_keys:
                        new_signals.append(signal)
                self._signals = new_signals

    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            {
                'total_signals': int,            # 总信号数
                'unique_keys': int,              # 唯一 key 数量
                'suppressed_total': int,         # 总抑制数
                'by_level': Dict[str, int],      # 按级别分组统计
                'by_type': Dict[str, int],       # 按类型分组统计
                'by_side': Dict[str, int]        # 按方向分组统计
            }
        """
        with self._lock:
            total_signals = len(self._signals)
            unique_keys = len(self._signal_index)

            # 计算总抑制数
            suppressed_total = sum(
                entry.get('suppressed_count', 0)
                for entry in self._signal_index.values()
            )

            # 按级别统计
            by_level: Dict[str, int] = {}
            for signal in self._signals:
                level = signal.level.value if isinstance(signal.level, SignalLevel) else signal.level
                by_level[level] = by_level.get(level, 0) + 1

            # 按类型统计
            by_type: Dict[str, int] = {}
            for signal in self._signals:
                sig_type = signal.signal_type.value if isinstance(signal.signal_type, SignalType) else signal.signal_type
                by_type[sig_type] = by_type.get(sig_type, 0) + 1

            # 按方向统计
            by_side: Dict[str, int] = {}
            for signal in self._signals:
                side = signal.side.value if isinstance(signal.side, SignalSide) else signal.side
                by_side[side] = by_side.get(side, 0) + 1

        return {
            'total_signals': total_signals,
            'unique_keys': unique_keys,
            'suppressed_total': suppressed_total,
            'by_level': by_level,
            'by_type': by_type,
            'by_side': by_side
        }

    # ==================== 可选方法（Phase 2 功能预留） ====================

    def cleanup_expired(self, max_age_seconds: float = 300) -> int:
        """
        清理过期信号

        Args:
            max_age_seconds: 信号最大保留时间（秒）

        Returns:
            清理的信号数量
        """
        pass

    def bundle_related_signals(self, window_ms: int = 500) -> List[List[SignalEvent]]:
        """
        聚合相关信号（时间窗口内）

        Args:
            window_ms: 时间窗口（毫秒）

        Returns:
            信号组列表（每组是时间相近的信号）
        """
        pass

    def apply_confidence_modifiers(self) -> None:
        """
        应用置信度调整器（Phase 2 功能预留）
        """
        pass

    # ==================== 辅助方法 ====================

    def get_signal_by_key(self, key: str) -> Optional[SignalEvent]:
        """
        根据 key 获取信号

        Args:
            key: 信号的唯一标识符

        Returns:
            信号对象，如果不存在则返回 None
        """
        with self._lock:
            entry = self._signal_index.get(key)
            return entry['signal'] if entry else None

    def contains_key(self, key: str) -> bool:
        """
        检查是否存在指定 key 的信号

        Args:
            key: 信号的唯一标识符

        Returns:
            True if key exists, False otherwise
        """
        with self._lock:
            return key in self._signal_index

    def size(self) -> int:
        """
        获取当前信号数量

        Returns:
            信号队列中的信号数量
        """
        with self._lock:
            return len(self._signals)

    def clear(self) -> None:
        """
        清空所有信号（不返回）
        """
        with self._lock:
            self._signals.clear()
            self._signal_index.clear()

    def get_suppressed_count(self, key: str) -> int:
        """
        获取指定 key 的抑制计数

        Args:
            key: 信号的唯一标识符

        Returns:
            抑制计数，如果 key 不存在则返回 0
        """
        with self._lock:
            entry = self._signal_index.get(key)
            return entry.get('suppressed_count', 0) if entry else 0


# ==================== 使用示例 ====================

def _example_usage():
    """使用示例（供文档参考）"""
    print("=" * 70)
    print("UnifiedSignalManager - 使用示例".center(70))
    print("=" * 70)

    # 1. 创建管理器
    manager = UnifiedSignalManager(maxlen=100)
    print("\n1. 创建管理器")
    print(f"   初始状态: {manager.size()} 个信号")

    # 2. 添加信号
    print("\n2. 添加信号")

    # 场景 1: 添加低优先级信号
    signal1 = SignalEvent(
        ts=1000.0,
        symbol="DOGE_USDT",
        side=SignalSide.BUY,
        level=SignalLevel.ACTIVITY,
        confidence=65.0,
        price=0.15,
        signal_type=SignalType.ICEBERG,
        key="iceberg:DOGE_USDT:BUY:ACTIVITY:price_0.15"
    )
    manager.add_signal(signal1)
    print(f"   添加 ACTIVITY 信号: {signal1.key}")
    print(f"   当前信号数: {manager.size()}")

    # 场景 2: 添加高优先级信号（不同 key，不会替换）
    signal2 = SignalEvent(
        ts=1001.0,
        symbol="DOGE_USDT",
        side=SignalSide.BUY,
        level=SignalLevel.CONFIRMED,
        confidence=85.0,
        price=0.15,
        signal_type=SignalType.ICEBERG,
        key="iceberg:DOGE_USDT:BUY:CONFIRMED:price_0.15"
    )
    manager.add_signal(signal2)
    print(f"   添加 CONFIRMED 信号: {signal2.key}")
    print(f"   当前信号数: {manager.size()}")

    # 场景 3: 添加不同类型信号
    signal3 = SignalEvent(
        ts=1002.0,
        symbol="BTC_USDT",
        side=SignalSide.SELL,
        level=SignalLevel.CRITICAL,
        confidence=95.0,
        price=42000.0,
        signal_type=SignalType.LIQ,
        key="liq:BTC_USDT:SELL:CRITICAL:price_42000"
    )
    manager.add_signal(signal3)
    print(f"   添加 CRITICAL/LIQ 信号: {signal3.key}")
    print(f"   当前信号数: {manager.size()}")

    # 场景 4: 添加低优先级信号（同 key，应被抑制）
    # 注意：使用旧时间戳，这样 sort_key 会更大（优先级更低）
    signal4 = SignalEvent(
        ts=999.0,  # 旧时间戳，sort_key = (1, 1, -999.0) > (1, 1, -1002.0)
        symbol="BTC_USDT",
        side=SignalSide.SELL,
        level=SignalLevel.CRITICAL,
        confidence=90.0,  # 置信度更低
        price=42000.0,
        signal_type=SignalType.LIQ,
        key="liq:BTC_USDT:SELL:CRITICAL:price_42000"
    )
    manager.add_signal(signal4)
    print(f"   添加重复 CRITICAL/LIQ 信号（旧时间戳+低置信度）")
    print(f"   当前信号数: {manager.size()} (应保持不变)")
    print(f"   抑制计数: {manager.get_suppressed_count(signal3.key)}")

    # 3. 获取 top 信号
    print("\n3. 获取优先级最高的 5 个信号")
    top_signals = manager.get_top_signals(n=5)
    for i, sig in enumerate(top_signals, 1):
        level_rank, type_rank, neg_ts = get_sort_key(sig)
        print(f"   {i}. [{sig.level.value:9}] {sig.signal_type.value:8} "
              f"| confidence={sig.confidence:.1f}% "
              f"| rank=({level_rank}, {type_rank})")

    # 4. 统计信息
    print("\n4. 统计信息")
    stats = manager.get_stats()
    print(f"   总信号数: {stats['total_signals']}")
    print(f"   唯一 key 数: {stats['unique_keys']}")
    print(f"   总抑制数: {stats['suppressed_total']}")
    print(f"   按级别: {stats['by_level']}")
    print(f"   按类型: {stats['by_type']}")
    print(f"   按方向: {stats['by_side']}")

    # 5. 去重测试（模拟时间流逝）
    print("\n5. 去重测试（窗口 = 2 秒）")
    print(f"   去重前信号数: {manager.size()}")
    time.sleep(0.1)  # 模拟时间流逝
    manager.dedupe_by_key(window_seconds=2.0)  # 窗口 2 秒，信号 ts=1000-1003，都应保留
    print(f"   去重后信号数: {manager.size()}")

    # 6. 清空
    print("\n6. 清空信号")
    flushed = manager.flush()
    print(f"   清空并返回 {len(flushed)} 个信号（排序后）")
    print(f"   清空后信号数: {manager.size()}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # 运行使用示例
    _example_usage()
