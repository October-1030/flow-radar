#!/usr/bin/env python3
"""
Flow Radar - Event Logger & Replayer
流动性雷达 - 事件记录与回放

用于记录市场数据和回测验证
"""

import json
import gzip
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Generator, Optional
from dataclasses import dataclass, asdict


@dataclass
class BacktestResult:
    """回测结果"""
    total_signals: int
    correct_signals: int
    wrong_signals: int
    hit_rate: float
    avg_profit_correct: float
    avg_loss_wrong: float
    details: List[Dict]


class EventLogger:
    """
    事件记录器

    以 JSONL 格式记录 orderbook、trades、signals
    支持 gzip 压缩
    """

    def __init__(self, symbol: str, output_dir: str = "./storage/events"):
        self.symbol = symbol
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = None
        self.current_date = None
        self.event_count = 0

    def _get_file(self) -> Any:
        """获取当前日期的文件句柄"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.current_date:
            if self.current_file:
                self.current_file.close()
            filename = self.output_dir / f"{self.symbol.replace('/', '_')}_{today}.jsonl.gz"
            self.current_file = gzip.open(filename, 'at', encoding='utf-8')
            self.current_date = today
        return self.current_file

    def log_orderbook(self, orderbook: Dict, timestamp: float = None):
        """记录订单簿快照"""
        if timestamp is None:
            timestamp = time.time()

        event = {
            "type": "orderbook",
            "ts": timestamp,
            "symbol": self.symbol,
            "bids": orderbook.get("bids", [])[:20],
            "asks": orderbook.get("asks", [])[:20]
        }
        self._write(event)

    def log_trades(self, trades: List[Dict], timestamp: float = None):
        """记录成交数据"""
        if timestamp is None:
            timestamp = time.time()

        event = {
            "type": "trades",
            "ts": timestamp,
            "symbol": self.symbol,
            "data": trades
        }
        self._write(event)

    def log_signal(self, signal: Dict, timestamp: float = None):
        """记录信号"""
        if timestamp is None:
            timestamp = time.time()

        event = {
            "type": "signal",
            "ts": timestamp,
            "symbol": self.symbol,
            "data": signal
        }
        self._write(event)

    def log_state(self, state: Dict, timestamp: float = None):
        """记录状态机状态"""
        if timestamp is None:
            timestamp = time.time()

        event = {
            "type": "state",
            "ts": timestamp,
            "symbol": self.symbol,
            "data": state
        }
        self._write(event)

    def _write(self, event: Dict):
        """写入事件"""
        f = self._get_file()
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
        f.flush()
        self.event_count += 1

    def close(self):
        """关闭文件"""
        if self.current_file:
            self.current_file.close()
            self.current_file = None


class EventReplayer:
    """
    事件回放器

    从 JSONL 文件读取事件并按时间顺序回放
    """

    def __init__(self, filepath: str):
        self.filepath = filepath

    def replay(self) -> Generator[Dict, None, None]:
        """
        生成器：逐事件回放

        Yields:
            Dict: 事件字典 {"type": "...", "ts": ..., "data": ...}
        """
        open_func = gzip.open if self.filepath.endswith('.gz') else open
        with open_func(self.filepath, 'rt', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        event = json.loads(line)
                        yield event
                    except json.JSONDecodeError:
                        continue

    def get_events_by_type(self, event_type: str) -> List[Dict]:
        """获取指定类型的所有事件"""
        events = []
        for event in self.replay():
            if event.get("type") == event_type:
                events.append(event)
        return events

    def get_time_range(self) -> tuple:
        """获取数据时间范围"""
        first_ts = None
        last_ts = None

        for event in self.replay():
            ts = event.get("ts")
            if ts:
                if first_ts is None:
                    first_ts = ts
                last_ts = ts

        return (first_ts, last_ts)


class BacktestEvaluator:
    """
    回测评估器

    评估信号质量：命中率、平均提前量、误报率
    """

    def __init__(self, lookahead_seconds: int = 900):
        """
        Args:
            lookahead_seconds: 信号后看多少秒 (默认15分钟)
        """
        self.lookahead_seconds = lookahead_seconds
        self.signals: List[Dict] = []
        self.prices: List[Dict] = []

    def add_signal(self, signal_type: str, timestamp: float, price: float,
                   confidence: float = 0, reason: str = ""):
        """添加信号"""
        self.signals.append({
            "type": signal_type,
            "ts": timestamp,
            "price": price,
            "confidence": confidence,
            "reason": reason
        })

    def add_price(self, timestamp: float, price: float):
        """添加价格点"""
        self.prices.append({"ts": timestamp, "price": price})

    def evaluate(self, min_move_pct: float = 0.5) -> BacktestResult:
        """
        评估信号质量

        Args:
            min_move_pct: 最小价格变动百分比 (认为有效)

        Returns:
            BacktestResult: 回测结果
        """
        results = {
            "total": 0,
            "correct": 0,
            "wrong": 0,
            "profits": [],
            "losses": [],
            "details": []
        }

        # 按时间排序
        self.prices.sort(key=lambda x: x["ts"])
        self.signals.sort(key=lambda x: x["ts"])

        min_move = min_move_pct / 100

        for signal in self.signals:
            # 找到 lookahead 后的价格
            future_prices = [
                p for p in self.prices
                if signal["ts"] < p["ts"] <= signal["ts"] + self.lookahead_seconds
            ]

            if not future_prices:
                continue

            # 取区间内的最高和最低价
            max_price = max(p["price"] for p in future_prices)
            min_price = min(p["price"] for p in future_prices)
            end_price = future_prices[-1]["price"]

            signal_price = signal["price"]
            price_change = (end_price - signal_price) / signal_price

            results["total"] += 1

            # 评估看多信号
            if signal["type"] in ["trend_up", "accumulating", "wash_accumulate"]:
                max_gain = (max_price - signal_price) / signal_price
                if price_change > min_move:
                    results["correct"] += 1
                    results["profits"].append(price_change)
                else:
                    results["wrong"] += 1
                    results["losses"].append(price_change)

                results["details"].append({
                    "signal": signal,
                    "end_price": end_price,
                    "max_price": max_price,
                    "change": price_change,
                    "max_gain": max_gain,
                    "correct": price_change > min_move
                })

            # 评估看空信号
            elif signal["type"] in ["trend_down", "distributing", "trap_distribution"]:
                max_drop = (signal_price - min_price) / signal_price
                if price_change < -min_move:
                    results["correct"] += 1
                    results["profits"].append(-price_change)
                else:
                    results["wrong"] += 1
                    results["losses"].append(-price_change)

                results["details"].append({
                    "signal": signal,
                    "end_price": end_price,
                    "min_price": min_price,
                    "change": price_change,
                    "max_drop": max_drop,
                    "correct": price_change < -min_move
                })

        # 计算统计
        hit_rate = results["correct"] / results["total"] if results["total"] > 0 else 0
        avg_profit = sum(results["profits"]) / len(results["profits"]) if results["profits"] else 0
        avg_loss = sum(results["losses"]) / len(results["losses"]) if results["losses"] else 0

        return BacktestResult(
            total_signals=results["total"],
            correct_signals=results["correct"],
            wrong_signals=results["wrong"],
            hit_rate=hit_rate,
            avg_profit_correct=avg_profit,
            avg_loss_wrong=avg_loss,
            details=results["details"]
        )


def list_event_files(directory: str = "./storage/events") -> List[Path]:
    """列出所有事件文件"""
    dir_path = Path(directory)
    if not dir_path.exists():
        return []
    return sorted(dir_path.glob("*.jsonl*"))


def merge_event_files(files: List[Path], output_path: str) -> int:
    """
    合并多个事件文件

    Args:
        files: 要合并的文件列表
        output_path: 输出文件路径

    Returns:
        int: 合并的事件数量
    """
    events = []

    for filepath in files:
        replayer = EventReplayer(str(filepath))
        for event in replayer.replay():
            events.append(event)

    # 按时间排序
    events.sort(key=lambda x: x.get("ts", 0))

    # 写入合并文件
    open_func = gzip.open if output_path.endswith('.gz') else open
    with open_func(output_path, 'wt', encoding='utf-8') as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return len(events)
