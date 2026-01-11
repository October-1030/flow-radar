#!/usr/bin/env python3
"""
Flow Radar - Alert Monitor (Upgraded)
流动性雷达 - 综合判断系统

自动监控 + 冰山检测 + 综合判断
"""

import asyncio
import argparse
import time
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

from config.settings import (
    CONFIG_MARKET, CONFIG_ICEBERG, CONFIG_WEBSOCKET,
    CONFIG_DISCORD, CONFIG_FEATURES, CONFIG_ALERT_THROTTLE
)
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
from core.state_saver import StateSaver, ExtendedState
from core.divergence_detector import DivergenceDetector, DivergenceType
from core.websocket_manager import WebSocketManager, load_websocket_config
from core.discord_notifier import DiscordNotifier, AlertMessage
from core.price_level import PriceLevel, IcebergLevel, CONFIG_PRICE_LEVEL
from core.run_metadata import RunMetadataRecorder

# P3-2 Phase 2: Multi-signal judgment system
if CONFIG_FEATURES.get("use_p3_phase2", False):
    from core.unified_signal_manager import UnifiedSignalManager
    from core.bundle_advisor import BundleAdvisor

# K神战法 2.0 (Phase 2 集成)
KGOD_ENABLED = CONFIG_FEATURES.get("use_kgod_radar", False)
if KGOD_ENABLED:
    from core.kgod_radar import create_kgod_radar, OrderFlowSnapshot, SignalStage, KGodSignal

# 布林带×订单流环境过滤器（第三十五轮三方共识）
BOLLINGER_FILTER_ENABLED = CONFIG_FEATURES.get("use_bollinger_filter", False)
BOLLINGER_FILTER_MODE = CONFIG_FEATURES.get("bollinger_filter_mode", "observe")
if BOLLINGER_FILTER_ENABLED:
    from core.bollinger_regime_filter import BollingerRegimeFilter, RegimeDecision, DecisionType

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


