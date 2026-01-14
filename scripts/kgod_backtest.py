"""
K神战法 Phase 3 - 历史数据回测系统
K-God Strategy Phase 3 - Historical Backtest System

基于已有的 KGOD 信号事件，评估信号准确率和策略有效性。

功能：
1. 从 storage/events/*.jsonl.gz 读取历史数据
2. 提取 K神信号和价格数据
3. 评估信号后续表现（Reversion Hit / Follow-through Hit）
4. 计算 MAE/MFE（最大不利/有利波动）
5. 生成详细 CSV 和摘要报告

作者: 三方共识（Claude + GPT + Gemini）
日期: 2026-01-10
版本: v3.0 Backtest
"""

import sys
import gzip
import json
import argparse
import csv
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from collections import defaultdict, deque

import numpy as np
import pandas as pd

# 添加项目根目录到 Python 路径
SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.kgod_radar import (
    KGodRadar, RollingBB, MACD, OrderFlowSnapshot,
    SignalStage, SignalSide
)
from config.kgod_settings import get_kgod_config


# ==================== 数据加载模块 ====================
class HistoricalDataLoader:
    """历史数据加载器"""

    def __init__(self, storage_dir: str = "storage/events"):
        """
        初始化数据加载器

        Args:
            storage_dir: 事件存储目录
        """
        self.storage_dir = Path(storage_dir)

    def load_events(self, symbol: str, start_date: Optional[str], end_date: Optional[str]) -> List[Dict]:
        """
        加载指定日期范围的事件数据

        Args:
            symbol: 交易对（如 "DOGE_USDT"）
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）

        Returns:
            事件列表（按时间戳排序）
        """
        # 查找所有相关文件（支持两种命名格式：DOGE_USDT 和 DOGE-USDT）
        pattern1 = f"{symbol}_*.jsonl.gz"
        symbol_dash = symbol.replace('_', '-')
        pattern2 = f"{symbol_dash}_*.jsonl.gz"

        all_files = sorted(set(
            list(self.storage_dir.glob(pattern1)) +
            list(self.storage_dir.glob(pattern2))
        ), key=lambda p: p.name)

        if not all_files:
            raise FileNotFoundError(f"未找到 {symbol} 的历史数据文件（尝试了 {pattern1} 和 {pattern2}）")

        # 过滤日期范围
        target_files = self._filter_files_by_date(all_files, symbol, start_date, end_date)

        if not target_files:
            raise ValueError(f"日期范围内无数据: {start_date} ~ {end_date}")

        # 加载所有文件
        events = []
        for file_path in target_files:
            print(f"加载: {file_path.name}")
            events.extend(self._load_single_file(file_path))

        # 按时间戳排序
        events.sort(key=lambda e: e['ts'])

        print(f"\n总共加载 {len(events)} 个事件")
        return events

    def _filter_files_by_date(self, files: List[Path], symbol: str,
                              start_date: Optional[str], end_date: Optional[str]) -> List[Path]:
        """根据日期范围过滤文件"""
        if not start_date and not end_date:
            return files

        # 解析日期
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None

        filtered = []
        for file_path in files:
            # 从文件名提取日期，支持两种格式：
            # - DOGE_USDT_2026-01-09.jsonl.gz
            # - DOGE-USDT_2026-01-12.jsonl.gz
            # 使用正则表达式提取日期
            import re
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path.name)
            if not date_match:
                continue

            date_str = date_match.group(1)

            try:
                file_dt = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                continue

            # 检查日期范围
            if start_dt and file_dt < start_dt:
                continue
            if end_dt and file_dt > end_dt:
                continue

            filtered.append(file_path)

        return filtered

    def _load_single_file(self, file_path: Path) -> List[Dict]:
        """加载单个 gzip 压缩的 JSONL 文件"""
        events = []

        # 尝试多种读取方式
        methods = [
            ('gzip', lambda p: gzip.open(p, 'rt', encoding='utf-8')),
            ('plain', lambda p: open(p, 'r', encoding='utf-8')),
        ]

        for method_name, open_fn in methods:
            try:
                with open_fn(file_path) as f:
                    line_count = 0
                    while True:
                        try:
                            line = f.readline()
                            if not line:
                                break

                            line = line.strip()
                            if not line:
                                continue

                            try:
                                event = json.loads(line)
                                events.append(event)
                                line_count += 1
                            except json.JSONDecodeError:
                                continue

                        except Exception:
                            # 文件可能在末尾损坏，但已读取的数据仍然有效
                            break

                # 成功读取，退出尝试
                if events:
                    break

            except Exception:
                continue

        return events


