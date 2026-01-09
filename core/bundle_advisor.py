#!/usr/bin/env python3
"""
P3-2 多信号综合判断系统 - 综合建议生成器

功能：
1. 生成多信号综合操作建议（STRONG_BUY/BUY/WATCH/SELL/STRONG_SELL）
2. 计算买卖方向得分（加权）
3. 生成建议理由
4. 格式化 Bundle 告警消息

算法：
- weighted_buy = sum(confidence * type_weight * level_weight for BUY signals)
- weighted_sell = sum(confidence * type_weight * level_weight for SELL signals)
- advice = STRONG_BUY if weighted_buy / weighted_sell > 1.5
           BUY if weighted_buy > weighted_sell
           WATCH if ratio ~= 1.0
           SELL/STRONG_SELL 类似

作者：Claude Code
日期：2026-01-09
版本：v2.0（Phase 2）
"""

from typing import List, Dict, Optional
from datetime import datetime

from core.signal_schema import SignalEvent
from config.p3_fusion_config import (
    STRONG_BUY_THRESHOLD,
    STRONG_SELL_THRESHOLD,
    get_bundle_type_weight,
    get_bundle_level_weight,
    MIN_SIGNALS_FOR_ADVICE,
    ADVICE_CONFIDENCE_WEIGHT,
    ADVICE_COUNT_WEIGHT,
)

# 布林带环境过滤器（可选）
try:
    from core.bollinger_regime_adapter import BollingerRegimeAdapter
    from core.bollinger_regime_filter import RegimeSignal
    BOLLINGER_AVAILABLE = True
except ImportError:
    BOLLINGER_AVAILABLE = False


