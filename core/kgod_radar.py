"""
K神战法 2.0 - 核心雷达模块
K-God Strategy 2.0 - Core Radar Module

基于布林带 + MACD + 订单流的四层信号识别系统
- PRE_ALERT: 预警（z ≥ 1.4）
- EARLY_CONFIRM: 早期确认（z ≥ 1.8 + MACD + 弱订单流）
- KGOD_CONFIRM: K神确认（z ≥ 2.0 + MACD强 + 强订单流 + 带宽扩张）
- BAN: 禁入（走轨风险：≥2条禁入，≥3条强制平仓）

作者: 三方共识（Claude + GPT + Gemini）
日期: 2026-01-09
版本: v2.0
参考: 第二十七轮、第二十八轮三方共识
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from enum import Enum

from config.kgod_settings import get_kgod_config


# ==================== 信号级别枚举 ====================
class SignalStage(Enum):
    """K神战法信号级别"""
    PRE_ALERT = "PRE_ALERT"              # 预警
    EARLY_CONFIRM = "EARLY_CONFIRM"      # 早期确认
    KGOD_CONFIRM = "KGOD_CONFIRM"        # K神确认
    BAN = "BAN"                          # 禁入（走轨风险）


class SignalSide(Enum):
    """信号方向"""
    BUY = "BUY"       # 看多（做多）
    SELL = "SELL"     # 看空（做空）


# ==================== 订单流快照 ====================
@dataclass
class OrderFlowSnapshot:
    """
    订单流快照（从 IcebergDetector、DeltaTracker 等模块获取）

    字段说明：
    - delta_5s: 5秒内累计 Delta（正=买压，负=卖压）
    - delta_slope_10s: 10秒 Delta 斜率（正=加速买入，负=加速卖出）
    - imbalance_1s: 1秒内买卖失衡比例（0.6 = 60% 买方）
    - absorption_ask: 卖方吸收率（高=买盘强劲吃掉卖单）
    - sweep_score_5s: 5秒扫单得分（>3 = 强扫单）
    - iceberg_intensity: 冰山强度（>2 = 冰山存在）
    - refill_count: 补单次数
    - acceptance_above_upper_s: 价格在上轨上方接受时间（秒）
    """
    delta_5s: float = 0.0
    delta_slope_10s: float = 0.0
    imbalance_1s: float = 0.5
    absorption_ask: float = 0.5
    absorption_bid: float = 0.5
    sweep_score_5s: float = 0.0
    iceberg_intensity: float = 0.0
    refill_count: int = 0
    acceptance_above_upper_s: float = 0.0
    acceptance_below_lower_s: float = 0.0


# ==================== K神信号输出 ====================
@dataclass
class KGodSignal:
    """
    K神战法信号输出结构

    字段说明：
    - symbol: 交易对符号
    - ts: 时间戳
    - side: 信号方向（BUY/SELL）
    - stage: 信号级别（PRE_ALERT/EARLY_CONFIRM/KGOD_CONFIRM/BAN）
    - confidence: 置信度（0-100）
    - reasons: 触发原因列表
    - debug: 调试信息（包含中间计算值）
    """
    symbol: str
    ts: float
    side: SignalSide
    stage: SignalStage
    confidence: float  # 0-100
    reasons: List[str] = field(default_factory=list)
    debug: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典格式（用于日志/存储）"""
        return {
            'symbol': self.symbol,
            'ts': self.ts,
            'side': self.side.value,
            'stage': self.stage.value,
            'confidence': self.confidence,
            'reasons': self.reasons,
            'debug': self.debug
        }


