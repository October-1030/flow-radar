#!/usr/bin/env python3
"""
统一信号管理器 - UnifiedSignalManager

功能：
1. 从各检测器收集信号（iceberg/whale/liq）
2. 转换为统一的 SignalEvent 格式
3. 构建信号关联关系（related_signals）
4. 按优先级排序（level_rank, type_rank）
5. 降噪去重

设计原则：
- 不改动现有检测器（IcebergDetector 等）
- 作为适配器层，将各检测器的输出转换为 SignalEvent
- Phase 1 只做信号聚合和关联，不做复杂的融合判断

作者：Claude Code
日期：2026-01-08
版本：v1.0（三方会谈第二十二轮共识 - 工作 2.4）
参考：docs/P3-2_multi_signal_design.md v1.2
"""

from typing import List, Dict, Optional, Set, Tuple
from datetime import datetime
import time

from core.signal_schema import SignalEvent, IcebergSignal, WhaleSignal, LiqSignal
from config.p3_settings import (
    sort_signals_by_priority,
    get_signal_priority,
    get_dedup_window,
    SIGNAL_CORRELATION_WINDOW,
    PRICE_BUCKET_PRECISION
)


# ==================== 统一信号管理器 ====================

class UnifiedSignalManager:
    """
    统一信号管理器

    负责：
    1. 收集各类信号（iceberg/whale/liq）
    2. 转换为 SignalEvent 格式
    3. 构建 related_signals
    4. 排序和去重

    不负责：
    - 信号检测逻辑（由各检测器负责）
    - 告警推送（由 AlertMonitor 负责）
    """

    def __init__(self):
        """初始化统一信号管理器"""
        # 信号历史记录（用于关联和去重）
        self._signal_history: List[SignalEvent] = []
        self._signal_keys: Set[str] = set()  # 用于快速查找

        # 统计信息
        self._stats = {
            'total_collected': 0,
            'deduplicated': 0,
            'correlated': 0,
        }


    def collect_signals(
        self,
        icebergs: Optional[List] = None,
        whales: Optional[List] = None,
        liqs: Optional[List] = None
    ) -> List[SignalEvent]:
        """
        收集所有类型的信号并转换为统一格式

        Args:
            icebergs: 冰山信号列表（来自 IcebergDetector）
            whales: 鲸鱼信号列表（来自 WhaleDetector，预留）
            liqs: 清算信号列表（来自 LiquidationMonitor，预留）

        Returns:
            统一格式的信号列表（SignalEvent）
        """
        all_signals = []

        # 转换冰山信号
        if icebergs:
            for iceberg in icebergs:
                signal = self._convert_iceberg(iceberg)
                if signal:
                    all_signals.append(signal)
                    self._stats['total_collected'] += 1

        # 转换鲸鱼信号（预留）
        if whales:
            for whale in whales:
                signal = self._convert_whale(whale)
                if signal:
                    all_signals.append(signal)
                    self._stats['total_collected'] += 1

        # 转换清算信号（预留）
        if liqs:
            for liq in liqs:
                signal = self._convert_liq(liq)
                if signal:
                    all_signals.append(signal)
                    self._stats['total_collected'] += 1

        return all_signals


    def process_signals(self, signals: List[SignalEvent]) -> List[SignalEvent]:
        """
        处理信号：建立关联、排序、去重

        Args:
            signals: 原始信号列表

        Returns:
            处理后的信号列表
        """
        if not signals:
            return []

        # 1. 建立信号关联
        signals = self._build_related_signals(signals)

        # 2. 去重（基于 key 和时间窗口）
        signals = self._deduplicate(signals)

        # 3. 按优先级排序
        signals = sort_signals_by_priority(signals)

        # 4. 更新历史记录
        self._update_history(signals)

        return signals


    # ==================== 信号转换适配器 ====================

    def _convert_iceberg(self, iceberg) -> Optional[IcebergSignal]:
        """
        转换冰山信号为 SignalEvent 格式

        Args:
            iceberg: 原始冰山信号对象（可能是 dict 或自定义类）

        Returns:
            IcebergSignal 对象
        """
        try:
            # 如果已经是 IcebergSignal，直接返回
            if isinstance(iceberg, IcebergSignal):
                return iceberg

            # 如果是字典，转换为 IcebergSignal
            if isinstance(iceberg, dict):
                # 兼容旧格式：可能有 'data' 嵌套
                data = iceberg.get('data', {})

                return IcebergSignal(
                    ts=iceberg.get('ts', time.time()),
                    symbol=iceberg.get('symbol', data.get('symbol', '')),
                    side=iceberg.get('side', data.get('side', '')),
                    level=iceberg.get('level', data.get('level', '')),
                    confidence=iceberg.get('confidence', data.get('confidence', 0.0)),
                    price=data.get('price') or iceberg.get('price'),
                    cumulative_filled=data.get('cumulative_filled', 0.0),
                    refill_count=data.get('refill_count', 0),
                    intensity=data.get('intensity', 0.0),
                    key=iceberg.get('key', self._generate_iceberg_key(iceberg)),
                    snippet_path=iceberg.get('snippet_path', ''),
                    offset=iceberg.get('offset', 0),
                    signal_type='iceberg'
                )

            # 如果是自定义对象，尝试读取属性
            return IcebergSignal(
                ts=getattr(iceberg, 'ts', time.time()),
                symbol=getattr(iceberg, 'symbol', ''),
                side=getattr(iceberg, 'side', ''),
                level=getattr(iceberg, 'level', ''),
                confidence=getattr(iceberg, 'confidence', 0.0),
                price=getattr(iceberg, 'price', None),
                cumulative_filled=getattr(iceberg, 'cumulative_filled', 0.0),
                refill_count=getattr(iceberg, 'refill_count', 0),
                intensity=getattr(iceberg, 'intensity', 0.0),
                key=getattr(iceberg, 'key', self._generate_iceberg_key(iceberg)),
                signal_type='iceberg'
            )

        except Exception as e:
            print(f"警告: 冰山信号转换失败: {e}")
            return None


    def _convert_whale(self, whale) -> Optional[WhaleSignal]:
        """
        转换鲸鱼信号为 SignalEvent 格式（预留）

        Args:
            whale: 原始鲸鱼信号对象

        Returns:
            WhaleSignal 对象
        """
        try:
            # 如果已经是 WhaleSignal，直接返回
            if isinstance(whale, WhaleSignal):
                return whale

            # 如果是字典
            if isinstance(whale, dict):
                return WhaleSignal(
                    ts=whale.get('ts', time.time()),
                    symbol=whale.get('symbol', ''),
                    side=whale.get('side', ''),
                    level=whale.get('level', ''),
                    confidence=whale.get('confidence', 0.0),
                    price=whale.get('price'),
                    trade_volume=whale.get('trade_volume', 0.0),
                    trade_count=whale.get('trade_count', 0),
                    key=whale.get('key', self._generate_whale_key(whale)),
                    signal_type='whale'
                )

            # 预留：从自定义对象转换
            return None

        except Exception as e:
            print(f"警告: 鲸鱼信号转换失败: {e}")
            return None


    def _convert_liq(self, liq) -> Optional[LiqSignal]:
        """
        转换清算信号为 SignalEvent 格式（预留）

        Args:
            liq: 原始清算信号对象

        Returns:
            LiqSignal 对象
        """
        try:
            # 如果已经是 LiqSignal，直接返回
            if isinstance(liq, LiqSignal):
                return liq

            # 如果是字典
            if isinstance(liq, dict):
                return LiqSignal(
                    ts=liq.get('ts', time.time()),
                    symbol=liq.get('symbol', ''),
                    side=liq.get('side', ''),
                    level=liq.get('level', ''),
                    confidence=liq.get('confidence', 0.0),
                    price=liq.get('price'),
                    liquidation_volume=liq.get('liquidation_volume', 0.0),
                    liquidation_count=liq.get('liquidation_count', 0),
                    is_cascade=liq.get('is_cascade', False),
                    key=liq.get('key', self._generate_liq_key(liq)),
                    signal_type='liq'
                )

            # 预留：从自定义对象转换
            return None

        except Exception as e:
            print(f"警告: 清算信号转换失败: {e}")
            return None


    # ==================== Key 生成器 ====================

    def _generate_iceberg_key(self, signal) -> str:
        """
        生成冰山信号的 key

        格式: iceberg:{symbol}:{side}:{level}:{price_bucket}
        示例: iceberg:DOGE/USDT:BUY:CONFIRMED:0.1508
        """
        symbol = signal.get('symbol', '') if isinstance(signal, dict) else getattr(signal, 'symbol', '')
        side = signal.get('side', '') if isinstance(signal, dict) else getattr(signal, 'side', '')
        level = signal.get('level', '') if isinstance(signal, dict) else getattr(signal, 'level', '')
        price = signal.get('price') if isinstance(signal, dict) else getattr(signal, 'price', None)

        if price:
            price_bucket = round(price, PRICE_BUCKET_PRECISION)
        else:
            price_bucket = 0.0

        return f"iceberg:{symbol}:{side}:{level}:{price_bucket}"


    def _generate_whale_key(self, signal) -> str:
        """
        生成鲸鱼信号的 key

        格式: whale:{symbol}:{side}:{level}:{time_bucket}
        示例: whale:DOGE/USDT:BUY:CONFIRMED:2026-01-08T10:30
        """
        symbol = signal.get('symbol', '')
        side = signal.get('side', '')
        level = signal.get('level', '')
        ts = signal.get('ts', time.time())

        # 5 分钟时间桶
        dt = datetime.fromtimestamp(ts)
        time_bucket = dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
        time_str = time_bucket.strftime('%Y-%m-%dT%H:%M')

        return f"whale:{symbol}:{side}:{level}:{time_str}"


    def _generate_liq_key(self, signal) -> str:
        """
        生成清算信号的 key

        格式: liq:{symbol}:{side}:{level}:market
        示例: liq:DOGE/USDT:SELL:CRITICAL:market
        """
        symbol = signal.get('symbol', '')
        side = signal.get('side', '')
        level = signal.get('level', '')

        return f"liq:{symbol}:{side}:{level}:market"


    # ==================== 信号关联 ====================

    def _build_related_signals(self, signals: List[SignalEvent]) -> List[SignalEvent]:
        """
        构建信号关联关系

        关联规则：
        1. 时间窗口内（默认 5 分钟）
        2. 同一交易对（symbol）
        3. 同一方向（side）或反向（可选）

        Args:
            signals: 信号列表

        Returns:
            添加了 related_signals 的信号列表
        """
        if not signals:
            return signals

        # 按时间排序
        signals_sorted = sorted(signals, key=lambda s: s.ts)

        # 为每个信号查找相关信号
        for i, signal in enumerate(signals_sorted):
            related_keys = []

            # 向前查找（时间窗口内的历史信号）
            for prev_signal in reversed(self._signal_history[-50:]):  # 只看最近 50 个
                if signal.ts - prev_signal.ts > SIGNAL_CORRELATION_WINDOW:
                    break  # 超出时间窗口

                if self._is_related(signal, prev_signal):
                    related_keys.append(prev_signal.key)

            # 向后查找（当前批次的后续信号）
            for j in range(i + 1, len(signals_sorted)):
                next_signal = signals_sorted[j]

                if next_signal.ts - signal.ts > SIGNAL_CORRELATION_WINDOW:
                    break  # 超出时间窗口

                if self._is_related(signal, next_signal):
                    related_keys.append(next_signal.key)

            # 更新 related_signals
            if related_keys:
                signal.related_signals = list(set(related_keys))  # 去重
                self._stats['correlated'] += 1

        return signals_sorted


    def _is_related(self, signal1: SignalEvent, signal2: SignalEvent) -> bool:
        """
        判断两个信号是否相关

        Args:
            signal1: 信号 1
            signal2: 信号 2

        Returns:
            True: 相关
            False: 不相关
        """
        # 同一信号，不关联
        if signal1.key == signal2.key:
            return False

        # 不同交易对，不关联
        if signal1.symbol != signal2.symbol:
            return False

        # 相同方向，可能关联
        if signal1.side == signal2.side:
            return True

        # 反向信号，也可能关联（例如：买卖压力对冲）
        # Phase 1 先简化，只关联同向信号
        return False


    # ==================== 降噪去重 ====================

    def _deduplicate(self, signals: List[SignalEvent]) -> List[SignalEvent]:
        """
        降噪去重

        去重规则：
        1. 相同 key 的信号
        2. 时间窗口内（根据 level 决定）

        Args:
            signals: 信号列表

        Returns:
            去重后的信号列表
        """
        if not signals:
            return signals

        unique_signals = []
        seen_keys = {}  # key -> latest_ts

        for signal in signals:
            # 获取该级别的去重时间窗口
            dedup_window = get_dedup_window(signal.level)

            # 检查是否重复
            if signal.key in seen_keys:
                last_ts = seen_keys[signal.key]

                # 在去重窗口内，跳过
                if signal.ts - last_ts < dedup_window:
                    self._stats['deduplicated'] += 1
                    continue

            # 不重复，添加到结果
            unique_signals.append(signal)
            seen_keys[signal.key] = signal.ts

        return unique_signals


    def _update_history(self, signals: List[SignalEvent]):
        """
        更新信号历史记录

        Args:
            signals: 新信号列表
        """
        self._signal_history.extend(signals)
        self._signal_keys.update(s.key for s in signals)

        # 保留最近 1000 个信号（避免内存溢出）
        if len(self._signal_history) > 1000:
            removed = self._signal_history[:len(self._signal_history) - 1000]
            self._signal_history = self._signal_history[-1000:]

            # 更新 key 集合
            self._signal_keys -= {s.key for s in removed}


    # ==================== 工具方法 ====================

    def get_stats(self) -> Dict[str, int]:
        """
        获取统计信息

        Returns:
            统计字典
        """
        return {
            **self._stats,
            'history_size': len(self._signal_history),
        }


    def clear_history(self):
        """清空历史记录"""
        self._signal_history.clear()
        self._signal_keys.clear()
        self._stats = {
            'total_collected': 0,
            'deduplicated': 0,
            'correlated': 0,
        }


    def process_signals_v2(
        self,
        signals: List[SignalEvent],
        price: Optional[float] = None,
        symbol: Optional[str] = None
    ) -> Dict:
        """
        Phase 2 增强版信号处理流程

        流程:
        1. 信号融合（填充 related_signals）
        2. 置信度调整（计算 confidence_modifier）
        3. 冲突解决（处理 BUY vs SELL）
        4. 优先级排序
        5. 降噪去重
        6. 生成综合建议（可选：布林带环境过滤）

        Args:
            signals: 原始信号列表
            price: 当前价格（用于布林带环境评估，可选）
            symbol: 交易对符号（可选）

        Returns:
            Dict: {
                'signals': List[SignalEvent],  # 处理后的信号
                'advice': Dict,                # 综合建议（来自 BundleAdvisor）
                'stats': Dict                  # 统计信息
            }

        Example:
            >>> manager = UnifiedSignalManager()
            >>> signals = manager.collect_signals(icebergs=data)
            >>> result = manager.process_signals_v2(signals, price=0.15080, symbol='DOGE_USDT')
            >>> print(result['advice']['advice'])
            'STRONG_BUY'
        """
        if not signals:
            return {
                'signals': [],
                'advice': self._no_advice_result(),
                'stats': self.get_stats()
            }

        # 导入 Phase 2 模块
        from core.signal_fusion_engine import SignalFusionEngine
        from core.confidence_modifier import ConfidenceModifier
        from core.conflict_resolver import ConflictResolver
        from core.bundle_advisor import BundleAdvisor

        # 步骤 1: 信号融合（填充 related_signals）
        fusion_engine = SignalFusionEngine()
        relations = fusion_engine.batch_find_relations(signals)

        # 将关联结果填充到信号对象
        for signal in signals:
            signal.related_signals = relations.get(signal.key, [])

        # 步骤 2: 置信度调整（计算 confidence_modifier）
        modifier = ConfidenceModifier()
        modifier.batch_apply_modifiers(signals, relations)

        # 步骤 3: 冲突解决（处理 BUY vs SELL）
        resolver = ConflictResolver()
        signals = resolver.resolve_conflicts(signals)

        # 步骤 4: 优先级排序
        signals = sort_signals_by_priority(signals)

        # 步骤 5: 降噪去重（复用 Phase 1 逻辑）
        signals = self._deduplicate(signals)

        # 步骤 6: 生成综合建议（支持布林带环境过滤）
        from config.settings import CONFIG_FEATURES
        use_bollinger = CONFIG_FEATURES.get('use_bollinger_regime', False)

        advisor = BundleAdvisor(use_bollinger=use_bollinger)
        advice = advisor.generate_advice(signals, price=price, symbol=symbol)

        # 步骤 7: 更新历史记录
        self._update_history(signals)

        # 步骤 8: 组合统计信息
        stats = self.get_stats()
        stats['advice'] = advice['advice']
        stats['advice_confidence'] = advice['confidence']
        stats['fusion_stats'] = fusion_engine.get_stats()
        stats['conflict_stats'] = resolver.get_stats()

        return {
            'signals': signals,
            'advice': advice,
            'stats': stats
        }


    def _no_advice_result(self) -> Dict:
        """
        返回无建议结果（信号不足）

        Returns:
            空建议字典
        """
        return {
            'advice': 'WATCH',
            'buy_score': 0.0,
            'sell_score': 0.0,
            'weighted_buy': 0.0,
            'weighted_sell': 0.0,
            'buy_count': 0,
            'sell_count': 0,
            'confidence': 0.0,
            'reason': '信号不足，无法生成建议。'
        }


    def __repr__(self) -> str:
        """字符串表示"""
        stats = self.get_stats()
        return (
            f"UnifiedSignalManager("
            f"collected={stats['total_collected']}, "
            f"deduplicated={stats['deduplicated']}, "
            f"correlated={stats['correlated']}, "
            f"history={stats['history_size']})"
        )