class BundleAdvisor:
    """
    综合建议生成器

    负责根据多个信号生成综合操作建议
    """

    def __init__(self, config=None, use_bollinger=False):
        """
        初始化综合建议生成器

        Args:
            config: 配置模块（默认使用 p3_fusion_config）
            use_bollinger: 是否使用布林带环境过滤器（默认 False）
        """
        if config is None:
            from config import p3_fusion_config as config

        self.config = config
        self.use_bollinger = use_bollinger and BOLLINGER_AVAILABLE

        # 初始化布林带适配器（如果启用）
        if self.use_bollinger:
            self.bollinger_adapter = BollingerRegimeAdapter()
        else:
            self.bollinger_adapter = None

    def generate_advice(
        self,
        signals: List[SignalEvent],
        price: Optional[float] = None,
        symbol: Optional[str] = None
    ) -> Dict:
        """
        生成综合操作建议

        Args:
            signals: 处理后的信号列表（已关联、已调整置信度、已解决冲突）
            price: 当前价格（用于布林带环境评估，可选）
            symbol: 交易对符号（可选）

        Returns:
            Dict: {
                'advice': 'STRONG_BUY' | 'BUY' | 'WATCH' | 'SELL' | 'STRONG_SELL',
                'buy_score': 240.0,        # BUY 信号总置信度
                'sell_score': 65.0,        # SELL 信号总置信度
                'weighted_buy': 360.0,     # BUY 加权得分
                'weighted_sell': 65.0,     # SELL 加权得分
                'buy_count': 3,            # BUY 信号数量
                'sell_count': 1,           # SELL 信号数量
                'confidence': 0.85,        # 建议置信度
                'reason': '...',           # 建议理由
                'bollinger_regime': {...}  # 布林带环境信息（如果启用）
            }

        Example:
            >>> advisor = BundleAdvisor(use_bollinger=True)
            >>> advice = advisor.generate_advice(signals, price=0.15080, symbol='DOGE_USDT')
            >>> print(advice['advice'])
            'STRONG_BUY'
        """
        # 检查最小信号数
        if len(signals) < MIN_SIGNALS_FOR_ADVICE:
            return self._no_advice_result()

        # 计算买卖方向得分
        buy_signals = [s for s in signals if s.side == 'BUY']
        sell_signals = [s for s in signals if s.side == 'SELL']

        buy_score = sum(s.confidence for s in buy_signals)
        sell_score = sum(s.confidence for s in sell_signals)

        weighted_buy = sum(
            s.confidence * get_bundle_type_weight(s.signal_type) * get_bundle_level_weight(s.level)
            for s in buy_signals
        )
        weighted_sell = sum(
            s.confidence * get_bundle_type_weight(s.signal_type) * get_bundle_level_weight(s.level)
            for s in sell_signals
        )

        # 确定建议级别
        advice = self._determine_advice_level(weighted_buy, weighted_sell)

        # 布林带环境检查（如果启用且提供价格）
        bollinger_regime = None
        if self.use_bollinger and price is not None and self.bollinger_adapter:
            bollinger_regime = self._apply_bollinger_regime(
                advice, price, signals, symbol or "UNKNOWN"
            )

            # 根据布林带判定调整建议
            if bollinger_regime['adjusted']:
                advice = bollinger_regime['final_advice']

        # 计算建议置信度
        confidence = self._calculate_advice_confidence(signals, advice, weighted_buy, weighted_sell)

        # 生成建议理由
        reason = self._generate_reason(signals, advice, buy_signals, sell_signals, bollinger_regime)

        result = {
            'advice': advice,
            'buy_score': buy_score,
            'sell_score': sell_score,
            'weighted_buy': weighted_buy,
            'weighted_sell': weighted_sell,
            'buy_count': len(buy_signals),
            'sell_count': len(sell_signals),
            'confidence': confidence,
            'reason': reason
        }

        # 添加布林带环境信息（如果有）
        if bollinger_regime:
            result['bollinger_regime'] = bollinger_regime

        return result

    def _determine_advice_level(self, weighted_buy: float, weighted_sell: float) -> str:
        """
        根据加权得分确定建议级别

        逻辑:
        - weighted_buy / weighted_sell > 1.5 → STRONG_BUY
        - weighted_buy > weighted_sell → BUY
        - weighted_sell / weighted_buy > 1.5 → STRONG_SELL
        - weighted_sell > weighted_buy → SELL
        - else → WATCH

        Args:
            weighted_buy: BUY 加权得分
            weighted_sell: SELL 加权得分

        Returns:
            建议级别
        """
        # 处理边界情况
        if weighted_buy == 0 and weighted_sell == 0:
            return 'WATCH'

        if weighted_sell == 0:
            return 'STRONG_BUY'

        if weighted_buy == 0:
            return 'STRONG_SELL'

        # 计算比率
        buy_sell_ratio = weighted_buy / weighted_sell

        if buy_sell_ratio > STRONG_BUY_THRESHOLD:
            return 'STRONG_BUY'
        elif buy_sell_ratio > 1.0:
            return 'BUY'
        elif buy_sell_ratio < 1.0 / STRONG_SELL_THRESHOLD:
            return 'STRONG_SELL'
        elif buy_sell_ratio < 1.0:
            return 'SELL'
        else:
            return 'WATCH'

    def _calculate_advice_confidence(
        self,
        signals: List[SignalEvent],
        advice: str,
        weighted_buy: float,
        weighted_sell: float
    ) -> float:
        """
        计算建议置信度

        置信度来源:
        - 70% 权重来自信号平均置信度
        - 30% 权重来自信号数量（归一化）

        Args:
            signals: 信号列表
            advice: 建议级别
            weighted_buy: BUY 加权得分
            weighted_sell: SELL 加权得分

        Returns:
            建议置信度 [0, 1]
        """
        if not signals:
            return 0.0

        # 计算信号平均置信度
        avg_confidence = sum(s.confidence for s in signals) / len(signals) / 100.0

        # 计算信号数量得分（归一化到 [0, 1]）
        # 假设 10 个信号为满分
        count_score = min(len(signals) / 10.0, 1.0)

        # 加权平均
        confidence = (
            avg_confidence * ADVICE_CONFIDENCE_WEIGHT +
            count_score * ADVICE_COUNT_WEIGHT
        )

        return confidence

    def _generate_reason(
        self,
        signals: List[SignalEvent],
        advice: str,
        buy_signals: List[SignalEvent],
        sell_signals: List[SignalEvent],
        bollinger_regime: Optional[Dict] = None
    ) -> str:
        """
        生成建议理由

        Args:
            signals: 所有信号
            advice: 建议级别
            buy_signals: BUY 信号列表
            sell_signals: SELL 信号列表
            bollinger_regime: 布林带环境信息（可选）

        Returns:
            建议理由文本
        """
        reasons = []

        # 统计高置信度信号
        high_conf_buy = [s for s in buy_signals if s.confidence >= 75]
        high_conf_sell = [s for s in sell_signals if s.confidence >= 75]

        # 统计有共振增强的信号
        resonance_buy = [s for s in buy_signals
                        if s.confidence_modifier.get('resonance_boost', 0) > 0]
        resonance_sell = [s for s in sell_signals
                         if s.confidence_modifier.get('resonance_boost', 0) > 0]

        # 统计有冲突惩罚的信号
        conflict_buy = [s for s in buy_signals
                       if s.confidence_modifier.get('conflict_penalty', 0) < 0]
        conflict_sell = [s for s in sell_signals
                        if s.confidence_modifier.get('conflict_penalty', 0) < 0]

        # 生成理由
        if advice in ('STRONG_BUY', 'BUY'):
            if high_conf_buy:
                reasons.append(f"{len(high_conf_buy)} 个高置信度 BUY 信号")
            if resonance_buy:
                total_boost = sum(s.confidence_modifier.get('resonance_boost', 0)
                                for s in resonance_buy)
                reasons.append(f"形成共振（+{total_boost:.0f} 置信度增强）")
            if conflict_sell:
                reasons.append(f"{len(conflict_sell)} 个 SELL 信号因冲突被惩罚")

        elif advice in ('STRONG_SELL', 'SELL'):
            if high_conf_sell:
                reasons.append(f"{len(high_conf_sell)} 个高置信度 SELL 信号")
            if resonance_sell:
                total_boost = sum(s.confidence_modifier.get('resonance_boost', 0)
                                for s in resonance_sell)
                reasons.append(f"形成共振（+{total_boost:.0f} 置信度增强）")
            if conflict_buy:
                reasons.append(f"{len(conflict_buy)} 个 BUY 信号因冲突被惩罚")

        else:  # WATCH
            reasons.append(f"BUY 和 SELL 信号力量均衡")
            if conflict_buy or conflict_sell:
                reasons.append(f"多个信号存在冲突")

        # 添加布林带环境信息（如果有）
        if bollinger_regime and bollinger_regime.get('adjusted'):
            regime_info = bollinger_regime.get('signal', '未知')
            if bollinger_regime.get('banned'):
                reasons.append(f"布林带环境: {regime_info}（禁止回归）")
            elif bollinger_regime.get('allowed'):
                confidence = bollinger_regime.get('confidence', 0)
                reasons.append(f"布林带环境: {regime_info}（支持回归，置信度 {confidence:.0%}）")

        # 组合理由
        if reasons:
            return "，".join(reasons) + "。"
        else:
            return "综合判断。"

    def _apply_bollinger_regime(
        self,
        advice: str,
        price: float,
        signals: List[SignalEvent],
        symbol: str
    ) -> Dict:
        """
        应用布林带环境过滤

        Args:
            advice: 初步建议
            price: 当前价格
            signals: 信号列表
            symbol: 交易对符号

        Returns:
            布林带环境信息字典 {
                'signal': '环境信号名称',
                'confidence': 0.85,
                'adjusted': True/False,  # 是否调整了建议
                'final_advice': '最终建议',
                'banned': True/False,    # 是否禁止回归
                'allowed': True/False,   # 是否允许回归
                'reason': '判定理由'
            }
        """
        # 评估布林带环境
        regime_result = self.bollinger_adapter.evaluate_regime(price, signals, symbol)

        # 信号名称映射
        signal_name = {
            RegimeSignal.ALLOW_REVERSION_SHORT: "允许做空回归",
            RegimeSignal.ALLOW_REVERSION_LONG: "允许做多回归",
            RegimeSignal.BAN_REVERSION: "禁止回归（走轨）",
            RegimeSignal.NO_TRADE: "观望（证据不足）"
        }.get(regime_result.signal, "未知")

        regime_info = {
            'signal': signal_name,
            'signal_enum': regime_result.signal.value,
            'confidence': regime_result.confidence,
            'band_position': regime_result.band_position,
            'triggers': regime_result.triggers,
            'ban_score': regime_result.ban_score,
            'reversion_score': regime_result.reversion_score,
            'adjusted': False,
            'final_advice': advice,
            'banned': False,
            'allowed': False,
            'reason': ''
        }

        # 根据布林带判定调整建议
        if regime_result.signal == RegimeSignal.BAN_REVERSION:
            # 禁止回归：如果建议是 BUY/SELL，改为 WATCH
            if advice in ('STRONG_BUY', 'BUY', 'STRONG_SELL', 'SELL'):
                regime_info['adjusted'] = True
                regime_info['final_advice'] = 'WATCH'
                regime_info['banned'] = True
                regime_info['reason'] = f"走轨风险（ban_score={regime_result.ban_score:.1f}）"

        elif regime_result.signal == RegimeSignal.ALLOW_REVERSION_SHORT:
            # 允许做空回归：支持 SELL 建议
            if advice in ('STRONG_SELL', 'SELL'):
                regime_info['allowed'] = True
                regime_info['reason'] = f"回归信号确认（{', '.join(regime_result.triggers[:2])}）"
            # 如果建议是 BUY 但布林带建议做空回归，可能需要调整
            elif advice in ('STRONG_BUY', 'BUY'):
                # 这里可以选择降级为 WATCH 或保持原建议
                # 暂时保持原建议，但标记冲突
                regime_info['reason'] = "与信号方向冲突"

        elif regime_result.signal == RegimeSignal.ALLOW_REVERSION_LONG:
            # 允许做多回归：支持 BUY 建议
            if advice in ('STRONG_BUY', 'BUY'):
                regime_info['allowed'] = True
                regime_info['reason'] = f"回归信号确认（{', '.join(regime_result.triggers[:2])}）"
            # 如果建议是 SELL 但布林带建议做多回归
            elif advice in ('STRONG_SELL', 'SELL'):
                regime_info['reason'] = "与信号方向冲突"

        elif regime_result.signal == RegimeSignal.NO_TRADE:
            # 证据不足：不调整建议
            regime_info['reason'] = "布林带证据不足"

        return regime_info

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

    def format_bundle_alert(self, advice_data: Dict, signals: List[SignalEvent]) -> str:
        """
        格式化 Bundle 告警消息

        Args:
            advice_data: 建议数据（来自 generate_advice）
            signals: 信号列表

        Returns:
            格式化的 Discord 消息

        Example:
            >>> advisor = BundleAdvisor()
            >>> message = advisor.format_bundle_alert(advice_data, signals)
            >>> print(message)
            🔔 综合信号告警 - DOGE/USDT
            ...
        """
        if not signals:
            return "❌ 无信号数据"

        # 获取交易对（假设所有信号同交易对）
        symbol = signals[0].symbol

        # 获取建议等级对应的 emoji
        advice_emoji = {
            'STRONG_BUY': '🚀',
            'BUY': '📈',
            'WATCH': '👀',
            'SELL': '📉',
            'STRONG_SELL': '⚠️',
        }.get(advice_data['advice'], '❓')

        # 构建消息
        lines = []
        lines.append(f"🔔 综合信号告警 - {symbol}\n")

        # 建议操作
        lines.append(f"{advice_emoji} 建议操作: **{advice_data['advice']}** "
                    f"(置信度: {advice_data['confidence']*100:.0f}%)")

        # 信号统计
        lines.append(f"📈 BUY 信号: {advice_data['buy_count']} 个"
                    f"（加权得分: {advice_data['weighted_buy']:.0f}）")
        lines.append(f"📉 SELL 信号: {advice_data['sell_count']} 个"
                    f"（加权得分: {advice_data['weighted_sell']:.0f}）\n")

        # 判断理由
        lines.append(f"💡 判断理由:")
        lines.append(advice_data['reason'])
        lines.append("")  # 空行

        # 信号明细
        lines.append(f"📊 信号明细（共 {len(signals)} 个）:\n")

        for i, sig in enumerate(signals[:10], 1):  # 最多显示 10 个
            # 信号类型 emoji
            type_emoji = {
                'iceberg': '🧊',
                'whale': '🐋',
                'liq': '💥',
            }.get(sig.signal_type, '❓')

            # 方向 emoji
            direction_emoji = '🟢' if sig.side == 'BUY' else '🔴'

            # 格式化置信度调整
            conf_modifier = sig.confidence_modifier or {}
            boost = conf_modifier.get('resonance_boost', 0)
            penalty = conf_modifier.get('conflict_penalty', 0)
            bonus = conf_modifier.get('type_bonus', 0)

            modifier_str = []
            if boost > 0:
                modifier_str.append(f"+{boost:.0f} 共振")
            if penalty < 0:
                modifier_str.append(f"{penalty:.0f} 冲突")
            if bonus > 0:
                modifier_str.append(f"+{bonus:.0f} 组合")

            modifier_text = " ".join(modifier_str) if modifier_str else ""

            # 构建信号行
            lines.append(
                f"{i}. {direction_emoji} {type_emoji} **{sig.level}** {sig.signal_type} "
                f"{sig.side} @{sig.price}"
            )
            lines.append(
                f"   置信度: {sig.confidence:.0f}% "
                f"(基础 {conf_modifier.get('base', sig.confidence):.0f}%"
                + (f", {modifier_text}" if modifier_text else "") + ")"
            )

            # 添加信号特有字段
            if sig.signal_type == 'iceberg' and sig.data:
                refill = sig.data.get('refill_count', 'N/A')
                intensity = sig.data.get('intensity', 'N/A')
                lines.append(f"   补单: {refill} 次, 强度: {intensity}")

            lines.append("")  # 信号之间空行

        # 如果信号数超过 10 个，显示提示
        if len(signals) > 10:
            lines.append(f"... 还有 {len(signals) - 10} 个信号未显示\n")

        # 时间戳
        lines.append(f"⏰ 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        return "\n".join(lines)
