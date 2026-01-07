#!/usr/bin/env python3
"""
Flow Radar - State Saver
流动性雷达 - 状态持久化

重启后恢复 CVD、冰山统计等关键状态
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass, asdict


@dataclass
class SystemState:
    """系统状态"""
    ts: float                           # 保存时间戳
    symbol: str                         # 交易对
    cvd_total: float                    # 累计 CVD
    total_whale_flow: float             # 累计鲸鱼流
    iceberg_buy_count: int              # 冰山买单数量
    iceberg_sell_count: int             # 冰山卖单数量
    iceberg_buy_volume: float           # 冰山买单累计量
    iceberg_sell_volume: float          # 冰山卖单累计量
    current_state: str                  # 状态机当前状态
    last_score: int                     # 最后分数
    last_price: float                   # 最后价格


@dataclass
class ExtendedState:
    """
    P2-4: 扩展状态 (冰山检测 + 告警节流)

    用于保存和恢复完整的运行状态
    """
    ts: float                           # 保存时间戳
    symbol: str                         # 交易对
    # 基础状态 (与 SystemState 兼容)
    cvd_total: float = 0
    total_whale_flow: float = 0
    iceberg_buy_count: int = 0
    iceberg_sell_count: int = 0
    iceberg_buy_volume: float = 0
    iceberg_sell_volume: float = 0
    current_state: str = 'neutral'
    last_score: int = 50
    last_price: float = 0
    # P2-4: 活跃冰山信号摘要
    active_icebergs: list = None        # 活跃冰山列表 [{side, price, cumulative_filled, refill_count, intensity, level}]
    # P2-4: 告警节流状态
    throttle_state: dict = None         # 节流状态 {key: {last_time, count, silenced_until, suppressed_count, iceberg_level}}

    def __post_init__(self):
        if self.active_icebergs is None:
            self.active_icebergs = []
        if self.throttle_state is None:
            self.throttle_state = {}


class StateSaver:
    """
    状态保存器

    功能：
    - 每分钟自动保存状态
    - 原子写入防止损坏
    - 重启后自动恢复
    """

    def __init__(self, symbol: str, save_dir: str = "./storage/state"):
        """
        Args:
            symbol: 交易对 (如 "DOGE/USDT")
            save_dir: 保存目录
        """
        self.symbol = symbol
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.save_dir / f"{symbol.replace('/', '_')}_state.json"
        self.last_save_ts = 0
        self.save_interval = 60  # 每分钟保存

    def save(self, state: Dict, current_ts: float = None, force: bool = False) -> bool:
        """
        保存状态

        Args:
            state: 状态字典
            current_ts: 当前时间戳
            force: 强制保存 (忽略时间间隔)

        Returns:
            bool: 是否成功保存
        """
        if current_ts is None:
            current_ts = time.time()

        # 检查保存间隔
        if not force and current_ts - self.last_save_ts < self.save_interval:
            return False

        checkpoint = {
            'ts': current_ts,
            'symbol': self.symbol,
            'cvd_total': state.get('cvd_total', 0),
            'total_whale_flow': state.get('total_whale_flow', 0),
            'iceberg_buy_count': state.get('iceberg_buy_count', 0),
            'iceberg_sell_count': state.get('iceberg_sell_count', 0),
            'iceberg_buy_volume': state.get('iceberg_buy_volume', 0),
            'iceberg_sell_volume': state.get('iceberg_sell_volume', 0),
            'current_state': state.get('current_state', 'neutral'),
            'last_score': state.get('last_score', 50),
            'last_price': state.get('last_price', 0),
        }

        try:
            # 原子写入：先写临时文件，再替换
            tmp_path = self.filepath.with_suffix('.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, indent=2)
            tmp_path.replace(self.filepath)  # replace() 可以覆盖已存在的文件

            self.last_save_ts = current_ts
            return True

        except Exception as e:
            print(f"[StateSaver] 保存失败: {e}")
            return False

    def load(self) -> Optional[SystemState]:
        """
        加载状态

        Returns:
            Optional[SystemState]: 状态对象，如果不存在或损坏则返回 None
        """
        if not self.filepath.exists():
            return None

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return SystemState(
                ts=data.get('ts', 0),
                symbol=data.get('symbol', self.symbol),
                cvd_total=data.get('cvd_total', 0),
                total_whale_flow=data.get('total_whale_flow', 0),
                iceberg_buy_count=data.get('iceberg_buy_count', 0),
                iceberg_sell_count=data.get('iceberg_sell_count', 0),
                iceberg_buy_volume=data.get('iceberg_buy_volume', 0),
                iceberg_sell_volume=data.get('iceberg_sell_volume', 0),
                current_state=data.get('current_state', 'neutral'),
                last_score=data.get('last_score', 50),
                last_price=data.get('last_price', 0)
            )

        except Exception as e:
            print(f"[StateSaver] 加载失败: {e}")
            return None

    def load_dict(self) -> Optional[Dict]:
        """加载状态为字典"""
        state = self.load()
        if state:
            return asdict(state)
        return None

    def get_state_age(self) -> Optional[float]:
        """
        获取状态年龄 (秒)

        Returns:
            Optional[float]: 状态年龄，如果不存在返回 None
        """
        state = self.load()
        if state:
            return time.time() - state.ts
        return None

    def is_stale(self, max_age_hours: float = 24) -> bool:
        """
        检查状态是否过期

        Args:
            max_age_hours: 最大有效时间 (小时)

        Returns:
            bool: True 表示过期或不存在
        """
        age = self.get_state_age()
        if age is None:
            return True
        return age > max_age_hours * 3600

    def delete(self) -> bool:
        """删除状态文件"""
        try:
            if self.filepath.exists():
                self.filepath.unlink()
            return True
        except Exception as e:
            print(f"[StateSaver] 删除失败: {e}")
            return False

    # ==================== P2-4: 扩展状态保存/恢复 ====================

    def save_extended(self, state: Dict, active_icebergs: list = None,
                      throttle_state: dict = None, current_ts: float = None,
                      force: bool = False) -> bool:
        """
        P2-4: 保存扩展状态 (含冰山 + 节流)

        Args:
            state: 基础状态字典
            active_icebergs: 活跃冰山列表 [{side, price, cumulative_filled, ...}]
            throttle_state: 告警节流状态字典
            current_ts: 当前时间戳
            force: 强制保存

        Returns:
            bool: 是否成功保存
        """
        if current_ts is None:
            current_ts = time.time()

        # 检查保存间隔
        if not force and current_ts - self.last_save_ts < self.save_interval:
            return False

        # 构建扩展状态
        checkpoint = {
            'ts': current_ts,
            'symbol': self.symbol,
            'version': 2,  # 版本号，用于兼容性检查
            # 基础状态
            'cvd_total': state.get('cvd_total', 0),
            'total_whale_flow': state.get('total_whale_flow', 0),
            'iceberg_buy_count': state.get('iceberg_buy_count', 0),
            'iceberg_sell_count': state.get('iceberg_sell_count', 0),
            'iceberg_buy_volume': state.get('iceberg_buy_volume', 0),
            'iceberg_sell_volume': state.get('iceberg_sell_volume', 0),
            'current_state': state.get('current_state', 'neutral'),
            'last_score': state.get('last_score', 50),
            'last_price': state.get('last_price', 0),
            # P2-4: 扩展状态
            'active_icebergs': active_icebergs or [],
            'throttle_state': self._sanitize_throttle_state(throttle_state or {}),
        }

        try:
            # 原子写入
            tmp_path = self.filepath.with_suffix('.tmp')
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(checkpoint, f, indent=2)
            tmp_path.replace(self.filepath)

            self.last_save_ts = current_ts
            return True

        except Exception as e:
            print(f"[StateSaver] 扩展状态保存失败: {e}")
            return False

    def _sanitize_throttle_state(self, throttle_state: dict) -> dict:
        """
        P2-4: 清理节流状态以便 JSON 序列化

        移除过期条目，确保所有值可序列化（datetime -> timestamp）
        """
        from datetime import datetime
        now = time.time()
        sanitized = {}

        for key, state in throttle_state.items():
            # 获取 last_time 并转换为时间戳
            last_time_value = state.get('last_time', now)
            if isinstance(last_time_value, datetime):
                last_time = last_time_value.timestamp()
            elif isinstance(last_time_value, (int, float)):
                last_time = float(last_time_value)
            else:
                last_time = now

            # 跳过过期的静默条目 (超过 1 小时)
            if now - last_time > 3600:
                continue

            # 获取 silenced_until 并转换为时间戳
            silenced_until_value = state.get('silenced_until')
            if silenced_until_value:
                if isinstance(silenced_until_value, datetime):
                    silenced_until = silenced_until_value.timestamp()
                elif isinstance(silenced_until_value, (int, float)):
                    silenced_until = float(silenced_until_value)
                else:
                    silenced_until = None
            else:
                silenced_until = None

            sanitized[key] = {
                'last_time': last_time,
                'count': state.get('count', 0),
                'silenced_until': silenced_until,
                'suppressed_count': state.get('suppressed_count', 0),
                'iceberg_level': state.get('iceberg_level'),
            }

        return sanitized

    def load_extended(self) -> Optional[ExtendedState]:
        """
        P2-4: 加载扩展状态

        Returns:
            Optional[ExtendedState]: 扩展状态对象
        """
        if not self.filepath.exists():
            return None

        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            return ExtendedState(
                ts=data.get('ts', 0),
                symbol=data.get('symbol', self.symbol),
                cvd_total=data.get('cvd_total', 0),
                total_whale_flow=data.get('total_whale_flow', 0),
                iceberg_buy_count=data.get('iceberg_buy_count', 0),
                iceberg_sell_count=data.get('iceberg_sell_count', 0),
                iceberg_buy_volume=data.get('iceberg_buy_volume', 0),
                iceberg_sell_volume=data.get('iceberg_sell_volume', 0),
                current_state=data.get('current_state', 'neutral'),
                last_score=data.get('last_score', 50),
                last_price=data.get('last_price', 0),
                active_icebergs=data.get('active_icebergs', []),
                throttle_state=data.get('throttle_state', {}),
            )

        except Exception as e:
            print(f"[StateSaver] 扩展状态加载失败: {e}")
            return None

    def has_extended_state(self) -> bool:
        """P2-4: 检查是否有扩展状态"""
        if not self.filepath.exists():
            return False
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('version', 1) >= 2
        except:
            return False