# ==================== O(1) 增量布林带计算 ====================
class RollingBB:
    """
    O(1) 复杂度的增量布林带计算器

    使用 collections.deque 实现滑动窗口，避免每次重新计算整个窗口。

    输出：
    - mid: 中轨（SMA）
    - upper: 上轨（mid + num_std * std）
    - lower: 下轨（mid - num_std * std）
    - bandwidth: 带宽（(upper - lower) / mid）
    - bw_slope: 带宽斜率（最近 N 个 tick 的带宽变化）
    - z: 当前价格的 z-score（(price - mid) / std）
    """

    def __init__(self, period: int = 20, num_std: float = 2.0, bw_slope_window: int = 5):
        """
        初始化布林带计算器

        Args:
            period: 布林带周期（默认 20）
            num_std: 标准差倍数（默认 2.0）
            bw_slope_window: 带宽斜率计算窗口（默认 5）
        """
        self.period = period
        self.num_std = num_std
        self.bw_slope_window = bw_slope_window

        # 价格队列（deque 实现 O(1) append/popleft）
        self.prices = deque(maxlen=period)

        # 中间变量（增量计算用）
        self.sum_prices = 0.0
        self.sum_sq_prices = 0.0

        # 带宽历史（用于计算斜率）
        self.bandwidth_history = deque(maxlen=bw_slope_window)

        # 当前输出
        self.mid = 0.0
        self.upper = 0.0
        self.lower = 0.0
        self.bandwidth = 0.0
        self.bw_slope = 0.0
        self.z = 0.0

    def update(self, price: float) -> Dict:
        """
        更新布林带（O(1) 复杂度）

        Args:
            price: 新价格

        Returns:
            包含所有输出的字典
        """
        # 如果队列已满，移除最旧价格的贡献
        if len(self.prices) == self.period:
            old_price = self.prices[0]
            self.sum_prices -= old_price
            self.sum_sq_prices -= old_price ** 2

        # 添加新价格
        self.prices.append(price)
        self.sum_prices += price
        self.sum_sq_prices += price ** 2

        # 计算中轨（SMA）
        n = len(self.prices)
        self.mid = self.sum_prices / n

        # 计算标准差（增量方式）
        variance = (self.sum_sq_prices / n) - (self.mid ** 2)
        std = math.sqrt(max(variance, 0))  # 避免负数

        # 计算上下轨
        self.upper = self.mid + self.num_std * std
        self.lower = self.mid - self.num_std * std

        # 计算带宽
        if self.mid > 0:
            self.bandwidth = (self.upper - self.lower) / self.mid
        else:
            self.bandwidth = 0.0

        # 计算带宽斜率
        self.bandwidth_history.append(self.bandwidth)
        if len(self.bandwidth_history) >= 2:
            self.bw_slope = self.bandwidth_history[-1] - self.bandwidth_history[0]
        else:
            self.bw_slope = 0.0

        # 计算 z-score
        if std > 0:
            self.z = (price - self.mid) / std
        else:
            self.z = 0.0

        return self.get_values()

    def get_values(self) -> Dict:
        """获取当前布林带所有输出"""
        return {
            'mid': self.mid,
            'upper': self.upper,
            'lower': self.lower,
            'bandwidth': self.bandwidth,
            'bw_slope': self.bw_slope,
            'z': self.z
        }

    def is_ready(self) -> bool:
        """布林带是否准备就绪（数据量 >= period）"""
        return len(self.prices) >= self.period


# ==================== O(1) 增量 MACD 计算 ====================
class MACD:
    """
    O(1) 复杂度的增量 MACD 计算器

    使用 EMA 增量公式，避免每次重新计算。

    输出：
    - macd: MACD 线（快线 - 慢线）
    - signal: 信号线（MACD 的 EMA）
    - hist: 柱状图（MACD - signal）
    - hist_slope: 柱状图斜率（最近 N 个 tick 的变化）
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26,
                 signal_period: int = 9, hist_slope_window: int = 3):
        """
        初始化 MACD 计算器

        Args:
            fast_period: 快线周期（默认 12）
            slow_period: 慢线周期（默认 26）
            signal_period: 信号线周期（默认 9）
            hist_slope_window: 柱状图斜率窗口（默认 3）
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.hist_slope_window = hist_slope_window

        # EMA 系数
        self.alpha_fast = 2.0 / (fast_period + 1)
        self.alpha_slow = 2.0 / (slow_period + 1)
        self.alpha_signal = 2.0 / (signal_period + 1)

        # EMA 值（增量计算）
        self.ema_fast = None
        self.ema_slow = None
        self.ema_signal = None

        # 柱状图历史（用于斜率）
        self.hist_history = deque(maxlen=hist_slope_window)

        # 当前输出
        self.macd = 0.0
        self.signal = 0.0
        self.hist = 0.0
        self.hist_slope = 0.0

        # 初始化计数器
        self.count = 0

    def update(self, price: float) -> Dict:
        """
        更新 MACD（O(1) 复杂度）

        Args:
            price: 新价格

        Returns:
            包含所有输出的字典
        """
        self.count += 1

        # 初始化 EMA（第一个值）
        if self.ema_fast is None:
            self.ema_fast = price
            self.ema_slow = price
            return self.get_values()

        # 增量更新快线和慢线
        self.ema_fast = self.alpha_fast * price + (1 - self.alpha_fast) * self.ema_fast
        self.ema_slow = self.alpha_slow * price + (1 - self.alpha_slow) * self.ema_slow

        # 计算 MACD 线
        self.macd = self.ema_fast - self.ema_slow

        # 增量更新信号线
        if self.ema_signal is None:
            self.ema_signal = self.macd
        else:
            self.ema_signal = self.alpha_signal * self.macd + (1 - self.alpha_signal) * self.ema_signal

        self.signal = self.ema_signal

        # 计算柱状图
        self.hist = self.macd - self.signal

        # 计算柱状图斜率
        self.hist_history.append(self.hist)
        if len(self.hist_history) >= 2:
            self.hist_slope = self.hist_history[-1] - self.hist_history[0]
        else:
            self.hist_slope = 0.0

        return self.get_values()

    def get_values(self) -> Dict:
        """获取当前 MACD 所有输出"""
        return {
            'macd': self.macd,
            'signal': self.signal,
            'hist': self.hist,
            'hist_slope': self.hist_slope
        }

    def is_ready(self) -> bool:
        """MACD 是否准备就绪（数据量 >= slow_period）"""
        return self.count >= self.slow_period