# ==================== K 线聚合模块 ====================
class KlineBuilder:
    """从 tick 数据聚合 K 线"""

    @staticmethod
    def extract_prices(events: List[Dict]) -> List[Tuple[float, float]]:
        """
        从事件中提取价格时间序列

        Args:
            events: 事件列表

        Returns:
            [(timestamp, price), ...]
        """
        prices = []

        for event in events:
            ts = event.get('ts')
            if not ts:
                continue

            # 提取价格
            price = None

            # 从 state 事件提取
            if event.get('type') == 'state' and 'data' in event:
                price = event['data'].get('price')

            # 从 trades 事件提取（使用最后一笔成交）
            elif event.get('type') == 'trades' and 'data' in event:
                trades = event['data']
                if trades:
                    price = trades[-1]['price']

            # 从 orderbook 事件提取（中间价）
            elif event.get('type') == 'orderbook':
                bids = event.get('bids', [])
                asks = event.get('asks', [])
                if bids and asks:
                    price = (bids[0][0] + asks[0][0]) / 2

            if price:
                prices.append((ts, price))

        return prices

    @staticmethod
    def build_klines(prices: List[Tuple[float, float]], timeframe: str = '1m') -> pd.DataFrame:
        """
        聚合 K 线数据

        Args:
            prices: [(timestamp, price), ...]
            timeframe: K 线周期（'1m', '5m'）

        Returns:
            DataFrame with columns: ts, open, high, low, close, volume
        """
        if not prices:
            raise ValueError("价格数据为空")

        # 转换为 DataFrame
        df = pd.DataFrame(prices, columns=['ts', 'price'])
        df['ts'] = pd.to_datetime(df['ts'], unit='s')
        df = df.set_index('ts')

        # 聚合
        resample_rule = '1min' if timeframe == '1m' else '5min'

        klines = df['price'].resample(resample_rule).agg(['first', 'max', 'min', 'last', 'count'])

        # 重命名列
        klines.columns = ['open', 'high', 'low', 'close', 'volume']

        # 去除空 K 线
        klines = klines.dropna()

        # 重置索引，保留时间戳
        klines = klines.reset_index()
        klines['ts_unix'] = klines['ts'].astype(np.int64) // 10**9

        return klines


# ==================== 信号提取模块 ====================
# ==================== 事件重放模块 ====================
class EventReplayer:
    """
    事件重放器 - 从历史数据重新生成 K神信号
    
    功能：
    1. 按时间顺序处理 trades 和 orderbook 事件
    2. 计算 CVD、OBI 等订单流指标
    3. 构建 OrderFlowSnapshot 并调用 KGodRadar
    4. 收集生成的信号
    """
    
    def __init__(self, symbol: str = "DOGE/USDT"):
        """
        初始化事件重放器
        
        Args:
            symbol: 交易对
        """
        self.symbol = symbol
        
        # 初始化 KGodRadar
        from core.kgod_radar import create_kgod_radar, OrderFlowSnapshot
        self.radar = create_kgod_radar(symbol)
        self.OrderFlowSnapshot = OrderFlowSnapshot
        
        # 状态变量
        self.cvd_total = 0.0
        self.cvd_history = []
        self.price_history = []
        self.last_price = 0.0
        self.last_obi = 0.0
        
        # 信号收集
        self.signals = []
        
    def replay_events(self, events: List[Dict], 
                      min_confidence: float = 0.0,
                      progress_interval: int = 10000) -> List[Dict]:
        """
        重放事件并生成信号
        
        Args:
            events: 事件列表（按时间排序）
            min_confidence: 最低置信度过滤
            progress_interval: 进度报告间隔
            
        Returns:
            生成的信号列表
        """
        self.signals = []
        total_events = len(events)
        trades_count = 0
        orderbook_count = 0
        
        print(f"开始重放 {total_events} 个事件...")
        
        for i, event in enumerate(events):
            # 进度报告
            if (i + 1) % progress_interval == 0:
                print(f"  进度: {i+1}/{total_events} ({100*(i+1)/total_events:.1f}%)")
            
            event_type = event.get('type')
            ts = event.get('ts', 0)
            
            if event_type == 'trades':
                trades_count += 1
                self._process_trades(event, ts)
                
            elif event_type == 'orderbook':
                orderbook_count += 1
                self._process_orderbook(event, ts)
                
                # 每次 orderbook 更新后尝试生成信号
                if self.last_price > 0:
                    signal = self._generate_signal(ts)
                    if signal and signal.get('confidence', 0) >= min_confidence:
                        self.signals.append(signal)
        
        print(f"\n重放完成: trades={trades_count}, orderbook={orderbook_count}")
        print(f"生成 {len(self.signals)} 个信号（置信度>={min_confidence}）")
        
        return self.signals
    
    def _process_trades(self, event: Dict, ts: float):
        """处理交易事件，更新 CVD"""
        trades = event.get('data', [])
        
        for trade in trades:
            price = trade.get('price', 0)
            qty = trade.get('quantity', 0)
            is_buyer_maker = trade.get('is_buyer_maker', False)
            
            # 更新价格
            if price > 0:
                self.last_price = price
                self.price_history.append(price)
                if len(self.price_history) > 100:
                    self.price_history.pop(0)
            
            # 更新 CVD（买入为正，卖出为负）
            if is_buyer_maker:
                # 买方是 maker，说明卖方主动卖出
                self.cvd_total -= qty * price
            else:
                # 卖方是 maker，说明买方主动买入
                self.cvd_total += qty * price
        
        # 更新 CVD 历史
        self.cvd_history.append(self.cvd_total)
        if len(self.cvd_history) > 100:
            self.cvd_history.pop(0)
    
    def _process_orderbook(self, event: Dict, ts: float):
        """处理订单簿事件，计算 OBI"""
        bids = event.get('bids', [])
        asks = event.get('asks', [])
        
        # 计算买卖量
        bid_volume = sum(b[1] for b in bids[:5]) if bids else 0
        ask_volume = sum(a[1] for a in asks[:5]) if asks else 0
        
        # 计算 OBI（Order Book Imbalance）
        total_volume = bid_volume + ask_volume
        if total_volume > 0:
            self.last_obi = (bid_volume - ask_volume) / total_volume  # 范围 [-1, 1]
        else:
            self.last_obi = 0.0
    
    def _generate_signal(self, ts: float) -> Optional[Dict]:
        """生成 K神信号"""
        if self.last_price <= 0:
            return None
        
        # 计算 CVD Delta（最近5个点）
        cvd_delta_5s = 0.0
        if len(self.cvd_history) >= 5:
            cvd_delta_5s = self.cvd_history[-1] - self.cvd_history[-5]
        
        # 计算 Delta 斜率
        delta_slope_10s = 0.0
        if len(self.cvd_history) >= 10:
            recent_cvd = self.cvd_history[-10:]
            n = len(recent_cvd)
            x_mean = (n - 1) / 2
            y_mean = sum(recent_cvd) / n
            numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(recent_cvd))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            if denominator > 0:
                delta_slope_10s = numerator / denominator
        
        # 构建 OrderFlowSnapshot（基于可用数据估算参数）
        imbalance_1s = 0.5 + self.last_obi / 2  # OBI [-1,1] -> imbalance [0,1]
        
        # 估算吸收率（基于失衡）
        absorption_ask = 0.5 + self.last_obi * 0.3 if self.last_obi > 0 else 0.5
        absorption_bid = 0.5 - self.last_obi * 0.3 if self.last_obi < 0 else 0.5
        
        # 估算扫单得分（基于 CVD 变化强度）
        sweep_score = 0.0
        if len(self.cvd_history) >= 5:
            cvd_change = abs(cvd_delta_5s)
            # 标准化：假设 10000 USDT 的 CVD 变化对应 5 分
            sweep_score = min(cvd_change / 2000, 10.0)
        
        # 估算冰山强度（基于 Delta 斜率和失衡的组合）
        iceberg_intensity = 0.0
        if abs(delta_slope_10s) > 100 and abs(self.last_obi) > 0.3:
            # 强 Delta 斜率 + 强失衡 = 可能存在冰山
            iceberg_intensity = min(abs(delta_slope_10s) / 500, 5.0)
        
        order_flow = self.OrderFlowSnapshot(
            delta_5s=cvd_delta_5s,
            delta_slope_10s=delta_slope_10s,
            imbalance_1s=imbalance_1s,
            absorption_ask=absorption_ask,
            absorption_bid=absorption_bid,
            sweep_score_5s=sweep_score,
            iceberg_intensity=iceberg_intensity,
            refill_count=int(iceberg_intensity),  # 估算补单次数
            acceptance_above_upper_s=0.0,
            acceptance_below_lower_s=0.0
        )
        
        # 调用雷达
        try:
            signal = self.radar.update(self.last_price, order_flow, ts)
            if signal:
                return {
                    'ts': signal.ts,
                    'stage': signal.stage.value,
                    'side': signal.side.value,
                    'confidence': signal.confidence,
                    'reasons': signal.reasons,
                    'debug': signal.debug,
                    'symbol': signal.symbol
                }
        except Exception as e:
            pass
        
        return None


