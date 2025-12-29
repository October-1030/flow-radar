#!/usr/bin/env python3
"""
Flow Radar - Alert Monitor (Upgraded)
流动性雷达 - 综合判断系统

自动监控 + 冰山检测 + 综合判断
"""

import asyncio
import argparse
import winsound
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field

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


@dataclass
class PriceLevel:
    """价格层级追踪"""
    price: float
    visible_quantity: float = 0.0
    cumulative_filled: float = 0.0
    fill_count: int = 0
    first_seen: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)
    refill_count: int = 0
    previous_visible: float = 0.0

    def update(self, new_visible: float, filled: float = 0):
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
        if self.visible_quantity == 0:
            return 0.0
        return self.cumulative_filled / self.visible_quantity

    @property
    def is_iceberg(self) -> bool:
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
    side: str
    cumulative_volume: float
    visible_depth: float
    intensity: float
    refill_count: int
    confidence: float = 0.0


class AlertMonitor:
    """综合判断系统"""

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
        self.total_whale_flow = 0
        self.last_pattern = ""
        self.alerts_history: List[Dict] = []
        self.current_price = 0.0

        # 警报阈值
        self.score_buy_threshold = 60
        self.score_sell_threshold = 35
        self.whale_flow_threshold = 100000

        # MTF趋势
        self.mtf_trends = {"1D": "中性", "4H": "中性", "15M": "中性"}

        # 合约数据
        self.funding_rate = None
        self.open_interest = None
        self.long_short_ratio = None

        # ========== 冰山检测 ==========
        self.bid_levels: Dict[float, PriceLevel] = {}
        self.ask_levels: Dict[float, PriceLevel] = {}
        self.iceberg_signals: List[IcebergSignal] = []
        self.active_icebergs: Dict[float, IcebergSignal] = {}

        # 冰山统计
        self.iceberg_buy_count = 0
        self.iceberg_sell_count = 0
        self.iceberg_buy_volume = 0.0
        self.iceberg_sell_volume = 0.0

        # 综合判断
        self.conclusion = ""
        self.recommendation = ""
        self.surface_bias = "中性"
        self.hidden_bias = "中性"

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
                winsound.Beep(800, 200)
                winsound.Beep(1000, 200)
                winsound.Beep(1200, 300)
            elif alert_type == "sell":
                winsound.Beep(600, 200)
                winsound.Beep(400, 200)
                winsound.Beep(300, 300)
            elif alert_type == "warning":
                for _ in range(3):
                    winsound.Beep(1000, 100)
                    winsound.Beep(500, 100)
            else:
                winsound.Beep(700, 300)
        except:
            pass

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
        self.play_alert(alert_type)

    async def fetch_data(self) -> Optional[Dict]:
        """获取所有数据"""
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
            self.open_interest = data.get("open_interest")
            self.long_short_ratio = data.get("long_short_ratio")
        except:
            pass

    # ========== 冰山检测方法 ==========

    def _normalize_price(self, price: float) -> float:
        return round(price, 6)

    def _update_orderbook_levels(self, orderbook: Dict):
        """更新订单簿层级"""
        current_time = datetime.now()
        cleanup_threshold = current_time - timedelta(seconds=CONFIG_ICEBERG['detection_window'])

        current_bids = {self._normalize_price(b[0]): b[1] for b in orderbook.get('bids', [])}
        for price, quantity in current_bids.items():
            if price in self.bid_levels:
                old_visible = self.bid_levels[price].visible_quantity
                if quantity < old_visible:
                    filled = old_visible - quantity
                    self.bid_levels[price].update(quantity, filled)
                else:
                    self.bid_levels[price].update(quantity)
            else:
                self.bid_levels[price] = PriceLevel(price=price, visible_quantity=quantity)

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

        # 清理过期
        self.bid_levels = {
            p: l for p, l in self.bid_levels.items()
            if l.last_updated > cleanup_threshold or l.is_iceberg
        }
        self.ask_levels = {
            p: l for p, l in self.ask_levels.items()
            if l.last_updated > cleanup_threshold or l.is_iceberg
        }

    def _calculate_confidence(self, level: PriceLevel) -> float:
        confidence = 50.0
        if level.intensity >= 10:
            confidence += 20
        elif level.intensity >= 5:
            confidence += 10
        if level.refill_count >= 10:
            confidence += 15
        elif level.refill_count >= 5:
            confidence += 10
        if level.cumulative_filled >= 5000:
            confidence += 15
        elif level.cumulative_filled >= 2000:
            confidence += 10
        return min(95.0, confidence)

    def detect_icebergs(self):
        """检测冰山单"""
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
                self.iceberg_signals.append(signal)
                self.active_icebergs[price] = signal

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
                self.iceberg_signals.append(signal)
                self.active_icebergs[price] = signal

        # 更新统计
        buy_signals = [s for s in self.iceberg_signals if s.side == 'BUY']
        sell_signals = [s for s in self.iceberg_signals if s.side == 'SELL']
        self.iceberg_buy_count = len(buy_signals)
        self.iceberg_sell_count = len(sell_signals)
        self.iceberg_buy_volume = sum(s.cumulative_volume for s in buy_signals)
        self.iceberg_sell_volume = sum(s.cumulative_volume for s in sell_signals)

    # ========== 综合判断 ==========

    def make_judgment(self, score: int, whale_flow: float, retail_flow: float):
        """生成综合判断 - 详细版"""
        # 1. 判断表面信号偏向
        if score >= 70:
            self.surface_bias = "强多"
        elif score >= 60:
            self.surface_bias = "偏多"
        elif score <= 25:
            self.surface_bias = "强空"
        elif score <= 35:
            self.surface_bias = "偏空"
        else:
            self.surface_bias = "中性"

        # 2. 判断暗盘信号偏向
        total_iceberg = self.iceberg_buy_volume + self.iceberg_sell_volume
        ice_diff = self.iceberg_buy_volume - self.iceberg_sell_volume
        if total_iceberg > 0:
            buy_ratio = self.iceberg_buy_volume / total_iceberg
            if buy_ratio > 0.65:
                self.hidden_bias = "强多"
            elif buy_ratio > 0.55:
                self.hidden_bias = "偏多"
            elif buy_ratio < 0.35:
                self.hidden_bias = "强空"
            elif buy_ratio < 0.45:
                self.hidden_bias = "偏空"
            else:
                self.hidden_bias = "中性"
        else:
            self.hidden_bias = "无数据"

        # 3. 生成详细结论
        # 洗盘吸筹: 表面空 + 暗盘多
        if self.surface_bias in ["偏空", "强空"] and self.hidden_bias in ["偏多", "强多"]:
            buy_vol = self.iceberg_buy_volume / 10000
            self.conclusion = f"洗盘吸筹! 表面看空，暗地买入{buy_vol:.0f}万U"
            self.recommendation = f"可以关注! 冰山买单累计{buy_vol:.0f}万U撑底"

        # 诱多出货: 表面多 + 暗盘空
        elif self.surface_bias in ["偏多", "强多"] and self.hidden_bias in ["偏空", "强空"]:
            sell_vol = self.iceberg_sell_volume / 10000
            self.conclusion = f"诱多出货! 表面看多，暗地卖出{sell_vol:.0f}万U"
            self.recommendation = f"不要追高! 隐藏卖压{sell_vol:.0f}万U"

        # 真实下跌: 表面空 + 暗盘空
        elif self.surface_bias in ["偏空", "强空"] and self.hidden_bias in ["偏空", "强空"]:
            sell_vol = self.iceberg_sell_volume / 10000
            self.conclusion = f"真实下跌! 表面和暗盘都在卖，不是洗盘!"
            self.recommendation = f"不要抄底! 等冰山买单出现再考虑"

        # 真实上涨: 表面多 + 暗盘多
        elif self.surface_bias in ["偏多", "强多"] and self.hidden_bias in ["偏多", "强多"]:
            buy_vol = self.iceberg_buy_volume / 10000
            self.conclusion = f"真实上涨! 表面和暗盘都在买，趋势确认!"
            self.recommendation = f"可以买入! 冰山买单{buy_vol:.0f}万U支撑"

        # 暗盘无数据
        elif self.hidden_bias == "无数据":
            if self.surface_bias in ["偏空", "强空"]:
                self.conclusion = "表面偏空，暂无冰山数据验证"
                self.recommendation = "观望，等待冰山信号出现"
            elif self.surface_bias in ["偏多", "强多"]:
                self.conclusion = "表面偏多，暂无冰山数据验证"
                self.recommendation = "谨慎乐观，关注冰山买单是否出现"
            else:
                self.conclusion = "震荡盘整，等待方向选择"
                self.recommendation = "观望，等待明确信号"

        # 表面中性 + 暗盘有方向
        elif self.surface_bias == "中性":
            if self.hidden_bias in ["偏多", "强多"]:
                buy_vol = self.iceberg_buy_volume / 10000
                self.conclusion = f"暗中吸筹! 表面平静，暗盘买入{buy_vol:.0f}万U"
                self.recommendation = "可以关注! 大户在悄悄建仓"
            elif self.hidden_bias in ["偏空", "强空"]:
                sell_vol = self.iceberg_sell_volume / 10000
                self.conclusion = f"暗中出货! 表面平静，暗盘卖出{sell_vol:.0f}万U"
                self.recommendation = "小心! 大户在悄悄出货"
            else:
                # 计算净额
                net = abs(ice_diff) / 10000
                if ice_diff > 100000:  # 净买超过10万
                    self.conclusion = f"多空博弈，买方略占优，净买{net:.0f}万U"
                    self.recommendation = "观望偏多，关注能否突破"
                elif ice_diff < -100000:  # 净卖超过10万
                    self.conclusion = f"多空博弈，卖方略占优，净卖{net:.0f}万U"
                    self.recommendation = "观望偏空，关注支撑位"
                else:
                    self.conclusion = "多空博弈胶着，暂无明确方向"
                    self.recommendation = "观望，等待一方胜出"

        # 其他情况
        else:
            net = abs(ice_diff) / 10000
            if ice_diff > 0:
                self.conclusion = f"多空博弈中，冰山净买{net:.0f}万U"
                self.recommendation = "观望偏多"
            else:
                self.conclusion = f"多空博弈中，冰山净卖{net:.0f}万U"
                self.recommendation = "观望偏空"

    def analyze_and_alert(self, data: Dict):
        """分析数据并触发警报"""
        # 计算指标
        ind = self.indicators.calculate_all(
            orderbook=data['orderbook'],
            trades=data['trades']
        )

        self.current_price = data['ticker']['last']

        # 更新冰山检测
        self._update_orderbook_levels(data['orderbook'])
        self.detect_icebergs()

        # 计算净鲸流
        whale_flow = 0
        for trade in data['trades']:
            value = trade['price'] * trade['quantity']
            if value >= CONFIG_MARKET['whale_threshold_usd']:
                is_buy = not trade['is_buyer_maker']
                whale_flow += value if is_buy else -value

        self.total_whale_flow += whale_flow

        # 计算分级CVD
        binned_cvd = calculate_binned_cvd(data['trades'], self.current_price)

        # 计算综合分数
        score = 50
        bullish = sum(1 for t in self.mtf_trends.values() if t == "多")
        bearish = sum(1 for t in self.mtf_trends.values() if t == "空")
        score += (bullish - bearish) * 10
        score += int(ind.obi * 20)

        if self.total_whale_flow > 50000:
            score += 15
        elif self.total_whale_flow > 20000:
            score += 10
        elif self.total_whale_flow > 5000:
            score += 5
        elif self.total_whale_flow < -50000:
            score -= 15
        elif self.total_whale_flow < -20000:
            score -= 10
        elif self.total_whale_flow < -5000:
            score -= 5

        if ind.cvd > 5000:
            score += 10
        elif ind.cvd < -5000:
            score -= 10

        score = max(0, min(100, score))

        # 生成综合判断
        self.make_judgment(score, self.total_whale_flow, binned_cvd.retail_cvd)

        # ========== 警报检测 (结合综合判断) ==========
        # 判断是否为危险信号
        is_danger = "出货" in self.conclusion or "下跌" in self.conclusion or "不要" in self.recommendation
        is_safe = "吸筹" in self.conclusion or "上涨" in self.conclusion or "可以" in self.recommendation

        if score >= 60 and self.last_score < 60:
            if is_danger:
                self.add_alert("⚠️ 警告", f"分数60但暗盘危险! {self.conclusion[:20]}", "warning")
            elif is_safe:
                self.add_alert("🟢 买入", f"分数突破60! 暗盘确认! 当前: {score}", "buy")
            else:
                self.add_alert("📢 信号", f"分数突破60! 当前: {score} | 观察暗盘", "normal")
        elif score >= 70 and self.last_score < 70:
            if is_danger:
                self.add_alert("⚠️ 警告", f"分数70但暗盘在出货! 不要追高!", "warning")
            elif is_safe:
                self.add_alert("🟢 买入", f"分数突破70! 暗盘确认! 强烈买入!", "buy")
            else:
                self.add_alert("📢 信号", f"分数突破70! 当前: {score} | 等暗盘确认", "normal")
        elif score <= 35 and self.last_score > 35:
            if is_safe:
                self.add_alert("📢 信号", f"分数35但暗盘在吸筹! 可能是洗盘", "normal")
            else:
                self.add_alert("🔴 卖出", f"分数跌破35! 当前: {score} | 不要买入", "sell")
        elif score <= 25 and self.last_score > 25:
            if is_safe:
                self.add_alert("📢 信号", f"分数25但暗盘在吸筹! 关注抄底机会", "normal")
            else:
                self.add_alert("🔴 卖出", f"分数跌破25! 当前: {score} | 强烈看空!", "sell")

        # 更新状态
        self.last_score = score
        self.last_whale_flow = whale_flow

        return {
            "price": self.current_price,
            "score": score,
            "whale_flow": self.total_whale_flow,
            "binned_cvd": binned_cvd,
            "indicators": ind
        }

    def build_display(self, analysis: Dict) -> Text:
        """构建综合判断显示"""
        lines = []

        # 清屏分隔
        lines.append(Text("=" * 55, style="cyan"))

        # ========== 标题 ==========
        title = Text()
        title.append(f"  {self.symbol} 综合判断 ", style="bold yellow")
        title.append(f"| {datetime.now().strftime('%H:%M:%S')}", style="dim")
        lines.append(title)

        lines.append(Text("=" * 55, style="cyan"))

        # ========== 表面信号 ==========
        lines.append(Text(""))
        lines.append(Text("📊 表面信号 (Surface)", style="bold cyan"))

        # 战略地图
        mtf_line = Text()
        mtf_line.append("   战略地图: ")
        for tf, trend in self.mtf_trends.items():
            color = "green" if trend == "多" else "red" if trend == "空" else "yellow"
            mtf_line.append(f"{tf}:{trend} ", style=color)
        lines.append(mtf_line)

        # 分数
        score = analysis['score']
        score_color = "green" if score >= 60 else "red" if score <= 35 else "yellow"
        score_line = Text()
        score_line.append(f"   分数: ")
        score_line.append(f"{score} ", style=f"bold {score_color}")
        score_line.append(f"({self.surface_bias})", style=score_color)
        lines.append(score_line)

        # 鲸鱼流
        wf = analysis['whale_flow']
        wf_color = "green" if wf > 0 else "red" if wf < 0 else "white"
        whale_line = Text()
        whale_line.append(f"   鲸鱼流: ")
        whale_line.append(f"${wf:+,.0f}", style=wf_color)
        # OI百分比
        if self.open_interest and self.open_interest.open_interest_value > 0:
            oi_value = self.open_interest.open_interest_value * self.current_price
            if oi_value > 0:
                oi_pct = abs(wf) / oi_value * 100
                whale_line.append(f" (占OI: {oi_pct:.2f}%)", style="cyan")
        lines.append(whale_line)

        # 散户
        cvd = analysis['binned_cvd']
        retail_line = Text()
        retail_line.append(f"   散户: ")
        retail_line.append(f"{cvd.retail_cvd:+,.0f}", style="green" if cvd.retail_cvd > 0 else "red")
        lines.append(retail_line)

        # 费率
        if self.funding_rate:
            rate = self.funding_rate.funding_rate * 100
            rate_line = Text()
            rate_line.append(f"   费率: ")
            rate_color = "red" if rate > 0.05 else "green" if rate < -0.05 else "yellow"
            rate_line.append(f"{rate:+.4f}% ", style=rate_color)
            rate_line.append(f"({self.funding_rate.sentiment})", style=rate_color)
            lines.append(rate_line)

        # ========== 暗盘信号 ==========
        lines.append(Text(""))
        lines.append(Text("🔍 暗盘信号 (Hidden)", style="bold magenta"))

        # 冰山统计
        ice_count_line = Text()
        ice_count_line.append(f"   冰山买单: ")
        ice_count_line.append(f"{self.iceberg_buy_count}个 ", style="green")
        ice_count_line.append(f"累计: ")
        ice_count_line.append(f"{self.iceberg_buy_volume/10000:.1f}万U", style="green")
        lines.append(ice_count_line)

        ice_sell_line = Text()
        ice_sell_line.append(f"   冰山卖单: ")
        ice_sell_line.append(f"{self.iceberg_sell_count}个 ", style="red")
        ice_sell_line.append(f"累计: ")
        ice_sell_line.append(f"{self.iceberg_sell_volume/10000:.1f}万U", style="red")
        lines.append(ice_sell_line)

        # 买卖比
        total_ice = self.iceberg_buy_count + self.iceberg_sell_count
        if total_ice > 0:
            ratio = self.iceberg_buy_count / total_ice if total_ice > 0 else 0.5
            ratio_line = Text()
            ratio_line.append(f"   买卖比: ")
            ratio_color = "green" if ratio > 0.55 else "red" if ratio < 0.45 else "yellow"
            ratio_line.append(f"{ratio:.2f} ", style=ratio_color)
            if ratio > 0.6:
                ratio_line.append("(买方优势)", style="green")
            elif ratio < 0.4:
                ratio_line.append("(卖方优势)", style="red")
            else:
                ratio_line.append("(均衡)", style="yellow")
            lines.append(ratio_line)

        # 最强信号
        if self.active_icebergs:
            strongest = max(self.active_icebergs.values(), key=lambda x: x.intensity)
            strong_line = Text()
            strong_line.append(f"   最强信号: ")
            side_color = "green" if strongest.side == 'BUY' else "red"
            strong_line.append(f"{'买' if strongest.side == 'BUY' else '卖'} ", style=side_color)
            strong_line.append(f"@ ${strongest.price:.6f} ")
            strong_line.append(f"({strongest.cumulative_volume/10000:.1f}万U, {strongest.intensity:.1f}x)", style="cyan")
            lines.append(strong_line)

        # ========== 对比表格 ==========
        lines.append(Text(""))
        lines.append(Text("⚖️ 表面 vs 暗盘", style="bold white"))

        table_header = Text()
        table_header.append("   ┌────────────────┬────────────────┐")
        lines.append(table_header)

        table_title = Text()
        table_title.append("   │ ")
        table_title.append("表面信号      ", style="cyan")
        table_title.append("│ ")
        table_title.append("暗盘信号      ", style="magenta")
        table_title.append("│")
        lines.append(table_title)

        table_mid = Text()
        table_mid.append("   ├────────────────┼────────────────┤")
        lines.append(table_mid)

        # 偏向对比
        table_row1 = Text()
        table_row1.append("   │ ")
        surface_color = "green" if "多" in self.surface_bias else "red" if "空" in self.surface_bias else "yellow"
        hidden_color = "green" if "多" in self.hidden_bias else "red" if "空" in self.hidden_bias else "yellow"
        table_row1.append(f"分数{analysis['score']} ", style=surface_color)
        table_row1.append(f"{self.surface_bias}    ", style=surface_color)
        table_row1.append("│ ")
        if self.hidden_bias != "无数据":
            table_row1.append(f"冰山 ", style=hidden_color)
            table_row1.append(f"{self.hidden_bias}      ", style=hidden_color)
        else:
            table_row1.append("等待数据...   ", style="dim")
        table_row1.append("│")
        lines.append(table_row1)

        # 资金流对比
        table_row2 = Text()
        table_row2.append("   │ ")
        wf_str = f"鲸流{'+' if wf > 0 else ''}{wf/10000:.0f}万" if abs(wf) >= 10000 else f"鲸流${wf:+,.0f}"
        table_row2.append(f"{wf_str[:12]:12}", style="green" if wf > 0 else "red")
        table_row2.append("│ ")
        ice_diff = self.iceberg_buy_volume - self.iceberg_sell_volume
        ice_str = f"净买{ice_diff/10000:+.0f}万U" if abs(ice_diff) >= 10000 else f"净额{ice_diff:+,.0f}"
        table_row2.append(f"{ice_str[:12]:12}", style="green" if ice_diff > 0 else "red")
        table_row2.append("│")
        lines.append(table_row2)

        table_footer = Text()
        table_footer.append("   └────────────────┴────────────────┘")
        lines.append(table_footer)

        # ========== 综合结论 ==========
        lines.append(Text(""))
        lines.append(Text("🎯 综合结论", style="bold yellow"))

        conclusion_box_top = Text()
        conclusion_box_top.append("   ┌" + "─" * 44 + "┐")
        lines.append(conclusion_box_top)

        conclusion_line = Text()
        conclusion_line.append("   │ ")
        # 根据结论选择颜色和图标
        if "下跌" in self.conclusion or "出货" in self.conclusion:
            conclusion_line.append("🔴 ", style="red")
            conclusion_line.append(f"{self.conclusion[:38]:38}", style="bold red")
        elif "上涨" in self.conclusion or "吸筹" in self.conclusion:
            conclusion_line.append("🟢 ", style="green")
            conclusion_line.append(f"{self.conclusion[:38]:38}", style="bold green")
        else:
            conclusion_line.append("🟡 ", style="yellow")
            conclusion_line.append(f"{self.conclusion[:38]:38}", style="bold yellow")
        conclusion_line.append(" │")
        lines.append(conclusion_line)

        conclusion_box_bottom = Text()
        conclusion_box_bottom.append("   └" + "─" * 44 + "┘")
        lines.append(conclusion_box_bottom)

        # ========== 操作建议 ==========
        lines.append(Text(""))
        advice_line = Text()
        advice_line.append("📍 操作建议: ")
        if "买入" in self.recommendation or "关注" in self.recommendation:
            advice_line.append(f"🟢 {self.recommendation}", style="bold green")
        elif "不要" in self.recommendation:
            advice_line.append(f"🔴 {self.recommendation}", style="bold red")
        else:
            advice_line.append(f"🟡 {self.recommendation}", style="bold yellow")
        lines.append(advice_line)

        # ========== 最近警报 ==========
        if self.alerts_history:
            lines.append(Text(""))
            lines.append(Text("─" * 48, style="dim"))
            lines.append(Text("🔔 最近警报:", style="bold"))
            for alert in self.alerts_history[-3:]:
                alert_line = Text()
                alert_line.append(f"  [{alert['time'].strftime('%H:%M:%S')}] ", style="dim")
                alert_line.append(f"{alert['level']} ", style="bold")
                alert_line.append(alert['message'][:35], style="white")
                lines.append(alert_line)

        # 底部分隔
        lines.append(Text("=" * 55, style="cyan"))

        return Text("\n").join(lines)

    async def run(self):
        """主运行循环"""
        await self.initialize()
        self.running = True

        # 初始更新
        await self.update_mtf()
        await self.update_derivatives()

        counter = 0

        # 使用 Live 显示，screen=True 可以避免重复打印
        with Live(console=console, refresh_per_second=1, screen=False, transient=False) as live:
            while self.running:
                try:
                    data = await self.fetch_data()
                    if data:
                        analysis = self.analyze_and_alert(data)
                        live.update(self.build_display(analysis))

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
    parser = argparse.ArgumentParser(description='Flow Radar 综合判断系统')
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
