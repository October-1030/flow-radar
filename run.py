#!/usr/bin/env python3
"""
Flow Radar - 统一启动脚本
流动性雷达 - 一键启动所有子系统
"""

import asyncio
import argparse
import sys
from datetime import datetime

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)


console = Console()


def print_banner():
    """打印启动横幅"""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ███████╗██╗      ██████╗ ██╗    ██╗                        ║
    ║   ██╔════╝██║     ██╔═══██╗██║    ██║                        ║
    ║   █████╗  ██║     ██║   ██║██║ █╗ ██║                        ║
    ║   ██╔══╝  ██║     ██║   ██║██║███╗██║                        ║
    ║   ██║     ███████╗╚██████╔╝╚███╔███╔╝                        ║
    ║   ╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝                         ║
    ║                                                               ║
    ║   ██████╗  █████╗ ██████╗  █████╗ ██████╗                    ║
    ║   ██╔══██╗██╔══██╗██╔══██╗██╔══██╗██╔══██╗                   ║
    ║   ██████╔╝███████║██║  ██║███████║██████╔╝                   ║
    ║   ██╔══██╗██╔══██║██║  ██║██╔══██║██╔══██╗                   ║
    ║   ██║  ██║██║  ██║██████╔╝██║  ██║██║  ██║                   ║
    ║   ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝                   ║
    ║                                                               ║
    ║   FLOW RADAR - Microstructure Trading System                 ║
    ║   流动性雷达 - 微观结构量化交易系统                           ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="cyan")
    console.print(f"    启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n", style="dim")


async def run_market_watcher(symbol: str, interval: int):
    """运行市场监控"""
    from main import MarketWatcher
    watcher = MarketWatcher(symbol=symbol, interval=interval)
    await watcher.run()


async def run_iceberg_detector(symbol: str, threshold: float):
    """运行冰山检测"""
    from iceberg_detector import IcebergDetector
    detector = IcebergDetector(symbol=symbol, threshold=threshold)
    await detector.run()


async def run_chain_analyzer(symbol: str):
    """运行链上分析"""
    from chain_analyzer import ChainAnalyzer
    analyzer = ChainAnalyzer(symbol=symbol)
    await analyzer.run()


async def run_command_center(symbol: str, mode: str):
    """运行战情指挥"""
    from command_center import CommandCenter
    center = CommandCenter(symbol=symbol, mode=mode)
    await center.run()


async def run_all(symbol: str):
    """运行所有系统"""
    console.print("[bold green]启动全部子系统...[/bold green]")

    console.print("""
[yellow]建议在不同终端分别运行各子系统:[/yellow]

终端1 (System M - 盘面监控):
  python main.py --symbol {symbol}

终端2 (System I - 冰山检测):
  python iceberg_detector.py --symbol {symbol}

终端3 (System A - 链上分析):
  python chain_analyzer.py --symbol {symbol}

终端4 (System C - 战情指挥):
  python command_center.py --symbol {symbol} --mode full_resonance

或者只运行战情指挥中心（已整合M模块）:
  python command_center.py --symbol {symbol}
""".format(symbol=symbol))


def main():
    print_banner()

    parser = argparse.ArgumentParser(
        description='Flow Radar - 流动性雷达 微观结构量化交易系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
子系统说明:
  market (M)    - 盘面监控层: 实时价格、成交量、基础指标
  iceberg (I)   - 冰山检测层: 隐藏大单识别、订单簿分析
  chain (A)     - 链上分析层: 资金流向、大额转账追踪
  command (C)   - 战情指挥: 多维度信号融合与共振判定
  backtest (R)  - 回测复盘: 历史信号回测与策略评估

使用示例:
  python run.py market -s DOGE/USDT
  python run.py command -s DOGE/USDT -m full_resonance
  python run.py backtest -d 7 --synthetic 100
        """
    )

    subparsers = parser.add_subparsers(dest='system', help='选择要运行的子系统')

    # Market Watcher
    market_parser = subparsers.add_parser('market', help='System M - 盘面监控')
    market_parser.add_argument('-s', '--symbol', default='DOGE/USDT', help='交易对')
    market_parser.add_argument('-i', '--interval', type=int, default=5, help='刷新间隔(秒)')

    # Iceberg Detector
    iceberg_parser = subparsers.add_parser('iceberg', help='System I - 冰山检测')
    iceberg_parser.add_argument('-s', '--symbol', default='DOGE/USDT', help='交易对')
    iceberg_parser.add_argument('-t', '--threshold', type=float, default=5.0, help='强度阈值')

    # Chain Analyzer
    chain_parser = subparsers.add_parser('chain', help='System A - 链上分析')
    chain_parser.add_argument('-s', '--symbol', default='DOGE/USDT', help='交易对')

    # Command Center
    command_parser = subparsers.add_parser('command', help='System C - 战情指挥')
    command_parser.add_argument('-s', '--symbol', default='DOGE/USDT', help='交易对')
    command_parser.add_argument('-m', '--mode', default='full_resonance',
                                choices=['full_resonance', 'market_only', 'alert_only'])

    # Backtest
    backtest_parser = subparsers.add_parser('backtest', help='System R - 回测复盘')
    backtest_parser.add_argument('-s', '--symbol', default='DOGE/USDT', help='交易对')
    backtest_parser.add_argument('-d', '--days', type=int, default=7, help='回测天数')
    backtest_parser.add_argument('-f', '--signals', help='信号文件路径')
    backtest_parser.add_argument('--synthetic', type=int, default=0, help='生成模拟信号数量')

    # All
    all_parser = subparsers.add_parser('all', help='运行所有系统(显示启动指南)')
    all_parser.add_argument('-s', '--symbol', default='DOGE/USDT', help='交易对')

    args = parser.parse_args()

    if args.system is None:
        parser.print_help()
        return

    try:
        if args.system == 'market':
            asyncio.run(run_market_watcher(args.symbol, args.interval))
        elif args.system == 'iceberg':
            asyncio.run(run_iceberg_detector(args.symbol, args.threshold))
        elif args.system == 'chain':
            asyncio.run(run_chain_analyzer(args.symbol))
        elif args.system == 'command':
            asyncio.run(run_command_center(args.symbol, args.mode))
        elif args.system == 'backtest':
            from scripts.backtest_reviewer import main as backtest_main
            sys.argv = ['backtest_reviewer.py',
                        '-s', args.symbol,
                        '-d', str(args.days)]
            if args.signals:
                sys.argv.extend(['-f', args.signals])
            if args.synthetic:
                sys.argv.extend(['--synthetic', str(args.synthetic)])
            asyncio.run(backtest_main())
        elif args.system == 'all':
            asyncio.run(run_all(args.symbol))

    except KeyboardInterrupt:
        console.print("\n[yellow]系统已停止[/yellow]")
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise


if __name__ == "__main__":
    main()