class SignalExtractor:
    """从事件中提取 K神信号"""

    @staticmethod
    def load_signals_from_file(signals_dir: str = "storage/signals",
                                start_date: Optional[str] = None,
                                end_date: Optional[str] = None,
                                min_confidence: float = 0.0) -> List[Dict]:
        """
        从信号文件加载 K神信号

        Args:
            signals_dir: 信号存储目录
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            min_confidence: 最低置信度过滤

        Returns:
            K神信号列表
        """
        import re
        from datetime import datetime

        signals_path = Path(signals_dir)
        if not signals_path.exists():
            print(f"信号目录不存在: {signals_dir}")
            return []

        # 加载所有 .jsonl 文件
        signal_files = sorted(signals_path.glob("*.jsonl"))

        # 日期过滤
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else None
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else None

        filtered_files = []
        for f in signal_files:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
            if date_match:
                file_dt = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                if start_dt and file_dt < start_dt:
                    continue
                if end_dt and file_dt > end_dt:
                    continue
            filtered_files.append(f)

        signals = []
        for signal_file in filtered_files:
            print(f"加载信号文件: {signal_file.name}")
            try:
                with open(signal_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            event = json.loads(line.strip())

                            # 只处理 K神信号（k_god_buy 或 k_god_sell）
                            signal_type = event.get('signal_type', '')
                            if not signal_type.startswith('k_god'):
                                continue

                            # 提取数据
                            data = event.get('data', {})
                            confidence = event.get('confidence', 0.0)

                            if confidence < min_confidence:
                                continue

                            # 从 timestamp 转换为 ts
                            ts_str = event.get('timestamp', '')
                            if ts_str:
                                from datetime import datetime
                                try:
                                    dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                    ts = dt.timestamp()
                                except:
                                    ts = 0
                            else:
                                ts = 0

                            # 标准化信号
                            signal = {
                                'ts': ts,
                                'stage': data.get('stage', 'UNKNOWN'),
                                'side': 'BUY' if signal_type == 'k_god_buy' else 'SELL',
                                'confidence': confidence,
                                'reasons': [],
                                'debug': data,
                                'symbol': event.get('symbol', 'UNKNOWN')
                            }
                            signals.append(signal)

                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"加载失败 {signal_file.name}: {e}")

        print(f"从信号文件加载到 {len(signals)} 个 K神信号")
        return signals

    @staticmethod
    def extract_kgod_signals(events: List[Dict], min_confidence: float = 0.0) -> List[Dict]:
        """
        提取 K神信号事件

        Args:
            events: 事件列表
            min_confidence: 最低置信度过滤

        Returns:
            KGOD 信号列表
        """
        signals = []

        for event in events:
            # 检查是否是 KGOD 信号事件
            if event.get('type') not in ['kgod_signal', 'signal']:
                continue

            # 提取信号数据
            signal_data = event.get('data', event)

            # 检查是否有 stage 字段
            stage = signal_data.get('stage')
            if not stage:
                continue

            # 置信度过滤
            confidence = signal_data.get('confidence', 0.0)
            if confidence < min_confidence:
                continue

            # 标准化信号字段
            signal = {
                'ts': event.get('ts') or signal_data.get('ts'),
                'stage': stage,
                'side': signal_data.get('side', 'UNKNOWN'),
                'confidence': confidence,
                'reasons': signal_data.get('reasons', []),
                'debug': signal_data.get('debug', {}),
                'symbol': event.get('symbol', signal_data.get('symbol', 'UNKNOWN'))
            }

            signals.append(signal)

        print(f"提取到 {len(signals)} 个 KGOD 信号")
        return signals


