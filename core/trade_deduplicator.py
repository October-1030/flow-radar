#!/usr/bin/env python3
"""
Flow Radar - Trade Deduplicator
流动性雷达 - 成交去重器

解决 REST/WebSocket 切换时的重复成交问题
"""

from collections import OrderedDict
from typing import Dict, Optional
import hashlib


class TradeDeduplicator:
    """
    成交去重器

    功能：
    - 按 trade_id 或 (timestamp, price, size, side) 哈希去重
    - 自动清理过期数据
    - 限制内存使用
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: int = 300):
        """
        Args:
            max_size: 最大记录数量
            ttl_seconds: 记录过期时间 (秒)
        """
        self.seen: OrderedDict[str, float] = OrderedDict()
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.duplicate_count = 0
        self.total_count = 0

    def is_duplicate(self, trade: Dict, current_ts: float = None) -> bool:
        """
        检查成交是否重复

        Args:
            trade: 成交数据字典
            current_ts: 当前时间戳 (用于清理过期)

        Returns:
            bool: True 表示重复，应该跳过
        """
        import time
        if current_ts is None:
            current_ts = time.time()

        # 生成唯一 ID
        trade_id = trade.get('id') or self._hash_trade(trade)

        # 清理过期
        self._cleanup(current_ts)

        self.total_count += 1

        # 检查重复
        if trade_id in self.seen:
            self.duplicate_count += 1
            return True

        # 记录
        self.seen[trade_id] = current_ts

        # 限制大小 (FIFO)
        while len(self.seen) > self.max_size:
            self.seen.popitem(last=False)

        return False

    def _hash_trade(self, trade: Dict) -> str:
        """
        生成成交哈希 (当没有 trade_id 时)

        Args:
            trade: 成交数据

        Returns:
            str: 哈希字符串
        """
        # 使用 (timestamp, price, amount, side) 生成唯一标识
        key = f"{trade.get('timestamp')}_{trade.get('price')}_{trade.get('amount')}_{trade.get('side')}"
        return hashlib.md5(key.encode()).hexdigest()

    def _cleanup(self, current_ts: float):
        """清理过期记录"""
        cutoff = current_ts - self.ttl_seconds
        expired = [k for k, v in self.seen.items() if v < cutoff]
        for k in expired:
            del self.seen[k]

    def filter_trades(self, trades: list, current_ts: float = None) -> list:
        """
        过滤成交列表，返回非重复的成交

        Args:
            trades: 成交列表
            current_ts: 当前时间戳

        Returns:
            list: 过滤后的非重复成交列表
        """
        import time
        if current_ts is None:
            current_ts = time.time()

        return [t for t in trades if not self.is_duplicate(t, current_ts)]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            "total_count": self.total_count,
            "duplicate_count": self.duplicate_count,
            "unique_count": self.total_count - self.duplicate_count,
            "duplicate_rate": self.duplicate_count / self.total_count if self.total_count > 0 else 0,
            "cache_size": len(self.seen)
        }

    def reset(self):
        """重置去重器"""
        self.seen.clear()
        self.duplicate_count = 0
        self.total_count = 0
