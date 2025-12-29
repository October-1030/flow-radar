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
except ImportError:
    print("请安装 rich: pip install rich")
    sys.exit(1)

from config.settings import CONFIG_MARKET, CONFIG_ICEBERG
from core.indicators import Indicators
from core.derivatives import (
    DerivativesDataFetcher, calculate_binned_cvd,
    predict_liquidation_cascade
)
from core.state_machine import (
    HysteresisStateMachine, MarketState, SignalOutput,
    STATE_NAMES, is_danger_state, is_opportunity_state
)
from core.event_logger import EventLogger
from core.dynamic_threshold import DynamicThresholdEngine
from core.trade_deduplicator import TradeDeduplicator
from core.state_saver import StateSaver
from core.divergence_detector import DivergenceDetector, DivergenceType

console = Console()


class MetricsCollector:
    """72小时验证监控指标收集器 (GPT建议)"""

    def __init__(self):
        self.tick_intervals = []
        self.dedup_hits = 0
        self.dedup_total = 0
        self.save_durations = []
        self.activity_count = 0
        self.confirmed_count = 0
        self.divergence_count = 0
        self.alert_count = 0
        self.last_tick_ts = None
        self.start_time = None

    def record_tick(self, event_ts: float):
        """记录每次 tick 的时间间隔"""
        if self.start_time is None:
            self.start_time = event_ts
        if self.last_tick_ts:
            interval = event_ts - self.last_tick_ts
            self.tick_intervals.append(interval)
        self.last_tick_ts = event_ts

    def record_dedup(self, total: int, duplicates: int):
        """记录去重统计"""
        self.dedup_total += total
        self.dedup_hits += duplicates

    def record_iceberg(self, activity: int, confirmed: int):
        """记录冰山统计"""
        self.activity_count = activity
        self.confirmed_count = confirmed

    def record_divergence(self):
        """记录背离触发"""
        self.divergence_count += 1

    def record_alert(self):
        """记录告警"""
        self.alert_count += 1

    def record_save_duration(self, duration_ms: float):
        """记录状态保存耗时"""
        self.save_durations.append(duration_ms)

    def report(self) -> dict:
        """生成监控报告"""
        runtime_hours = (self.last_tick_ts - self.start_time) / 3600 if self.start_time and self.last_tick_ts else 1
        return {
            'runtime_hours': runtime_hours,
            'avg_tick_interval': sum(self.tick_intervals) / len(self.tick_intervals) if self.tick_intervals else 0,
            'max_tick_interval': max(self.tick_intervals) if self.tick_intervals else 0,
            'tick_count': len(self.tick_intervals),
            'dedup_hit_rate': self.dedup_hits / self.dedup_total if self.dedup_total > 0 else 0,
            'confirmed_ratio': self.confirmed_count / self.activity_count if self.activity_count > 0 else 0,
            'divergence_count': self.divergence_count,
            'alerts_per_hour': self.alert_count / runtime_hours if runtime_hours > 0 else 0,
            'avg_save_duration_ms': sum(self.save_durations) / len(self.save_durations) if self.save_durations else 0,
            'max_save_duration_ms': max(self.save_durations) if self.save_durations else 0,
        }

    def print_report(self):
        """打印监控报告"""
        r = self.report()
        console.print("\n[bold cyan]===== 72小时验证监控报告 =====[/bold cyan]")
        console.print(f"运行时间: {r['runtime_hours']:.2f} 小时")
        console.print(f"Tick 次数: {r['tick_count']}")
        console.print(f"平均间隔: {r['avg_tick_interval']:.2f}s, 最大: {r['max_tick_interval']:.2f}s")
        console.print(f"去重命中率: {r['dedup_hit_rate']*100:.2f}%")
        console.print(f"确认转化率: {r['confirmed_ratio']*100:.2f}%")
        console.print(f"背离触发: {r['divergence_count']} 次")
        console.print(f"告警频率: {r['alerts_per_hour']:.2f} 次/小时")
        console.print(f"保存耗时: 平均{r['avg_save_duration_ms']:.1f}ms, 最大{r['max_save_duration_ms']:.1f}ms")