# ==================== 双标签评估模块 ====================
class SignalEvaluator:
    """信号后续表现评估器"""

    def __init__(self, config: Dict):
        """
        初始化评估器

        Args:
            config: 回测配置
        """
        self.config = config
        self.lookforward_bars = config['lookforward_bars']
        self.regression_threshold = config['regression_threshold']
        self.followthrough_k_sigma = config.get('followthrough_k_sigma', 2.0)

    def evaluate_signal(self, signal: Dict, klines: pd.DataFrame,
                       bb_values: Optional[Dict] = None) -> Dict:
        """
        评估单个信号的后续表现

        Args:
            signal: KGOD 信号
            klines: K 线数据
            bb_values: 布林带数据（如果提供）

        Returns:
            评估结果字典
        """
        # 查找信号对应的 K 线位置
        signal_ts = signal['ts']
        signal_idx = self._find_signal_index(signal_ts, klines)

        if signal_idx is None:
            return {
                'error': 'signal_not_found',
                'signal': signal
            }

        # 提取未来价格窗口
        future_window_end = min(signal_idx + self.lookforward_bars, len(klines))
        future_klines = klines.iloc[signal_idx:future_window_end]

        if len(future_klines) < 2:
            return {
                'error': 'insufficient_future_data',
                'signal': signal
            }

        future_prices = future_klines['close'].values

        # 获取信号时的布林带值
        if bb_values is None:
            bb_values = self._estimate_bb_values(signal, klines, signal_idx)

        bb_mid = bb_values.get('mid', 0.0)
        bb_sigma = bb_values.get('sigma', 0.0)
        bb_upper = bb_values.get('upper', 0.0)
        bb_lower = bb_values.get('lower', 0.0)

        # 检查 Reversion Hit
        reversion_hit, rev_bar, rev_price = self._check_reversion_hit(
            signal, future_prices, bb_mid, bb_sigma
        )

        # 检查 Follow-through Hit
        followthrough_hit, ft_bar, ft_price = self._check_followthrough_hit(
            signal, future_prices, bb_mid, bb_sigma, bb_upper, bb_lower
        )

        # 计算 MAE/MFE
        mae_mfe = self._calculate_mae_mfe(signal, future_prices, bb_sigma)

        return {
            'signal': signal,
            'signal_idx': signal_idx,
            'bb_mid': bb_mid,
            'bb_sigma': bb_sigma,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'reversion_hit': reversion_hit,
            'reversion_bar': rev_bar,
            'reversion_price': rev_price,
            'followthrough_hit': followthrough_hit,
            'followthrough_bar': ft_bar,
            'followthrough_price': ft_price,
            **mae_mfe
        }

    def _find_signal_index(self, signal_ts: float, klines: pd.DataFrame) -> Optional[int]:
        """查找信号对应的 K 线索引"""
        # 二分查找最接近的 K 线
        ts_unix = klines['ts_unix'].values
        idx = np.searchsorted(ts_unix, signal_ts)

        if idx >= len(klines):
            return len(klines) - 1

        return idx

    def _estimate_bb_values(self, signal: Dict, klines: pd.DataFrame, signal_idx: int) -> Dict:
        """从信号 debug 信息或历史数据估算布林带值"""
        # 1. 尝试从 debug 提取
        debug = signal.get('debug', {})
        bb_debug = debug.get('bb', {})

        if bb_debug and 'mid' in bb_debug and 'upper' in bb_debug and 'lower' in bb_debug:
            mid = bb_debug['mid']
            upper = bb_debug['upper']
            lower = bb_debug['lower']
            sigma = (upper - lower) / (2 * 2.0)  # 假设 2σ
            return {
                'mid': mid,
                'upper': upper,
                'lower': lower,
                'sigma': sigma
            }

        # 2. 如果没有 debug，使用历史数据重新计算
        warmup_bars = 100
        start_idx = max(0, signal_idx - warmup_bars)
        warmup_klines = klines.iloc[start_idx:signal_idx + 1]

        if len(warmup_klines) < 20:
            # 数据不足，返回默认值
            return {
                'mid': klines.iloc[signal_idx]['close'],
                'upper': 0.0,
                'lower': 0.0,
                'sigma': 0.0
            }

        # 重新计算布林带
        bb = RollingBB(period=20, num_std=2.0)
        for price in warmup_klines['close'].values:
            bb.update(price)

        sigma = (bb.upper - bb.lower) / (2 * 2.0) if bb.upper > bb.lower else 0.0

        return {
            'mid': bb.mid,
            'upper': bb.upper,
            'lower': bb.lower,
            'sigma': sigma
        }

    def _check_reversion_hit(self, signal: Dict, future_prices: np.ndarray,
                            bb_mid: float, bb_sigma: float) -> Tuple[bool, int, float]:
        """
        检查价格是否回归到中轨

        判定条件：|price - mid_band| <= regression_threshold * sigma

        Returns:
            (hit: bool, hit_bar: int, hit_price: float)
        """
        if bb_sigma <= 0:
            return False, -1, 0.0

        threshold = self.regression_threshold * bb_sigma

        for i, price in enumerate(future_prices):
            distance = abs(price - bb_mid)
            if distance <= threshold:
                return True, i, price

        return False, -1, 0.0

    def _check_followthrough_hit(self, signal: Dict, future_prices: np.ndarray,
                                bb_mid: float, bb_sigma: float,
                                bb_upper: float, bb_lower: float) -> Tuple[bool, int, float]:
        """
        检查价格是否延伸到 k * sigma（走轨）

        Args:
            k_sigma: σ 倍数（默认 2.0）

        Returns:
            (hit: bool, hit_bar: int, hit_price: float)
        """
        if bb_sigma <= 0:
            return False, -1, 0.0

        side = signal.get('side', 'BUY')

        # BUY 信号：检查是否突破上轨
        if side == 'BUY':
            target = bb_upper
            for i, price in enumerate(future_prices):
                if price >= target:
                    return True, i, price

        # SELL 信号：检查是否突破下轨
        else:
            target = bb_lower
            for i, price in enumerate(future_prices):
                if price <= target:
                    return True, i, price

        return False, -1, 0.0

    def _calculate_mae_mfe(self, signal: Dict, future_prices: np.ndarray,
                          bb_sigma: float) -> Dict:
        """
        计算 MAE (Maximum Adverse Excursion) 和 MFE (Maximum Favorable Excursion)

        Args:
            signal: 信号数据（含 side: BUY/SELL）
            future_prices: 未来价格序列
            bb_sigma: 布林带标准差（用于归一化）

        Returns:
            {
                'mae': float,  # 最大反向波动（σ 倍数）
                'mae_bar': int,  # MAE 发生位置
                'mfe': float,  # 最大正向波动（σ 倍数）
                'mfe_bar': int,  # MFE 发生位置
            }
        """
        if len(future_prices) < 2:
            return {
                'mae': 0.0,
                'mae_bar': -1,
                'mfe': 0.0,
                'mfe_bar': -1
            }

        entry_price = future_prices[0]
        side = signal.get('side', 'BUY')

        # BUY 信号：MAE = 最大跌幅，MFE = 最大涨幅
        if side == 'BUY':
            # 最大不利波动（跌幅）
            min_price = np.min(future_prices)
            mae_abs = entry_price - min_price
            mae_bar = int(np.argmin(future_prices))

            # 最大有利波动（涨幅）
            max_price = np.max(future_prices)
            mfe_abs = max_price - entry_price
            mfe_bar = int(np.argmax(future_prices))

        # SELL 信号：MAE = 最大涨幅，MFE = 最大跌幅
        else:
            # 最大不利波动（涨幅）
            max_price = np.max(future_prices)
            mae_abs = max_price - entry_price
            mae_bar = int(np.argmax(future_prices))

            # 最大有利波动（跌幅）
            min_price = np.min(future_prices)
            mfe_abs = entry_price - min_price
            mfe_bar = int(np.argmin(future_prices))

        # 归一化为 σ 倍数
        if bb_sigma > 0:
            mae = mae_abs / bb_sigma
            mfe = mfe_abs / bb_sigma
        else:
            mae = 0.0
            mfe = 0.0

        return {
            'mae': mae,
            'mae_bar': mae_bar,
            'mfe': mfe,
            'mfe_bar': mfe_bar
        }