# PriceLevel 和 IcebergLevel 已从 core.price_level 导入


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

        # P2-3: 告警降噪
        self._alert_throttle: Dict[str, Dict] = {}  # key -> {last_time, count, silenced_until}

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

        # ========== WebSocket 实时数据 ==========
        self.ws_manager: Optional[WebSocketManager] = None
        self.use_websocket = CONFIG_FEATURES.get('websocket_enabled', False) and CONFIG_WEBSOCKET.get('enabled', False)
        if self.use_websocket:
            self.ws_manager = WebSocketManager(self.symbol, load_websocket_config())

        # ========== Discord 通知 ==========
        self.discord_notifier: Optional[DiscordNotifier] = None
        self.use_discord = CONFIG_FEATURES.get('discord_enabled', False) and CONFIG_DISCORD.get('enabled', False)
        if self.use_discord:
            self.discord_notifier = DiscordNotifier(CONFIG_DISCORD)

        # ========== P3: 健康检查通知 ==========
        self._last_health_status: str = 'HEALTHY'
        self._last_health_notify_time: float = 0
        self._health_notify_cooldown: float = 60.0  # 同状态 60s 内只发一次

        # ========== P3: Run 元信息记录 ==========
        self.run_recorder = RunMetadataRecorder(symbols=[self.symbol])
        self.run_recorder.save()
        console.print(f"[dim]Run ID: {self.run_recorder.run_id}[/dim]")

        # ========== K神战法 2.0 雷达 ==========
        self.kgod_radar = None
        self.use_kgod = KGOD_ENABLED
        if self.use_kgod:
            self.kgod_radar = create_kgod_radar(symbol=self.symbol)
            console.print(f"[cyan]K神战法 2.0 雷达已启用[/cyan]")

        # K神雷达历史数据（用于计算 Delta斜率）
        self.price_history = []          # 最近价格历史
        self.cvd_history = []            # 最近 CVD 历史
        self.last_cvd = 0.0              # 上次 CVD 值

        # ========== 布林带×订单流环境过滤器（第三十五轮）==========
        self.bollinger_filter = None
        self.use_bollinger_filter = BOLLINGER_FILTER_ENABLED
        self.bollinger_filter_mode = BOLLINGER_FILTER_MODE
        self.filter_skipped_count = 0     # 预热期跳过计数
        self.last_filter_decision = None  # 最近的过滤器决策（用于Discord通知）
        if self.use_bollinger_filter:
            try:
                self.bollinger_filter = BollingerRegimeFilter()
                console.print(f"[cyan]布林带环境过滤器已启用 (模式: {self.bollinger_filter_mode})[/cyan]")
            except Exception as e:
                console.print(f"[yellow]⚠️  布林带过滤器初始化失败: {e}[/yellow]")
                console.print(f"[yellow]过滤器已禁用，继续运行[/yellow]")
                self.use_bollinger_filter = False
                self.bollinger_filter = None

    def _restore_state(self):
        """Step C: 启动时恢复状态 (P2-4: 扩展版)"""
        # P2-4: 优先尝试加载扩展状态
        if self.state_saver.has_extended_state():
            saved = self.state_saver.load_extended()
        else:
            saved = self.state_saver.load()

        if saved:
            # 检查状态是否过期 (超过24小时视为过期)
            if not self.state_saver.is_stale(max_age_hours=24):
                # 恢复基础状态
                self.cvd_total = saved.cvd_total
                self.total_whale_flow = saved.total_whale_flow
                self.iceberg_buy_count = saved.iceberg_buy_count
                self.iceberg_sell_count = saved.iceberg_sell_count
                self.iceberg_buy_volume = saved.iceberg_buy_volume
                self.iceberg_sell_volume = saved.iceberg_sell_volume
                self.last_score = saved.last_score

                # P2-4: 恢复扩展状态
                extended_restored = False
                if isinstance(saved, ExtendedState):
                    extended_restored = self._restore_extended_state(saved)

                status_msg = f"CVD={self.cvd_total:.0f}, 鲸流={self.total_whale_flow:.0f}"
                if extended_restored:
                    status_msg += " [扩展状态已恢复]"
                console.print(f"[green]✓ 状态恢复成功[/green] {status_msg}")
            else:
                console.print(f"[yellow]⚠ 状态已过期，重新开始[/yellow]")
        else:
            console.print(f"[dim]无历史状态，从零开始[/dim]")

    def _restore_extended_state(self, saved: ExtendedState) -> bool:
        """
        P2-4: 恢复扩展状态 (冰山 + 节流)

        Args:
            saved: 扩展状态对象

        Returns:
            bool: 是否成功恢复
        """
        restored = False

        # 恢复告警节流状态
        if saved.throttle_state:
            now = time.time()
            for key, state in saved.throttle_state.items():
                # 跳过超过 30 分钟的条目
                last_time_value = state.get('last_time', 0)

                # 处理类型转换：如果是 float/int，转换为 datetime；如果已是 datetime，保持不变
                if isinstance(last_time_value, (int, float)):
                    if now - last_time_value > 1800:
                        continue
                    state['last_time'] = datetime.fromtimestamp(last_time_value)
                elif isinstance(last_time_value, str):
                    # 如果是字符串，尝试解析
                    try:
                        state['last_time'] = datetime.fromisoformat(last_time_value)
                    except:
                        continue

                # 同样处理 silenced_until
                silenced_until = state.get('silenced_until')
                if silenced_until:
                    if isinstance(silenced_until, (int, float)):
                        state['silenced_until'] = datetime.fromtimestamp(silenced_until)
                    elif isinstance(silenced_until, str):
                        try:
                            state['silenced_until'] = datetime.fromisoformat(silenced_until)
                        except:
                            state['silenced_until'] = None

                self._alert_throttle[key] = state
            if self._alert_throttle:
                console.print(f"[dim]  ├─ 节流状态: {len(self._alert_throttle)} 条目[/dim]")
                restored = True

        # 恢复活跃冰山信号
        if saved.active_icebergs:
            now = time.time()
            restored_count = 0
            for ice in saved.active_icebergs:
                # 跳过超过 5 分钟的冰山
                last_updated_ts = ice.get('last_updated', 0)  # 修复字段名: last_update -> last_updated
                if now - last_updated_ts > 300:
                    continue

                price = ice.get('price', 0)
                side = ice.get('side', 'BUY')

                # 重建 PriceLevel
                level = PriceLevel(price=price)
                level.cumulative_filled = ice.get('cumulative_filled', 0)
                level.refill_count = ice.get('refill_count', 0)
                level.intensity = ice.get('intensity', 0)
                # 修复: 将 float 时间戳转为 datetime 对象
                first_seen_ts = ice.get('first_seen', now)
                level.first_seen = datetime.fromtimestamp(first_seen_ts) if first_seen_ts > 0 else datetime.now()
                level.last_updated = datetime.fromtimestamp(last_updated_ts) if last_updated_ts > 0 else datetime.now()

                if side == 'BUY':
                    self.bid_levels[price] = level
                else:
                    self.ask_levels[price] = level
                restored_count += 1

            if restored_count > 0:
                console.print(f"[dim]  └─ 活跃冰山: {restored_count} 个[/dim]")
                restored = True

        return restored

    def _save_state(self, event_ts: float):
        """Step C: 定期保存状态 (P2-4: 扩展版)"""
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

        # P2-4: 使用扩展保存 (含冰山 + 节流)
        active_icebergs = self._serialize_active_icebergs()
        self.state_saver.save_extended(
            state=state,
            active_icebergs=active_icebergs,
            throttle_state=self._alert_throttle,
            current_ts=event_ts
        )

    def _serialize_active_icebergs(self) -> list:
        """
        P2-4: 序列化活跃冰山信号

        Returns:
            list: 活跃冰山列表 [{side, price, cumulative_filled, ...}]
        """
        active = []

        for price, level in self.bid_levels.items():
            ice_level = level.get_iceberg_level()
            if ice_level != IcebergLevel.NONE:
                active.append({
                    'side': 'BUY',
                    'price': price,
                    'cumulative_filled': level.cumulative_filled,
                    'refill_count': level.refill_count,
                    'intensity': level.intensity,
                    'level': ice_level.name,
                    'first_seen': level.first_seen.timestamp(),  # 修复: datetime -> timestamp
                    'last_updated': level.last_updated.timestamp(),  # 修复: datetime -> timestamp
                })

        for price, level in self.ask_levels.items():
            ice_level = level.get_iceberg_level()
            if ice_level != IcebergLevel.NONE:
                active.append({
                    'side': 'SELL',
                    'price': price,
                    'cumulative_filled': level.cumulative_filled,
                    'refill_count': level.refill_count,
                    'intensity': level.intensity,
                    'level': ice_level.name,
                    'first_seen': level.first_seen.timestamp(),  # 修复: datetime -> timestamp
                    'last_updated': level.last_updated.timestamp(),  # 修复: datetime -> timestamp
                })

        return active

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

    def add_alert(self, level: str, message: str, alert_type: str = "normal", confidence: float = 50.0):
        """
        添加警报 (P2-3: 含降噪逻辑)

        Args:
            level: 告警级别 (info/warning/critical/opportunity)
            message: 告警消息
            alert_type: 告警类型 (用于声音)
            confidence: 置信度
        """
        # P2-3: 告警降噪检查
        if CONFIG_ALERT_THROTTLE.get('enabled', True):
            if self._is_alert_throttled(level, message):
                return  # 被节流，跳过

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

        # Discord 通知
        if self.discord_notifier and self.discord_notifier.should_notify(confidence):
            asyncio.create_task(self._send_discord_alert(level, message, alert_type, confidence))

    def _make_throttle_key(self, level: str, message: str,
                           side: str = None, price: float = None,
                           iceberg_level: str = None,
                           alert_type: str = None) -> str:
        """
        P3-1: 生成节流 key (含 type 字段)

        格式:
        - 冰山告警: iceberg:{symbol}:{side}:{level}:{price_bucket}
        - 普通告警: {type}:{level}:{msg_prefix}
        - 健康告警: health:{symbol}:{status}

        Args:
            level: 告警级别
            message: 告警消息
            side: 方向 (BUY/SELL)
            price: 价格
            iceberg_level: 冰山等级 (ACTIVITY/CONFIRMED)
            alert_type: 告警类型 (iceberg/whale/health/system)
        """
        if side and price is not None:
            # 冰山告警: type:symbol:side:level:price_bucket
            price_bucket = round(price, 4)
            ice_lvl = iceberg_level or 'UNKNOWN'
            return f"iceberg:{self.symbol}:{side}:{ice_lvl}:{price_bucket}"
        elif alert_type == 'health':
            # 健康告警: health:symbol:status
            return f"health:{self.symbol}:{level}"
        else:
            # 普通告警: type:level:msg_prefix
            a_type = alert_type or 'alert'
            msg_prefix = message[:20] if len(message) > 20 else message
            return f"{a_type}:{level}:{msg_prefix}"

    @staticmethod
    def _iceberg_level_value(level_name: str) -> int:
        """
        将冰山等级名称转换为数值 (用于通用比较)

        NONE=0, ACTIVITY=1, CONFIRMED=2
        """
        level_map = {'NONE': 0, 'ACTIVITY': 1, 'CONFIRMED': 2}
        return level_map.get(level_name, 0)

    def _is_alert_throttled(self, level: str, message: str,
                            side: str = None, price: float = None,
                            iceberg_level: str = None,
                            prev_iceberg_level: str = None) -> bool:
        """
        P2-3.1: 检查告警是否被节流 (升级版)

        规则:
        1. 相同 key 的告警有冷却时间
        2. 重复超过阈值后进入静默期
        3. 静默期内不发送任何同类告警
        4. 等级升级 (new_level > old_level) 绕过节流

        Returns:
            True 如果应该被节流，False 如果应该发送
        """
        now = datetime.now()
        cfg = CONFIG_ALERT_THROTTLE

        # 通用等级升级绕过: new_level > old_level 即 bypass
        if prev_iceberg_level and iceberg_level:
            old_val = self._iceberg_level_value(prev_iceberg_level)
            new_val = self._iceberg_level_value(iceberg_level)
            if new_val > old_val:
                # 任何等级升级都必须放行 (如 NONE→ACTIVITY, ACTIVITY→CONFIRMED)
                return False

        # 生成告警 key
        alert_key = self._make_throttle_key(level, message, side, price, iceberg_level)

        # 获取该 key 的节流状态
        throttle_state = self._alert_throttle.get(alert_key)

        if throttle_state is None:
            # 首次告警，记录并放行
            self._alert_throttle[alert_key] = {
                'last_time': now,
                'count': 1,
                'silenced_until': None,
                'suppressed_count': 0,  # P2-3.1: 静默期间抑制计数
                'iceberg_level': iceberg_level,
            }
            return False

        # 检查是否在静默期
        if throttle_state.get('silenced_until'):
            if now < throttle_state['silenced_until']:
                throttle_state['suppressed_count'] += 1
                return True  # 仍在静默期
            else:
                # P2-3.1: 静默期结束，输出摘要
                suppressed = throttle_state.get('suppressed_count', 0)
                if suppressed > 0:
                    console.print(f"[dim]静默结束: '{alert_key}' 抑制了 {suppressed} 条告警[/dim]")
                # 重置状态
                throttle_state['count'] = 0
                throttle_state['silenced_until'] = None
                throttle_state['suppressed_count'] = 0

        # 检查冷却时间
        cooldown = cfg.get('level_cooldowns', {}).get(level, cfg.get('cooldown_seconds', 60))
        elapsed = (now - throttle_state['last_time']).total_seconds()

        if elapsed < cooldown:
            # 在冷却期内，增加计数
            throttle_state['count'] += 1

            # 检查是否超过最大重复次数
            if throttle_state['count'] >= cfg.get('max_repeat_count', 3):
                # 进入静默期
                silent_duration = cfg.get('silent_duration', 300)
                throttle_state['silenced_until'] = now + timedelta(seconds=silent_duration)
                throttle_state['suppressed_count'] = 0
                console.print(f"[dim]告警降噪: '{alert_key}' 进入 {silent_duration}s 静默期[/dim]")

            return True  # 节流

        # 冷却期已过，重置计数并放行
        throttle_state['last_time'] = now
        throttle_state['count'] = 1
        throttle_state['iceberg_level'] = iceberg_level
        return False

    def add_iceberg_alert(self, signal: 'IcebergSignal', prev_level: 'IcebergLevel' = None):
        """
        P2-3.1: 冰山专用告警 (含升级绕过)

        Args:
            signal: IcebergSignal 对象
            prev_level: 之前的等级 (用于检测升级)
        """
        ice_level_name = signal.level.name if hasattr(signal.level, 'name') else str(signal.level)
        prev_level_name = prev_level.name if prev_level and hasattr(prev_level, 'name') else None

        # 检查节流
        if CONFIG_ALERT_THROTTLE.get('enabled', True):
            if self._is_alert_throttled(
                level='iceberg',
                message='',
                side=signal.side,
                price=signal.price,
                iceberg_level=ice_level_name,
                prev_iceberg_level=prev_level_name
            ):
                return  # 被节流

        # 构建告警消息
        level_tag = "✓确认" if ice_level_name == 'CONFIRMED' else "?活动"
        side_cn = "买" if signal.side == 'BUY' else "卖"
        message = f"冰山{side_cn}单 [{level_tag}] @{signal.price:.6f} 累计:{signal.cumulative_volume:.0f}U"

        # 通用升级标记: new_level > old_level
        old_val = self._iceberg_level_value(prev_level_name) if prev_level_name else 0
        new_val = self._iceberg_level_value(ice_level_name)
        if new_val > old_val:
            message = f"🔺升级! {message}"

        alert_type = 'buy' if signal.side == 'BUY' else 'sell'

        self.metrics.record_alert()
        alert = {
            "time": datetime.now(),
            "level": "iceberg",
            "message": message
        }
        self.alerts_history.append(alert)
        if len(self.alerts_history) > 20:
            self.alerts_history = self.alerts_history[-20:]
        self.play_alert(alert_type)

        # Discord 通知
        if self.discord_notifier and self.discord_notifier.should_notify(signal.confidence):
            asyncio.create_task(self._send_discord_alert(
                "iceberg", message, alert_type, signal.confidence
            ))

    async def _send_discord_alert(self, level: str, message: str, alert_type: str, confidence: float):
        """异步发送 Discord 通知"""
        try:
            await self.discord_notifier.send_simple(
                symbol=self.symbol,
                level=level,
                message=message,
                alert_type=alert_type,
                price=self.current_price,
                confidence=confidence,
                state=self.current_signal.state_name if self.current_signal else "",
                score=self.last_score,
                extra_fields={
                    "鲸鱼流向": f"${self.total_whale_flow:,.0f}",
                    "MTF趋势": f"{self.mtf_trends.get('1D', '?')}/{self.mtf_trends.get('4H', '?')}/{self.mtf_trends.get('15M', '?')}",
                } if self.discord_notifier.include_fields else None
            )
        except Exception as e:
            console.print(f"[dim]Discord 通知失败: {e}[/dim]")

    def _on_health_status_change(self, status: str, data: dict = None):
        """
        P3: 健康状态变化处理

        触发条件:
        - STALE: 数据过期
        - DISCONNECTED: 连接断开
        - HEALTHY: 恢复正常 (发 RECOVERED)

        规则:
        - 同状态 60s 内只发一次
        - 恢复时发送 RECOVERED 通知
        """
        now = time.time()
        prev_status = self._last_health_status

        # 检查是否需要发送通知
        should_notify = False
        notify_type = status

        if status in ('STALE', 'DISCONNECTED'):
            # 异常状态
            if status != prev_status or (now - self._last_health_notify_time) >= self._health_notify_cooldown:
                should_notify = True
        elif status == 'HEALTHY' and prev_status in ('STALE', 'DISCONNECTED'):
            # 恢复状态
            notify_type = 'RECOVERED'
            should_notify = True

        if should_notify and self.discord_notifier:
            self._last_health_status = status
            self._last_health_notify_time = now

            # 构建消息
            if notify_type == 'STALE':
                data_age = data.get('data_age', 0) if data else 0
                message = f"⚠️ 数据过期 | {self.symbol} | {data_age:.0f}秒无数据"
                level = 'warning'
            elif notify_type == 'DISCONNECTED':
                message = f"🔴 连接断开 | {self.symbol}"
                level = 'warning'
            elif notify_type == 'RECOVERED':
                message = f"✅ 已恢复 | {self.symbol}"
                level = 'normal'
            else:
                return

            console.print(f"[dim]健康通知: {message}[/dim]")
            asyncio.create_task(self._send_health_discord(level, message))

        # 更新状态
        self._last_health_status = status

    async def _send_health_discord(self, level: str, message: str):
        """P3: 发送健康状态 Discord 通知"""
        try:
            await self.discord_notifier.send_simple(
                symbol=self.symbol,
                level=level,
                message=message,
                alert_type='health',
                confidence=100,  # 健康通知总是发送
            )
        except Exception as e:
            console.print(f"[dim]健康通知发送失败: {e}[/dim]")

    async def fetch_data(self) -> Optional[Dict]:
        """获取所有数据 (支持 WebSocket 混合模式)"""
        # 尝试使用 WebSocket 数据
        if self.ws_manager and self.ws_manager.is_connected:
            ws_data = self.ws_manager.get_snapshot()
            if ws_data:
                # 转换 WebSocket 数据格式
                formatted_trades = [
                    {
                        'price': t['price'],
                        'quantity': t['amount'],
                        'is_buyer_maker': t['side'] == 'sell',
                        'timestamp': t['timestamp']
                    }
                    for t in ws_data.get('trades', [])
                ]
                return {
                    'ticker': ws_data['ticker'],
                    'orderbook': ws_data['orderbook'],
                    'trades': formatted_trades
                }

        # 降级到 REST API
        return await self._fetch_rest_data()

    async def _fetch_rest_data(self) -> Optional[Dict]:
        """通过 REST API 获取数据"""
        try:
            # 添加10秒超时保护
            ticker, orderbook, trades = await asyncio.wait_for(
                asyncio.gather(
                    self.exchange.fetch_ticker(self.symbol),
                    self.exchange.fetch_order_book(self.symbol, limit=20),
                    self.exchange.fetch_trades(self.symbol, limit=100)
                ),
                timeout=10.0
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
        except asyncio.TimeoutError:
            console.print("[yellow]⚠ 数据获取超时，跳过本次更新[/yellow]")
            return None
        except Exception as e:
            console.print(f"[red]数据获取错误: {e}[/red]")
            return None

    async def update_mtf(self):
        """更新多时间框架"""
        tf_map = {"15M": "15m", "4H": "4h", "1D": "1d"}
        for tf_display, tf_api in tf_map.items():
            try:
                # 添加8秒超时保护
                ohlcv = await asyncio.wait_for(
                    self.exchange.fetch_ohlcv(self.symbol, tf_api, limit=20),
                    timeout=8.0
                )
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
            except asyncio.TimeoutError:
                console.print(f"[yellow]⚠ {tf_display} K线获取超时[/yellow]")
            except:
                pass

    async def update_derivatives(self):
        """更新合约数据"""
        try:
            # 添加8秒超时保护
            data = await asyncio.wait_for(
                self.derivatives.fetch_all(self.symbol),
                timeout=8.0
            )
            self.funding_rate = data.get("funding_rate")
            self.open_interest = data.get("open_interest")
            self.long_short_ratio = data.get("long_short_ratio")
        except asyncio.TimeoutError:
            console.print("[yellow]⚠ 合约数据获取超时[/yellow]")
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
        """
        计算冰山信号置信度 (P1-2: 集成 spoofing 惩罚)

        使用 PriceLevel 的统一 calculate_confidence 方法，
        已包含 spoofing 惩罚和可疑信号上限。
        """
        return level.calculate_confidence()

    def _log_iceberg_signal(self, signal: 'IcebergSignal'):
        """
        P2-2: 持久化冰山信号到事件日志

        Args:
            signal: IcebergSignal 对象
        """
        if self.event_logger:
            iceberg_data = {
                'side': signal.side,
                'price': signal.price,
                'cumulative_volume': signal.cumulative_volume,
                'visible_depth': signal.visible_depth,
                'intensity': signal.intensity,
                'refill_count': signal.refill_count,
                'confidence': signal.confidence,
                'level': signal.level.name if hasattr(signal.level, 'name') else str(signal.level),
            }
            self.event_logger.log_iceberg(iceberg_data, signal.timestamp.timestamp())

    def _update_kgod_radar(self, price: float, indicators, event_ts: float):
        """
        K神战法 2.0 雷达更新（简化版 OrderFlowSnapshot 构建）

        Args:
            price: 当前价格
            indicators: 指标结果（IndicatorResult）
            event_ts: 事件时间戳

        Returns:
            KGodSignal 或 None
        """
        if not self.kgod_radar:
            return None

        # 更新价格历史（用于计算 Delta斜率）
        self.price_history.append(price)
        if len(self.price_history) > 20:
            self.price_history.pop(0)

        # 更新 CVD 历史
        current_cvd = self.cvd_total
        cvd_delta_5s = current_cvd - self.last_cvd if self.last_cvd != 0 else 0
        self.cvd_history.append(current_cvd)
        if len(self.cvd_history) > 20:
            self.cvd_history.pop(0)
        self.last_cvd = current_cvd

        # 计算 Delta斜率（简化：最近10个点的线性回归斜率）
        delta_slope_10s = 0.0
        if len(self.cvd_history) >= 10:
            recent_cvd = self.cvd_history[-10:]
            # 简单线性回归斜率
            n = len(recent_cvd)
            x_mean = (n - 1) / 2
            y_mean = sum(recent_cvd) / n
            numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent_cvd))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            if denominator > 0:
                delta_slope_10s = numerator / denominator

        # 计算失衡（OBI转换为失衡比例）
        imbalance_1s = 0.5 + indicators.obi / 2  # OBI范围[-1,1] → 失衡范围[0,1]

        # 获取冰山强度（基于当前活跃冰山）
        iceberg_intensity = 0.0
        refill_count = 0
        if self.active_icebergs:
            # 取最强冰山的强度
            strongest_iceberg = max(self.active_icebergs.values(),
                                   key=lambda sig: sig.intensity if hasattr(sig, 'intensity') else 0,
                                   default=None)
            if strongest_iceberg:
                iceberg_intensity = strongest_iceberg.intensity if hasattr(strongest_iceberg, 'intensity') else 0
                refill_count = strongest_iceberg.refill_count if hasattr(strongest_iceberg, 'refill_count') else 0

        # 计算价格在布林带轨道的接受时间（简化：使用历史数据估算）
        acceptance_above_upper_s = 0.0
        acceptance_below_lower_s = 0.0
        # 注意：这个需要布林带数据，我们暂时跳过，让 KGodRadar 自己计算

        # 构建 OrderFlowSnapshot
        order_flow = OrderFlowSnapshot(
            delta_5s=cvd_delta_5s,                      # 5秒 CVD 变化
            delta_slope_10s=delta_slope_10s,            # 10秒 Delta 斜率
            imbalance_1s=imbalance_1s,                  # 1秒失衡（从OBI计算）
            absorption_ask=0.5,                         # 吸收率（暂时使用中性值）
            absorption_bid=0.5,
            sweep_score_5s=0.0,                         # 扫单得分（暂时未实现）
            iceberg_intensity=iceberg_intensity,        # 冰山强度
            refill_count=refill_count,                  # 补单次数
            acceptance_above_upper_s=acceptance_above_upper_s,
            acceptance_below_lower_s=acceptance_below_lower_s
        )

        # 更新雷达
        try:
            signal = self.kgod_radar.update(price, order_flow, event_ts)

            # 如果有信号，处理告警
            if signal:
                self._handle_kgod_signal(signal)

            return signal, order_flow  # 第三十五轮：返回 order_flow 供过滤器使用
        except Exception as e:
            console.print(f"[red]K神雷达更新失败: {e}[/red]")
            return None, None

    def _handle_kgod_signal(self, signal: 'KGodSignal'):
        """
        处理 K神信号（发送 Discord 告警）

        Args:
            signal: KGodSignal 对象
        """
        if not signal:
            return

        # 根据信号级别决定是否告警
        should_alert = False
        alert_level = "normal"

        if signal.stage == SignalStage.KGOD_CONFIRM:
            # K神确认：高优先级告警
            should_alert = signal.confidence >= 70
            alert_level = "opportunity"
        elif signal.stage == SignalStage.EARLY_CONFIRM:
            # 早期确认：中优先级告警
            should_alert = signal.confidence >= 60
            alert_level = "normal"
        elif signal.stage == SignalStage.BAN:
            # 走轨风险：立即告警
            should_alert = True
            alert_level = "warning"
        elif signal.stage == SignalStage.PRE_ALERT:
            # 预警：低优先级，不告警（除非置信度很高）
            should_alert = signal.confidence >= 50
            alert_level = "normal"

        if should_alert:
            self.add_alert(
                self._format_kgod_title(signal),
                self._format_kgod_message(signal),
                alert_level
            )

    def _apply_bollinger_filter(self, kgod_signal: 'KGodSignal',
                                order_flow: 'OrderFlowSnapshot',
                                event_ts: float) -> Optional['KGodSignal']:
        """
        应用布林带环境过滤器（第三十五轮三方共识）

        Args:
            kgod_signal: K神信号
            order_flow: 订单流快照
            event_ts: 事件时间戳

        Returns:
            处理后的信号（可能被 BAN 或增强），或 None（如果被禁止）
        """
        try:
            # 1. 调用过滤器评估
            decision = self.bollinger_filter.evaluate(
                price=self.current_price,
                order_flow=order_flow,
                timestamp=event_ts
            )

            # 2. 记录到事件日志（observe 和 enforce 模式都记录）
            self._log_filter_decision(decision, kgod_signal)

            # 存储决策用于Discord通知
            self.last_filter_decision = decision

            # 3. 如果是 observe 模式，只记录不干预
            if self.bollinger_filter_mode == "observe":
                return kgod_signal

            # 4. enforce 模式：应用决策
            # 4.1 BAN 决策优先（覆盖信号）
            if decision.decision == DecisionType.BAN_LONG and kgod_signal.side.value == "BUY":
                console.print(
                    f"[yellow]🚫 布林带过滤器 BAN 做多信号: {', '.join(decision.reasons)}[/yellow]"
                )
                return None  # 信号被禁止

            elif decision.decision == DecisionType.BAN_SHORT and kgod_signal.side.value == "SELL":
                console.print(
                    f"[yellow]🚫 布林带过滤器 BAN 做空信号: {', '.join(decision.reasons)}[/yellow]"
                )
                return None  # 信号被禁止

            # 4.2 置信度增强（仅在 EARLY_CONFIRM 和 KGOD_CONFIRM 阶段）
            if decision.confidence_boost > 0:
                from core.kgod_radar import SignalStage
                allowed_stages = [SignalStage.EARLY_CONFIRM, SignalStage.KGOD_CONFIRM]

                if kgod_signal.stage in allowed_stages:
                    # 使用乘法公式: new_conf = min(100, base_conf * (1 + boost))
                    old_confidence = kgod_signal.confidence
                    new_confidence = min(100.0, old_confidence * (1 + decision.confidence_boost))
                    kgod_signal.confidence = new_confidence

                    console.print(
                        f"[cyan]✨ 布林带过滤器增强置信度: {old_confidence:.1f}% → {new_confidence:.1f}% "
                        f"(+{decision.confidence_boost*100:.0f}%, {', '.join(decision.reasons)})[/cyan]"
                    )

            return kgod_signal

        except Exception as e:
            # 降级策略：出错时继续运行，不干预信号
            console.print(f"[yellow]⚠️  布林带过滤器执行失败: {e}，降级为 NEUTRAL[/yellow]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            return kgod_signal

    def _log_filter_decision(self, decision: 'RegimeDecision', kgod_signal: 'KGodSignal'):
        """记录布林带过滤器决策到事件日志（结构化）"""
        filter_log = {
            "enabled": self.use_bollinger_filter,
            "mode": self.bollinger_filter_mode,
            "decision": decision.decision.value,
            "confidence_boost": decision.confidence_boost,
            "reasons": decision.reasons,
            "acceptance_time_s": decision.meta.get("acceptance_time", 0.0),
            "state": decision.meta.get("state", "UNKNOWN"),
        }

        # 添加共振场景检测结果
        scenarios = []
        if decision.meta.get("absorption_reversal"):
            scenarios.append("absorption_reversal")
        if decision.meta.get("imbalance_reversal"):
            scenarios.append("imbalance_reversal")
        if decision.meta.get("iceberg_defense"):
            scenarios.append("iceberg_defense")
        if decision.meta.get("walkband_risk"):
            scenarios.append("walkband_risk")
        filter_log["scenarios"] = scenarios

        # 记录到 EventLogger（如果存在）
        if hasattr(self, 'event_logger') and self.event_logger:
            try:
                # 将过滤器决策添加到下一个事件记录中
                # TODO: 集成到 event_logger
                pass
            except Exception as e:
                pass

    def _format_kgod_title(self, signal: 'KGodSignal') -> str:
        """格式化 K神信号标题"""
        stage_icons = {
            SignalStage.PRE_ALERT: "💡",
            SignalStage.EARLY_CONFIRM: "📢",
            SignalStage.KGOD_CONFIRM: "🎯",
            SignalStage.BAN: "🚫"
        }
        side_text = "做多" if signal.side.value == "BUY" else "做空"
        icon = stage_icons.get(signal.stage, "📊")

        if signal.stage == SignalStage.BAN:
            return f"{icon} K神-走轨风险"
        else:
            return f"{icon} K神-{side_text}信号"

    def _format_kgod_message(self, signal: 'KGodSignal') -> str:
        """格式化 K神信号消息"""
        stage_names = {
            SignalStage.PRE_ALERT: "预警",
            SignalStage.EARLY_CONFIRM: "早期确认",
            SignalStage.KGOD_CONFIRM: "K神确认",
            SignalStage.BAN: "禁入/平仓"
        }

        stage_name = stage_names.get(signal.stage, "未知")
        side_text = "看多" if signal.side.value == "BUY" else "看空"

        # 构建消息
        lines = [f"级别: {stage_name}"]

        if signal.stage != SignalStage.BAN:
            lines.append(f"方向: {side_text}")
            lines.append(f"置信度: {signal.confidence:.1f}%")

        # 添加触发原因（最多3条）
        if signal.reasons:
            reasons_text = ", ".join(signal.reasons[:3])
            lines.append(f"原因: {reasons_text}")

        # BAN 信号特殊处理
        if signal.stage == SignalStage.BAN:
            ban_count = self.kgod_radar.get_ban_count() if self.kgod_radar else 0
            lines.append(f"BAN累计: {ban_count} 条")
            if self.kgod_radar:
                if self.kgod_radar.should_force_exit():
                    lines.append("⛔ 建议: 强制平仓")
                elif self.kgod_radar.should_ban_entry():
                    lines.append("🚫 建议: 禁止开仓")

        # 布林带共振场景（第三十五轮）
        if self.last_filter_decision and self.last_filter_decision.confidence_boost > 0:
            scenario_names = {
                "absorption_reversal": "吸收型回归",
                "imbalance_reversal": "失衡确认回归",
                "iceberg_defense": "冰山护盘回归",
            }
            scenarios = []
            for key, name in scenario_names.items():
                if self.last_filter_decision.meta.get(key):
                    scenarios.append(name)

            if scenarios:
                boost_pct = self.last_filter_decision.confidence_boost * 100
                scenarios_text = "+".join(scenarios)
                lines.append(f"✨ 共振: {scenarios_text} (+{boost_pct:.0f}%)")

        # 布林带 BAN 原因（第三十五轮）
        if self.last_filter_decision and self.last_filter_decision.decision.value.startswith("BAN"):
            if self.last_filter_decision.reasons:
                ban_reason = self.last_filter_decision.reasons[0]
                lines.append(f"🚫 布林带BAN: {ban_reason}")

        return " | ".join(lines)

    def detect_icebergs(self):
        """检测冰山单 (Step E: 区分 Activity vs Confirmed) + P2-3.1 告警"""
        # 检测买单冰山
        for price, level in self.bid_levels.items():
            if level.is_iceberg:
                ice_level = level.get_iceberg_level()
                prev_signal = self.active_icebergs.get(price)
                prev_level = prev_signal.level if prev_signal else None

                if price not in self.active_icebergs:
                    # 新冰山
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
                    self._log_iceberg_signal(signal)
                    self.add_iceberg_alert(signal)  # P2-3.1: 发送告警
                elif prev_level and prev_level != ice_level:
                    # P2-3.1: 等级变化，更新并发送告警
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
                    self.active_icebergs[price] = signal
                    self._log_iceberg_signal(signal)
                    self.add_iceberg_alert(signal, prev_level)  # 含升级绕过

        # 检测卖单冰山
        for price, level in self.ask_levels.items():
            if level.is_iceberg:
                ice_level = level.get_iceberg_level()
                prev_signal = self.active_icebergs.get(price)
                prev_level = prev_signal.level if prev_signal else None

                if price not in self.active_icebergs:
                    # 新冰山
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
                    self._log_iceberg_signal(signal)
                    self.add_iceberg_alert(signal)  # P2-3.1: 发送告警
                elif prev_level and prev_level != ice_level:
                    # P2-3.1: 等级变化，更新并发送告警
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
                    self.active_icebergs[price] = signal
                    self._log_iceberg_signal(signal)
                    self.add_iceberg_alert(signal, prev_level)  # 含升级绕过

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

        # P3-2 Phase 2: Multi-signal judgment and Bundle alert
        if CONFIG_FEATURES.get("use_p3_phase2", False) and self.iceberg_signals:
            self._process_phase2_bundle()

    def _process_phase2_bundle(self):
        """
        P3-2 Phase 2: 多信号综合判断与 Bundle 告警

        功能:
        1. 转换 IcebergSignal 为统一格式
        2. 使用 UnifiedSignalManager 处理（融合、调整、冲突、建议）
        3. 发送 Bundle 综合告警
        """
        try:
            # 初始化 Phase 2 组件
            manager = UnifiedSignalManager()

            # 转换 IcebergSignal 为字典格式
            iceberg_dicts = []
            for signal in self.iceberg_signals:
                iceberg_dict = {
                    'type': 'iceberg',
                    'symbol': self.symbol.replace('/', '_'),
                    'ts': signal.timestamp.timestamp(),
                    'side': signal.side,
                    'level': signal.level.name if hasattr(signal.level, 'name') else str(signal.level),
                    'price': signal.price,
                    'confidence': signal.confidence,
                    'intensity': signal.intensity,
                    'refill_count': signal.refill_count,
                    'cumulative_filled': signal.cumulative_volume,
                    'visible_depth': signal.visible_depth,
                }
                iceberg_dicts.append(iceberg_dict)

            # 收集信号（转换为 SignalEvent）
            signals = manager.collect_signals(icebergs=iceberg_dicts)

            if not signals:
                return

            # 执行 Phase 2 处理流程
            result = manager.process_signals_v2(signals)

            processed_signals = result['signals']
            advice = result['advice']

            # 发送 Bundle 告警
            if self.discord_notifier and processed_signals:
                advice_level = advice['advice']

                # 根据建议级别决定是否发送
                should_send = False
                if advice_level in ['STRONG_BUY', 'STRONG_SELL']:
                    should_send = True
                elif advice_level in ['BUY', 'SELL']:
                    # 中等建议，检查置信度
                    should_send = advice['confidence'] > 0.6

                if should_send:
                    asyncio.create_task(
                        self._send_phase2_bundle_alert(processed_signals, advice)
                    )

        except Exception as e:
            console.print(f"[yellow]Phase 2 处理出错: {e}[/yellow]")

    async def _send_phase2_bundle_alert(self, signals: List, advice: Dict):
        """
        发送 Phase 2 Bundle 告警到 Discord

        Args:
            signals: 处理后的 SignalEvent 列表
            advice: 综合建议数据
        """
        try:
            if hasattr(self.discord_notifier, 'send_bundle_alert'):
                # 使用 Phase 2 的 Bundle 告警
                await self.discord_notifier.send_bundle_alert(
                    symbol=self.symbol,
                    signals=signals,
                    advice=advice,
                    market_state={
                        'current_price': self.current_price,
                        'cvd_total': self.cvd_total,
                        'whale_flow': self.total_whale_flow,
                    }
                )
            else:
                console.print("[yellow]Discord notifier 不支持 Bundle 告警[/yellow]")
        except Exception as e:
            console.print(f"[red]发送 Bundle 告警失败: {e}[/red]")

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

        # ========== K神战法 2.0 雷达更新 ==========
        kgod_signal = None
        order_flow_snapshot = None
        if self.use_kgod and self.kgod_radar:
            kgod_signal, order_flow_snapshot = self._update_kgod_radar(self.current_price, ind, event_ts)

        # ========== 布林带环境过滤器（第三十五轮）==========
        if kgod_signal and self.use_bollinger_filter and self.bollinger_filter and order_flow_snapshot:
            kgod_signal = self._apply_bollinger_filter(kgod_signal, order_flow_snapshot, event_ts)

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

        # 连接 WebSocket (如果启用)
        if self.ws_manager:
            console.print("[cyan]尝试连接 WebSocket...[/cyan]")

            # P3: 注册健康检查回调
            self.ws_manager.on('data_stale', lambda d: self._on_health_status_change('STALE', d))
            self.ws_manager.on('data_recovered', lambda d: self._on_health_status_change('HEALTHY', d))
            self.ws_manager.on('disconnected', lambda d: self._on_health_status_change('DISCONNECTED', d))
            self.ws_manager.on('connected', lambda d: self._on_health_status_change('HEALTHY', d))

            ws_connected = await self.ws_manager.connect()
            if ws_connected:
                console.print("[green]WebSocket 已连接，使用实时数据[/green]")
            else:
                console.print("[yellow]WebSocket 连接失败，使用 REST 模式[/yellow]")

        # 初始化 Discord 通知
        if self.discord_notifier:
            await self.discord_notifier.initialize()
            console.print(f"[dim]Discord 通知已启用 (最低置信度: {CONFIG_DISCORD.get('min_confidence', 50)}%)[/dim]")

        # 初始更新
        await self.update_mtf()
        await self.update_derivatives()

        counter = 0
        # WebSocket 模式下使用更短的轮询间隔
        poll_interval = 1 if (self.ws_manager and self.ws_manager.is_connected) else 5

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

                    counter += poll_interval
                    if counter >= 60:
                        # 添加整体超时保护
                        try:
                            await asyncio.wait_for(self.update_mtf(), timeout=15.0)
                            await asyncio.wait_for(self.update_derivatives(), timeout=15.0)
                        except asyncio.TimeoutError:
                            console.print("[yellow]⚠ MTF/合约更新整体超时[/yellow]")
                        counter = 0

                    await asyncio.sleep(poll_interval)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    console.print(f"[red]错误: {e}[/red]")
                    await asyncio.sleep(5)

    async def shutdown(self):
        """关闭"""
        self.running = False

        # Step C: 强制保存状态 (使用 last_event_ts 保证确定性 - GPT建议)
        # P2-4: 使用扩展保存
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
            # P2-4: 扩展保存 (含冰山 + 节流)
            active_icebergs = self._serialize_active_icebergs()
            self.state_saver.save_extended(
                state=state,
                active_icebergs=active_icebergs,
                throttle_state=self._alert_throttle,
                current_ts=self.last_event_ts,
                force=True
            )
            ice_count = len(active_icebergs)
            throttle_count = len(self._alert_throttle)
            console.print(f"[green]✓ 状态已保存[/green] (冰山:{ice_count}, 节流:{throttle_count})")
        else:
            console.print("[yellow]⚠ 无 event_ts，跳过状态保存[/yellow]")

        # P3: 保存运行元信息
        if self.run_recorder:
            self.run_recorder.finalize(metrics={
                'total_signals': self.iceberg_buy_count + self.iceberg_sell_count,
                'confirmed_count': self.metrics.confirmed_count,
                'activity_count': self.metrics.activity_count,
                'reconnect_count': self.ws_manager.reconnect_count if self.ws_manager else 0,
                'throttle_count': len(self._alert_throttle),
            })
            console.print(f"[dim]Run 元信息已保存: {self.run_recorder.filepath}[/dim]")

        # 打印 72 小时验证监控报告
        self.metrics.print_report()

        # 关闭 WebSocket
        if self.ws_manager:
            await self.ws_manager.disconnect()

        # 关闭 Discord 通知器
        if self.discord_notifier:
            await self.discord_notifier.close()

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
    parser.add_argument('--web', action='store_true',
                        help='启动 Web 仪表板')
    parser.add_argument('--web-only', action='store_true',
                        help='仅启动 Web 仪表板 (无终端 UI)')
    parser.add_argument('--port', type=int, default=8080,
                        help='Web 服务器端口 (默认: 8080)')
    args = parser.parse_args()

    monitor = AlertMonitor(symbol=args.symbol)

    # Web 仪表板模式
    web_server = None
    web_runner = None

    if args.web or args.web_only:
        try:
            from web.server import DashboardServer
            from config.settings import CONFIG_WEB

            # 更新端口配置
            config = CONFIG_WEB.copy()
            config['port'] = args.port

            web_server = DashboardServer(
                monitors={args.symbol: monitor},
                config=config
            )
            web_runner = await web_server.start()
            console.print(f"[green]Web 仪表板: http://localhost:{args.port}[/green]")
        except ImportError as e:
            console.print(f"[red]无法启动 Web 服务器: {e}[/red]")
            console.print("[yellow]请安装 aiohttp: pip install aiohttp[/yellow]")

    try:
        if args.web_only:
            # 仅 Web 模式：后台运行监控，无终端 UI
            console.print("[cyan]Web-only 模式: 终端 UI 已禁用[/cyan]")
            await monitor.initialize()
            monitor.running = True

            # 连接 WebSocket
            if monitor.ws_manager:
                await monitor.ws_manager.connect()

            # 初始化 Discord
            if monitor.discord_notifier:
                await monitor.discord_notifier.initialize()

            # 后台数据更新循环
            import time
            counter = 0
            while monitor.running:
                try:
                    event_ts = time.time()
                    monitor.last_event_ts = event_ts
                    monitor.metrics.record_tick(event_ts)

                    data = await monitor.fetch_data()
                    if data:
                        monitor.analyze_and_alert(data, event_ts)

                    counter += 5
                    if counter >= 60:
                        try:
                            await asyncio.wait_for(monitor.update_mtf(), timeout=15.0)
                            await asyncio.wait_for(monitor.update_derivatives(), timeout=15.0)
                        except asyncio.TimeoutError:
                            pass
                        counter = 0

                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    console.print(f"[red]错误: {e}[/red]")
                    await asyncio.sleep(5)
        else:
            # 正常模式：终端 UI + 可选 Web
            await monitor.run()

    except KeyboardInterrupt:
        console.print("\n[yellow]正在关闭...[/yellow]")
    finally:
        # 关闭 Web 服务器
        if web_server:
            await web_server.stop()
        if web_runner:
            await web_runner.cleanup()

        await monitor.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
