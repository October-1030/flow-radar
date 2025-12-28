#!/usr/bin/env python3
"""
Flow Radar - System M (Market Watcher)
流动性雷达 - 盘面监控层

职责: 实时市场数据采集与基础指标计算
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass

try:
    import ccxt.async_support as ccxt
except ImportError:
    print("请安装 ccxt: pip install ccxt")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

from config.settings import CONFIG_MARKET, CONFIG_DISPLAY, TIMEFRAME_SECONDS
from core.indicators import Indicators, IndicatorResult


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG_MARKET['log_path']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SystemM')

console = Console()


@dataclass
class MarketData:
    """市场数据结构"""
    timestamp: datetime
    symbol: str
    price: float
    volume_24h: float
    high_24h: float
    low_24h: float
    change_24h: float
    orderbook: Dict
    recent_trades: List[Dict]


class RefreshCountdown:
    """刷新倒计时管理器"""

    def __init__(self):
        self.timeframes = ["15M", "4H", "1D"]

    def get_next_candle_close(self, timeframe: str) -> int:
        """计算距离下一根K线收盘的剩余秒数"""
        now = datetime.now()
        current_timestamp = now.timestamp()

        interval_seconds = TIMEFRAME_SECONDS.get(timeframe, 900)

        # 计算当前周期开始时间
        period_start = int(current_timestamp // interval_seconds) * interval_seconds
        # 下一周期开始时间
        next_period = period_start + interval_seconds
        # 剩余秒数
        remaining = int(next_period - current_timestamp)

        return max(0, remaining)

    def get_all_countdowns(self) -> Dict[str, int]:
        """获取所有时间框架的倒计时"""
        return {tf: self.get_next_candle_close(tf) for tf in self.timeframes}

    def format_countdown(self, seconds: int) -> str:
        """格式化倒计时显示"""
        if seconds >= 3600:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h{minutes}m"
        elif seconds >= 60:
            minutes = seconds // 60
            secs = seconds % 60
            return f"{minutes}m{secs}s"
        else:
            return f"{seconds}s"


class MarketWatcher:
    """System M - 盘面监控器"""

    def __init__(self, symbol: str = None, interval: int = None):
        self.symbol = symbol or CONFIG_MARKET['symbol']
        self.interval = interval or CONFIG_MARKET['refresh_interval']
        self.exchange: Optional[ccxt.Exchange] = None
        self.indicators = Indicators(whale_threshold_usd=CONFIG_MARKET['whale_threshold_usd'])
        self.countdown = RefreshCountdown()
        self.running = False

        # 历史数据缓存
        self.price_history: List[float] = []
        self.high_history: List[float] = []
        self.low_history: List[float] = []
        self.close_history: List[float] = []
        self.whale_trades: List[Dict] = []

        # 当前状态
        self.current_data: Optional[MarketData] = None
        self.current_indicators: Optional[IndicatorResult] = None
        self.mtf_trends: Dict[str, str] = {"1D": "中性", "4H": "中性", "15M": "中性"}

    async def initialize(self):
        """初始化交易所连接"""
        exchange_id = CONFIG_MARKET.get('exchange', 'binance')
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        logger.info(f"交易所 {exchange_id} 连接初始化完成")

    async def fetch_market_data(self) -> Optional[MarketData]:
        """获取市场数据"""
        try:
            # 并行获取多个数据
            ticker_task = self.exchange.fetch_ticker(self.symbol)
            orderbook_task = self.exchange.fetch_order_book(
                self.symbol,
                limit=CONFIG_MARKET['orderbook_depth']
            )
            trades_task = self.exchange.fetch_trades(self.symbol, limit=100)

            ticker, orderbook, trades = await asyncio.gather(
                ticker_task, orderbook_task, trades_task
            )

            # 转换成交记录格式
            recent_trades = [
                {
                    'price': t['price'],
                    'quantity': t['amount'],
                    'is_buyer_maker': t['side'] == 'sell',
                    'timestamp': t['timestamp'],
                    'value': t['price'] * t['amount']
                }
                for t in trades
            ]

            return MarketData(
                timestamp=datetime.now(),
                symbol=self.symbol,
                price=ticker['last'],
                volume_24h=ticker['quoteVolume'] or 0,
                high_24h=ticker['high'] or ticker['last'],
                low_24h=ticker['low'] or ticker['last'],
                change_24h=ticker['percentage'] or 0,
                orderbook=orderbook,
                recent_trades=recent_trades
            )

        except Exception as e:
            logger.error(f"获取市场数据失败: {e}")
            return None

    async def fetch_klines(self, timeframe: str = '15m', limit: int = 100) -> List[List]:
        """获取K线数据"""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(self.symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            logger.error(f"获取K线数据失败: {e}")
            return []

    def detect_whale_trade(self, trades: List[Dict]) -> List[Dict]:
        """检测大额交易"""
        threshold = CONFIG_MARKET['whale_threshold_usd']
        whales = []

        for trade in trades:
            if trade['value'] >= threshold:
                whale_info = {
                    **trade,
                    'type': 'BUY' if not trade['is_buyer_maker'] else 'SELL',
                    'detected_at': datetime.now()
                }
                whales.append(whale_info)
                logger.info(f"[WHALE] 检测到大额交易: {whale_info['type']} "
                           f"价格: {trade['price']:.6f} 数量: {trade['quantity']:.2f} "
                           f"价值: ${trade['value']:.2f}")

        return whales

    def analyze_market(self, data: MarketData) -> IndicatorResult:
        """分析市场数据"""
        # 更新价格历史
        self.price_history.append(data.price)
        if len(self.price_history) > 500:
            self.price_history = self.price_history[-500:]

        # 计算所有指标
        result = self.indicators.calculate_all(
            orderbook=data.orderbook,
            trades=data.recent_trades,
            prices=self.price_history,
            close_prices=self.close_history if self.close_history else None,
            high_prices=self.high_history if self.high_history else None,
            low_prices=self.low_history if self.low_history else None
        )

        return result

    def build_display(self) -> Panel:
        """构建显示面板"""
        if not self.current_data or not self.current_indicators:
            return Panel("等待数据...", title="System M - 盘面监控")

        data = self.current_data
        ind = self.current_indicators

        # 构建状态文本
        lines = []

        # 时间戳和基础信息
        timestamp = data.timestamp.strftime("%H:%M:%S")
        price_color = "green" if data.change_24h >= 0 else "red"

        # 第一行: 时间 + 价格 + 涨跌幅
        line1 = Text()
        line1.append(f"[{timestamp}] ", style="dim")
        line1.append("◉ 监控中 ", style="cyan")
        line1.append(f"| 价: {data.price:.6f} ", style=price_color)
        line1.append(f"({data.change_24h:+.2f}%) ", style=price_color)
        lines.append(line1)

        # 第二行: 核心指标
        line2 = Text()
        obi_color = "green" if ind.obi > 0 else "red" if ind.obi < 0 else "white"
        cvd_color = "green" if ind.cvd > 0 else "red" if ind.cvd < 0 else "white"
        line2.append(f"| OBI: {ind.obi:+.3f} ", style=obi_color)
        line2.append(f"| CVD: {ind.cvd:+.0f} ", style=cvd_color)
        line2.append(f"| RSI: {ind.rsi:.1f} ")
        line2.append(f"| VR: {ind.vr:.2f} ")
        lines.append(line2)

        # 第三行: 更多指标
        line3 = Text()
        slope_color = "green" if ind.slope > 0 else "red" if ind.slope < 0 else "white"
        line3.append(f"| Slope: {ind.slope:+.4f} ", style=slope_color)
        line3.append(f"| VWAP: {ind.vwap:.6f} ")
        line3.append(f"| 鲸鱼: {ind.whale_pct:.1f}% ({ind.whale_direction}) ")
        lines.append(line3)

        # 第四行: 综合评分和极端状态
        line4 = Text()
        score_color = "green" if ind.score >= 60 else "red" if ind.score <= 40 else "yellow"
        line4.append(f"| Score: {ind.score} ", style=score_color)
        line4.append(f"({self.indicators.get_score_description(ind.score)}) ", style=score_color)
        if ind.extreme_state:
            extreme_color = "red" if "卖" in ind.extreme_state else "green"
            line4.append(f" {ind.extreme_state} ", style=f"bold {extreme_color}")
        lines.append(line4)

        # 第五行: 多时间框架趋势
        line5 = Text()
        line5.append("| MTF: ")
        for tf, trend in self.mtf_trends.items():
            trend_color = "green" if "多" in trend else "red" if "空" in trend else "yellow"
            line5.append(f"{tf}:{trend} ", style=trend_color)
        lines.append(line5)

        # 第六行: 倒计时
        countdowns = self.countdown.get_all_countdowns()
        line6 = Text()
        line6.append("| [下次刷新] ", style="dim")
        for tf, secs in countdowns.items():
            line6.append(f"{tf}: {self.countdown.format_countdown(secs)} ", style="cyan")
        lines.append(line6)

        # 组合所有行
        content = Text("\n").join(lines)

        return Panel(
            content,
            title=f"[bold cyan]System M - {self.symbol} 盘面监控[/bold cyan]",
            border_style="cyan"
        )

    async def update_mtf_trends(self):
        """更新多时间框架趋势"""
        timeframe_map = {"15M": "15m", "4H": "4h", "1D": "1d"}

        for tf_display, tf_api in timeframe_map.items():
            try:
                klines = await self.fetch_klines(tf_api, limit=20)
                if klines:
                    closes = [k[4] for k in klines]  # 收盘价
                    if len(closes) >= 10:
                        # 简单趋势判断
                        ma_short = sum(closes[-5:]) / 5
                        ma_long = sum(closes[-10:]) / 10
                        current = closes[-1]

                        if current > ma_short > ma_long:
                            self.mtf_trends[tf_display] = "多"
                        elif current < ma_short < ma_long:
                            self.mtf_trends[tf_display] = "空"
                        else:
                            self.mtf_trends[tf_display] = "中性"
            except Exception as e:
                logger.debug(f"更新 {tf_display} 趋势失败: {e}")

    async def run_once(self):
        """执行一次数据获取和分析"""
        data = await self.fetch_market_data()
        if data:
            self.current_data = data
            self.current_indicators = self.analyze_market(data)

            # 检测大额交易
            whales = self.detect_whale_trade(data.recent_trades)
            self.whale_trades.extend(whales)

            # 保持大额交易记录在合理范围
            if len(self.whale_trades) > 100:
                self.whale_trades = self.whale_trades[-100:]

    async def run(self):
        """主运行循环"""
        await self.initialize()
        self.running = True

        console.print("[bold green]System M - 盘面监控已启动[/bold green]")
        console.print(f"监控交易对: {self.symbol}")
        console.print(f"刷新间隔: {self.interval}秒")
        console.print("-" * 50)

        # 初始获取K线数据用于历史指标
        klines = await self.fetch_klines('15m', limit=100)
        if klines:
            self.close_history = [k[4] for k in klines]
            self.high_history = [k[2] for k in klines]
            self.low_history = [k[3] for k in klines]

        # 更新MTF趋势
        await self.update_mtf_trends()

        mtf_update_counter = 0

        with Live(self.build_display(), console=console, refresh_per_second=1) as live:
            while self.running:
                try:
                    await self.run_once()

                    # 每60秒更新一次MTF趋势
                    mtf_update_counter += self.interval
                    if mtf_update_counter >= 60:
                        await self.update_mtf_trends()
                        mtf_update_counter = 0

                    live.update(self.build_display())
                    await asyncio.sleep(self.interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"运行错误: {e}")
                    await asyncio.sleep(self.interval)

    async def shutdown(self):
        """关闭监控器"""
        self.running = False
        if self.exchange:
            await self.exchange.close()
        logger.info("System M 已关闭")


async def main():
    parser = argparse.ArgumentParser(description='Shell Market Watcher - System M')
    parser.add_argument('--symbol', '-s', type=str, default=CONFIG_MARKET['symbol'],
                        help='交易对 (默认: SHELL/USDT)')
    parser.add_argument('--interval', '-i', type=int, default=CONFIG_MARKET['refresh_interval'],
                        help='刷新间隔秒数 (默认: 5)')
    args = parser.parse_args()

    watcher = MarketWatcher(symbol=args.symbol, interval=args.interval)

    # 设置信号处理
    def signal_handler(sig, frame):
        console.print("\n[yellow]正在关闭...[/yellow]")
        asyncio.create_task(watcher.shutdown())

    signal.signal(signal.SIGINT, signal_handler)

    try:
        await watcher.run()
    finally:
        await watcher.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
