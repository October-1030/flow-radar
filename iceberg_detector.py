#!/usr/bin/env python3
"""
Flow Radar - System I (Iceberg Detector)
流动性雷达 - 冰山单检测层

职责: 隐藏大单识别与订单簿深度分析
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

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

from config.settings import CONFIG_ICEBERG, CONFIG_MARKET


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG_ICEBERG['log_path']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SystemI')

console = Console()


@dataclass
class PriceLevel:
    """价格层级追踪"""
    price: float
    visible_quantity: float = 0.0          # 当前可见挂单量
    cumulative_filled: float = 0.0          # 累计成交量
    fill_count: int = 0                     # 成交次数
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    refill_count: int = 0                   # 补单次数
    previous_visible: float = 0.0           # 上次可见量

    def update(self, new_visible: float, filled: float = 0):
        """更新价格层级"""
        # 检测补单行为
        if new_visible > self.visible_quantity and self.visible_quantity > 0:
            self.refill_count += 1

        self.previous_visible = self.visible_quantity
        self.visible_quantity = new_visible
        self.cumulative_filled += filled
        if filled > 0:
            self.fill_count += 1
        self.last_updated = datetime.now()

    @property
    def intensity(self) -> float:
        """计算冰山强度"""
        if self.visible_quantity == 0:
            return 0.0
        return self.cumulative_filled / self.visible_quantity

    @property
    def is_iceberg(self) -> bool:
        """判断是否为冰山单"""
        return (
            self.intensity >= CONFIG_ICEBERG['intensity_threshold'] and
            self.cumulative_filled >= CONFIG_ICEBERG['min_cumulative_volume'] and
            self.refill_count >= CONFIG_ICEBERG['min_refill_count']
        )


@dataclass
class IcebergSignal:
    """冰山单信号"""
    timestamp: datetime
    price: float
    side: str                              # 'BUY' or 'SELL'
    cumulative_volume: float
    visible_depth: float
    intensity: float
    refill_count: int
    confidence: float = 0.0

    def __str__(self):
        return (f"[ICEBERG] {'◉发现隐藏买单' if self.side == 'BUY' else '◉发现隐藏卖单'} | "
                f"价格: {self.price:.6f} | 累计成交: {self.cumulative_volume:.2f}U | "
                f"挂单深度: {self.visible_depth:.2f}U | 强度: {self.intensity:.2f}x")


class IcebergDetector:
    """System I - 冰山单检测器"""

    def __init__(self, symbol: str = None, threshold: float = None):
        self.symbol = symbol or CONFIG_MARKET['symbol']
        self.intensity_threshold = threshold or CONFIG_ICEBERG['intensity_threshold']
        self.exchange: Optional[ccxt.Exchange] = None
        self.running = False

        # 价格层级追踪
        self.bid_levels: Dict[float, PriceLevel] = {}
        self.ask_levels: Dict[float, PriceLevel] = {}

        # 成交记录
        self.recent_trades: List[Dict] = []

        # 检测到的冰山单
        self.iceberg_signals: List[IcebergSignal] = []
        self.active_icebergs: Dict[float, IcebergSignal] = {}

        # 价格容差
        self.price_tolerance = CONFIG_ICEBERG['price_tolerance']

    async def initialize(self):
        """初始化交易所连接"""
        exchange_id = CONFIG_MARKET.get('exchange', 'binance')
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        logger.info(f"System I - 冰山检测器初始化完成")

    def _normalize_price(self, price: float) -> float:
        """价格标准化（处理价格容差）"""
        return round(price, 6)

    def _match_trades_to_levels(self, trades: List[Dict], orderbook: Dict):
        """将成交匹配到价格层级"""
        for trade in trades:
            price = self._normalize_price(trade['price'])
            quantity = trade['quantity']
            is_buy = not trade.get('is_buyer_maker', True)

            # 更新相应的价格层级
            if is_buy:
                # 主动买入 -> 吃掉卖单
                if price in self.ask_levels:
                    self.ask_levels[price].update(
                        self.ask_levels[price].visible_quantity,
                        quantity
                    )
            else:
                # 主动卖出 -> 吃掉买单
                if price in self.bid_levels:
                    self.bid_levels[price].update(
                        self.bid_levels[price].visible_quantity,
                        quantity
                    )

    def _update_orderbook_levels(self, orderbook: Dict):
        """更新订单簿层级"""
        current_time = datetime.now()
        cleanup_threshold = current_time - timedelta(seconds=CONFIG_ICEBERG['detection_window'])

        # 更新买单层级
        current_bids = {self._normalize_price(b[0]): b[1] for b in orderbook.get('bids', [])}
        for price, quantity in current_bids.items():
            if price in self.bid_levels:
                old_visible = self.bid_levels[price].visible_quantity
                # 如果可见量减少，说明有成交
                if quantity < old_visible:
                    filled = old_visible - quantity
                    self.bid_levels[price].update(quantity, filled)
                else:
                    self.bid_levels[price].update(quantity)
            else:
                self.bid_levels[price] = PriceLevel(price=price, visible_quantity=quantity)

        # 更新卖单层级
        current_asks = {self._normalize_price(a[0]): a[1] for a in orderbook.get('asks', [])}
        for price, quantity in current_asks.items():
            if price in self.ask_levels:
                old_visible = self.ask_levels[price].visible_quantity
                if quantity < old_visible:
                    filled = old_visible - quantity
                    self.ask_levels[price].update(quantity, filled)
                else:
                    self.ask_levels[price].update(quantity)
            else:
                self.ask_levels[price] = PriceLevel(price=price, visible_quantity=quantity)

        # 清理过期层级
        self._cleanup_old_levels(cleanup_threshold)

    def _cleanup_old_levels(self, threshold: datetime):
        """清理过期的价格层级"""
        self.bid_levels = {
            p: l for p, l in self.bid_levels.items()
            if l.last_updated > threshold or l.is_iceberg
        }
        self.ask_levels = {
            p: l for p, l in self.ask_levels.items()
            if l.last_updated > threshold or l.is_iceberg
        }

    def detect_icebergs(self) -> List[IcebergSignal]:
        """检测冰山单"""
        detected = []

        # 检测买单冰山
        for price, level in self.bid_levels.items():
            if level.is_iceberg and price not in self.active_icebergs:
                signal = IcebergSignal(
                    timestamp=datetime.now(),
                    price=price,
                    side='BUY',
                    cumulative_volume=level.cumulative_filled,
                    visible_depth=level.visible_quantity,
                    intensity=level.intensity,
                    refill_count=level.refill_count,
                    confidence=self._calculate_confidence(level)
                )
                detected.append(signal)
                self.active_icebergs[price] = signal
                logger.info(str(signal))

        # 检测卖单冰山
        for price, level in self.ask_levels.items():
            if level.is_iceberg and price not in self.active_icebergs:
                signal = IcebergSignal(
                    timestamp=datetime.now(),
                    price=price,
                    side='SELL',
                    cumulative_volume=level.cumulative_filled,
                    visible_depth=level.visible_quantity,
                    intensity=level.intensity,
                    refill_count=level.refill_count,
                    confidence=self._calculate_confidence(level)
                )
                detected.append(signal)
                self.active_icebergs[price] = signal
                logger.info(str(signal))

        self.iceberg_signals.extend(detected)
        return detected

    def _calculate_confidence(self, level: PriceLevel) -> float:
        """计算冰山单置信度"""
        confidence = 50.0

        # 强度贡献
        if level.intensity >= 10:
            confidence += 20
        elif level.intensity >= 5:
            confidence += 10

        # 补单次数贡献
        if level.refill_count >= 10:
            confidence += 15
        elif level.refill_count >= 5:
            confidence += 10

        # 累计成交量贡献
        if level.cumulative_filled >= 5000:
            confidence += 15
        elif level.cumulative_filled >= 2000:
            confidence += 10

        return min(95.0, confidence)

    def get_summary_stats(self) -> Dict:
        """获取汇总统计"""
        buy_icebergs = [s for s in self.iceberg_signals if s.side == 'BUY']
        sell_icebergs = [s for s in self.iceberg_signals if s.side == 'SELL']

        return {
            'total_detected': len(self.iceberg_signals),
            'buy_count': len(buy_icebergs),
            'sell_count': len(sell_icebergs),
            'active_count': len(self.active_icebergs),
            'total_buy_volume': sum(s.cumulative_volume for s in buy_icebergs),
            'total_sell_volume': sum(s.cumulative_volume for s in sell_icebergs),
            'avg_intensity': (
                sum(s.intensity for s in self.iceberg_signals) / len(self.iceberg_signals)
                if self.iceberg_signals else 0
            )
        }

    def build_display(self) -> Panel:
        """构建显示面板"""
        lines = []

        # 标题行
        header = Text()
        header.append(f"[{datetime.now().strftime('%H:%M:%S')}] ", style="dim")
        header.append("System I - 冰山单检测 ", style="cyan bold")
        header.append(f"| 监控: {self.symbol}", style="white")
        lines.append(header)

        # 统计信息
        stats = self.get_summary_stats()
        stat_line = Text()
        stat_line.append(f"| 检测到: {stats['total_detected']} ", style="yellow")
        stat_line.append(f"| 买单: {stats['buy_count']} ", style="green")
        stat_line.append(f"| 卖单: {stats['sell_count']} ", style="red")
        stat_line.append(f"| 活跃: {stats['active_count']}", style="cyan")
        lines.append(stat_line)

        # 活跃冰山单列表
        if self.active_icebergs:
            lines.append(Text("\n活跃冰山单:", style="bold"))
            for price, signal in list(self.active_icebergs.items())[-5:]:
                ice_line = Text()
                side_style = "green" if signal.side == 'BUY' else "red"
                ice_line.append(f"  {'◉买' if signal.side == 'BUY' else '◉卖'} ", style=side_style)
                ice_line.append(f"价格: {signal.price:.6f} ")
                ice_line.append(f"| 累计: {signal.cumulative_volume:.0f}U ")
                ice_line.append(f"| 强度: {signal.intensity:.1f}x ")
                ice_line.append(f"| 置信度: {signal.confidence:.0f}%", style="yellow")
                lines.append(ice_line)
        else:
            lines.append(Text("\n[扫描中] 等待冰山单信号...", style="dim"))

        # 最近检测
        if self.iceberg_signals:
            lines.append(Text("\n最近检测:", style="bold"))
            for signal in self.iceberg_signals[-3:]:
                recent_line = Text()
                side_style = "green" if signal.side == 'BUY' else "red"
                time_str = signal.timestamp.strftime('%H:%M:%S')
                recent_line.append(f"  [{time_str}] ", style="dim")
                recent_line.append(f"{'隐藏买单' if signal.side == 'BUY' else '隐藏卖单'} ", style=side_style)
                recent_line.append(f"@ {signal.price:.6f} ")
                recent_line.append(f"强度: {signal.intensity:.1f}x")
                lines.append(recent_line)

        content = Text("\n").join(lines)
        return Panel(
            content,
            title="[bold magenta]System I - Iceberg Detector[/bold magenta]",
            border_style="magenta"
        )

    async def run_once(self):
        """执行一次检测"""
        try:
            # 获取订单簿
            orderbook = await self.exchange.fetch_order_book(
                self.symbol,
                limit=CONFIG_MARKET['orderbook_depth']
            )

            # 获取最近成交
            trades = await self.exchange.fetch_trades(self.symbol, limit=50)
            formatted_trades = [
                {
                    'price': t['price'],
                    'quantity': t['amount'],
                    'is_buyer_maker': t['side'] == 'sell',
                    'timestamp': t['timestamp']
                }
                for t in trades
            ]

            # 更新订单簿层级
            self._update_orderbook_levels(orderbook)

            # 匹配成交到层级
            self._match_trades_to_levels(formatted_trades, orderbook)

            # 检测冰山单
            new_icebergs = self.detect_icebergs()

            if new_icebergs:
                for signal in new_icebergs:
                    console.print(f"[bold {'green' if signal.side == 'BUY' else 'red'}]{signal}[/bold]")

        except Exception as e:
            logger.error(f"检测错误: {e}")

    async def run(self):
        """主运行循环"""
        await self.initialize()
        self.running = True

        console.print("[bold magenta]System I - 冰山单检测已启动[/bold magenta]")
        console.print(f"监控交易对: {self.symbol}")
        console.print(f"强度阈值: {self.intensity_threshold}x")
        console.print("-" * 50)

        with Live(self.build_display(), console=console, refresh_per_second=1) as live:
            while self.running:
                try:
                    await self.run_once()
                    live.update(self.build_display())
                    await asyncio.sleep(2)  # 冰山检测需要更频繁的更新

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"运行错误: {e}")
                    await asyncio.sleep(5)

    async def shutdown(self):
        """关闭检测器"""
        self.running = False
        if self.exchange:
            await self.exchange.close()
        logger.info("System I 已关闭")


async def main():
    parser = argparse.ArgumentParser(description='Shell Market Watcher - System I')
    parser.add_argument('--symbol', '-s', type=str, default=CONFIG_MARKET['symbol'],
                        help='交易对 (默认: SHELL/USDT)')
    parser.add_argument('--threshold', '-t', type=float, default=CONFIG_ICEBERG['intensity_threshold'],
                        help='强度阈值 (默认: 5.0)')
    args = parser.parse_args()

    detector = IcebergDetector(symbol=args.symbol, threshold=args.threshold)

    def signal_handler(sig, frame):
        console.print("\n[yellow]正在关闭...[/yellow]")
        asyncio.create_task(detector.shutdown())

    signal.signal(signal.SIGINT, signal_handler)

    try:
        await detector.run()
    finally:
        await detector.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
