#!/usr/bin/env python3
"""
Flow Radar - Alert Monitor
流动性雷达 - 自动盯盘警报系统

自动监控并在重要信号出现时发出警报
"""

import asyncio
import argparse
import winsound
import sys
from datetime import datetime
from typing import Optional, Dict, List

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
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

from config.settings import CONFIG_MARKET, CONFIG_ICEBERG
from core.indicators import Indicators
from core.derivatives import (
    DerivativesDataFetcher, calculate_binned_cvd,
    predict_liquidation_cascade
)

console = Console()


class AlertMonitor:
    """自动盯盘警报系统"""

    def __init__(self, symbol: str = None):
        self.symbol = symbol or CONFIG_MARKET['symbol']
        self.exchange = None
        self.running = False

        # 组件
        self.indicators = Indicators(whale_threshold_usd=CONFIG_MARKET['whale_threshold_usd'])
        self.derivatives = DerivativesDataFetcher()

        # 状态追踪
        self.last_score = 50
        self.last_whale_flow = 0
        self.total_whale_flow = 0  # 累计净鲸流
        self.last_pattern = ""
        self.alerts_history: List[Dict] = []

        # 警报阈值
        self.score_buy_threshold = 60      # 分数超过这个考虑买
        self.score_sell_threshold = 35     # 分数低于这个考虑卖
        self.whale_flow_threshold = 100000  # 净鲸流变化超过10万触发

        # MTF趋势
        self.mtf_trends = {"1D": "中性", "4H": "中性", "15M": "中性"}

        # 冰山单
        self.iceberg_buys = []
        self.iceberg_sells = []

        # 合约数据
        self.funding_rate = None
        self.long_short_ratio = None

    async def initialize(self):
        """初始化"""
        exchange_id = CONFIG_MARKET.get('exchange', 'okx')
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })

    def play_alert(self, alert_type: str = "normal"):
        """播放警报声音"""
        try:
            if alert_type == "buy":
                # 上涨音效 - 高音
                winsound.Beep(800, 200)
                winsound.Beep(1000, 200)
                winsound.Beep(1200, 300)
            elif alert_type == "sell":
                # 下跌音效 - 低音
                winsound.Beep(600, 200)
                winsound.Beep(400, 200)
                winsound.Beep(300, 300)
            elif alert_type == "warning":
                # 警告音效
                for _ in range(3):
                    winsound.Beep(1000, 100)
                    winsound.Beep(500, 100)
            else:
                # 普通提示音
                winsound.Beep(700, 300)
        except:
            pass  # 静默失败

    def add_alert(self, level: str, message: str, alert_type: str = "normal"):
        """添加警报"""
        alert = {
            "time": datetime.now(),
            "level": level,
            "message": message
        }
        self.alerts_history.append(alert)
        if len(self.alerts_history) > 20:
            self.alerts_history = self.alerts_history[-20:]

        # 播放声音
        self.play_alert(alert_type)

        # 打印到控制台
        color = {
            "🟢 买入": "green",
            "🔴 卖出": "red",
            "⚠️ 警告": "yellow",
            "📢 信号": "cyan"
        }.get(level, "white")

        console.print(f"\n[bold {color}]{'='*60}[/bold {color}]")
        console.print(f"[bold {color}]{level}[/bold {color}] {message}")
        console.print(f"[dim]时间: {alert['time'].strftime('%H:%M:%S')}[/dim]")
        console.print(f"[bold {color}]{'='*60}[/bold {color}]\n")

    async def fetch_data(self) -> Optional[Dict]:
        """获取所有数据"""
        try:
            # 基础数据
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
            return None

    async def update_mtf(self):
        """更新多时间框架"""
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
            except:
                pass

    async def update_derivatives(self):
        """更新合约数据"""
        try:
            data = await self.derivatives.fetch_all(self.symbol)
            self.funding_rate = data.get("funding_rate")
            self.long_short_ratio = data.get("long_short_ratio")
        except:
            pass

    def analyze_and_alert(self, data: Dict):
        """分析数据并触发警报"""
        # 计算指标
        ind = self.indicators.calculate_all(
            orderbook=data['orderbook'],
            trades=data['trades']
        )

        price = data['ticker']['last']

        # 计算净鲸流 (本次)
        whale_flow = 0
        for trade in data['trades']:
            value = trade['price'] * trade['quantity']
            if value >= CONFIG_MARKET['whale_threshold_usd']:
                is_buy = not trade['is_buyer_maker']
                whale_flow += value if is_buy else -value

        # 累加到总净鲸流
        self.total_whale_flow += whale_flow

        # 计算分级CVD
        binned_cvd = calculate_binned_cvd(data['trades'], price)

        # 计算综合分数 (与 Command Center 保持一致)
        score = 50
        bullish = sum(1 for t in self.mtf_trends.values() if t == "多")
        bearish = sum(1 for t in self.mtf_trends.values() if t == "空")
        score += (bullish - bearish) * 10
        score += int(ind.obi * 20)

        # 使用累计净鲸流而不是单次
        total_whale_flow = self.total_whale_flow
        if total_whale_flow > 50000:
            score += 15
        elif total_whale_flow > 20000:
            score += 10
        elif total_whale_flow > 5000:
            score += 5
        elif total_whale_flow < -50000:
            score -= 15
        elif total_whale_flow < -20000:
            score -= 10
        elif total_whale_flow < -5000:
            score -= 5

        # CVD加分
        if ind.cvd > 5000:
            score += 10
        elif ind.cvd < -5000:
            score -= 10

        score = max(0, min(100, score))

        # 检测模式
        pattern = ""
        # 战略洗盘
        if whale_flow > 10000 and (self.mtf_trends['15M'] == "空" or self.mtf_trends['4H'] == "空"):
            pattern = "战略洗盘"
        # 诱多陷阱
        elif self.mtf_trends['1D'] == "空" and self.mtf_trends['15M'] == "多":
            if ind.obi > 0.3:
                pattern = "诱多陷阱"
        # 诱空陷阱
        elif self.mtf_trends['1D'] == "多" and self.mtf_trends['15M'] == "空":
            if ind.obi < -0.3:
                pattern = "诱空陷阱"

        # 聪明钱信号
        smart_money = ""
        if binned_cvd.whale_cvd > 5000 and binned_cvd.retail_cvd < -3000:
            smart_money = "聪明钱买入，散户恐慌"
        elif binned_cvd.whale_cvd < -5000 and binned_cvd.retail_cvd > 3000:
            smart_money = "聪明钱出货，散户接盘"

        # ========== 警报检测 ==========

        # 1. 分数突破
        if score >= 60 and self.last_score < 60:
            self.add_alert("🟢 买入", f"分数突破60! 当前: {score} | 可以考虑买入", "buy")
        elif score >= 70 and self.last_score < 70:
            self.add_alert("🟢 买入", f"分数突破70! 当前: {score} | 强烈买入信号!", "buy")
        elif score <= 35 and self.last_score > 35:
            self.add_alert("🔴 卖出", f"分数跌破35! 当前: {score} | 不要买入", "sell")
        elif score <= 25 and self.last_score > 25:
            self.add_alert("🔴 卖出", f"分数跌破25! 当前: {score} | 强烈看空!", "sell")

        # 2. 模式检测
        if pattern and pattern != self.last_pattern:
            if pattern == "战略洗盘":
                self.add_alert("📢 信号", f"【{pattern}】大户净流入为正，回踩锚点支撑，严禁恐慌抛售!", "buy")
            elif pattern == "诱多陷阱":
                self.add_alert("⚠️ 警告", f"【{pattern}】检测到高位派发，请勿追涨!", "warning")
            elif pattern == "诱空陷阱":
                self.add_alert("📢 信号", f"【{pattern}】检测到低位吸筹，请勿追跌!", "buy")

        # 3. 聪明钱信号
        if smart_money:
            if "买入" in smart_money:
                self.add_alert("🟢 买入", f"【聪明钱】{smart_money}", "buy")
            else:
                self.add_alert("🔴 卖出", f"【聪明钱】{smart_money}", "sell")

        # 4. 鲸鱼大动作
        flow_change = whale_flow - self.last_whale_flow
        if abs(flow_change) > self.whale_flow_threshold:
            if flow_change > 0:
                self.add_alert("🟢 买入", f"鲸鱼大买! 净流入: +${whale_flow:,.0f}", "buy")
            else:
                self.add_alert("🔴 卖出", f"鲸鱼大卖! 净流出: ${whale_flow:,.0f}", "sell")

        # 5. 三时间框架共振
        if all(t == "多" for t in self.mtf_trends.values()):
            self.add_alert("🟢 买入", "【三重共振】1D+4H+15M 全部看多!", "buy")
        elif all(t == "空" for t in self.mtf_trends.values()):
            self.add_alert("🔴 卖出", "【三重共振】1D+4H+15M 全部看空!", "sell")

        # 6. 多空比极端
        if self.long_short_ratio:
            ls = self.long_short_ratio.long_short_ratio
            if ls > 2.5:
                self.add_alert("⚠️ 警告", f"散户极度看多! 多空比: {ls:.2f} | 小心回调", "warning")
            elif ls < 0.4:
                self.add_alert("📢 信号", f"散户极度看空! 多空比: {ls:.2f} | 可能反弹", "buy")

        # 更新状态
        self.last_score = score
        self.last_whale_flow = whale_flow
        self.last_pattern = pattern

        return {
            "price": price,
            "score": score,
            "whale_flow": self.total_whale_flow,  # 使用累计值
            "pattern": pattern,
            "smart_money": smart_money,
            "binned_cvd": binned_cvd,
            "indicators": ind
        }

    def build_display(self, analysis: Dict) -> Panel:
        """构建显示面板"""
        lines = []

        # 标题
        title = Text()
        title.append(f"🎯 DOGE 自动盯盘 ", style="bold yellow")
        title.append(f"| {datetime.now().strftime('%H:%M:%S')}", style="dim")
        lines.append(title)
        lines.append(Text(""))

        # 核心数据
        price_line = Text()
        price_line.append(f"💰 价格: ${analysis['price']:.6f} ", style="cyan")
        score = analysis['score']
        score_color = "green" if score >= 60 else "red" if score <= 35 else "yellow"
        price_line.append(f"| 分数: {score} ", style=f"bold {score_color}")
        lines.append(price_line)

        # MTF
        mtf_line = Text()
        mtf_line.append("📊 趋势: ")
        for tf, trend in self.mtf_trends.items():
            color = "green" if trend == "多" else "red" if trend == "空" else "yellow"
            mtf_line.append(f"{tf}:{trend} ", style=color)
        lines.append(mtf_line)

        # 鲸鱼流
        whale_line = Text()
        wf = analysis['whale_flow']
        wf_color = "green" if wf > 0 else "red" if wf < 0 else "white"
        whale_line.append(f"🐋 净鲸流: ", style="white")
        whale_line.append(f"${wf:+,.0f}", style=wf_color)
        lines.append(whale_line)

        # 分级CVD
        cvd = analysis['binned_cvd']
        cvd_line = Text()
        cvd_line.append("📈 资金流: ")
        cvd_line.append(f"鲸鱼:{cvd.whale_cvd:+,.0f} ", style="green" if cvd.whale_cvd > 0 else "red")
        cvd_line.append(f"散户:{cvd.retail_cvd:+,.0f}", style="green" if cvd.retail_cvd > 0 else "red")
        lines.append(cvd_line)

        # 当前信号
        lines.append(Text(""))
        if analysis['pattern']:
            pattern_line = Text()
            pattern_line.append(f"⚡ 【{analysis['pattern']}】", style="bold magenta")
            lines.append(pattern_line)

        if analysis['smart_money']:
            smart_line = Text()
            smart_line.append(f"🧠 {analysis['smart_money']}", style="bold cyan")
            lines.append(smart_line)

        # 最近警报
        if self.alerts_history:
            lines.append(Text(""))
            lines.append(Text("📢 最近警报:", style="bold"))
            for alert in self.alerts_history[-5:]:
                alert_line = Text()
                alert_line.append(f"  [{alert['time'].strftime('%H:%M:%S')}] ", style="dim")
                alert_line.append(f"{alert['level']} ", style="bold")
                alert_line.append(alert['message'][:40], style="white")
                lines.append(alert_line)

        # 操作建议
        lines.append(Text(""))
        lines.append(Text("-" * 50, style="dim"))
        advice_line = Text()
        score = analysis['score']
        if score >= 70:
            advice_line.append("💡 建议: 可以买入!", style="bold green")
        elif score >= 50:
            advice_line.append("💡 建议: 观望偏多", style="yellow")
        elif score >= 35:
            advice_line.append("💡 建议: 观望", style="yellow")
        else:
            advice_line.append("💡 建议: 不要买!", style="bold red")
        lines.append(advice_line)

        content = Text("\n").join(lines)
        return Panel(
            content,
            title=f"[bold cyan]Flow Radar Alert Monitor - {self.symbol}[/bold cyan]",
            border_style="cyan"
        )

    async def run(self):
        """主运行循环"""
        await self.initialize()
        self.running = True

        console.print("[bold cyan]=" * 60)
        console.print("[bold cyan]🎯 Flow Radar 自动盯盘系统启动!")
        console.print(f"[bold cyan]   监控: {self.symbol}")
        console.print("[bold cyan]   有重要信号时会自动发出声音警报!")
        console.print("[bold cyan]=" * 60)
        console.print("")

        # 初始更新
        await self.update_mtf()
        await self.update_derivatives()

        counter = 0

        with Live(console=console, refresh_per_second=1) as live:
            while self.running:
                try:
                    data = await self.fetch_data()
                    if data:
                        analysis = self.analyze_and_alert(data)
                        live.update(self.build_display(analysis))

                    # 每60秒更新MTF和合约数据
                    counter += 5
                    if counter >= 60:
                        await self.update_mtf()
                        await self.update_derivatives()
                        counter = 0

                    await asyncio.sleep(5)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    console.print(f"[red]错误: {e}[/red]")
                    await asyncio.sleep(5)

    async def shutdown(self):
        """关闭"""
        self.running = False
        if self.exchange:
            await self.exchange.close()
        if self.derivatives:
            await self.derivatives.close()


async def main():
    parser = argparse.ArgumentParser(description='Flow Radar Alert Monitor')
    parser.add_argument('--symbol', '-s', type=str, default='DOGE/USDT',
                        help='交易对 (默认: DOGE/USDT)')
    args = parser.parse_args()

    monitor = AlertMonitor(symbol=args.symbol)

    try:
        await monitor.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]正在关闭...[/yellow]")
    finally:
        await monitor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
