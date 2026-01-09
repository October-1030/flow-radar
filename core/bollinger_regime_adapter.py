#!/usr/bin/env python3
"""
Bollinger Regime Adapter - 布林带环境过滤器适配器
流动性雷达 - 将布林带过滤器集成到 Phase 2 系统

功能:
- 将 Phase 2 的信号和市场数据转换为布林带过滤器的输入
- 评估当前市场环境（允许回归/禁止回归/观望）
- 影响 BundleAdvisor 的最终操作建议

设计原则:
- 非侵入性：作为可选模块，不影响现有流程
- 配置化：通过 CONFIG_FEATURES 开关控制
- 订单流融合：使用 Phase 2 的订单流数据

作者: Claude Code (三方共识)
日期: 2026-01-09
版本: v1.0
参考: 第二十五轮三方共识
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

from core.bollinger_regime_filter import BollingerRegimeFilter, RegimeSignal, RegimeResult
from core.signal_schema import SignalEvent
from config.bollinger_settings import CONFIG_BOLLINGER_REGIME, CONFIG_BOLLINGER_BANDS


@dataclass
class RegimeContext:
    """环境上下文（从 Phase 2 信号中提取）"""
    price: float
    symbol: str
    timestamp: float

    # 订单流指标（从信号中聚合）
    delta_cumulative: float = 0.0
    delta_slope: float = 0.0
    absorption_ratio: float = 0.0
    imbalance: Optional[Dict] = None
    sweep_score: float = 0.0
    depth_depletion: float = 0.0
    acceptance_time: float = 0.0

    # 冰山信号
    iceberg_signals: Optional[List] = None


class BollingerRegimeAdapter:
    """
    布林带环境过滤器适配器

    职责:
    1. 从 SignalEvent 列表中提取订单流数据
    2. 调用 BollingerRegimeFilter 评估市场环境
    3. 返回环境判定结果，供 BundleAdvisor 参考

    使用场景:
    - BundleAdvisor 在生成操作建议前，先查询布林带环境
    - 如果环境判定为 BAN_REVERSION，则不应建议回归交易
    - 如果环境判定为 ALLOW_REVERSION，则增强回归信号的置信度
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化适配器

        Args:
            config: 配置字典（可选，默认使用 bollinger_settings.py）
        """
        if config is None:
            self.config = {
                'bollinger_bands': CONFIG_BOLLINGER_BANDS,
                'regime_filter': CONFIG_BOLLINGER_REGIME
            }
        else:
            self.config = config

        # 初始化布林带过滤器
        self.regime_filter = BollingerRegimeFilter(config=self.config)

        # 统计信息
        self._stats = {
            'total_evaluations': 0,
            'allow_reversion': 0,
            'ban_reversion': 0,
            'no_trade': 0
        }


    def evaluate_regime(
        self,
        price: float,
        signals: List[SignalEvent],
        symbol: str = "UNKNOWN"
    ) -> RegimeResult:
        """
        评估当前市场环境

        Args:
            price: 当前价格
            signals: Phase 2 处理后的信号列表
            symbol: 交易对符号

        Returns:
            RegimeResult: 环境判定结果
        """
        # 1. 从信号中提取订单流数据
        context = self._extract_context(price, signals, symbol)

        # 2. 调用布林带过滤器
        result = self.regime_filter.evaluate(
            price=context.price,
            delta_cumulative=context.delta_cumulative,
            delta_slope=context.delta_slope,
            absorption_ratio=context.absorption_ratio,
            imbalance=context.imbalance,
            sweep_score=context.sweep_score,
            iceberg_signals=context.iceberg_signals,
            acceptance_time=context.acceptance_time,
            depth_depletion=context.depth_depletion
        )

        # 3. 更新统计
        self._stats['total_evaluations'] += 1
        if result.signal == RegimeSignal.ALLOW_REVERSION_SHORT or \
           result.signal == RegimeSignal.ALLOW_REVERSION_LONG:
            self._stats['allow_reversion'] += 1
        elif result.signal == RegimeSignal.BAN_REVERSION:
            self._stats['ban_reversion'] += 1
        else:
            self._stats['no_trade'] += 1

        return result


    def _extract_context(
        self,
        price: float,
        signals: List[SignalEvent],
        symbol: str
    ) -> RegimeContext:
        """
        从 SignalEvent 列表中提取订单流数据

        策略:
        - Delta: 从信号的 metadata 中提取（如果有）
        - 失衡: 根据 BUY/SELL 信号比例计算
        - 冰山信号: 提取 iceberg 类型的信号
        - 吸收率: 从 metadata 中提取（如果有）

        Args:
            price: 当前价格
            signals: 信号列表
            symbol: 交易对

        Returns:
            RegimeContext: 环境上下文
        """
        context = RegimeContext(
            price=price,
            symbol=symbol,
            timestamp=signals[0].ts if signals else 0.0
        )

        # 统计 BUY/SELL 信号比例
        buy_signals = [s for s in signals if s.side == "BUY"]
        sell_signals = [s for s in signals if s.side == "SELL"]

        total = len(buy_signals) + len(sell_signals)
        if total > 0:
            context.imbalance = {
                "buy_ratio": len(buy_signals) / total,
                "sell_ratio": len(sell_signals) / total
            }

        # 提取冰山信号
        iceberg_signals = []
        for signal in signals:
            if signal.signal_type == "iceberg":
                # 转换为布林带过滤器需要的格式
                iceberg_signals.append(self._convert_to_iceberg_signal(signal))

        if iceberg_signals:
            context.iceberg_signals = iceberg_signals

        # 从信号 metadata 中提取订单流指标（如果有）
        for signal in signals:
            # 尝试获取 metadata 属性（可能不存在）
            metadata = getattr(signal, 'metadata', None) or {}

            # Delta 相关
            if 'delta_cumulative' in metadata:
                context.delta_cumulative = metadata['delta_cumulative']
            if 'delta_slope' in metadata:
                context.delta_slope = metadata['delta_slope']

            # 吸收率
            if 'absorption_ratio' in metadata:
                context.absorption_ratio = metadata['absorption_ratio']

            # 扫单得分
            if 'sweep_score' in metadata:
                context.sweep_score = metadata['sweep_score']

            # 深度耗尽
            if 'depth_depletion' in metadata:
                context.depth_depletion = metadata['depth_depletion']

        return context


    def _convert_to_iceberg_signal(self, signal: SignalEvent):
        """
        转换 SignalEvent 为布林带过滤器的冰山信号格式

        Args:
            signal: SignalEvent 对象

        Returns:
            简单对象，包含 side 和 level 属性
        """
        from dataclasses import dataclass

        @dataclass
        class SimpleIcebergSignal:
            side: str
            level: str

        return SimpleIcebergSignal(
            side=signal.side,
            level=signal.level
        )


    def should_allow_reversion(
        self,
        price: float,
        signals: List[SignalEvent],
        direction: str,  # "SHORT" or "LONG"
        symbol: str = "UNKNOWN"
    ) -> tuple[bool, float, str]:
        """
        简化接口：判断是否允许回归交易

        Args:
            price: 当前价格
            signals: 信号列表
            direction: 回归方向（"SHORT" 或 "LONG"）
            symbol: 交易对

        Returns:
            (是否允许, 置信度, 原因)
        """
        result = self.evaluate_regime(price, signals, symbol)

        # 判断是否允许
        if direction == "SHORT":
            allowed = result.signal == RegimeSignal.ALLOW_REVERSION_SHORT
        elif direction == "LONG":
            allowed = result.signal == RegimeSignal.ALLOW_REVERSION_LONG
        else:
            allowed = False

        # 如果禁止回归，返回 False
        if result.signal == RegimeSignal.BAN_REVERSION:
            reason = f"走轨风险 (ban_score={result.ban_score:.1f})"
            return False, 0.0, reason

        # 如果证据不足，返回 False
        if result.signal == RegimeSignal.NO_TRADE:
            reason = "证据不足"
            return False, 0.0, reason

        # 如果允许回归
        if allowed:
            reason = f"回归信号确认 (triggers={', '.join(result.triggers[:3])})"
            return True, result.confidence, reason
        else:
            reason = "方向不匹配"
            return False, 0.0, reason


    def get_regime_summary(
        self,
        price: float,
        signals: List[SignalEvent],
        symbol: str = "UNKNOWN"
    ) -> Dict:
        """
        获取环境摘要（用于日志和调试）

        Args:
            price: 当前价格
            signals: 信号列表
            symbol: 交易对

        Returns:
            环境摘要字典
        """
        result = self.evaluate_regime(price, signals, symbol)

        # 格式化信号名称
        signal_name = {
            RegimeSignal.ALLOW_REVERSION_SHORT: "允许做空回归",
            RegimeSignal.ALLOW_REVERSION_LONG: "允许做多回归",
            RegimeSignal.BAN_REVERSION: "禁止回归（走轨）",
            RegimeSignal.NO_TRADE: "观望（证据不足）"
        }.get(result.signal, "未知")

        return {
            'signal': signal_name,
            'signal_enum': result.signal.value,
            'confidence': result.confidence,
            'band_position': result.band_position,
            'triggers': result.triggers,
            'ban_score': result.ban_score,
            'reversion_score': result.reversion_score,
            'scenario': result.scenario,
            'bands': result.bands
        }


    def get_stats(self) -> Dict:
        """获取统计信息"""
        total = self._stats['total_evaluations']

        return {
            **self._stats,
            'allow_reversion_pct': self._stats['allow_reversion'] / total * 100 if total > 0 else 0,
            'ban_reversion_pct': self._stats['ban_reversion'] / total * 100 if total > 0 else 0,
            'no_trade_pct': self._stats['no_trade'] / total * 100 if total > 0 else 0
        }


    def reset(self):
        """重置适配器和过滤器"""
        self.regime_filter.reset_loss_counter()
        self._stats = {
            'total_evaluations': 0,
            'allow_reversion': 0,
            'ban_reversion': 0,
            'no_trade': 0
        }


# ==================== 便捷函数 ====================

def create_regime_adapter(config: Optional[Dict] = None) -> BollingerRegimeAdapter:
    """
    工厂函数：创建布林带环境适配器

    Args:
        config: 配置字典（可选）

    Returns:
        BollingerRegimeAdapter 实例
    """
    return BollingerRegimeAdapter(config=config)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Bollinger Regime Adapter - 测试")
    print("=" * 60)

    # 创建适配器
    adapter = create_regime_adapter()

    # 模拟信号
    from core.signal_schema import IcebergSignal

    signals = [
        IcebergSignal(
            symbol="DOGE_USDT",
            side="SELL",
            level="CONFIRMED",
            confidence=0.85,
            price=0.15068,
            strength=3.41,
            ts=1704700000.0
        )
    ]

    # 评估环境
    price = 0.15080
    result = adapter.evaluate_regime(price, signals, "DOGE_USDT")

    print(f"\n当前价格: {price}")
    print(f"信号: {result.signal.value}")
    print(f"置信度: {result.confidence:.1%}")
    print(f"位置: {result.band_position}")
    print(f"触发因素: {', '.join(result.triggers)}")

    # 判断是否允许回归
    allowed, conf, reason = adapter.should_allow_reversion(
        price, signals, "SHORT", "DOGE_USDT"
    )

    print(f"\n是否允许做空回归: {allowed}")
    print(f"置信度: {conf:.1%}")
    print(f"原因: {reason}")

    # 统计信息
    print(f"\n统计信息:")
    stats = adapter.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n✅ 适配器测试完成")
