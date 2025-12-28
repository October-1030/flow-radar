#!/usr/bin/env python3
"""
Flow Radar - System A (Chain Analyzer)
流动性雷达 - 链上分析层

职责: 链上数据监控与资金流向分析
"""

import asyncio
import argparse
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field
from enum import Enum
import aiohttp

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

from config.settings import CONFIG_CHAIN, CONFIG_MARKET


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(CONFIG_CHAIN['log_path']),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SystemA')

console = Console()


class ChainState(Enum):
    """链上状态枚举"""
    LARGE_INFLOW = "流入"         # 大额流入交易所（利空）
    LARGE_OUTFLOW = "流出"        # 大额流出交易所（利多）
    SMALL_INFLOW = "小幅流入"     # 净流入但量不大
    SMALL_OUTFLOW = "小幅流出"    # 净流出但量不大
    NEUTRAL = "中性"              # 无明显净流向


@dataclass
class LargeTransfer:
    """大额转账记录"""
    timestamp: datetime
    tx_hash: str
    amount: float
    from_address: str
    to_address: str
    direction: str              # 'inflow' or 'outflow'
    exchange: Optional[str] = None

    @property
    def age_minutes(self) -> float:
        """转账发生至今的分钟数"""
        return (datetime.now() - self.timestamp).total_seconds() / 60


@dataclass
class ChainMetrics:
    """链上指标"""
    timestamp: datetime
    exchange_inflow: float = 0.0       # 流入交易所总量
    exchange_outflow: float = 0.0      # 流出交易所总量
    net_flow: float = 0.0              # 净流量
    large_transfers: List[LargeTransfer] = field(default_factory=list)
    holder_change: float = 0.0         # 持仓分布变化
    active_addresses: int = 0          # 活跃地址数
    state: ChainState = ChainState.NEUTRAL

    def calculate_state(self) -> ChainState:
        """计算链上状态"""
        # 检查最近30分钟的大额转账
        recent_large_inflow = sum(
            t.amount for t in self.large_transfers
            if t.direction == 'inflow' and t.age_minutes < 30
        )
        recent_large_outflow = sum(
            t.amount for t in self.large_transfers
            if t.direction == 'outflow' and t.age_minutes < 30
        )

        large_threshold = CONFIG_CHAIN['large_transfer_threshold']
        small_threshold = CONFIG_CHAIN['small_flow_threshold']

        if recent_large_inflow > large_threshold:
            return ChainState.LARGE_INFLOW
        elif recent_large_outflow > large_threshold:
            return ChainState.LARGE_OUTFLOW
        elif self.net_flow > small_threshold:
            return ChainState.SMALL_INFLOW
        elif self.net_flow < -small_threshold:
            return ChainState.SMALL_OUTFLOW
        else:
            return ChainState.NEUTRAL


@dataclass
class ChainSignal:
    """链上信号"""
    timestamp: datetime
    signal_type: str            # 'CHAIN_INFLOW' or 'CHAIN_OUTFLOW'
    amount: float
    direction: str              # 'SHORT' or 'LONG'
    details: str
    confidence: float = 50.0

    def __str__(self):
        arrow = "▼" if self.signal_type == 'CHAIN_INFLOW' else "▲"
        return (f"[CHAIN] {arrow} {self.details} | "
                f"数量: {self.amount:,.0f} | 方向: {self.direction}")


