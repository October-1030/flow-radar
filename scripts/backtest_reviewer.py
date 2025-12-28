#!/usr/bin/env python3
"""
Shell Market Watcher - System R (Replay Engine)
回测复盘引擎

职责: 历史信号回测与策略评估
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
import logging

try:
    import ccxt.async_support as ccxt
    import pandas as pd
    import numpy as np
except ImportError:
    print("请安装依赖: pip install ccxt pandas numpy")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import CONFIG_MARKET, SIGNAL_DIR, BACKTEST_DIR
from core.indicators import Indicators


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('SystemR')

console = Console()


@dataclass
class BacktestSignal:
    """回测信号"""
    timestamp: datetime
    signal_type: str
    direction: str
    entry_price: float
    confidence: float
    details: Dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    """回测结果"""
    signal: BacktestSignal
    exit_price: float
    exit_time: datetime
    holding_period: int             # 秒
    pnl_pct: float                  # 百分比收益
    is_win: bool
    max_favorable: float            # 最大有利方向移动
    max_adverse: float              # 最大不利方向移动


@dataclass
class SignalTypeStats:
    """信号类型统计"""
    signal_type: str
    samples: int
    win_rate: float
    profit_factor: float
    expectancy: float               # 期望收益
    avg_win: float
    avg_loss: float
    avg_holding_period: float


class BacktestReviewer:
    """System R - 回测复盘引擎"""

    def __init__(self, symbol: str = None):
        self.symbol = symbol or CONFIG_MARKET['symbol']
        self.exchange: Optional[ccxt.Exchange] = None
        self.indicators = Indicators()

        # 回测数据
        self.signals: List[BacktestSignal] = []
        self.results: List[BacktestResult] = []
        self.ohlcv_data: Optional[pd.DataFrame] = None

        # 回测参数
        self.holding_periods = [60, 300, 900, 1800, 3600]  # 评估时间点（秒）
        self.default_holding = 900  # 默认持有15分钟

    async def initialize(self):
        """初始化"""
        exchange_id = CONFIG_MARKET.get('exchange', 'binance')
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({'enableRateLimit': True})
        logger.info("System R - 回测引擎初始化完成")

    async def fetch_historical_data(
        self,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = '1m'
    ) -> pd.DataFrame:
        """获取历史K线数据"""
        console.print(f"获取历史数据: {start_date} - {end_date}")

        all_ohlcv = []
        current = start_date

        with Progress() as progress:
            task = progress.add_task("下载K线数据...", total=100)

            while current < end_date:
                try:
                    ohlcv = await self.exchange.fetch_ohlcv(
                        self.symbol,
                        timeframe,
                        since=int(current.timestamp() * 1000),
                        limit=1000
                    )

                    if not ohlcv:
                        break

                    all_ohlcv.extend(ohlcv)
                    current = datetime.fromtimestamp(ohlcv[-1][0] / 1000) + timedelta(minutes=1)

                    # 更新进度
                    progress_pct = min(100, ((current - start_date) / (end_date - start_date)) * 100)
                    progress.update(task, completed=progress_pct)

                    await asyncio.sleep(0.1)  # 避免速率限制

                except Exception as e:
                    logger.error(f"获取数据错误: {e}")
                    await asyncio.sleep(1)

        if not all_ohlcv:
            return pd.DataFrame()

        df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df[~df.index.duplicated(keep='first')]

        console.print(f"获取到 {len(df)} 条K线数据")
        self.ohlcv_data = df
        return df

    def load_signals_from_file(self, filepath: str) -> int:
        """从文件加载信号"""
        path = Path(filepath)
        if not path.exists():
            logger.error(f"文件不存在: {filepath}")
            return 0

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        loaded = 0
        for s in data.get('signals', []):
            try:
                signal = BacktestSignal(
                    timestamp=datetime.fromisoformat(s['timestamp']),
                    signal_type=s['signal_type'],
                    direction=s['direction'],
                    entry_price=s['price_at_signal'],
                    confidence=s.get('confidence', 50),
                    details=s.get('details', {})
                )
                self.signals.append(signal)
                loaded += 1
            except Exception as e:
                logger.warning(f"加载信号失败: {e}")

        console.print(f"加载了 {loaded} 个信号")
        return loaded

    def generate_synthetic_signals(self, count: int = 100):
        """生成模拟信号用于测试"""
        if self.ohlcv_data is None or len(self.ohlcv_data) == 0:
            logger.error("没有K线数据，无法生成模拟信号")
            return

        import random

        signal_types = [
            'WHALE_BUY', 'WHALE_SELL',
            'ICEBERG_BUY', 'ICEBERG_SELL',
            'STRONG_BULLISH', 'STRONG_BEARISH'
        ]

        indices = random.sample(range(len(self.ohlcv_data) - 100), min(count, len(self.ohlcv_data) - 100))

        for idx in indices:
            row = self.ohlcv_data.iloc[idx]
            signal_type = random.choice(signal_types)

            self.signals.append(BacktestSignal(
                timestamp=row.name.to_pydatetime(),
                signal_type=signal_type,
                direction='LONG' if 'BUY' in signal_type or 'BULLISH' in signal_type else 'SHORT',
                entry_price=row['close'],
                confidence=random.uniform(40, 90)
            ))

        console.print(f"生成了 {len(self.signals)} 个模拟信号")

    def backtest_signal(
        self,
        signal: BacktestSignal,
        holding_period: int = None
    ) -> Optional[BacktestResult]:
        """回测单个信号"""
        if self.ohlcv_data is None:
            return None

        holding_period = holding_period or self.default_holding

        # 找到信号时间对应的数据
        try:
            start_idx = self.ohlcv_data.index.get_indexer([signal.timestamp], method='nearest')[0]
        except:
            return None

        # 计算结束位置
        end_idx = start_idx + (holding_period // 60)  # 假设1分钟K线
        if end_idx >= len(self.ohlcv_data):
            return None

        # 获取期间数据
        period_data = self.ohlcv_data.iloc[start_idx:end_idx + 1]

        if len(period_data) == 0:
            return None

        entry_price = signal.entry_price
        exit_price = period_data.iloc[-1]['close']
        exit_time = period_data.index[-1].to_pydatetime()

        # 计算最大有利/不利移动
        if signal.direction == 'LONG':
            max_favorable = (period_data['high'].max() - entry_price) / entry_price * 100
            max_adverse = (entry_price - period_data['low'].min()) / entry_price * 100
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            max_favorable = (entry_price - period_data['low'].min()) / entry_price * 100
            max_adverse = (period_data['high'].max() - entry_price) / entry_price * 100
            pnl_pct = (entry_price - exit_price) / entry_price * 100

        return BacktestResult(
            signal=signal,
            exit_price=exit_price,
            exit_time=exit_time,
            holding_period=holding_period,
            pnl_pct=pnl_pct,
            is_win=pnl_pct > 0,
            max_favorable=max_favorable,
            max_adverse=max_adverse
        )

    def run_backtest(self, holding_period: int = None) -> List[BacktestResult]:
        """运行回测"""
        console.print(f"\n运行回测: {len(self.signals)} 个信号, 持有时间: {holding_period or self.default_holding}秒")

        self.results = []

        with Progress() as progress:
            task = progress.add_task("回测中...", total=len(self.signals))

            for signal in self.signals:
                result = self.backtest_signal(signal, holding_period)
                if result:
                    self.results.append(result)
                progress.advance(task)

        console.print(f"完成回测: {len(self.results)} 个有效结果")
        return self.results

    def calculate_stats_by_type(self) -> List[SignalTypeStats]:
        """按信号类型计算统计"""
        if not self.results:
            return []

        # 按类型分组
        type_results: Dict[str, List[BacktestResult]] = {}
        for result in self.results:
            signal_type = result.signal.signal_type
            if signal_type not in type_results:
                type_results[signal_type] = []
            type_results[signal_type].append(result)

        stats_list = []
        for signal_type, results in type_results.items():
            wins = [r for r in results if r.is_win]
            losses = [r for r in results if not r.is_win]

            win_rate = len(wins) / len(results) * 100 if results else 0

            total_win = sum(r.pnl_pct for r in wins)
            total_loss = abs(sum(r.pnl_pct for r in losses))

            profit_factor = total_win / total_loss if total_loss > 0 else float('inf')

            avg_win = total_win / len(wins) if wins else 0
            avg_loss = total_loss / len(losses) if losses else 0

            # 期望收益 = 胜率 * 平均盈利 - 败率 * 平均亏损
            expectancy = (win_rate / 100) * avg_win - ((100 - win_rate) / 100) * avg_loss

            avg_holding = sum(r.holding_period for r in results) / len(results)

            stats_list.append(SignalTypeStats(
                signal_type=signal_type,
                samples=len(results),
                win_rate=win_rate,
                profit_factor=profit_factor,
                expectancy=expectancy,
                avg_win=avg_win,
                avg_loss=avg_loss,
                avg_holding_period=avg_holding
            ))

        return stats_list

    def generate_report(self) -> str:
        """生成回测报告"""
        if not self.results:
            return "没有回测结果"

        stats = self.calculate_stats_by_type()

        # 创建表格
        table = Table(title="信号类型回测统计", show_header=True, header_style="bold magenta")
        table.add_column("类型", style="cyan")
        table.add_column("样本数", justify="right")
        table.add_column("胜率%", justify="right")
        table.add_column("盈亏比", justify="right")
        table.add_column("期望收益%", justify="right")
        table.add_column("平均盈利%", justify="right")
        table.add_column("平均亏损%", justify="right")

        for s in sorted(stats, key=lambda x: x.expectancy, reverse=True):
            pf_str = f"{s.profit_factor:.3f}" if s.profit_factor != float('inf') else "INF"
            table.add_row(
                s.signal_type,
                str(s.samples),
                f"{s.win_rate:.2f}",
                pf_str,
                f"{s.expectancy:.3f}",
                f"{s.avg_win:.3f}",
                f"-{s.avg_loss:.3f}"
            )

        console.print(table)

        # 总体统计
        total_trades = len(self.results)
        total_wins = len([r for r in self.results if r.is_win])
        overall_win_rate = total_wins / total_trades * 100 if total_trades else 0

        total_pnl = sum(r.pnl_pct for r in self.results)
        avg_pnl = total_pnl / total_trades if total_trades else 0

        summary = Panel(
            f"总交易数: {total_trades}\n"
            f"总胜率: {overall_win_rate:.2f}%\n"
            f"累计收益: {total_pnl:.3f}%\n"
            f"平均收益: {avg_pnl:.3f}%",
            title="总体统计",
            border_style="green"
        )
        console.print(summary)

        return f"回测完成: {total_trades} 笔交易, 胜率 {overall_win_rate:.2f}%"

    def save_results(self, filename: str = None):
        """保存回测结果"""
        if filename is None:
            filename = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = BACKTEST_DIR / filename

        data = {
            'generated_at': datetime.now().isoformat(),
            'symbol': self.symbol,
            'total_signals': len(self.signals),
            'total_results': len(self.results),
            'stats': [
                {
                    'signal_type': s.signal_type,
                    'samples': s.samples,
                    'win_rate': s.win_rate,
                    'profit_factor': s.profit_factor if s.profit_factor != float('inf') else 'INF',
                    'expectancy': s.expectancy,
                    'avg_win': s.avg_win,
                    'avg_loss': s.avg_loss
                }
                for s in self.calculate_stats_by_type()
            ],
            'results': [
                {
                    'signal_type': r.signal.signal_type,
                    'direction': r.signal.direction,
                    'entry_time': r.signal.timestamp.isoformat(),
                    'entry_price': r.signal.entry_price,
                    'exit_time': r.exit_time.isoformat(),
                    'exit_price': r.exit_price,
                    'pnl_pct': r.pnl_pct,
                    'is_win': r.is_win,
                    'max_favorable': r.max_favorable,
                    'max_adverse': r.max_adverse
                }
                for r in self.results
            ]
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        console.print(f"结果已保存到: {filepath}")

    async def shutdown(self):
        """关闭"""
        if self.exchange:
            await self.exchange.close()


async def main():
    parser = argparse.ArgumentParser(description='Shell Market Watcher - System R')
    parser.add_argument('--symbol', '-s', type=str, default=CONFIG_MARKET['symbol'],
                        help='交易对')
    parser.add_argument('--signals', '-f', type=str,
                        help='信号文件路径')
    parser.add_argument('--days', '-d', type=int, default=7,
                        help='回测天数')
    parser.add_argument('--holding', '-t', type=int, default=900,
                        help='持有时间（秒）')
    parser.add_argument('--synthetic', '-g', type=int, default=0,
                        help='生成模拟信号数量（用于测试）')
    args = parser.parse_args()

    reviewer = BacktestReviewer(symbol=args.symbol)

    try:
        await reviewer.initialize()

        # 获取历史数据
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
        await reviewer.fetch_historical_data(start_date, end_date)

        # 加载或生成信号
        if args.signals:
            reviewer.load_signals_from_file(args.signals)
        elif args.synthetic > 0:
            reviewer.generate_synthetic_signals(args.synthetic)
        else:
            # 尝试加载最新的信号文件
            signal_files = list(SIGNAL_DIR.glob('signals_*.json'))
            if signal_files:
                latest = max(signal_files, key=lambda f: f.stat().st_mtime)
                reviewer.load_signals_from_file(str(latest))
            else:
                console.print("[yellow]未找到信号文件，生成100个模拟信号进行测试[/yellow]")
                reviewer.generate_synthetic_signals(100)

        # 运行回测
        reviewer.run_backtest(args.holding)

        # 生成报告
        reviewer.generate_report()

        # 保存结果
        reviewer.save_results()

    finally:
        await reviewer.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