# ==================== 报告生成模块 ====================
class ReportGenerator:
    """回测报告生成器"""

    def __init__(self, results: List[Dict], config: Dict):
        """
        初始化报告生成器

        Args:
            results: 评估结果列表
            config: 回测配置
        """
        self.results = results
        self.config = config

    def save_csv(self, output_path: str):
        """保存详细 CSV 记录"""
        if not self.results:
            print("无结果可保存")
            return

        # 过滤错误记录
        valid_results = [r for r in self.results if 'error' not in r]

        if not valid_results:
            print("无有效结果可保存")
            return

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)

            # 表头
            writer.writerow([
                'ts', 'signal_type', 'side', 'confidence', 'price',
                'bb_mid', 'bb_upper', 'bb_lower', 'bb_sigma',
                'reversion_hit', 'reversion_bar', 'reversion_price',
                'followthrough_hit', 'followthrough_bar', 'followthrough_price',
                'mae', 'mae_bar', 'mfe', 'mfe_bar',
                'reasons'
            ])

            # 数据行
            for result in valid_results:
                signal = result['signal']
                writer.writerow([
                    datetime.fromtimestamp(signal['ts']).strftime('%Y-%m-%d %H:%M:%S'),
                    signal['stage'],
                    signal['side'],
                    f"{signal['confidence']:.1f}",
                    f"{result.get('bb_mid', 0.0):.5f}",
                    f"{result.get('bb_mid', 0.0):.5f}",
                    f"{result.get('bb_upper', 0.0):.5f}",
                    f"{result.get('bb_lower', 0.0):.5f}",
                    f"{result.get('bb_sigma', 0.0):.5f}",
                    result.get('reversion_hit', False),
                    result.get('reversion_bar', -1),
                    f"{result.get('reversion_price', 0.0):.5f}",
                    result.get('followthrough_hit', False),
                    result.get('followthrough_bar', -1),
                    f"{result.get('followthrough_price', 0.0):.5f}",
                    f"{result.get('mae', 0.0):.3f}",
                    result.get('mae_bar', -1),
                    f"{result.get('mfe', 0.0):.3f}",
                    result.get('mfe_bar', -1),
                    '; '.join(signal.get('reasons', []))
                ])

        print(f"\nCSV 保存成功: {output_path}")

    def generate_summary(self) -> str:
        """生成摘要统计报告"""
        # 过滤错误记录
        valid_results = [r for r in self.results if 'error' not in r]

        if not valid_results:
            return "无有效结果可统计"

        # 提取信号
        signals = [r['signal'] for r in valid_results]

        # 统计信号数量
        stage_counts = defaultdict(int)
        for signal in signals:
            stage_counts[signal['stage']] += 1

        # 按 stage 分类统计准确率
        stage_stats = self._calculate_stage_stats(valid_results)

        # 置信度分层统计
        confidence_stats = self._calculate_confidence_stats(valid_results)

        # BAN 有效性评估
        ban_stats = self._calculate_ban_stats(valid_results)

        # MAE/MFE 统计
        mae_mfe_stats = self._calculate_mae_mfe_stats(valid_results)

        # 生成报告
        report = self._format_summary_report(
            stage_counts, stage_stats, confidence_stats,
            ban_stats, mae_mfe_stats
        )

        return report

    def _calculate_stage_stats(self, results: List[Dict]) -> Dict:
        """按 stage 分类统计准确率"""
        stats = defaultdict(lambda: {'total': 0, 'reversion_hit': 0, 'followthrough_hit': 0})

        for result in results:
            stage = result['signal']['stage']
            stats[stage]['total'] += 1

            if result.get('reversion_hit', False):
                stats[stage]['reversion_hit'] += 1

            if result.get('followthrough_hit', False):
                stats[stage]['followthrough_hit'] += 1

        # 计算准确率
        for stage, data in stats.items():
            total = data['total']
            data['reversion_rate'] = data['reversion_hit'] / total if total > 0 else 0.0
            data['followthrough_rate'] = data['followthrough_hit'] / total if total > 0 else 0.0

        return dict(stats)

    def _calculate_confidence_stats(self, results: List[Dict]) -> Dict:
        """置信度分层统计"""
        buckets = {
            '90+': [],
            '80-90': [],
            '70-80': [],
            '60-70': [],
            '<60': []
        }

        for result in results:
            confidence = result['signal'].get('confidence', 0.0)

            if confidence >= 90:
                bucket = '90+'
            elif confidence >= 80:
                bucket = '80-90'
            elif confidence >= 70:
                bucket = '70-80'
            elif confidence >= 60:
                bucket = '60-70'
            else:
                bucket = '<60'

            buckets[bucket].append(result)

        # 统计各分桶准确率
        stats = {}
        for bucket, bucket_results in buckets.items():
            if not bucket_results:
                continue

            total = len(bucket_results)
            reversion_hit = sum(1 for r in bucket_results if r.get('reversion_hit', False))
            reversion_rate = reversion_hit / total if total > 0 else 0.0

            stats[bucket] = {
                'total': total,
                'reversion_hit': reversion_hit,
                'reversion_rate': reversion_rate,
                'sufficient_sample': total >= 20
            }

        return stats

    def _calculate_ban_stats(self, results: List[Dict]) -> Dict:
        """BAN 有效性评估"""
        ban_results = [r for r in results if r['signal']['stage'] == 'BAN']

        if not ban_results:
            return {'total': 0}

        total = len(ban_results)
        effective = sum(1 for r in ban_results if r.get('followthrough_hit', False))
        false_positive = sum(1 for r in ban_results if r.get('reversion_hit', False))

        effective_rate = effective / total if total > 0 else 0.0
        false_positive_rate = false_positive / total if total > 0 else 0.0

        # 按原因分类
        by_reason = defaultdict(lambda: {'total': 0, 'effective': 0})
        for result in ban_results:
            reasons = result['signal'].get('reasons', [])
            for reason in reasons:
                # 简化原因（提取关键词）
                if '上轨上方' in reason or '下轨下方' in reason:
                    key = 'acceptance'
                elif '带宽' in reason:
                    key = 'bb_squeeze'
                elif 'MACD' in reason:
                    key = 'macd_divergence'
                elif 'Delta' in reason or '失衡' in reason:
                    key = 'flow_reversal'
                elif '冰山' in reason:
                    key = 'iceberg_loss'
                else:
                    key = 'other'

                by_reason[key]['total'] += 1
                if result.get('followthrough_hit', False):
                    by_reason[key]['effective'] += 1

        # 计算各原因有效率
        for key, data in by_reason.items():
            total_reason = data['total']
            data['effective_rate'] = data['effective'] / total_reason if total_reason > 0 else 0.0

        return {
            'total': total,
            'effective': effective,
            'effective_rate': effective_rate,
            'false_positive': false_positive,
            'false_positive_rate': false_positive_rate,
            'by_reason': dict(by_reason)
        }

    def _calculate_mae_mfe_stats(self, results: List[Dict]) -> Dict:
        """MAE/MFE 统计"""
        mae_values = [r.get('mae', 0.0) for r in results if r.get('mae', 0.0) > 0]
        mfe_values = [r.get('mfe', 0.0) for r in results if r.get('mfe', 0.0) > 0]

        if not mae_values or not mfe_values:
            return {
                'mae_mean': 0.0,
                'mfe_mean': 0.0,
                'risk_reward_ratio': 0.0
            }

        mae_mean = np.mean(mae_values)
        mfe_mean = np.mean(mfe_values)
        risk_reward_ratio = mfe_mean / mae_mean if mae_mean > 0 else 0.0

        return {
            'mae_mean': mae_mean,
            'mfe_mean': mfe_mean,
            'risk_reward_ratio': risk_reward_ratio
        }

    def _format_summary_report(self, stage_counts: Dict, stage_stats: Dict,
                               confidence_stats: Dict, ban_stats: Dict,
                               mae_mfe_stats: Dict) -> str:
        """格式化摘要报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("K神战法 Phase 3 回测报告")
        lines.append("=" * 60)

        # 时间范围
        if self.results:
            first_signal = self.results[0]['signal']
            last_signal = self.results[-1]['signal']
            start_time = datetime.fromtimestamp(first_signal['ts']).strftime('%Y-%m-%d %H:%M:%S')
            end_time = datetime.fromtimestamp(last_signal['ts']).strftime('%Y-%m-%d %H:%M:%S')
            lines.append(f"时间范围: {start_time} ~ {end_time}")

        lines.append(f"交易对: {self.config.get('symbol', 'UNKNOWN')}")
        lines.append(f"总信号数: {len(self.results)}")
        lines.append("")

        # 信号统计
        lines.append("--- 信号统计 ---")
        for stage, count in sorted(stage_counts.items()):
            lines.append(f"{stage}: {count} 个")
        lines.append("")

        # 准确率（Reversion Hit）
        lines.append("--- 准确率（Reversion Hit）---")
        for stage, data in sorted(stage_stats.items()):
            total = data['total']
            hit = data['reversion_hit']
            rate = data['reversion_rate']
            suffix = " [样本充足]" if total >= 20 else " [样本不足]" if total > 0 else ""
            lines.append(f"{stage}: {rate*100:.1f}% ({hit}/{total}){suffix}")
        lines.append("")

        # 置信度分层
        lines.append("--- 置信度分层 ---")
        for bucket in ['90+', '80-90', '70-80', '60-70', '<60']:
            if bucket in confidence_stats:
                data = confidence_stats[bucket]
                total = data['total']
                hit = data['reversion_hit']
                rate = data['reversion_rate']
                suffix = "" if data['sufficient_sample'] else " [样本不足]"
                lines.append(f"{bucket}: {rate*100:.1f}% ({hit}/{total}){suffix}")
        lines.append("")

        # BAN 有效性
        if ban_stats['total'] > 0:
            lines.append("--- BAN 有效性 ---")
            total = ban_stats['total']
            effective_rate = ban_stats['effective_rate']
            fp_rate = ban_stats['false_positive_rate']
            suffix = "" if total >= 20 else " [样本不足]"
            lines.append(f"BAN 有效率: {effective_rate*100:.1f}% ({ban_stats['effective']}/{total}){suffix}")
            lines.append(f"BAN 误杀率: {fp_rate*100:.1f}% ({ban_stats['false_positive']}/{total})")
            lines.append("")

            lines.append("按原因分类:")
            for key, data in sorted(ban_stats['by_reason'].items()):
                total_reason = data['total']
                effective_reason = data['effective']
                rate_reason = data['effective_rate']
                suffix_reason = "" if total_reason >= 5 else " [样本不足]"
                lines.append(f"  - {key}: {rate_reason*100:.1f}% ({effective_reason}/{total_reason}){suffix_reason}")
            lines.append("")

        # MAE/MFE 统计
        lines.append("--- MAE/MFE 统计 ---")
        lines.append(f"平均 MAE: {mae_mfe_stats['mae_mean']:.2f}σ (建议止损位)")
        lines.append(f"平均 MFE: {mae_mfe_stats['mfe_mean']:.2f}σ")
        lines.append(f"风险回报比: {mae_mfe_stats['risk_reward_ratio']:.2f}x")
        lines.append("")

        lines.append("=" * 60)

        return '\n'.join(lines)


# ==================== 回测引擎主类 ====================
class KGodBacktest:
    """K神战法回测引擎"""

    def __init__(self, config: Dict):
        """
        初始化回测引擎

        Args:
            config: 回测配置
        """
        self.config = config
        self.symbol = config['symbol']
        self.mode = config['mode']
        self.timeframe = config['timeframe']

        # 数据容器
        self.events = []
        self.klines = None
        self.kgod_signals = []
        self.results = []

        # 模块初始化
        self.loader = HistoricalDataLoader()
        self.kline_builder = KlineBuilder()
        self.signal_extractor = SignalExtractor()
        self.evaluator = SignalEvaluator(config)

    def load_data(self, start_date: Optional[str], end_date: Optional[str]):
        """加载历史数据"""
        print("\n=== 加载历史数据 ===")
        self.events = self.loader.load_events(self.symbol, start_date, end_date)

    def build_klines(self):
        """聚合 K 线数据"""
        print("\n=== 聚合 K 线数据 ===")
        prices = self.kline_builder.extract_prices(self.events)
        print(f"提取到 {len(prices)} 个价格点")

        self.klines = self.kline_builder.build_klines(prices, self.timeframe)
        print(f"聚合得到 {len(self.klines)} 根 K 线")

    def run_signal_outcome_eval(self, start_date: Optional[str] = None, end_date: Optional[str] = None):
        """Mode 2: 信号结果评估"""
        print("\n=== 运行信号结果评估 ===")

        # 1. 提取 KGOD 信号（先从事件文件，再从信号文件）
        min_confidence = self.config.get('min_confidence', 0.0)
        self.kgod_signals = self.signal_extractor.extract_kgod_signals(
            self.events, min_confidence
        )

        # 如果事件文件中没有信号，尝试从信号文件加载
        if not self.kgod_signals:
            print("事件文件中无 KGOD 信号，尝试从信号文件加载...")
            self.kgod_signals = self.signal_extractor.load_signals_from_file(
                signals_dir="storage/signals",
                start_date=start_date,
                end_date=end_date,
                min_confidence=min_confidence
            )

        if not self.kgod_signals:
            print("未找到符合条件的 KGOD 信号")
            return

        # 2. 评估每个信号
        print(f"\n开始评估 {len(self.kgod_signals)} 个信号...")
        self.results = []

        for i, signal in enumerate(self.kgod_signals):
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(self.kgod_signals)}")

            result = self.evaluator.evaluate_signal(signal, self.klines)
            self.results.append(result)

        print(f"评估完成: {len(self.results)} 个结果")

    def run_full_replay(self):
        """Mode 1: 完整回放 - 从历史数据重新生成 K神信号"""
        print("\n=== 运行完整回放模式 ===")

        # 1. 初始化事件重放器
        replayer = EventReplayer(self.symbol)
        min_confidence = self.config.get('min_confidence', 0.0)

        # 2. 重放事件生成信号
        self.kgod_signals = replayer.replay_events(
            self.events,
            min_confidence=min_confidence,
            progress_interval=50000
        )

        if not self.kgod_signals:
            print("未生成任何符合条件的 KGOD 信号")
            return

        # 3. 评估信号
        print(f"\n开始评估 {len(self.kgod_signals)} 个信号...")
        self.results = []

        for i, signal in enumerate(self.kgod_signals):
            if (i + 1) % 50 == 0:
                print(f"  进度: {i+1}/{len(self.kgod_signals)}")

            result = self.evaluator.evaluate_signal(signal, self.klines)
            self.results.append(result)

        print(f"评估完成: {len(self.results)} 个结果")

    def generate_reports(self):
        """生成 CSV 和摘要报告"""
        print("\n=== 生成报告 ===")

        generator = ReportGenerator(self.results, self.config)

        # 保存 CSV
        output_csv = self.config.get('output_csv', 'backtest_results.csv')
        generator.save_csv(output_csv)

        # 生成摘要
        summary = generator.generate_summary()

        # 保存摘要
        output_report = self.config.get('output_report', 'backtest_report.txt')
        with open(output_report, 'w', encoding='utf-8') as f:
            f.write(summary)

        print(f"报告保存成功: {output_report}")

        # 打印摘要
        print("\n" + summary)


# ==================== CLI 主函数 ====================
def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='K神战法 Phase 3 历史数据回测',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 评估最近 3 天的信号
  python scripts/kgod_backtest.py --start_date 2026-01-07 --end_date 2026-01-09

  # 只评估高置信度信号
  python scripts/kgod_backtest.py --min_confidence 70.0

  # 自定义观察窗口
  python scripts/kgod_backtest.py --lookforward_bars 120
        """
    )

    # 运行模式
    parser.add_argument(
        '--mode',
        choices=['full_replay', 'signal_outcome_eval'],
        default='signal_outcome_eval',
        help='运行模式（推荐先用 signal_outcome_eval）'
    )

    # 交易对
    parser.add_argument(
        '--symbol',
        default='DOGE_USDT',
        help='交易对'
    )

    # 日期范围
    parser.add_argument(
        '--start_date',
        help='开始日期（YYYY-MM-DD），默认最早数据'
    )

    parser.add_argument(
        '--end_date',
        help='结束日期（YYYY-MM-DD），默认最新数据'
    )

    # K 线周期
    parser.add_argument(
        '--timeframe',
        choices=['1m', '5m'],
        default='1m',
        help='K 线周期'
    )

    # 观察窗口
    parser.add_argument(
        '--lookforward_bars',
        type=int,
        default=60,
        help='观察窗口（K 线根数）'
    )

    # 回归阈值
    parser.add_argument(
        '--regression_threshold',
        type=float,
        default=0.5,
        help='回归判定阈值（σ 倍数）'
    )

    # 最低置信度
    parser.add_argument(
        '--min_confidence',
        type=float,
        default=0.0,
        help='最低置信度过滤'
    )

    # 主指标
    parser.add_argument(
        '--primary_objective',
        choices=['reversion', 'follow_through'],
        default='reversion',
        help='主指标选择'
    )

    # 输出文件
    parser.add_argument(
        '--output_csv',
        default='backtest_results.csv',
        help='CSV 输出文件路径'
    )

    parser.add_argument(
        '--output_report',
        default='backtest_report.txt',
        help='报告输出文件路径'
    )

    args = parser.parse_args()

    # 构建配置
    config = {
        'mode': args.mode,
        'symbol': args.symbol,
        'timeframe': args.timeframe,
        'lookforward_bars': args.lookforward_bars,
        'regression_threshold': args.regression_threshold,
        'min_confidence': args.min_confidence,
        'primary_objective': args.primary_objective,
        'output_csv': args.output_csv,
        'output_report': args.output_report,
        'followthrough_k_sigma': 2.0,
    }

    # 创建回测引擎
    backtest = KGodBacktest(config)

    try:
        # 加载数据
        backtest.load_data(args.start_date, args.end_date)

        # 聚合 K 线
        backtest.build_klines()

        # 运行回测
        if args.mode == 'signal_outcome_eval':
            backtest.run_signal_outcome_eval(args.start_date, args.end_date)
        else:
            backtest.run_full_replay()

        # 生成报告
        backtest.generate_reports()

        print(f"\n回测完成!")
        print(f"CSV 输出: {args.output_csv}")
        print(f"报告输出: {args.output_report}")

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