class ChainAnalyzer:
    """System A - 链上分析器"""

    def __init__(self, symbol: str = None):
        self.symbol = symbol or CONFIG_MARKET['symbol']
        self.token = self.symbol.split('/')[0]  # 提取代币符号
        self.running = False

        # 已知交易所钱包
        self.exchange_wallets: Dict[str, str] = {
            # 这里需要配置实际的交易所钱包地址
            # "0x...": "Binance",
            # "0x...": "OKX",
        }

        # 数据存储
        self.metrics_history: List[ChainMetrics] = []
        self.large_transfers: List[LargeTransfer] = []
        self.signals: List[ChainSignal] = []
        self.current_metrics: Optional[ChainMetrics] = None

        # API会话
        self.session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """初始化"""
        self.session = aiohttp.ClientSession()
        logger.info(f"System A - 链上分析器初始化完成 | 监控: {self.token}")

        # 加载交易所钱包配置
        if CONFIG_CHAIN.get('exchange_wallets'):
            self.exchange_wallets.update({
                addr: "Exchange" for addr in CONFIG_CHAIN['exchange_wallets']
            })

    async def fetch_chain_data(self) -> Optional[ChainMetrics]:
        """
        获取链上数据

        注意: 这里提供了模拟数据结构
        实际使用需要对接链上数据API (如 Etherscan, Dune Analytics, Glassnode 等)
        """
        try:
            # TODO: 实际实现需要调用链上数据API
            # 示例代码展示数据结构
            """
            async with self.session.get(
                f"{CONFIG_CHAIN['api_endpoint']}/token/{self.token}/flow",
                headers={"Authorization": f"Bearer {CONFIG_CHAIN['api_key']}"}
            ) as response:
                data = await response.json()
            """

            # 模拟数据 - 实际使用时需替换为真实API调用
            import random

            # 模拟流入流出数据
            inflow = random.uniform(0, 200000)
            outflow = random.uniform(0, 200000)

            # 模拟大额转账
            transfers = []
            if random.random() > 0.8:  # 20%概率出现大额转账
                amount = random.uniform(50000, 500000)
                direction = 'inflow' if random.random() > 0.5 else 'outflow'
                transfers.append(LargeTransfer(
                    timestamp=datetime.now(),
                    tx_hash=f"0x{''.join(random.choices('0123456789abcdef', k=64))}",
                    amount=amount,
                    from_address=f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                    to_address=f"0x{''.join(random.choices('0123456789abcdef', k=40))}",
                    direction=direction,
                    exchange="Binance" if direction == 'inflow' else None
                ))

            metrics = ChainMetrics(
                timestamp=datetime.now(),
                exchange_inflow=inflow,
                exchange_outflow=outflow,
                net_flow=inflow - outflow,
                large_transfers=transfers,
                active_addresses=random.randint(100, 1000)
            )
            metrics.state = metrics.calculate_state()

            return metrics

        except Exception as e:
            logger.error(f"获取链上数据失败: {e}")
            return None

    def detect_signals(self, metrics: ChainMetrics) -> List[ChainSignal]:
        """检测链上信号"""
        signals = []

        # 检查大额流入
        for transfer in metrics.large_transfers:
            if transfer.direction == 'inflow' and transfer.amount >= CONFIG_CHAIN['large_transfer_threshold']:
                signal = ChainSignal(
                    timestamp=transfer.timestamp,
                    signal_type='CHAIN_INFLOW',
                    amount=transfer.amount,
                    direction='SHORT',
                    details=f"大额流入交易所 -> {transfer.exchange or 'Unknown'}",
                    confidence=self._calculate_confidence(transfer)
                )
                signals.append(signal)
                logger.info(str(signal))

            elif transfer.direction == 'outflow' and transfer.amount >= CONFIG_CHAIN['large_transfer_threshold']:
                signal = ChainSignal(
                    timestamp=transfer.timestamp,
                    signal_type='CHAIN_OUTFLOW',
                    amount=transfer.amount,
                    direction='LONG',
                    details="大额流出交易所 (提币)",
                    confidence=self._calculate_confidence(transfer)
                )
                signals.append(signal)
                logger.info(str(signal))

        return signals

    def _calculate_confidence(self, transfer: LargeTransfer) -> float:
        """计算信号置信度"""
        confidence = 50.0

        # 金额越大置信度越高
        if transfer.amount >= 500000:
            confidence += 25
        elif transfer.amount >= 200000:
            confidence += 15
        elif transfer.amount >= 100000:
            confidence += 10

        # 如果目标是已知交易所，置信度更高
        if transfer.exchange:
            confidence += 10

        return min(90.0, confidence)

    def get_state_label(self) -> str:
        """获取链上状态标签"""
        if not self.current_metrics:
            return "[链上: 等待数据]"
        return f"[链上: {self.current_metrics.state.value}]"

    def get_state_color(self) -> str:
        """获取状态颜色"""
        if not self.current_metrics:
            return "dim"

        state = self.current_metrics.state
        if state == ChainState.LARGE_INFLOW:
            return "red"
        elif state == ChainState.LARGE_OUTFLOW:
            return "green"
        elif state == ChainState.SMALL_INFLOW:
            return "yellow"
        elif state == ChainState.SMALL_OUTFLOW:
            return "cyan"
        else:
            return "white"

    def build_display(self) -> Panel:
        """构建显示面板"""
        lines = []

        # 标题
        header = Text()
        header.append(f"[{datetime.now().strftime('%H:%M:%S')}] ", style="dim")
        header.append("System A - 链上分析 ", style="blue bold")
        header.append(f"| 代币: {self.token}", style="white")
        lines.append(header)

        # 当前状态
        if self.current_metrics:
            metrics = self.current_metrics
            state_line = Text()
            state_line.append(f"| 状态: ", style="white")
            state_line.append(self.get_state_label(), style=self.get_state_color())
            state_line.append(f" | 净流量: {metrics.net_flow:+,.0f}", style="white")
            lines.append(state_line)

            # 流入流出详情
            flow_line = Text()
            flow_line.append(f"| 流入: {metrics.exchange_inflow:,.0f} ", style="red")
            flow_line.append(f"| 流出: {metrics.exchange_outflow:,.0f} ", style="green")
            flow_line.append(f"| 活跃地址: {metrics.active_addresses}", style="cyan")
            lines.append(flow_line)
        else:
            lines.append(Text("| 等待链上数据...", style="dim"))

        # 最近大额转账
        recent_transfers = [t for t in self.large_transfers if t.age_minutes < 60][-5:]
        if recent_transfers:
            lines.append(Text("\n最近大额转账:", style="bold"))
            for transfer in recent_transfers:
                t_line = Text()
                arrow = "▼" if transfer.direction == 'inflow' else "▲"
                color = "red" if transfer.direction == 'inflow' else "green"
                t_line.append(f"  {arrow} ", style=color)
                t_line.append(f"{transfer.amount:,.0f} {self.token} ")
                t_line.append(f"({int(transfer.age_minutes)}分钟前) ", style="dim")
                if transfer.exchange:
                    t_line.append(f"-> {transfer.exchange}", style="yellow")
                lines.append(t_line)

        # 最近信号
        if self.signals:
            lines.append(Text("\n链上信号:", style="bold"))
            for signal in self.signals[-3:]:
                s_line = Text()
                arrow = "▼" if signal.signal_type == 'CHAIN_INFLOW' else "▲"
                color = "red" if signal.direction == 'SHORT' else "green"
                time_str = signal.timestamp.strftime('%H:%M:%S')
                s_line.append(f"  [{time_str}] ", style="dim")
                s_line.append(f"{arrow} {signal.details} ", style=color)
                s_line.append(f"置信度: {signal.confidence:.0f}%", style="yellow")
                lines.append(s_line)

        content = Text("\n").join(lines)
        return Panel(
            content,
            title="[bold blue]System A - Chain Analyzer[/bold blue]",
            border_style="blue"
        )

    async def run_once(self):
        """执行一次分析"""
        metrics = await self.fetch_chain_data()
        if metrics:
            self.current_metrics = metrics
            self.metrics_history.append(metrics)

            # 保留最近的数据
            if len(self.metrics_history) > 1000:
                self.metrics_history = self.metrics_history[-1000:]

            # 添加大额转账记录
            for transfer in metrics.large_transfers:
                self.large_transfers.append(transfer)

            # 保留最近24小时的转账
            cutoff = datetime.now() - timedelta(hours=24)
            self.large_transfers = [t for t in self.large_transfers if t.timestamp > cutoff]

            # 检测信号
            new_signals = self.detect_signals(metrics)
            self.signals.extend(new_signals)

            # 保留最近的信号
            if len(self.signals) > 100:
                self.signals = self.signals[-100:]

    async def run(self):
        """主运行循环"""
        await self.initialize()
        self.running = True

        console.print("[bold blue]System A - 链上分析已启动[/bold blue]")
        console.print(f"监控代币: {self.token}")
        console.print(f"监控间隔: {CONFIG_CHAIN['monitoring_interval']}秒")
        console.print("-" * 50)

        with Live(self.build_display(), console=console, refresh_per_second=1) as live:
            while self.running:
                try:
                    await self.run_once()
                    live.update(self.build_display())
                    await asyncio.sleep(CONFIG_CHAIN['monitoring_interval'])

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"运行错误: {e}")
                    await asyncio.sleep(30)

    async def shutdown(self):
        """关闭分析器"""
        self.running = False
        if self.session:
            await self.session.close()
        logger.info("System A 已关闭")


async def main():
    parser = argparse.ArgumentParser(description='Shell Market Watcher - System A')
    parser.add_argument('--symbol', '-s', type=str, default=CONFIG_MARKET['symbol'],
                        help='交易对 (默认: SHELL/USDT)')
    args = parser.parse_args()

    analyzer = ChainAnalyzer(symbol=args.symbol)

    def signal_handler(sig, frame):
        console.print("\n[yellow]正在关闭...[/yellow]")
        asyncio.create_task(analyzer.shutdown())

    signal.signal(signal.SIGINT, signal_handler)

    try:
        await analyzer.run()
    finally:
        await analyzer.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
