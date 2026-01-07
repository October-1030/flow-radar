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
from core.price_level import PriceLevel, IcebergLevel, CONFIG_PRICE_LEVEL


# 配置日志（强制 UTF-8 编码以支持中文）
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG_ICEBERG['log_path'], encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('SystemI')

# 强制 StreamHandler 使用 UTF-8（Windows 兼容）
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.stream.reconfigure(encoding='utf-8') if hasattr(handler.stream, 'reconfigure') else None

# Rich Console 配置（强制 UTF-8，禁用旧版 Windows 渲染）
console = Console(force_terminal=True, legacy_windows=False)


# PriceLevel 和 IcebergLevel 已从 core.price_level 导入


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


class TradeDeduplicator:
    """
    P0-2: 成交去重器 (P2-1: deque 优化版)

    使用 (timestamp, id) 组合作为唯一标识，
    维护一个固定容量的 seen-set 防止重复处理同一笔成交。

    性能优化: 使用 collections.deque 替代 list，淘汰操作从 O(n) 变为 O(1)
    """

    def __init__(self, max_size: int = 1000):
        """
        Args:
            max_size: seen-set 最大容量，超出时自动移除最旧的记录
        """
        from collections import deque
        self.max_size = max_size
        self._seen: Dict[str, datetime] = {}      # trade_key -> first_seen_time
        self._order: deque = deque(maxlen=max_size)  # 自动淘汰，O(1) 性能

    def _make_key(self, timestamp: int, trade_id: str) -> str:
        """
        生成唯一键

        Args:
            timestamp: 成交时间戳 (毫秒)
            trade_id: 成交ID (可能是字符串或数字)

        Returns:
            唯一键字符串
        """
        trade_id_str = str(trade_id) if trade_id is not None else ""
        return f"{timestamp}:{trade_id_str}"

    def is_duplicate(self, timestamp: int, trade_id: str) -> bool:
        """
        检查成交是否重复

        Args:
            timestamp: 成交时间戳 (毫秒)
            trade_id: 成交ID

        Returns:
            True 如果是重复成交，False 如果是新成交
        """
        key = self._make_key(timestamp, trade_id)

        if key in self._seen:
            return True

        # 新成交，添加到 seen-set
        # deque(maxlen=N) 满时自动丢弃最左边的元素，需要同步清理 _seen
        if len(self._order) == self.max_size:
            oldest_key = self._order[0]  # 即将被淘汰的 key
            self._seen.pop(oldest_key, None)

        self._seen[key] = datetime.now()
        self._order.append(key)  # 自动淘汰旧元素

        return False

    def filter_trades(self, trades: List[Dict]) -> List[Dict]:
        """
        过滤掉重复的成交记录

        Args:
            trades: 原始成交列表，每个元素需包含 'timestamp' 和 'id' 字段

        Returns:
            去重后的成交列表
        """
        unique_trades = []
        for trade in trades:
            ts = trade.get('timestamp', 0)
            tid = trade.get('id', trade.get('trade_id', ''))

            if not self.is_duplicate(ts, tid):
                unique_trades.append(trade)

        return unique_trades

    @property
    def seen_count(self) -> int:
        """返回已见成交数量"""
        return len(self._seen)

    def clear(self) -> None:
        """清空去重缓存"""
        self._seen.clear()
        self._order.clear()


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

        # P0-2: 成交去重器
        self.trade_deduplicator = TradeDeduplicator(max_size=1000)

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
        """
        将成交匹配到价格层级

        P0-3: 同时用成交数据"解释"订单簿的消失量
        """
        for trade in trades:
            price = self._normalize_price(trade['price'])
            quantity = trade['quantity']
            is_buy = not trade.get('is_buyer_maker', True)

            # 更新相应的价格层级
            if is_buy:
                # 主动买入 -> 吃掉卖单
                if price in self.ask_levels:
                    level = self.ask_levels[price]
                    level.update(level.visible_quantity, quantity)
                    # P0-3: 用实际成交解释消失量
                    level.explain_with_trade(quantity)
            else:
                # 主动卖出 -> 吃掉买单
                if price in self.bid_levels:
                    level = self.bid_levels[price]
                    level.update(level.visible_quantity, quantity)
                    # P0-3: 用实际成交解释消失量
                    level.explain_with_trade(quantity)

    def _update_orderbook_levels(self, orderbook: Dict):
        """
        更新订单簿层级

        P0-3: 记录消失量，但不假设都是成交。
        实际成交由 _match_trades_to_levels 确认。
        """
        current_time = datetime.now()
        cleanup_threshold = current_time - timedelta(seconds=CONFIG_ICEBERG['detection_window'])

        # 更新买单层级
        current_bids = {self._normalize_price(b[0]): b[1] for b in orderbook.get('bids', [])}
        for price, quantity in current_bids.items():
            if price in self.bid_levels:
                old_visible = self.bid_levels[price].visible_quantity
                # 如果可见量减少，记录消失量（可能是成交或撤单）
                if quantity < old_visible:
                    disappeared = old_visible - quantity
                    # P0-3: 只记录消失，不假设成交
                    self.bid_levels[price].record_disappeared(disappeared)
                    self.bid_levels[price].update(quantity)  # 不传 filled，由 _match_trades 确认
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
                    disappeared = old_visible - quantity
                    # P0-3: 只记录消失，不假设成交
                    self.ask_levels[price].record_disappeared(disappeared)
                    self.ask_levels[price].update(quantity)  # 不传 filled，由 _match_trades 确认
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
        """
        计算冰山单置信度

        P0-3: 增加 Spoofing 惩罚机制
        """
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

        # P0-3: iceberg_strength 贡献
        if level.iceberg_strength >= 1.0:
            confidence += 10
        elif level.iceberg_strength >= 0.5:
            confidence += 5

        # P0-3: Spoofing 惩罚 - 低解释比例降低置信度
        spoofing_penalty = level.get_confidence_penalty()
        confidence -= spoofing_penalty

        # 确保置信度在合理范围内
        return max(20.0, min(95.0, confidence))

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

        # 实时监控数据
        monitor_line = Text()
        monitor_line.append(f"| 买盘层级: {len(self.bid_levels)} ", style="green")
        monitor_line.append(f"| 卖盘层级: {len(self.ask_levels)} ", style="red")
        monitor_line.append(f"| 成交追踪中...", style="dim")
        lines.append(monitor_line)

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
                    'timestamp': t['timestamp'],
                    'id': t.get('id', t.get('trade_id', '')),  # P0-2: 添加 id 用于去重
                }
                for t in trades
            ]

            # P0-2: 成交去重 - 过滤掉已处理过的成交
            unique_trades = self.trade_deduplicator.filter_trades(formatted_trades)

            # 更新订单簿层级
            self._update_orderbook_levels(orderbook)

            # 匹配成交到层级（只处理新成交）
            self._match_trades_to_levels(unique_trades, orderbook)

            # 检测冰山单
            new_icebergs = self.detect_icebergs()

            if new_icebergs:
                for signal in new_icebergs:
                    color = 'green' if signal.side == 'BUY' else 'red'
                    # 转义方括号避免 Rich 解析错误
                    signal_text = str(signal).replace('[', '\\[').replace(']', '\\]')
                    console.print(f"[bold {color}]{signal_text}[/bold]")

        except Exception as e:
            import traceback
            logger.error(f"检测错误: {e}")
            logger.debug(f"详细错误信息:\n{traceback.format_exc()}")

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
