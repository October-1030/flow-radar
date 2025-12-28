"""
Flow Radar - Core Indicators Module
流动性雷达 - 核心指标计算模块

包含: OBI, CVD, VWAP, Flow Toxicity, VR, Slope, 鲸鱼占比, 综合评分等
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from enum import Enum


class TrendState(Enum):
    STRONG_UP = "强势上涨"
    MILD_UP = "温和上涨"
    SIDEWAYS = "横盘"
    MILD_DOWN = "温和下跌"
    STRONG_DOWN = "强势下跌"


class VolumeState(Enum):
    EXTREME_LOW = "极度缩量"
    LOW = "缩量"
    NORMAL = "正常"
    HIGH = "显著放量"
    EXTREME_HIGH = "极端放量"


class WhaleState(Enum):
    RETAIL = "散户主导"
    NORMAL = "正常"
    ACTIVE = "鲸鱼活跃"
    DOMINANT = "鲸鱼主导"


class ExtremeState(Enum):
    EXTREME_BUY = "[极买]"
    EXTREME_SELL = "[极卖]"
    OVERBOUGHT = "[超买]"
    OVERSOLD = "[超卖]"
    NEUTRAL = ""


@dataclass
class IndicatorResult:
    """指标计算结果"""
    obi: float = 0.0                    # 订单簿失衡 [-1, 1]
    cvd: float = 0.0                    # 累积成交量差值
    vwap: float = 0.0                   # 成交量加权平均价
    flow_toxicity: float = 0.0          # 订单流毒性 [0, 1]
    vr: float = 1.0                     # 量比
    slope: float = 0.0                  # 价格斜率
    whale_pct: float = 0.0              # 鲸鱼占比 %
    whale_direction: str = "neutral"     # 鲸鱼方向
    score: int = 50                     # 综合评分 [0, 100]
    rsi: float = 50.0                   # RSI
    atr: float = 0.0                    # ATR
    extreme_state: str = ""             # 极端状态标签


class Indicators:
    """核心指标计算器"""

    def __init__(self, whale_threshold_usd: float = 5000):
        self.whale_threshold_usd = whale_threshold_usd
        self._price_history: List[float] = []
        self._volume_history: List[float] = []
        self._avg_volume_window = 20  # 计算平均成交量的窗口

    def calculate_obi(self, orderbook: Dict) -> float:
        """
        计算订单簿失衡度 (Order Book Imbalance)
        返回值范围: [-1, 1]
        正值表示买盘强势，负值表示卖盘强势
        """
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        # 取前10档
        bid_volume = sum([level[1] for level in bids[:10]])
        ask_volume = sum([level[1] for level in asks[:10]])

        total = bid_volume + ask_volume
        if total == 0:
            return 0.0

        obi = (bid_volume - ask_volume) / total
        return round(obi, 4)

    def calculate_cvd(self, trades: List[Dict]) -> float:
        """
        计算累积成交量差值 (Cumulative Volume Delta)
        正值表示主动买入占优，负值表示主动卖出占优
        """
        buy_volume = sum([t['quantity'] for t in trades if not t.get('is_buyer_maker', True)])
        sell_volume = sum([t['quantity'] for t in trades if t.get('is_buyer_maker', True)])

        return buy_volume - sell_volume

    def calculate_vwap(self, trades: List[Dict]) -> float:
        """
        计算成交量加权平均价 (Volume Weighted Average Price)
        """
        if not trades:
            return 0.0

        total_value = sum([t['price'] * t['quantity'] for t in trades])
        total_volume = sum([t['quantity'] for t in trades])

        if total_volume == 0:
            return 0.0

        return round(total_value / total_volume, 6)

    def calculate_flow_toxicity(self, trades: List[Dict]) -> float:
        """
        计算订单流毒性 (Flow Toxicity)
        高毒性表示知情交易者活跃
        返回值范围: [0, 1]
        """
        if not trades:
            return 0.0

        cvd = self.calculate_cvd(trades)
        total_volume = sum([t['quantity'] for t in trades])

        if total_volume == 0:
            return 0.0

        toxicity = abs(cvd) / total_volume
        return round(min(toxicity, 1.0), 4)

    def calculate_volume_ratio(self, current_volume: float, avg_volume: Optional[float] = None) -> float:
        """
        计算量比 (Volume Ratio)
        VR > 1: 当前成交量高于平均水平（放量）
        VR < 1: 当前成交量低于平均水平（缩量）
        """
        # 更新成交量历史
        self._volume_history.append(current_volume)
        if len(self._volume_history) > self._avg_volume_window:
            self._volume_history = self._volume_history[-self._avg_volume_window:]

        # 计算平均成交量
        if avg_volume is None:
            if len(self._volume_history) < 2:
                return 1.0
            avg_volume = np.mean(self._volume_history[:-1])

        if avg_volume == 0:
            return 0.0

        vr = current_volume / avg_volume
        return round(vr, 2)

    def get_volume_state(self, vr: float) -> VolumeState:
        """获取量比状态"""
        if vr < 0.5:
            return VolumeState.EXTREME_LOW
        elif vr < 1.0:
            return VolumeState.LOW
        elif vr < 2.0:
            return VolumeState.NORMAL
        elif vr < 5.0:
            return VolumeState.HIGH
        else:
            return VolumeState.EXTREME_HIGH

    def calculate_price_slope(self, prices: Optional[List[float]] = None, window: int = 10) -> float:
        """
        计算价格斜率（趋势强度）
        正值表示上涨趋势，负值表示下跌趋势
        绝对值越大，趋势越强
        """
        if prices:
            self._price_history.extend(prices)

        if len(self._price_history) < window:
            return 0.0

        recent_prices = self._price_history[-window:]

        # 使用线性回归计算斜率
        x = np.arange(window)
        y = np.array(recent_prices)

        x_mean = np.mean(x)
        y_mean = np.mean(y)

        numerator = np.sum((x - x_mean) * (y - y_mean))
        denominator = np.sum((x - x_mean) ** 2)

        if denominator == 0 or y_mean == 0:
            return 0.0

        slope = numerator / denominator

        # 标准化为百分比变化率
        normalized_slope = slope / y_mean
        return round(normalized_slope, 4)

    def get_trend_state(self, slope: float) -> TrendState:
        """获取趋势状态"""
        if slope > 0.05:
            return TrendState.STRONG_UP
        elif slope > 0.01:
            return TrendState.MILD_UP
        elif slope > -0.01:
            return TrendState.SIDEWAYS
        elif slope > -0.05:
            return TrendState.MILD_DOWN
        else:
            return TrendState.STRONG_DOWN

    def calculate_whale_percentage(self, trades: List[Dict]) -> Tuple[float, str]:
        """
        计算鲸鱼成交占比和方向
        返回: (占比百分比, 方向: 'buy'/'sell'/'neutral')
        """
        if not trades:
            return 0.0, "neutral"

        total_volume = sum([t['quantity'] * t['price'] for t in trades])

        whale_buy_volume = 0.0
        whale_sell_volume = 0.0

        for t in trades:
            trade_value = t['quantity'] * t['price']
            if trade_value >= self.whale_threshold_usd:
                if not t.get('is_buyer_maker', True):
                    whale_buy_volume += trade_value
                else:
                    whale_sell_volume += trade_value

        whale_volume = whale_buy_volume + whale_sell_volume

        if total_volume == 0:
            return 0.0, "neutral"

        whale_pct = (whale_volume / total_volume) * 100

        # 判断鲸鱼方向
        if whale_buy_volume > whale_sell_volume * 1.5:
            direction = "buy"
        elif whale_sell_volume > whale_buy_volume * 1.5:
            direction = "sell"
        else:
            direction = "neutral"

        return round(whale_pct, 2), direction

    def get_whale_state(self, whale_pct: float) -> WhaleState:
        """获取鲸鱼状态"""
        if whale_pct < 5:
            return WhaleState.RETAIL
        elif whale_pct < 10:
            return WhaleState.NORMAL
        elif whale_pct < 20:
            return WhaleState.ACTIVE
        else:
            return WhaleState.DOMINANT

    def calculate_composite_score(self, indicators: Dict) -> int:
        """
        计算综合评分（0-100）
        综合多个指标生成单一分数，便于快速判断
        """
        score = 50  # 基准分

        # OBI 贡献（-15 ~ +15）
        obi = indicators.get('obi', 0)
        score += int(obi * 15)

        # CVD 方向贡献（-10 ~ +10）
        cvd = indicators.get('cvd', 0)
        if cvd > 0:
            score += min(10, int(cvd / 1000))
        else:
            score += max(-10, int(cvd / 1000))

        # 斜率贡献（-10 ~ +10）
        slope = indicators.get('slope', 0)
        score += int(min(10, max(-10, slope * 100)))

        # 量比贡献（0 ~ +10）
        vr = indicators.get('vr', 1)
        if vr > 2:
            score += min(10, int((vr - 1) * 5))

        # 鲸鱼占比贡献（-5 ~ +5，结合方向）
        whale_pct = indicators.get('whale_pct', 0)
        whale_direction = indicators.get('whale_direction', 'neutral')
        if whale_pct > 10:
            if whale_direction == 'buy':
                score += 5
            elif whale_direction == 'sell':
                score -= 5

        # RSI 超买超卖调整（-5 ~ +5）
        rsi = indicators.get('rsi', 50)
        if rsi > 70:
            score -= min(5, int((rsi - 70) / 6))
        elif rsi < 30:
            score += min(5, int((30 - rsi) / 6))

        # 限制范围
        return max(0, min(100, score))

    def get_score_description(self, score: int) -> str:
        """获取分数描述"""
        if score < 20:
            return "极度看空"
        elif score < 40:
            return "看空"
        elif score < 60:
            return "中性"
        elif score < 80:
            return "看多"
        else:
            return "极度看多"

    def calculate_extreme_state(self, indicators: Dict, timeframe: str = "15m") -> ExtremeState:
        """
        计算极端状态指标
        返回: [极买]/[极卖]/[超买]/[超卖]/空
        """
        obi = indicators.get('obi', 0)
        cvd = indicators.get('cvd', 0)
        rsi = indicators.get('rsi', 50)
        vr = indicators.get('vr', 1)
        flow_toxicity = indicators.get('flow_toxicity', 0)

        # 极端买入条件
        extreme_buy_conditions = [
            obi > 0.6,
            cvd > 5000,
            flow_toxicity > 0.7,
            vr > 3.0
        ]

        # 极端卖出条件
        extreme_sell_conditions = [
            obi < -0.6,
            cvd < -5000,
            flow_toxicity > 0.7,
            vr > 3.0
        ]

        # 统计满足条件数量
        buy_count = sum(extreme_buy_conditions)
        sell_count = sum(extreme_sell_conditions)

        # 极端状态判定（需要满足3个以上条件）
        if buy_count >= 3:
            return ExtremeState.EXTREME_BUY
        elif sell_count >= 3:
            return ExtremeState.EXTREME_SELL

        # 超买超卖判定（基于RSI）
        if rsi > 80:
            return ExtremeState.OVERBOUGHT
        elif rsi < 20:
            return ExtremeState.OVERSOLD

        return ExtremeState.NEUTRAL

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        计算 RSI (Relative Strength Index)
        """
        if len(prices) < period + 1:
            return 50.0

        # 计算价格变化
        deltas = np.diff(prices[-(period + 1):])

        # 分离涨跌
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        # 计算平均涨跌幅
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi, 2)

    def calculate_atr(self, high_prices: List[float], low_prices: List[float],
                      close_prices: List[float], period: int = 14) -> float:
        """
        计算 ATR (Average True Range)
        """
        if len(high_prices) < period or len(low_prices) < period or len(close_prices) < period:
            return 0.0

        tr_list = []
        for i in range(1, len(high_prices)):
            high = high_prices[i]
            low = low_prices[i]
            prev_close = close_prices[i - 1]

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_list.append(tr)

        if len(tr_list) < period:
            return 0.0

        atr = np.mean(tr_list[-period:])
        return round(atr, 6)

    def check_symmetry_break(self, obi: float, cvd: float, price: float, vwap: float) -> Dict:
        """
        检测市场对称性是否被破坏
        当三个指标同时指向同一方向时，触发信号
        """
        signals = {
            'obi_bullish': obi > 0.3,
            'obi_bearish': obi < -0.3,
            'cvd_bullish': cvd > 0,
            'cvd_bearish': cvd < 0,
            'price_above_vwap': price > vwap,
            'price_below_vwap': price < vwap
        }

        # 三重看多共振
        if signals['obi_bullish'] and signals['cvd_bullish'] and signals['price_above_vwap']:
            return {
                'signal': 'SYMMETRY_BREAK_UP',
                'direction': 'LONG',
                'strength': 'HIGH',
                'details': signals
            }

        # 三重看空共振
        if signals['obi_bearish'] and signals['cvd_bearish'] and signals['price_below_vwap']:
            return {
                'signal': 'SYMMETRY_BREAK_DOWN',
                'direction': 'SHORT',
                'strength': 'HIGH',
                'details': signals
            }

        # 双重共振检测
        bullish_count = sum([signals['obi_bullish'], signals['cvd_bullish'], signals['price_above_vwap']])
        bearish_count = sum([signals['obi_bearish'], signals['cvd_bearish'], signals['price_below_vwap']])

        if bullish_count >= 2:
            return {
                'signal': 'PARTIAL_BULLISH',
                'direction': 'LONG',
                'strength': 'MEDIUM',
                'details': signals
            }

        if bearish_count >= 2:
            return {
                'signal': 'PARTIAL_BEARISH',
                'direction': 'SHORT',
                'strength': 'MEDIUM',
                'details': signals
            }

        return {
            'signal': 'NEUTRAL',
            'direction': None,
            'strength': 'LOW',
            'details': signals
        }

    def calculate_all(self, orderbook: Dict, trades: List[Dict],
                      prices: List[float] = None,
                      high_prices: List[float] = None,
                      low_prices: List[float] = None,
                      close_prices: List[float] = None) -> IndicatorResult:
        """
        计算所有指标
        """
        # 基础指标
        obi = self.calculate_obi(orderbook)
        cvd = self.calculate_cvd(trades)
        vwap = self.calculate_vwap(trades)
        flow_toxicity = self.calculate_flow_toxicity(trades)

        # 成交量相关
        current_volume = sum([t['quantity'] for t in trades])
        vr = self.calculate_volume_ratio(current_volume)

        # 价格相关
        if prices:
            self._price_history.extend(prices)
        slope = self.calculate_price_slope()

        # 鲸鱼分析
        whale_pct, whale_direction = self.calculate_whale_percentage(trades)

        # RSI & ATR
        rsi = 50.0
        atr = 0.0
        if close_prices and len(close_prices) >= 15:
            rsi = self.calculate_rsi(close_prices)
        if high_prices and low_prices and close_prices:
            atr = self.calculate_atr(high_prices, low_prices, close_prices)

        # 综合评分
        indicators_dict = {
            'obi': obi,
            'cvd': cvd,
            'slope': slope,
            'vr': vr,
            'whale_pct': whale_pct,
            'whale_direction': whale_direction,
            'rsi': rsi,
            'flow_toxicity': flow_toxicity
        }
        score = self.calculate_composite_score(indicators_dict)

        # 极端状态
        extreme_state = self.calculate_extreme_state(indicators_dict)

        return IndicatorResult(
            obi=obi,
            cvd=cvd,
            vwap=vwap,
            flow_toxicity=flow_toxicity,
            vr=vr,
            slope=slope,
            whale_pct=whale_pct,
            whale_direction=whale_direction,
            score=score,
            rsi=rsi,
            atr=atr,
            extreme_state=extreme_state.value
        )

    def add_price(self, price: float):
        """添加价格到历史记录"""
        self._price_history.append(price)
        # 保持历史记录在合理范围内
        if len(self._price_history) > 1000:
            self._price_history = self._price_history[-500:]

    def reset(self):
        """重置历史数据"""
        self._price_history = []
        self._volume_history = []