class IcebergLevel(Enum):
    """冰山信号级别 (GPT 建议: 区分噪音和确认信号)"""
    NONE = "none"                        # 无冰山活动
    ACTIVITY = "refill_activity"         # 有补单活动 (可能是做市噪音)
    CONFIRMED = "confirmed_iceberg"      # 确认冰山 (满足吸收度条件)


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
    max_visible: float = 0.0  # 历史最大可见量

    def update(self, new_visible: float, filled: float = 0):
        """
        更新价格层级状态

        修复 Full Absorption 漏判：
        - 旧逻辑: visible_quantity > 0 时才判断 refill，100→0→100 会漏报
        - 新逻辑: 基于 previous_visible 判断，被吃掉80%以上且回补50%以上计为 refill
        """
        # 更新历史最大值
        self.max_visible = max(self.max_visible, new_visible)

        # 检测补单 (refill)
        if self.previous_visible > 0:
            # 计算被吃掉的比例
            consumed_ratio = 1 - (self.visible_quantity / self.previous_visible)
            # 被吃掉80%以上，且回补超过历史峰值的50%，计为一次 refill
            if consumed_ratio >= 0.8 and new_visible >= self.max_visible * 0.5:
                self.refill_count += 1
        elif self.visible_quantity == 0 and new_visible > 0 and self.cumulative_filled > 0:
            # 完全消耗后又出现 (100→0→100 场景)
            self.refill_count += 1

        self.previous_visible = self.visible_quantity
        self.visible_quantity = new_visible
        self.cumulative_filled += filled
        if filled > 0:
            self.fill_count += 1
        self.last_updated = datetime.now()

    @property
    def intensity(self) -> float:
        # 使用历史最大值计算强度，避免除零
        base = max(self.visible_quantity, self.max_visible, 1)
        return self.cumulative_filled / base

    @property
    def is_iceberg(self) -> bool:
        return (
            self.intensity >= CONFIG_ICEBERG['intensity_threshold'] and
            self.cumulative_filled >= CONFIG_ICEBERG['min_cumulative_volume'] and
            self.refill_count >= CONFIG_ICEBERG['min_refill_count']
        )

    def get_iceberg_level(self) -> IcebergLevel:
        """
        获取冰山信号级别 (GPT 建议: 区分 Activity vs Confirmed)

        - NONE: 无任何冰山活动
        - ACTIVITY: 有补单活动，可能是做市噪音
        - CONFIRMED: 满足吸收度 >= 3，确认是冰山单

        Returns:
            IcebergLevel: 冰山信号级别
        """
        # 计算吸收度 (累计成交 / 可见量)
        absorption = self.cumulative_filled / max(self.max_visible, 1)

        # 确认冰山: 吸收度 >= 3 且补单次数 >= 3
        if absorption >= 3.0 and self.refill_count >= 3:
            return IcebergLevel.CONFIRMED

        # 有活动: 至少有1次补单
        if self.refill_count >= 1:
            return IcebergLevel.ACTIVITY

        return IcebergLevel.NONE


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
    level: IcebergLevel = IcebergLevel.ACTIVITY  # Step E: 信号级别


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

        # Step E: 确认冰山统计 (区分噪音和真信号)
        self.confirmed_buy_count = 0
        self.confirmed_sell_count = 0
        self.confirmed_buy_volume = 0.0
        self.confirmed_sell_volume = 0.0

        # 综合判断
        self.conclusion = ""
        self.recommendation = ""
        self.surface_bias = "中性"
        self.hidden_bias = "中性"

        # ========== 滞回状态机 ==========
        self.state_machine = HysteresisStateMachine(cooldown_seconds=30)
        self.current_signal: Optional[SignalOutput] = None

        # ========== 事件记录 ==========
        self.event_logger = EventLogger(symbol=self.symbol)
        self.logging_enabled = True  # 可以通过参数关闭

        # ========== 动态阈值 ==========
        self.threshold_engine = DynamicThresholdEngine(
            window_hours=24,
            min_samples=100,
            min_whale_usd=CONFIG_MARKET.get('whale_threshold_usd', 10000)
        )
        self.use_dynamic_threshold = True  # 启用动态阈值

        # ========== Step B: 成交去重 ==========
        self.deduplicator = TradeDeduplicator(max_size=10000, ttl_seconds=300)

        # ========== Step C: 状态持久化 ==========
        self.state_saver = StateSaver(symbol=self.symbol)
        self._restore_state()  # 启动时恢复状态

        # ========== Step F: 背离检测 ==========
        self.divergence_detector = DivergenceDetector(window=20)
        self.last_divergence = None

        # ========== CVD 累计 ==========
        self.cvd_total = 0.0

        # ========== 确定性时间戳 (GPT 建议) ==========
        self.last_event_ts = None  # 用于 shutdown 保存状态

        # ========== 72小时验证监控 ==========
        self.metrics = MetricsCollector()

    def _restore_state(self):
        """Step C: 启动时恢复状态"""
        saved = self.state_saver.load()
        if saved:
            # 检查状态是否过期 (超过24小时视为过期)
            if not self.state_saver.is_stale(max_age_hours=24):
                self.cvd_total = saved.cvd_total
                self.total_whale_flow = saved.total_whale_flow
                self.iceberg_buy_count = saved.iceberg_buy_count
                self.iceberg_sell_count = saved.iceberg_sell_count
                self.iceberg_buy_volume = saved.iceberg_buy_volume
                self.iceberg_sell_volume = saved.iceberg_sell_volume
                self.last_score = saved.last_score
                console.print(f"[green]✓ 状态恢复成功[/green] CVD={self.cvd_total:.0f}, 鲸流={self.total_whale_flow:.0f}")
            else:
                console.print(f"[yellow]⚠ 状态已过期，重新开始[/yellow]")
        else:
            console.print(f"[dim]无历史状态，从零开始[/dim]")

    def _save_state(self, event_ts: float):
        """Step C: 定期保存状态"""
        state = {
            'cvd_total': self.cvd_total,
            'total_whale_flow': self.total_whale_flow,
            'iceberg_buy_count': self.iceberg_buy_count,
            'iceberg_sell_count': self.iceberg_sell_count,
            'iceberg_buy_volume': self.iceberg_buy_volume,
            'iceberg_sell_volume': self.iceberg_sell_volume,
            'current_state': self.current_signal.state.value if self.current_signal else 'neutral',
            'last_score': self.last_score,
            'last_price': self.current_price,
        }
        self.state_saver.save(state, event_ts)

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
        self.metrics.record_alert()  # 监控: 记录告警
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
        """检测冰山单 (Step E: 区分 Activity vs Confirmed)"""
        # 检测买单冰山
        for price, level in self.bid_levels.items():
            if level.is_iceberg and price not in self.active_icebergs:
                ice_level = level.get_iceberg_level()
                signal = IcebergSignal(
                    timestamp=datetime.now(),
                    price=price,
                    side='BUY',
                    cumulative_volume=level.cumulative_filled,
                    visible_depth=level.visible_quantity,
                    intensity=level.intensity,
                    refill_count=level.refill_count,
                    confidence=self._calculate_confidence(level),
                    level=ice_level
                )
                self.iceberg_signals.append(signal)
                self.active_icebergs[price] = signal

        # 检测卖单冰山
        for price, level in self.ask_levels.items():
            if level.is_iceberg and price not in self.active_icebergs:
                ice_level = level.get_iceberg_level()
                signal = IcebergSignal(
                    timestamp=datetime.now(),
                    price=price,
                    side='SELL',
                    cumulative_volume=level.cumulative_filled,
                    visible_depth=level.visible_quantity,
                    intensity=level.intensity,
                    refill_count=level.refill_count,
                    confidence=self._calculate_confidence(level),
                    level=ice_level
                )
                self.iceberg_signals.append(signal)
                self.active_icebergs[price] = signal

        # 更新统计 (所有冰山)
        buy_signals = [s for s in self.iceberg_signals if s.side == 'BUY']
        sell_signals = [s for s in self.iceberg_signals if s.side == 'SELL']
        self.iceberg_buy_count = len(buy_signals)
        self.iceberg_sell_count = len(sell_signals)
        self.iceberg_buy_volume = sum(s.cumulative_volume for s in buy_signals)
        self.iceberg_sell_volume = sum(s.cumulative_volume for s in sell_signals)

        # Step E: 仅统计确认冰山 (CONFIRMED level)
        confirmed_buy = [s for s in buy_signals if s.level == IcebergLevel.CONFIRMED]
        confirmed_sell = [s for s in sell_signals if s.level == IcebergLevel.CONFIRMED]
        self.confirmed_buy_count = len(confirmed_buy)
        self.confirmed_sell_count = len(confirmed_sell)
        self.confirmed_buy_volume = sum(s.cumulative_volume for s in confirmed_buy)
        self.confirmed_sell_volume = sum(s.cumulative_volume for s in confirmed_sell)

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

        # 2. 判断暗盘信号偏向 (同时考虑比例和净额)
        total_iceberg = self.iceberg_buy_volume + self.iceberg_sell_volume
        ice_diff = self.iceberg_buy_volume - self.iceberg_sell_volume
        total_count = self.iceberg_buy_count + self.iceberg_sell_count

        if total_iceberg > 0 or total_count > 0:
            # 用成交量计算比例
            vol_ratio = self.iceberg_buy_volume / total_iceberg if total_iceberg > 0 else 0.5
            # 用数量计算比例
            count_ratio = self.iceberg_buy_count / total_count if total_count > 0 else 0.5
            # 取更保守的判断（两个都要满足才算强信号）
            avg_ratio = (vol_ratio + count_ratio) / 2

            # 净额判断辅助（大额净流入/流出强化判断）
            # 净卖出超过1000万，加强空头判断
            strong_sell = ice_diff < -10000000
            # 净买入超过1000万，加强多头判断
            strong_buy = ice_diff > 10000000

            if avg_ratio > 0.65 or (avg_ratio > 0.55 and strong_buy):
                self.hidden_bias = "强多"
            elif avg_ratio > 0.55 or strong_buy:
                self.hidden_bias = "偏多"
            elif avg_ratio < 0.35 or (avg_ratio < 0.45 and strong_sell):
                self.hidden_bias = "强空"
            elif avg_ratio < 0.45 or strong_sell:
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

    def analyze_and_alert(self, data: Dict, event_ts: float = None):
        """分析数据并触发警报"""
        import time

        # ========== Step A: 时间源统一 ==========
        if event_ts is None:
            event_ts = time.time()

        # ========== Step B: 成交去重 ==========
        raw_trades = data['trades']
        trades = self.deduplicator.filter_trades(raw_trades, event_ts)

        # 监控: 记录去重统计
        dedup_count = len(raw_trades) - len(trades)
        self.metrics.record_dedup(len(raw_trades), dedup_count)

        # 计算指标 (使用去重后的 trades)
        ind = self.indicators.calculate_all(
            orderbook=data['orderbook'],
            trades=trades
        )

        self.current_price = data['ticker']['last']

        # 更新动态阈值引擎
        self.threshold_engine.add_price(self.current_price, event_ts)

        # 更新冰山检测
        self._update_orderbook_levels(data['orderbook'])
        self.detect_icebergs()

        # 监控: 记录冰山统计
        self.metrics.record_iceberg(
            self.iceberg_buy_count + self.iceberg_sell_count,
            self.confirmed_buy_count + self.confirmed_sell_count
        )

        # 获取动态鲸鱼阈值
        if self.use_dynamic_threshold:
            whale_threshold = self.threshold_engine.get_whale_threshold()
        else:
            whale_threshold = CONFIG_MARKET['whale_threshold_usd']

        # 计算净鲸流 (使用动态阈值和去重后的 trades)
        whale_flow = 0
        cvd_delta = 0
        for trade in trades:
            value = trade['price'] * trade['quantity']
            is_buy = not trade['is_buyer_maker']

            # 喂给阈值引擎学习
            self.threshold_engine.add_trade(value, event_ts)

            # CVD 累计
            cvd_delta += trade['quantity'] if is_buy else -trade['quantity']

            if value >= whale_threshold:
                whale_flow += value if is_buy else -value

        self.total_whale_flow += whale_flow
        self.cvd_total += cvd_delta

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

        # 生成综合判断 (旧版，保留兼容)
        self.make_judgment(score, self.total_whale_flow, binned_cvd.retail_cvd)

        # ========== Step F: 背离检测 ==========
        # 获取价格高低点 (简化：使用当前价格)
        high_price = max(t['price'] for t in trades) if trades else self.current_price
        low_price = min(t['price'] for t in trades) if trades else self.current_price

        self.last_divergence = self.divergence_detector.update(
            price=self.current_price,
            cvd=self.cvd_total,
            high=high_price,
            low=low_price,
            timestamp=event_ts
        )

        # 如果检测到背离，调整置信度
        divergence_adjustment = 0
        divergence_warning = ""
        if self.last_divergence and self.last_divergence.detected:
            self.metrics.record_divergence()  # 监控: 记录背离触发
            if self.last_divergence.type == DivergenceType.BEARISH:
                # 看跌背离：价格新高但 CVD 下降，降低多头置信度
                divergence_adjustment = -int(self.last_divergence.confidence * 30)
                divergence_warning = f"⚠️ 背离警告: {self.last_divergence.description}"
            elif self.last_divergence.type == DivergenceType.BULLISH:
                # 看涨背离：价格新低但 CVD 上升，降低空头信心
                divergence_adjustment = int(self.last_divergence.confidence * 30)
                divergence_warning = f"📢 背离信号: {self.last_divergence.description}"

        # ========== 滞回状态机判断 ==========
        # 计算冰山买卖比
        total_ice_count = self.iceberg_buy_count + self.iceberg_sell_count
        iceberg_ratio = self.iceberg_buy_count / total_ice_count if total_ice_count > 0 else 0.5

        # 更新状态机 (传入 event_ts)
        self.current_signal = self.state_machine.update(
            score=score,
            iceberg_ratio=iceberg_ratio,
            ice_buy_vol=self.iceberg_buy_volume,
            ice_sell_vol=self.iceberg_sell_volume,
            event_ts=event_ts
        )

        # 如果有背离，调整置信度
        if divergence_adjustment != 0:
            self.current_signal.confidence = max(0, min(100,
                self.current_signal.confidence + divergence_adjustment))
            if divergence_warning:
                self.current_signal.reason += f" | {divergence_warning}"

        # 用状态机的结果更新结论和建议
        self.conclusion = self.current_signal.state_name + "! " + self.current_signal.detail
        self.recommendation = self.current_signal.recommendation

        # ========== 基于状态机的警报 ==========
        if self.current_signal.state_changed:
            prev_state = self.current_signal.previous_state
            new_state = self.current_signal.state

            # 从安全状态变成危险状态
            if is_opportunity_state(prev_state) and is_danger_state(new_state):
                self.add_alert("🔴 变盘", f"{STATE_NAMES[new_state]}! 信号反转!", "warning")

            # 从危险状态变成安全状态
            elif is_danger_state(prev_state) and is_opportunity_state(new_state):
                self.add_alert("🟢 转多", f"{STATE_NAMES[new_state]}! 机会出现!", "buy")

            # 进入上涨状态
            elif new_state == MarketState.TREND_UP:
                self.add_alert("🟢 买入", f"真实上涨确认! 置信度:{self.current_signal.confidence:.0f}%", "buy")

            # 进入下跌状态
            elif new_state == MarketState.TREND_DOWN:
                self.add_alert("🔴 卖出", f"真实下跌确认! 置信度:{self.current_signal.confidence:.0f}%", "sell")

            # 进入洗盘吸筹
            elif new_state == MarketState.WASH_ACCUMULATE:
                self.add_alert("📢 机会", f"洗盘吸筹! 关注抄底机会", "normal")

            # 进入诱多出货
            elif new_state == MarketState.TRAP_DISTRIBUTION:
                self.add_alert("⚠️ 警告", f"诱多出货! 不要追高!", "warning")

            # 进入暗中吸筹
            elif new_state == MarketState.ACCUMULATING:
                self.add_alert("📢 关注", f"暗中吸筹! 大户在建仓", "normal")

            # 进入暗中出货
            elif new_state == MarketState.DISTRIBUTING:
                self.add_alert("⚠️ 小心", f"暗中出货! 大户在卖", "warning")

        # 更新状态
        self.last_score = score
        self.last_whale_flow = whale_flow

        # ========== Step C: 定期保存状态 ==========
        self._save_state(event_ts)

        # ========== 记录数据 (使用统一的 event_ts) ==========
        if self.logging_enabled:
            # 记录订单簿
            self.event_logger.log_orderbook(data['orderbook'], event_ts)

            # 记录成交 (原始数据，用于回放)
            self.event_logger.log_trades(raw_trades, event_ts)

            # 记录状态机状态 (用于回测)
            if self.current_signal:
                self.event_logger.log_state({
                    "state": self.current_signal.state.value,
                    "state_name": self.current_signal.state_name,
                    "confidence": self.current_signal.confidence,
                    "score": score,
                    "iceberg_ratio": iceberg_ratio,
                    "price": self.current_price,
                    "conclusion": self.conclusion,
                    "recommendation": self.recommendation,
                    "cvd_total": self.cvd_total,
                    "divergence": self.last_divergence.type.value if self.last_divergence and self.last_divergence.detected else None
                }, event_ts)

                # 如果状态变化，记录信号
                if self.current_signal.state_changed:
                    self.event_logger.log_signal({
                        "state": self.current_signal.state.value,
                        "confidence": self.current_signal.confidence,
                        "price": self.current_price,
                        "reason": self.current_signal.reason
                    }, event_ts)

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
        # 动态阈值
        if self.use_dynamic_threshold:
            threshold = self.threshold_engine.get_whale_threshold()
            whale_line.append(f" [阈值>${threshold/1000:.1f}k]", style="dim")
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

        # Step E: 冰山统计 (区分 Activity vs Confirmed)
        ice_count_line = Text()
        ice_count_line.append(f"   冰山买单: ")
        ice_count_line.append(f"{self.iceberg_buy_count}个 ", style="green")
        if self.confirmed_buy_count > 0:
            ice_count_line.append(f"(确认:{self.confirmed_buy_count}) ", style="bold green")
        ice_count_line.append(f"累计: ")
        ice_count_line.append(f"{self.iceberg_buy_volume/10000:.1f}万U", style="green")
        lines.append(ice_count_line)

        ice_sell_line = Text()
        ice_sell_line.append(f"   冰山卖单: ")
        ice_sell_line.append(f"{self.iceberg_sell_count}个 ", style="red")
        if self.confirmed_sell_count > 0:
            ice_sell_line.append(f"(确认:{self.confirmed_sell_count}) ", style="bold red")
        ice_sell_line.append(f"累计: ")
        ice_sell_line.append(f"{self.iceberg_sell_volume/10000:.1f}万U", style="red")
        lines.append(ice_sell_line)

        # 买卖比 (使用确认冰山计算更可靠)
        total_confirmed = self.confirmed_buy_count + self.confirmed_sell_count
        total_ice = self.iceberg_buy_count + self.iceberg_sell_count
        if total_confirmed > 0:
            # 使用确认冰山比例
            ratio = self.confirmed_buy_count / total_confirmed
            ratio_line = Text()
            ratio_line.append(f"   确认比: ")
            ratio_color = "green" if ratio > 0.55 else "red" if ratio < 0.45 else "yellow"
            ratio_line.append(f"{ratio:.2f} ", style=f"bold {ratio_color}")
            if ratio > 0.55:
                ratio_line.append("(买方主导)", style="bold green")
            elif ratio < 0.45:
                ratio_line.append("(卖方主导)", style="bold red")
            else:
                ratio_line.append("(均衡)", style="yellow")
            lines.append(ratio_line)
        elif total_ice > 0:
            # 退化使用所有冰山比例
            ratio = self.iceberg_buy_count / total_ice if total_ice > 0 else 0.5
            ratio_line = Text()
            ratio_line.append(f"   买卖比: ")
            ratio_color = "green" if ratio > 0.55 else "red" if ratio < 0.45 else "yellow"
            ratio_line.append(f"{ratio:.2f} ", style=ratio_color)
            ratio_line.append("(待确认)", style="dim")
            lines.append(ratio_line)

        # 最强信号 (优先显示 CONFIRMED)
        if self.active_icebergs:
            confirmed_signals = [s for s in self.active_icebergs.values() if s.level == IcebergLevel.CONFIRMED]
            if confirmed_signals:
                strongest = max(confirmed_signals, key=lambda x: x.intensity)
            else:
                strongest = max(self.active_icebergs.values(), key=lambda x: x.intensity)

            strong_line = Text()
            strong_line.append(f"   最强信号: ")
            side_color = "green" if strongest.side == 'BUY' else "red"
            level_tag = "✓" if strongest.level == IcebergLevel.CONFIRMED else "?"
            strong_line.append(f"{level_tag}{'买' if strongest.side == 'BUY' else '卖'} ", style=side_color)
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
        elif "不要" in self.recommendation or "小心" in self.recommendation:
            advice_line.append(f"🔴 {self.recommendation}", style="bold red")
        else:
            advice_line.append(f"🟡 {self.recommendation}", style="bold yellow")
        lines.append(advice_line)

        # ========== 状态机信息 ==========
        if self.current_signal:
            status_line = Text()
            status_line.append("📊 置信度: ")
            conf = self.current_signal.confidence
            conf_color = "green" if conf >= 60 else "yellow" if conf >= 40 else "dim"
            status_line.append(f"{conf:.0f}%", style=conf_color)

            # 冷却时间
            if self.current_signal.cooldown_remaining > 0:
                status_line.append(f"  ⏳ 冷却: {self.current_signal.cooldown_remaining}s", style="dim")

            # 原因
            status_line.append(f"  ({self.current_signal.reason})", style="dim")
            lines.append(status_line)

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
        import time
        with Live(console=console, refresh_per_second=1, screen=False, transient=False) as live:
            while self.running:
                try:
                    # Step A: 统一 event_ts
                    event_ts = time.time()
                    self.last_event_ts = event_ts  # GPT建议: 追踪最后的 event_ts
                    self.metrics.record_tick(event_ts)  # 监控: 记录 tick

                    data = await self.fetch_data()
                    if data:
                        analysis = self.analyze_and_alert(data, event_ts)
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

        # Step C: 强制保存状态 (使用 last_event_ts 保证确定性 - GPT建议)
        if self.last_event_ts:
            console.print("[dim]保存状态...[/dim]")
            state = {
                'cvd_total': self.cvd_total,
                'total_whale_flow': self.total_whale_flow,
                'iceberg_buy_count': self.iceberg_buy_count,
                'iceberg_sell_count': self.iceberg_sell_count,
                'iceberg_buy_volume': self.iceberg_buy_volume,
                'iceberg_sell_volume': self.iceberg_sell_volume,
                'current_state': self.current_signal.state.value if self.current_signal else 'neutral',
                'last_score': self.last_score,
                'last_price': self.current_price,
            }
            self.state_saver.save(state, self.last_event_ts, force=True)
            console.print("[green]✓ 状态已保存[/green]")
        else:
            console.print("[yellow]⚠ 无 event_ts，跳过状态保存[/yellow]")

        # 打印 72 小时验证监控报告
        self.metrics.print_report()

        if self.exchange:
            await self.exchange.close()
        if self.derivatives:
            await self.derivatives.close()
        if self.event_logger:
            self.event_logger.close()


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