# ==================== K神雷达核心类 ====================
class KGodRadar:
    """
    K神战法 2.0 核心雷达

    职责：
    1. 接收价格流和订单流数据
    2. 计算布林带和 MACD 指标
    3. 综合判断信号级别（PRE_ALERT / EARLY_CONFIRM / KGOD_CONFIRM / BAN）
    4. 输出带置信度的 KGodSignal
    5. 管理走轨风险（BAN 信号累计）

    使用示例：
    >>> radar = KGodRadar(symbol="DOGE_USDT")
    >>> flow = OrderFlowSnapshot(delta_5s=500, imbalance_1s=0.7)
    >>> signal = radar.update(price=0.15080, order_flow=flow, ts=time.time())
    >>> if signal:
    >>>     print(f"信号: {signal.stage.value}, 置信度: {signal.confidence}")
    """

    def __init__(self, symbol: str, config: Optional[Dict] = None):
        """
        初始化 K神雷达

        Args:
            symbol: 交易对符号
            config: 配置字典（可选，默认使用 kgod_settings.py）
        """
        self.symbol = symbol

        # 加载配置
        if config is None:
            config = get_kgod_config()
        self.config = config

        # 初始化布林带
        bb_cfg = config['bollinger']
        self.bb = RollingBB(
            period=bb_cfg['period'],
            num_std=bb_cfg['num_std'],
            bw_slope_window=bb_cfg['bw_slope_window']
        )

        # 初始化 MACD
        macd_cfg = config['macd']
        self.macd = MACD(
            fast_period=macd_cfg['fast_period'],
            slow_period=macd_cfg['slow_period'],
            signal_period=macd_cfg['signal_period'],
            hist_slope_window=macd_cfg['hist_slope_window']
        )

        # BAN 信号历史（走轨风险管理）
        max_ban_size = config['performance']['ban_history_size']
        self.ban_history: deque = deque(maxlen=max_ban_size)

        # 统计信息
        self.stats = {
            'total_updates': 0,
            'pre_alert_count': 0,
            'early_confirm_count': 0,
            'kgod_confirm_count': 0,
            'ban_count': 0
        }

    def update(self, price: float, order_flow: OrderFlowSnapshot, ts: float) -> Optional[KGodSignal]:
        """
        更新雷达状态并生成信号

        Args:
            price: 当前价格
            order_flow: 订单流快照
            ts: 时间戳

        Returns:
            KGodSignal 或 None（如果未触发信号）
        """
        self.stats['total_updates'] += 1

        # 更新指标
        bb_values = self.bb.update(price)
        macd_values = self.macd.update(price)

        # 检查是否准备就绪
        if not (self.bb.is_ready() and self.macd.is_ready()):
            return None

        # 检查 BAN 信号（走轨风险）
        ban_signal = self._check_ban_conditions(price, bb_values, macd_values, order_flow, ts)
        if ban_signal:
            self.ban_history.append(ban_signal)
            self.stats['ban_count'] += 1
            return ban_signal

        # 检查 K神确认信号
        kgod_signal = self._check_kgod_confirm(price, bb_values, macd_values, order_flow, ts)
        if kgod_signal:
            self.stats['kgod_confirm_count'] += 1
            return kgod_signal

        # 检查早期确认信号
        early_signal = self._check_early_confirm(price, bb_values, macd_values, order_flow, ts)
        if early_signal:
            self.stats['early_confirm_count'] += 1
            return early_signal

        # 检查预警信号
        pre_signal = self._check_pre_alert(price, bb_values, macd_values, order_flow, ts)
        if pre_signal:
            self.stats['pre_alert_count'] += 1
            return pre_signal

        return None

    def _check_ban_conditions(self, price: float, bb_values: Dict, macd_values: Dict,
                             order_flow: OrderFlowSnapshot, ts: float) -> Optional[KGodSignal]:
        """
        检查 BAN 信号（走轨风险）

        触发条件（任意一条即记录）：
        1. 价格持续在上轨上方 >30s
        2. 价格持续在下轨下方 >30s
        3. 带宽持续收缩
        4. MACD 柱状图反向
        5. 订单流方向反转
        6. 冰山信号消失

        Returns:
            BAN 信号或 None
        """
        ban_cfg = self.config['ban_detection']
        acceptance_cfg = self.config['acceptance']
        reasons = []

        # 1. 价格持续在上轨上方
        if ban_cfg['check_acceptance']:
            if order_flow.acceptance_above_upper_s > acceptance_cfg['acceptance_above_upper_s']:
                reasons.append(f"价格持续在上轨上方 {order_flow.acceptance_above_upper_s:.1f}s")

        # 2. 价格持续在下轨下方
        if ban_cfg['check_acceptance']:
            if order_flow.acceptance_below_lower_s > acceptance_cfg['acceptance_below_lower_s']:
                reasons.append(f"价格持续在下轨下方 {order_flow.acceptance_below_lower_s:.1f}s")

        # 3. 带宽持续收缩
        if ban_cfg['check_bandwidth_shrink']:
            if bb_values['bw_slope'] < ban_cfg['bw_shrink_threshold']:
                reasons.append(f"带宽持续收缩 (斜率={bb_values['bw_slope']:.6f})")

        # 4. MACD 柱状图反向
        if ban_cfg['check_macd_reversal']:
            if macd_values['hist_slope'] < -ban_cfg.get('macd_reversal_threshold', 0.000005):
                reasons.append(f"MACD 柱状图反向 (斜率={macd_values['hist_slope']:.6f})")

        # 5. 订单流方向反转
        if ban_cfg['check_flow_reversal']:
            if order_flow.delta_5s < ban_cfg['flow_reversal_delta']:
                reasons.append(f"Delta 大幅反转 ({order_flow.delta_5s:.1f} USDT)")
            imb_change = order_flow.imbalance_1s - 0.5
            if imb_change < ban_cfg['flow_reversal_imbalance']:
                reasons.append(f"失衡反转 (imbalance={order_flow.imbalance_1s:.2f})")

        # 6. 冰山信号消失
        if ban_cfg['check_iceberg_loss']:
            if order_flow.iceberg_intensity < 1.0 and order_flow.refill_count == 0:
                reasons.append("冰山信号消失")

        # 如果有任何 BAN 原因，生成信号
        if reasons:
            # 判断方向（基于价格位置）
            if price > bb_values['upper']:
                side = SignalSide.BUY  # 在上轨上方 = 多头走轨风险
            elif price < bb_values['lower']:
                side = SignalSide.SELL  # 在下轨下方 = 空头走轨风险
            else:
                side = SignalSide.BUY if bb_values['z'] > 0 else SignalSide.SELL

            return KGodSignal(
                symbol=self.symbol,
                ts=ts,
                side=side,
                stage=SignalStage.BAN,
                confidence=0.0,  # BAN 信号无置信度
                reasons=reasons,
                debug={
                    'bb': bb_values,
                    'macd': macd_values,
                    'order_flow': order_flow.__dict__,
                    'ban_count': len(self.ban_history)
                }
            )

        return None

    def _check_kgod_confirm(self, price: float, bb_values: Dict, macd_values: Dict,
                           order_flow: OrderFlowSnapshot, ts: float) -> Optional[KGodSignal]:
        """
        检查 K神确认信号（最高级别）

        触发条件：
        1. |z| ≥ 2.0
        2. MACD 柱状图同方向且斜率 > 阈值
        3. 强订单流确认（Delta 强 + 失衡强 + 扫单强）
        4. 带宽扩张

        Returns:
            KGOD_CONFIRM 信号或 None
        """
        stage_cfg = self.config['signal_stages']['kgod_confirm']
        flow_cfg = self.config['order_flow']
        bb_cfg = self.config['bollinger']
        boost_cfg = self.config['confidence_boost']

        # 条件 1: z-score ≥ 2.0
        if abs(bb_values['z']) < stage_cfg['z_min']:
            return None

        # 判断方向
        side = SignalSide.BUY if bb_values['z'] > 0 else SignalSide.SELL

        # 条件 2: MACD 强确认
        if stage_cfg['require_macd_strong']:
            if side == SignalSide.BUY:
                if macd_values['hist'] <= 0 or macd_values['hist_slope'] <= 0:
                    return None
            else:  # SELL
                if macd_values['hist'] >= 0 or macd_values['hist_slope'] >= 0:
                    return None

        # 条件 3: 强订单流确认
        if stage_cfg['require_order_flow_strong']:
            if side == SignalSide.BUY:
                # 需要：Delta 强 + 失衡强
                if order_flow.delta_5s < flow_cfg['delta_5s_strong']:
                    return None
                if order_flow.imbalance_1s < flow_cfg['imbalance_1s_strong']:
                    return None
            else:  # SELL
                if order_flow.delta_5s > -flow_cfg['delta_5s_strong']:
                    return None
                if order_flow.imbalance_1s > (1 - flow_cfg['imbalance_1s_strong']):
                    return None

        # 条件 4: 带宽扩张
        if stage_cfg['require_bandwidth_expand']:
            if bb_values['bw_slope'] < bb_cfg['bw_expand_min']:
                return None

        # 计算置信度
        confidence = stage_cfg['confidence_base']
        reasons = [f"|z| = {abs(bb_values['z']):.2f} ≥ 2.0"]

        # MACD 加成
        if abs(macd_values['hist']) > 0:
            confidence += boost_cfg['macd_hist_positive']
            reasons.append(f"MACD 同向 (hist={macd_values['hist']:.5f})")
        if abs(macd_values['hist_slope']) > 0:
            confidence += boost_cfg['macd_slope_positive']
            reasons.append(f"MACD 加速 (slope={macd_values['hist_slope']:.5f})")

        # 订单流加成
        if abs(order_flow.delta_5s) >= flow_cfg['delta_5s_strong']:
            confidence += boost_cfg['delta_strong']
            reasons.append(f"Delta 强 ({order_flow.delta_5s:.1f} USDT)")

        if side == SignalSide.BUY:
            if order_flow.imbalance_1s >= flow_cfg['imbalance_1s_strong']:
                confidence += boost_cfg['imbalance_strong']
                reasons.append(f"失衡强 ({order_flow.imbalance_1s:.2f})")
        else:
            if order_flow.imbalance_1s <= (1 - flow_cfg['imbalance_1s_strong']):
                confidence += boost_cfg['imbalance_strong']
                reasons.append(f"失衡强 ({order_flow.imbalance_1s:.2f})")

        if abs(order_flow.sweep_score_5s) >= flow_cfg['sweep_score_5s_strong']:
            confidence += boost_cfg['sweep_strong']
            reasons.append(f"扫单强 ({order_flow.sweep_score_5s:.1f})")

        # 冰山加成
        if order_flow.iceberg_intensity >= flow_cfg['iceberg_intensity_min']:
            confidence += boost_cfg['iceberg_present']
            confidence += boost_cfg['iceberg_refill_bonus'] * order_flow.refill_count
            reasons.append(f"冰山存在 (强度={order_flow.iceberg_intensity:.1f}, 补单={order_flow.refill_count})")

        # 带宽扩张加成
        if bb_values['bw_slope'] >= bb_cfg['bw_expand_strong']:
            confidence += boost_cfg['bandwidth_expand_strong']
            reasons.append(f"带宽强扩张 ({bb_values['bw_slope']:.5f})")
        elif bb_values['bw_slope'] >= bb_cfg['bw_expand_min']:
            confidence += boost_cfg['bandwidth_expand_weak']
            reasons.append(f"带宽扩张 ({bb_values['bw_slope']:.5f})")

        # 限制置信度上限
        confidence = min(confidence, stage_cfg['confidence_max'])

        return KGodSignal(
            symbol=self.symbol,
            ts=ts,
            side=side,
            stage=SignalStage.KGOD_CONFIRM,
            confidence=confidence,
            reasons=reasons,
            debug={
                'bb': bb_values,
                'macd': macd_values,
                'order_flow': order_flow.__dict__
            }
        )

    def _check_early_confirm(self, price: float, bb_values: Dict, macd_values: Dict,
                            order_flow: OrderFlowSnapshot, ts: float) -> Optional[KGodSignal]:
        """
        检查早期确认信号（中级别）

        触发条件：
        1. |z| ≥ 1.8
        2. MACD 柱状图同方向
        3. 弱订单流确认（Delta 弱或失衡弱）

        Returns:
            EARLY_CONFIRM 信号或 None
        """
        stage_cfg = self.config['signal_stages']['early_confirm']
        flow_cfg = self.config['order_flow']
        macd_cfg = self.config['macd']
        boost_cfg = self.config['confidence_boost']

        # 条件 1: z-score ≥ 1.8
        if abs(bb_values['z']) < stage_cfg['z_min']:
            return None

        # 判断方向
        side = SignalSide.BUY if bb_values['z'] > 0 else SignalSide.SELL

        # 条件 2: MACD 确认
        if stage_cfg['require_macd']:
            if side == SignalSide.BUY:
                if macd_values['hist'] < macd_cfg['hist_min_confirm']:
                    return None
            else:  # SELL
                if macd_values['hist'] > -macd_cfg['hist_min_confirm']:
                    return None

        # 条件 3: 弱订单流确认
        if stage_cfg['require_order_flow_weak']:
            if side == SignalSide.BUY:
                # Delta 弱或失衡弱
                has_weak_flow = (
                    order_flow.delta_5s >= flow_cfg['delta_5s_weak'] or
                    order_flow.imbalance_1s >= flow_cfg['imbalance_1s_weak']
                )
                if not has_weak_flow:
                    return None
            else:  # SELL
                has_weak_flow = (
                    order_flow.delta_5s <= -flow_cfg['delta_5s_weak'] or
                    order_flow.imbalance_1s <= (1 - flow_cfg['imbalance_1s_weak'])
                )
                if not has_weak_flow:
                    return None

        # 计算置信度
        confidence = stage_cfg['confidence_base']
        reasons = [f"|z| = {abs(bb_values['z']):.2f} ≥ 1.8"]

        # MACD 加成
        if abs(macd_values['hist']) > macd_cfg['hist_min_confirm']:
            confidence += boost_cfg['macd_hist_positive']
            reasons.append(f"MACD 同向 (hist={macd_values['hist']:.5f})")

        # 订单流加成
        if abs(order_flow.delta_5s) >= flow_cfg['delta_5s_weak']:
            confidence += boost_cfg['delta_weak']
            reasons.append(f"Delta 弱 ({order_flow.delta_5s:.1f} USDT)")

        if side == SignalSide.BUY:
            if order_flow.imbalance_1s >= flow_cfg['imbalance_1s_weak']:
                confidence += boost_cfg['imbalance_weak']
                reasons.append(f"失衡弱 ({order_flow.imbalance_1s:.2f})")
        else:
            if order_flow.imbalance_1s <= (1 - flow_cfg['imbalance_1s_weak']):
                confidence += boost_cfg['imbalance_weak']
                reasons.append(f"失衡弱 ({order_flow.imbalance_1s:.2f})")

        # 限制置信度上限
        confidence = min(confidence, stage_cfg['confidence_max'])

        return KGodSignal(
            symbol=self.symbol,
            ts=ts,
            side=side,
            stage=SignalStage.EARLY_CONFIRM,
            confidence=confidence,
            reasons=reasons,
            debug={
                'bb': bb_values,
                'macd': macd_values,
                'order_flow': order_flow.__dict__
            }
        )

    def _check_pre_alert(self, price: float, bb_values: Dict, macd_values: Dict,
                        order_flow: OrderFlowSnapshot, ts: float) -> Optional[KGodSignal]:
        """
        检查预警信号（最低级别）

        触发条件：
        1. |z| ≥ 1.4

        Returns:
            PRE_ALERT 信号或 None
        """
        stage_cfg = self.config['signal_stages']['pre_alert']

        # 条件 1: z-score ≥ 1.4
        if abs(bb_values['z']) < stage_cfg['z_min']:
            return None

        # 判断方向
        side = SignalSide.BUY if bb_values['z'] > 0 else SignalSide.SELL

        # 基础置信度
        confidence = stage_cfg['confidence_base']
        reasons = [f"|z| = {abs(bb_values['z']):.2f} ≥ 1.4"]

        # 简单加成（如果有 MACD 或订单流支持）
        boost_cfg = self.config['confidence_boost']
        if side == SignalSide.BUY:
            if macd_values['hist'] > 0:
                confidence += 5
                reasons.append("MACD 看涨")
            if order_flow.delta_5s > 0:
                confidence += 5
                reasons.append("Delta 正向")
        else:  # SELL
            if macd_values['hist'] < 0:
                confidence += 5
                reasons.append("MACD 看跌")
            if order_flow.delta_5s < 0:
                confidence += 5
                reasons.append("Delta 负向")

        # 限制置信度上限
        confidence = min(confidence, stage_cfg['confidence_max'])

        return KGodSignal(
            symbol=self.symbol,
            ts=ts,
            side=side,
            stage=SignalStage.PRE_ALERT,
            confidence=confidence,
            reasons=reasons,
            debug={
                'bb': bb_values,
                'macd': macd_values,
                'order_flow': order_flow.__dict__
            }
        )

    def get_ban_count(self) -> int:
        """获取当前 BAN 信号累计数"""
        return len(self.ban_history)

    def should_ban_entry(self) -> bool:
        """是否应该禁止开仓（≥2 条 BAN）"""
        threshold = self.config['signal_stages']['ban']['ban_threshold_enter']
        return len(self.ban_history) >= threshold

    def should_force_exit(self) -> bool:
        """是否应该强制平仓（≥3 条 BAN）"""
        threshold = self.config['signal_stages']['ban']['ban_threshold_force_exit']
        return len(self.ban_history) >= threshold

    def clear_ban_history(self):
        """清除 BAN 信号历史（在仓位平仓后调用）"""
        self.ban_history.clear()

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'ban_count_current': len(self.ban_history),
            'should_ban_entry': self.should_ban_entry(),
            'should_force_exit': self.should_force_exit()
        }

    def reset(self):
        """重置雷达状态（不重置配置）"""
        self.bb = RollingBB(
            period=self.config['bollinger']['period'],
            num_std=self.config['bollinger']['num_std'],
            bw_slope_window=self.config['bollinger']['bw_slope_window']
        )
        self.macd = MACD(
            fast_period=self.config['macd']['fast_period'],
            slow_period=self.config['macd']['slow_period'],
            signal_period=self.config['macd']['signal_period'],
            hist_slope_window=self.config['macd']['hist_slope_window']
        )
        self.ban_history.clear()
        self.stats = {
            'total_updates': 0,
            'pre_alert_count': 0,
            'early_confirm_count': 0,
            'kgod_confirm_count': 0,
            'ban_count': 0
        }


# ==================== 工厂函数 ====================
def create_kgod_radar(symbol: str, config: Optional[Dict] = None) -> KGodRadar:
    """
    工厂函数：创建 K神雷达实例

    Args:
        symbol: 交易对符号
        config: 配置字典（可选）

    Returns:
        KGodRadar 实例
    """
    return KGodRadar(symbol=symbol, config=config)


# ==================== 批量回测接口 ====================
def backtest_kgod_strategy(symbol: str, prices: List[float],
                          order_flows: List[OrderFlowSnapshot],
                          timestamps: List[float],
                          config: Optional[Dict] = None) -> List[KGodSignal]:
    """
    批量回测接口（离线回测用）

    Args:
        symbol: 交易对符号
        prices: 价格序列
        order_flows: 订单流序列
        timestamps: 时间戳序列
        config: 配置字典（可选）

    Returns:
        所有触发的信号列表
    """
    radar = create_kgod_radar(symbol, config)
    signals = []

    for price, flow, ts in zip(prices, order_flows, timestamps):
        signal = radar.update(price, flow, ts)
        if signal:
            signals.append(signal)

    return signals
