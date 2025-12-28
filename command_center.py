#!/usr/bin/env python3
"""
Flow Radar - System C (Command Center)
流动性雷达 - 战情指挥中心

职责: 多维度信号融合与共振判定
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

try:
    import ccxt.async_support as ccxt
except ImportError:
    print("请安装 ccxt: pip install ccxt")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.layout import Layout
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

from config.settings import (
    CONFIG_COMMAND, CONFIG_MARKET, CONFIG_ICEBERG,
    CONFIG_CHAIN, CONFIG_RISK, CONFIG_MTF, TIMEFRAME_SECONDS
)
from core.indicators import Indicators, IndicatorResult
from core.derivatives import (
    DerivativesDataFetcher, BinnedCVD, calculate_binned_cvd,
    predict_liquidation_cascade, FundingRateData, OpenInterestData,
    LongShortRatioData, LiquidationData
)


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG_COMMAND['log_path']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SystemC')

console = Console()


class ResonanceLevel(Enum):
    """共振等级"""
    NONE = 0            # 无共振
    SINGLE = 1          # 单一信号
    DOUBLE = 2          # 双重共振
    TRIPLE = 3          # 三重共振


class SignalDirection(Enum):
    """信号方向"""
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"


@dataclass
class SystemSignal:
    """子系统信号"""
    source: str                     # 'M', 'I', 'A'
    signal_type: str
    direction: SignalDirection
    strength: float                 # 0-100
    timestamp: datetime
    details: Dict = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return (datetime.now() - self.timestamp).total_seconds()


@dataclass
class ResonanceSignal:
    """共振信号"""
    timestamp: datetime
    level: ResonanceLevel
    direction: SignalDirection
    confidence: float               # 0-100
    sources: List[str]              # ['M', 'I', 'A']
    signals: List[SystemSignal]
    recommended_action: str
    details: Dict = field(default_factory=dict)

    def __str__(self):
        level_map = {
            ResonanceLevel.SINGLE: "单一信号",
            ResonanceLevel.DOUBLE: "双重共振",
            ResonanceLevel.TRIPLE: "三重共振"
        }
        sources_str = "+".join(self.sources)
        return (f"[{level_map[self.level]}] {sources_str} | "
                f"方向: {self.direction.value} | 置信度: {self.confidence:.0f}%")


@dataclass
class StrategicMap:
    """战略地图"""
    timestamp: datetime
    mtf_trends: Dict[str, str]      # {"1D": "中性", "4H": "多", "15M": "多"}
    current_pattern: str            # "诱多陷阱", "突破确认" 等
    execution_env: Dict             # 执行环境检查
    data_source_status: str         # 数据源对齐状态


@dataclass
class WhaleFlowTracker:
    """鲸鱼流量追踪"""
    buy_volume: float = 0.0         # 鲸鱼买入量 (USD)
    sell_volume: float = 0.0        # 鲸鱼卖出量 (USD)
    buy_trades: List[Dict] = field(default_factory=list)   # 买入交易记录
    sell_trades: List[Dict] = field(default_factory=list)  # 卖出交易记录

    @property
    def net_flow(self) -> float:
        """净鲸流 = 买入 - 卖出"""
        return self.buy_volume - self.sell_volume

    @property
    def physical_anchor(self) -> Optional[float]:
        """物理锚点 = 鲸鱼成交的VWAP"""
        all_trades = self.buy_trades + self.sell_trades
        if not all_trades:
            return None
        total_value = sum(t['value'] for t in all_trades)
        total_qty = sum(t['quantity'] for t in all_trades)
        if total_qty == 0:
            return None
        return total_value / total_qty

    def add_trade(self, price: float, quantity: float, value: float, is_buy: bool):
        """添加鲸鱼交易"""
        trade = {'price': price, 'quantity': quantity, 'value': value, 'timestamp': datetime.now()}
        if is_buy:
            self.buy_volume += value
            self.buy_trades.append(trade)
        else:
            self.sell_volume += value
            self.sell_trades.append(trade)

    def cleanup(self, max_age_seconds: int = 3600):
        """清理过期数据"""
        now = datetime.now()
        self.buy_trades = [t for t in self.buy_trades
                          if (now - t['timestamp']).total_seconds() < max_age_seconds]
        self.sell_trades = [t for t in self.sell_trades
                           if (now - t['timestamp']).total_seconds() < max_age_seconds]
        self.buy_volume = sum(t['value'] for t in self.buy_trades)
        self.sell_volume = sum(t['value'] for t in self.sell_trades)


class RefreshCountdown:
    """刷新倒计时"""

    def __init__(self):
        self.timeframes = ["15M", "4H", "1D"]

    def get_countdown(self, timeframe: str) -> int:
        """获取指定时间框架的倒计时秒数"""
        now = datetime.now()
        interval = TIMEFRAME_SECONDS.get(timeframe, 900)
        current_ts = now.timestamp()
        period_start = int(current_ts // interval) * interval
        next_period = period_start + interval
        return max(0, int(next_period - current_ts))

    def format(self, seconds: int) -> str:
        """格式化倒计时"""
        if seconds >= 3600:
            return f"{seconds // 3600}h{(seconds % 3600) // 60}m"
        elif seconds >= 60:
            return f"{seconds // 60}m{seconds % 60}s"
        return f"{seconds}s"


class CommandCenter:
    """System C - 战情指挥中心"""

    def __init__(self, symbol: str = None, mode: str = "full_resonance"):
        self.symbol = symbol or CONFIG_MARKET['symbol']
        self.mode = mode
        self.exchange: Optional[ccxt.Exchange] = None
        self.running = False

        # 核心组件
        self.indicators = Indicators(whale_threshold_usd=CONFIG_MARKET['whale_threshold_usd'])
        self.countdown = RefreshCountdown()

        # 信号缓存
        self.market_signals: List[SystemSignal] = []
        self.iceberg_signals: List[SystemSignal] = []
        self.chain_signals: List[SystemSignal] = []
        self.resonance_signals: List[ResonanceSignal] = []

        # 状态
        self.current_indicators: Optional[IndicatorResult] = None
        self.mtf_trends: Dict[str, str] = {"1D": "中性", "4H": "中性", "15M": "中性"}
        self.chain_state: str = "中性"
        self.extreme_state: str = ""
        self.current_pattern: str = ""
        self.current_price: float = 0.0

        # 鲸鱼流量追踪
        self.whale_tracker = WhaleFlowTracker()

        # 庄家演戏/战略洗盘状态
        self.manipulation_alert: str = ""  # 庄家演戏警告
        self.strategic_wash: str = ""      # 战略洗盘信号
        self.market_score: int = 50        # 综合评分 0-100

        # 合约数据
        self.derivatives_fetcher = DerivativesDataFetcher(exchange=CONFIG_MARKET.get('exchange', 'okx'))
        self.funding_rate: Optional[FundingRateData] = None
        self.open_interest: Optional[OpenInterestData] = None
        self.long_short_ratio: Optional[LongShortRatioData] = None
        self.liquidation_data: Optional[LiquidationData] = None
        self.binned_cvd: Optional[BinnedCVD] = None
        self.liquidation_warning: str = ""
        self.price_change_24h: float = 0.0

        # 执行环境
        self.execution_env = {
            "margin_available": True,
            "estimated_slippage": 0.0,
            "data_aligned": True
        }

        # 权重配置
        self.weights = CONFIG_COMMAND['resonance_weights']

    async def initialize(self):
        """初始化"""
        exchange_id = CONFIG_MARKET.get('exchange', 'binance')
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        logger.info(f"System C - 战情指挥中心初始化完成")

    async def fetch_market_data(self) -> Optional[Dict]:
        """获取市场数据"""
        try:
            ticker, orderbook, trades = await asyncio.gather(
                self.exchange.fetch_ticker(self.symbol),
                self.exchange.fetch_order_book(self.symbol, limit=20),
                self.exchange.fetch_trades(self.symbol, limit=100)
            )

            formatted_trades = [
                {
                    'price': t['price'],
                    'quantity': t['amount'],
                    'is_buyer_maker': t['side'] == 'sell',
                    'timestamp': t['timestamp']
                }
                for t in trades
            ]

            return {
                'ticker': ticker,
                'orderbook': orderbook,
                'trades': formatted_trades
            }
        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return None

    async def fetch_derivatives_data(self):
        """获取合约数据"""
        try:
            data = await self.derivatives_fetcher.fetch_all(self.symbol)
            self.funding_rate = data.get("funding_rate")
            self.open_interest = data.get("open_interest")
            self.long_short_ratio = data.get("long_short_ratio")
            self.liquidation_data = data.get("liquidations")

            # 预测爆仓瀑布
            risk_level, warning = predict_liquidation_cascade(
                self.funding_rate,
                self.open_interest,
                self.long_short_ratio,
                self.price_change_24h
            )
            self.liquidation_warning = warning

        except Exception as e:
            logger.debug(f"获取合约数据失败: {e}")

    async def update_mtf_trends(self):
        """更新多时间框架趋势"""
        tf_map = {"15M": "15m", "4H": "4h", "1D": "1d"}

        for tf_display, tf_api in tf_map.items():
            try:
                ohlcv = await self.exchange.fetch_ohlcv(self.symbol, tf_api, limit=20)
                if ohlcv and len(ohlcv) >= 10:
                    closes = [k[4] for k in ohlcv]
                    ma5 = sum(closes[-5:]) / 5
                    ma10 = sum(closes[-10:]) / 10
                    current = closes[-1]

                    if current > ma5 > ma10:
                        self.mtf_trends[tf_display] = "多"
                    elif current < ma5 < ma10:
                        self.mtf_trends[tf_display] = "空"
                    else:
                        self.mtf_trends[tf_display] = "中性"
            except Exception as e:
                logger.debug(f"更新 {tf_display} 趋势失败: {e}")

    def analyze_market_signals(self, data: Dict) -> List[SystemSignal]:
        """分析市场信号 (System M)"""
        signals = []

        # 计算指标
        self.current_indicators = self.indicators.calculate_all(
            orderbook=data['orderbook'],
            trades=data['trades']
        )
        ind = self.current_indicators
        self.current_price = data['ticker']['last']

        # 清理过期鲸鱼数据
        self.whale_tracker.cleanup(max_age_seconds=3600)

        # 检测大额交易
        for trade in data['trades']:
            value = trade['price'] * trade['quantity']
            if value >= CONFIG_MARKET['whale_threshold_usd']:
                is_buy = not trade['is_buyer_maker']

                # 记录鲸鱼交易
                self.whale_tracker.add_trade(
                    price=trade['price'],
                    quantity=trade['quantity'],
                    value=value,
                    is_buy=is_buy
                )

                signals.append(SystemSignal(
                    source='M',
                    signal_type='WHALE_BUY' if is_buy else 'WHALE_SELL',
                    direction=SignalDirection.LONG if is_buy else SignalDirection.SHORT,
                    strength=min(90, 50 + (value / 1000)),
                    timestamp=datetime.now(),
                    details={'value': value, 'price': trade['price']}
                ))

        # OBI/CVD 强势信号
        if ind.obi > 0.5 and ind.cvd > 3000:
            signals.append(SystemSignal(
                source='M',
                signal_type='STRONG_BULLISH',
                direction=SignalDirection.LONG,
                strength=70 + ind.obi * 20,
                timestamp=datetime.now(),
                details={'obi': ind.obi, 'cvd': ind.cvd}
            ))
        elif ind.obi < -0.5 and ind.cvd < -3000:
            signals.append(SystemSignal(
                source='M',
                signal_type='STRONG_BEARISH',
                direction=SignalDirection.SHORT,
                strength=70 + abs(ind.obi) * 20,
                timestamp=datetime.now(),
                details={'obi': ind.obi, 'cvd': ind.cvd}
            ))

        # 对称性破坏检测
        price = data['ticker']['last']
        sym_result = self.indicators.check_symmetry_break(ind.obi, ind.cvd, price, ind.vwap)
        if sym_result['signal'] in ['SYMMETRY_BREAK_UP', 'SYMMETRY_BREAK_DOWN']:
            signals.append(SystemSignal(
                source='M',
                signal_type=sym_result['signal'],
                direction=SignalDirection.LONG if 'UP' in sym_result['signal'] else SignalDirection.SHORT,
                strength=85,
                timestamp=datetime.now(),
                details=sym_result['details']
            ))

        # 更新极端状态
        self.extreme_state = ind.extreme_state

        # 计算分级CVD
        self.binned_cvd = calculate_binned_cvd(data['trades'], data['ticker']['last'])

        # 获取24h价格变化
        if 'ticker' in data and 'percentage' in data['ticker']:
            self.price_change_24h = data['ticker'].get('percentage', 0) or 0

        return signals

    def detect_resonance(self) -> Optional[ResonanceSignal]:
        """检测共振信号"""
        now = datetime.now()
        decay_window = CONFIG_COMMAND['signal_decay_window']

        # 获取有效信号（在衰减窗口内）
        valid_m = [s for s in self.market_signals if s.age_seconds < decay_window]
        valid_i = [s for s in self.iceberg_signals if s.age_seconds < decay_window]
        valid_a = [s for s in self.chain_signals if s.age_seconds < decay_window]

        # 统计各方向的信号
        long_sources = []
        short_sources = []
        long_signals = []
        short_signals = []

        for signals, source in [(valid_m, 'M'), (valid_i, 'I'), (valid_a, 'A')]:
            if signals:
                # 取最强信号
                strongest = max(signals, key=lambda s: s.strength)
                if strongest.direction == SignalDirection.LONG:
                    long_sources.append(source)
                    long_signals.append(strongest)
                elif strongest.direction == SignalDirection.SHORT:
                    short_sources.append(source)
                    short_signals.append(strongest)

        # 判断共振等级
        if len(long_sources) >= 3:
            return self._create_resonance(ResonanceLevel.TRIPLE, SignalDirection.LONG,
                                          long_sources, long_signals)
        elif len(short_sources) >= 3:
            return self._create_resonance(ResonanceLevel.TRIPLE, SignalDirection.SHORT,
                                          short_sources, short_signals)
        elif len(long_sources) >= 2:
            return self._create_resonance(ResonanceLevel.DOUBLE, SignalDirection.LONG,
                                          long_sources, long_signals)
        elif len(short_sources) >= 2:
            return self._create_resonance(ResonanceLevel.DOUBLE, SignalDirection.SHORT,
                                          short_sources, short_signals)
        elif long_signals or short_signals:
            if long_signals:
                return self._create_resonance(ResonanceLevel.SINGLE, SignalDirection.LONG,
                                              long_sources, long_signals)
            else:
                return self._create_resonance(ResonanceLevel.SINGLE, SignalDirection.SHORT,
                                              short_sources, short_signals)

        return None

    def _create_resonance(self, level: ResonanceLevel, direction: SignalDirection,
                          sources: List[str], signals: List[SystemSignal]) -> ResonanceSignal:
        """创建共振信号"""
        # 计算置信度
        base_confidence = {
            ResonanceLevel.SINGLE: 30,
            ResonanceLevel.DOUBLE: 55,
            ResonanceLevel.TRIPLE: 80
        }[level]

        # 加权平均信号强度
        weighted_strength = sum(
            s.strength * self.weights.get(
                {'M': 'market', 'I': 'iceberg', 'A': 'chain'}[s.source], 0.33
            )
            for s in signals
        )
        confidence = min(95, base_confidence + weighted_strength * 0.2)

        # 推荐操作
        if level == ResonanceLevel.TRIPLE and confidence >= CONFIG_COMMAND['min_confidence_to_trade']:
            action = f"建议{'开多' if direction == SignalDirection.LONG else '开空'}"
        elif level == ResonanceLevel.DOUBLE:
            action = f"观察{'做多' if direction == SignalDirection.LONG else '做空'}机会"
        else:
            action = "仅记录，不操作"

        return ResonanceSignal(
            timestamp=datetime.now(),
            level=level,
            direction=direction,
            confidence=confidence,
            sources=sources,
            signals=signals,
            recommended_action=action,
            details={'weighted_strength': weighted_strength}
        )

    def detect_pattern(self) -> str:
        """检测当前市场模式"""
        if not self.current_indicators:
            return ""

        ind = self.current_indicators

        # 诱多/诱空检测
        if self.mtf_trends['1D'] == "空" and self.mtf_trends['15M'] == "多":
            if ind.obi > 0.3 and ind.rsi > 65:
                return "诱多陷阱"

        if self.mtf_trends['1D'] == "多" and self.mtf_trends['15M'] == "空":
            if ind.obi < -0.3 and ind.rsi < 35:
                return "诱空陷阱"

        # 突破确认
        if all(t == "多" for t in self.mtf_trends.values()) and ind.score > 70:
            return "多头突破确认"
        if all(t == "空" for t in self.mtf_trends.values()) and ind.score < 30:
            return "空头突破确认"

        # 震荡盘整
        if all(t == "中性" for t in self.mtf_trends.values()):
            return "震荡盘整"

        return ""

    def detect_manipulation(self, data: Dict) -> str:
        """检测庄家演戏 - 对倒诱多/诱空"""
        if not self.current_indicators:
            return ""

        ind = self.current_indicators
        whale_ratio = ind.whale_ratio if hasattr(ind, 'whale_ratio') else 0

        # 对倒诱多检测条件:
        # 1. 鲸鱼占比很高 (>50%)
        # 2. OBI正值 (看似买方强)
        # 3. 但价格斜率为负或很小 (价格不涨)
        # 4. 大趋势为空
        if whale_ratio > 50 and ind.obi > 0.3:
            if ind.slope < 0.05 and self.mtf_trends['1D'] == "空":
                return "诱多警告"

        # 对倒诱空检测条件:
        # 1. 鲸鱼占比很高
        # 2. OBI负值 (看似卖方强)
        # 3. 但价格斜率为正或很小 (价格不跌)
        # 4. 大趋势为多
        if whale_ratio > 50 and ind.obi < -0.3:
            if ind.slope > -0.05 and self.mtf_trends['1D'] == "多":
                return "诱空警告"

        return ""

    def detect_strategic_wash(self) -> Tuple[str, str]:
        """检测战略洗盘"""
        if not self.current_indicators:
            return "", ""

        ind = self.current_indicators
        net_flow = self.whale_tracker.net_flow
        anchor = self.whale_tracker.physical_anchor

        # 战略洗盘条件:
        # 1. 净鲸流为正 (大户在买)
        # 2. 短期趋势为空 (价格在跌)
        # 3. 价格接近物理锚点 (支撑位)
        if net_flow > 10000:  # 净流入超过1万U
            if self.mtf_trends['15M'] == "空" or self.mtf_trends['4H'] == "空":
                if anchor and self.current_price > 0:
                    distance_pct = abs(self.current_price - anchor) / self.current_price * 100
                    if distance_pct < 3:  # 价格距离锚点3%以内
                        message = "大户净流入为正, 回踩锚点支撑, 严禁恐慌抛售"
                        return "STRATEGIC_WASH", message

        # 反向洗盘 (诱空洗盘)
        if net_flow < -10000:  # 净流出超过1万U
            if self.mtf_trends['15M'] == "多" or self.mtf_trends['4H'] == "多":
                if anchor and self.current_price > 0:
                    distance_pct = abs(self.current_price - anchor) / self.current_price * 100
                    if distance_pct < 3:
                        message = "大户净流出, 反弹至锚点压力, 请勿追高"
                        return "STRATEGIC_WASH_DOWN", message

        return "", ""

    def calculate_score(self) -> int:
        """计算综合评分 0-100"""
        if not self.current_indicators:
            return 50

        ind = self.current_indicators
        score = 50  # 基础分

        # MTF趋势加分
        bullish_count = sum(1 for t in self.mtf_trends.values() if t == "多")
        bearish_count = sum(1 for t in self.mtf_trends.values() if t == "空")
        score += (bullish_count - bearish_count) * 10

        # OBI加分
        score += int(ind.obi * 20)

        # 净鲸流加分
        net_flow = self.whale_tracker.net_flow
        if net_flow > 50000:
            score += 15
        elif net_flow > 20000:
            score += 10
        elif net_flow > 5000:
            score += 5
        elif net_flow < -50000:
            score -= 15
        elif net_flow < -20000:
            score -= 10
        elif net_flow < -5000:
            score -= 5

        # CVD加分
        if ind.cvd > 5000:
            score += 10
        elif ind.cvd < -5000:
            score -= 10

        # 限制范围
        return max(0, min(100, score))

    def build_display(self) -> Panel:
        """构建显示面板"""
        lines = []

        # 系统标题
        header = Text()
        header.append(f"[SYSTEM C] ", style="bold yellow")
        header.append("◉ 战情指挥中心已上线 ", style="green")
        header.append(f"| 模式: {self.mode}", style="cyan")
        lines.append(header)

        # 监听信息
        info_line = Text()
        info_line.append("[INFO] 正在监听: ", style="dim")
        info_line.append("Market(M) + Iceberg(I) + Chain(A)", style="cyan")
        lines.append(info_line)

        lines.append(Text(""))  # 空行

        # 战略地图
        map_line1 = Text()
        map_line1.append("┌" + "─" * 70 + "┐")
        lines.append(map_line1)

        # MTF趋势 + 分数
        mtf_line = Text()
        mtf_line.append("│ [战略地图] ")
        for tf, trend in self.mtf_trends.items():
            color = "green" if trend == "多" else "red" if trend == "空" else "yellow"
            mtf_line.append(f"{tf}: {trend} ", style=color)
            mtf_line.append("| ")
        # 添加分数显示
        score_color = "green" if self.market_score >= 60 else "red" if self.market_score <= 40 else "yellow"
        mtf_line.append(f"分数: {self.market_score} ", style=f"bold {score_color}")
        mtf_line.append(" " * max(0, 70 - len(str(mtf_line)) + 15) + "│")
        lines.append(mtf_line)

        # 模式识别
        if self.current_pattern:
            pattern_line = Text()
            pattern_line.append("│   ◉ ")
            pattern_line.append(f"【{self.current_pattern}】", style="bold red" if "陷阱" in self.current_pattern else "bold green")
            if "诱多" in self.current_pattern:
                pattern_line.append(" 检测到高位派发, 请勿追涨!", style="yellow")
            elif "诱空" in self.current_pattern:
                pattern_line.append(" 检测到低位吸筹, 请勿追空!", style="yellow")
            pattern_line.append(" " * max(0, 70 - len(str(pattern_line)) + 15) + "│")
            lines.append(pattern_line)

        # 庄家演戏警告
        if self.manipulation_alert:
            manip_line = Text()
            manip_line.append("│   ◉ ")
            manip_line.append(f"【庄家演戏】{self.manipulation_alert}", style="bold red")
            manip_line.append(" 检测到疑似对倒, 严禁入场!", style="yellow")
            manip_line.append(" " * max(0, 70 - len(str(manip_line)) + 15) + "│")
            lines.append(manip_line)

        # 战略洗盘信号
        if self.strategic_wash:
            wash_line = Text()
            wash_line.append("│   ◉ ")
            wash_line.append(f"【战略洗盘】", style="bold cyan")
            wash_line.append(f" {self.strategic_wash}", style="cyan")
            wash_line.append(" " * max(0, 70 - len(str(wash_line)) + 15) + "│")
            lines.append(wash_line)

        # 鲸鱼流量
        whale_line = Text()
        whale_line.append("│ [鲸鱼流] ")
        net_flow = self.whale_tracker.net_flow
        flow_color = "green" if net_flow > 0 else "red" if net_flow < 0 else "white"
        flow_sign = "+" if net_flow > 0 else ""
        whale_line.append(f"净鲸流: {flow_sign}${net_flow:,.0f}", style=flow_color)
        # 计算占OI百分比
        if self.open_interest and self.open_interest.open_interest_value > 0:
            oi_value = self.open_interest.open_interest_value * self.current_price  # OI in USD
            if oi_value > 0:
                oi_pct = abs(net_flow) / oi_value * 100
                whale_line.append(f" (占OI: {oi_pct:.2f}%)", style="cyan")
        whale_line.append(" ")
        anchor = self.whale_tracker.physical_anchor
        if anchor:
            whale_line.append(f"| 物理锚点: ${anchor:.6f}", style="cyan")
        else:
            whale_line.append("| 物理锚点: N/A", style="dim")
        whale_line.append(" " * max(0, 70 - len(str(whale_line)) + 15) + "│")
        lines.append(whale_line)

        # 资金费率 + 多空比
        if self.funding_rate or self.long_short_ratio:
            deriv_line1 = Text()
            deriv_line1.append("│ [合约] ")
            if self.funding_rate:
                rate = self.funding_rate.funding_rate * 100
                rate_color = "red" if rate > 0.05 else "green" if rate < -0.05 else "yellow"
                deriv_line1.append(f"费率: {rate:+.4f}% ", style=rate_color)
                deriv_line1.append(f"({self.funding_rate.sentiment}) ", style=rate_color)
            if self.long_short_ratio:
                ls = self.long_short_ratio.long_short_ratio
                ls_color = "red" if ls > 1.5 else "green" if ls < 0.67 else "yellow"
                deriv_line1.append(f"| 多空比: {ls:.2f} ", style=ls_color)
            deriv_line1.append(" " * max(0, 70 - len(str(deriv_line1)) + 15) + "│")
            lines.append(deriv_line1)

        # 持仓量 + 爆仓
        if self.open_interest or self.liquidation_data:
            deriv_line2 = Text()
            deriv_line2.append("│ [杠杆] ")
            if self.open_interest:
                oi_val = self.open_interest.open_interest_value
                if oi_val > 1000000:
                    deriv_line2.append(f"OI: ${oi_val/1000000:.1f}M ", style="cyan")
                else:
                    deriv_line2.append(f"OI: ${oi_val:,.0f} ", style="cyan")
            if self.liquidation_data:
                total_liq = self.liquidation_data.total_liquidations_24h
                if total_liq > 0:
                    liq_color = "red" if total_liq > 100000 else "yellow"
                    deriv_line2.append(f"| 24h爆仓: ${total_liq:,.0f} ", style=liq_color)
                    deriv_line2.append(f"({self.liquidation_data.liquidation_bias})", style=liq_color)
            deriv_line2.append(" " * max(0, 70 - len(str(deriv_line2)) + 15) + "│")
            lines.append(deriv_line2)

        # 分级CVD
        if self.binned_cvd:
            cvd_line = Text()
            cvd_line.append("│ [资金流] ")
            whale_cvd = self.binned_cvd.whale_cvd
            shark_cvd = self.binned_cvd.shark_cvd
            retail_cvd = self.binned_cvd.retail_cvd
            cvd_line.append(f"鲸鱼: {whale_cvd:+,.0f} ", style="green" if whale_cvd > 0 else "red")
            cvd_line.append(f"| 鲨鱼: {shark_cvd:+,.0f} ", style="green" if shark_cvd > 0 else "red")
            cvd_line.append(f"| 散户: {retail_cvd:+,.0f}", style="green" if retail_cvd > 0 else "red")
            cvd_line.append(" " * max(0, 70 - len(str(cvd_line)) + 15) + "│")
            lines.append(cvd_line)

            # 聪明钱信号
            smart_signal = self.binned_cvd.smart_money_signal
            if smart_signal:
                smart_line = Text()
                smart_line.append("│   ◉ ")
                smart_line.append(f"【聪明钱】{smart_signal}", style="bold magenta")
                smart_line.append(" " * max(0, 70 - len(str(smart_line)) + 15) + "│")
                lines.append(smart_line)

        # 爆仓瀑布警告
        if self.liquidation_warning:
            liq_warn_line = Text()
            liq_warn_line.append("│   ")
            liq_warn_line.append(self.liquidation_warning, style="bold red")
            liq_warn_line.append(" " * max(0, 70 - len(str(liq_warn_line)) + 15) + "│")
            lines.append(liq_warn_line)

        # 多空比反向信号
        if self.long_short_ratio:
            contrarian = self.long_short_ratio.contrarian_signal
            if "极度" in contrarian or "警惕" in contrarian or "可能" in contrarian:
                contra_line = Text()
                contra_line.append("│   ◉ ")
                contra_line.append(f"【反向指标】{contrarian}", style="bold yellow")
                contra_line.append(" " * max(0, 70 - len(str(contra_line)) + 15) + "│")
                lines.append(contra_line)

        # 执行环境
        env_line = Text()
        env_line.append("│ [执行环境] ")
        margin_status = "OK" if self.execution_env['margin_available'] else "不可用"
        margin_color = "green" if self.execution_env['margin_available'] else "red"
        env_line.append(f"借币可用性: {margin_status} ", style=margin_color)
        env_line.append(f"| 预估滑点: {self.execution_env['estimated_slippage']:.2f}%")
        env_line.append(" " * max(0, 70 - len(str(env_line)) + 15) + "│")
        lines.append(env_line)

        # 数据源状态
        data_line = Text()
        data_line.append("│ [数据源] ")
        data_line.append("A+M+I 实时对齐" if self.execution_env['data_aligned'] else "数据同步中...",
                         style="green" if self.execution_env['data_aligned'] else "yellow")
        data_line.append(" " * max(0, 70 - len(str(data_line)) + 15) + "│")
        lines.append(data_line)

        map_line2 = Text()
        map_line2.append("└" + "─" * 70 + "┘")
        lines.append(map_line2)

        lines.append(Text(""))  # 空行

        # 扫描状态行
        now = datetime.now()
        scan_line = Text()
        scan_line.append(f"[扫描中] {now.strftime('%H:%M:%S')} ", style="dim")

        # MTF简要
        for tf, trend in self.mtf_trends.items():
            color = "green" if trend == "多" else "red" if trend == "空" else "yellow"
            scan_line.append(f"{tf}:{trend} ", style=color)

        # 状态
        if self.resonance_signals:
            latest = self.resonance_signals[-1]
            if latest.level == ResonanceLevel.TRIPLE:
                scan_line.append(f"| 三重共振! ", style="bold green")
            elif latest.level == ResonanceLevel.DOUBLE:
                scan_line.append(f"| 双重共振 ", style="yellow")
            else:
                scan_line.append("| 状态:静默 ", style="dim")
        else:
            scan_line.append("| 状态:静默, 等待共振信号... ", style="dim")

        # 极端状态
        if self.extreme_state:
            extreme_color = "red" if "卖" in self.extreme_state else "green"
            scan_line.append(f"{self.extreme_state} ", style=f"bold {extreme_color}")

        # 倒计时
        scan_line.append("| [下次刷新] ", style="dim")
        for tf in ["4H", "1D"]:
            secs = self.countdown.get_countdown(tf)
            scan_line.append(f"{tf}: {self.countdown.format(secs)} ", style="cyan")

        lines.append(scan_line)

        # 最近共振信号
        if self.resonance_signals:
            lines.append(Text("\n最近共振:", style="bold"))
            for signal in self.resonance_signals[-3:]:
                sig_line = Text()
                time_str = signal.timestamp.strftime('%H:%M:%S')
                level_style = {
                    ResonanceLevel.TRIPLE: "bold green",
                    ResonanceLevel.DOUBLE: "yellow",
                    ResonanceLevel.SINGLE: "dim"
                }[signal.level]
                sig_line.append(f"  [{time_str}] ", style="dim")
                sig_line.append(f"{signal} ", style=level_style)
                sig_line.append(f"| {signal.recommended_action}", style="cyan")
                lines.append(sig_line)

        content = Text("\n").join(lines)
        return Panel(
            content,
            title="[bold yellow]System C - Command Center[/bold yellow]",
            border_style="yellow"
        )

    async def run_once(self):
        """执行一次分析"""
        # 获取市场数据
        data = await self.fetch_market_data()
        if not data:
            return

        # 分析市场信号
        new_m_signals = self.analyze_market_signals(data)
        self.market_signals.extend(new_m_signals)

        # 清理过期信号
        decay = CONFIG_COMMAND['signal_decay_window']
        self.market_signals = [s for s in self.market_signals if s.age_seconds < decay * 2]
        self.iceberg_signals = [s for s in self.iceberg_signals if s.age_seconds < decay * 2]
        self.chain_signals = [s for s in self.chain_signals if s.age_seconds < decay * 2]

        # 检测共振
        resonance = self.detect_resonance()
        if resonance and resonance.level != ResonanceLevel.NONE:
            # 避免重复信号
            if not self.resonance_signals or \
               (datetime.now() - self.resonance_signals[-1].timestamp).total_seconds() > 60:
                self.resonance_signals.append(resonance)
                logger.info(str(resonance))

                # 高置信度信号提醒
                if resonance.confidence >= CONFIG_COMMAND['min_confidence_to_alert']:
                    console.print(f"[bold yellow]!ALERT[/bold yellow] {resonance}")

        # 检测模式
        self.current_pattern = self.detect_pattern()

        # 检测庄家演戏
        self.manipulation_alert = self.detect_manipulation(data)

        # 检测战略洗盘
        wash_type, wash_msg = self.detect_strategic_wash()
        self.strategic_wash = wash_msg

        # 计算综合评分
        self.market_score = self.calculate_score()

        # 保持信号记录在合理范围
        if len(self.resonance_signals) > 100:
            self.resonance_signals = self.resonance_signals[-100:]

    async def run(self):
        """主运行循环"""
        await self.initialize()
        self.running = True

        console.print("[bold yellow]System C - 战情指挥中心已启动[/bold yellow]")
        console.print(f"监控交易对: {self.symbol}")
        console.print(f"运行模式: {self.mode}")
        console.print("-" * 50)

        # 初始更新MTF趋势和合约数据
        await self.update_mtf_trends()
        await self.fetch_derivatives_data()

        mtf_counter = 0

        with Live(self.build_display(), console=console, refresh_per_second=1) as live:
            while self.running:
                try:
                    await self.run_once()

                    # 每60秒更新MTF趋势和合约数据
                    mtf_counter += 5
                    if mtf_counter >= 60:
                        await self.update_mtf_trends()
                        await self.fetch_derivatives_data()
                        mtf_counter = 0

                    live.update(self.build_display())
                    await asyncio.sleep(5)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"运行错误: {e}")
                    await asyncio.sleep(5)

    async def shutdown(self):
        """关闭"""
        self.running = False
        if self.exchange:
            await self.exchange.close()
        if self.derivatives_fetcher:
            await self.derivatives_fetcher.close()
        logger.info("System C 已关闭")


async def main():
    parser = argparse.ArgumentParser(description='Shell Market Watcher - System C')
    parser.add_argument('--symbol', '-s', type=str, default=CONFIG_MARKET['symbol'],
                        help='交易对 (默认: SHELL/USDT)')
    parser.add_argument('--mode', '-m', type=str, default='full_resonance',
                        choices=['full_resonance', 'market_only', 'alert_only'],
                        help='运行模式')
    args = parser.parse_args()

    center = CommandCenter(symbol=args.symbol, mode=args.mode)

    def signal_handler(sig, frame):
        console.print("\n[yellow]正在关闭...[/yellow]")
        asyncio.create_task(center.shutdown())

    signal.signal(signal.SIGINT, signal_handler)

    try:
        await center.run()
    finally:
        await center.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
