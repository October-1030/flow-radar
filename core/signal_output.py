"""
Flow Radar - 专用信号输出器

供 Signal Commander 读取的信号输出模块。

输出位置：storage/signals/YYYY-MM-DD.jsonl
格式：每行一个 JSON 对象（JSONL）

信号类型：
    - iceberg_detected: 检测到冰山单
    - iceberg_absorbed: 冰山单被吸收
    - k_god_buy: K神买入信号
    - k_god_sell: K神卖出信号

方向规则：
    - iceberg_detected: BUY 侧 → bullish，SELL 侧 → bearish
    - iceberg_absorbed: 被吸收后反向：原 BUY → bearish，原 SELL → bullish
    - k_god_buy: 固定 bullish
    - k_god_sell: 固定 bearish

作者: Claude Code
日期: 2026-01-11
"""

import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("SignalOutput")


class SignalOutput:
    """
    专用信号输出器

    线程安全，每次写入后立即刷盘。

    使用示例：
        >>> from core.signal_output import signal_output
        >>> signal_output.emit(
        ...     signal_type="iceberg_detected",
        ...     symbol="DOGE-USDT",
        ...     direction="bullish",
        ...     data={"price": 0.14, "intensity": 2.5}
        ... )
    """

    # Schema 版本号（便于后续升级）
    SCHEMA_VERSION = 1

    def __init__(self, output_dir: str = "storage/signals"):
        """
        初始化信号输出器

        Args:
            output_dir: 输出目录，相对于项目根目录
        """
        # 确定项目根目录
        self._base_dir = Path(__file__).parent.parent
        self.output_dir = self._base_dir / output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 线程锁
        self._lock = threading.Lock()

        # 统计
        self._emit_count = 0

        logger.info(f"SignalOutput 初始化完成，输出目录: {self.output_dir}")

    def emit(
        self,
        signal_type: str,
        symbol: str,
        direction: str,
        data: Dict[str, Any],
        confidence: Optional[float] = None,
    ) -> str:
        """
        输出信号到专用文件

        Args:
            signal_type: 信号类型
                - iceberg_detected: 检测到冰山单
                - iceberg_absorbed: 冰山单被吸收
                - k_god_buy: K神买入信号
                - k_god_sell: K神卖出信号
            symbol: 交易对，原始格式（如 DOGE-USDT），会自动转换为 DOGE/USDT
            direction: 信号方向
                - bullish: 看多
                - bearish: 看空
                - neutral: 中性
            data: 原始数据字典（包含价格、强度等详细信息）
            confidence: 置信度（0-100），可选

        Returns:
            event_id: 生成的事件 ID

        Raises:
            ValueError: 如果 signal_type 或 direction 无效
        """
        # 验证 signal_type
        valid_types = {"iceberg_detected", "iceberg_absorbed", "k_god_buy", "k_god_sell"}
        if signal_type not in valid_types:
            raise ValueError(f"无效的 signal_type: {signal_type}，有效值: {valid_types}")

        # 验证 direction
        valid_directions = {"bullish", "bearish", "neutral"}
        if direction not in valid_directions:
            raise ValueError(f"无效的 direction: {direction}，有效值: {valid_directions}")

        # 生成事件 ID
        event_id = self._generate_event_id()

        # 构建信号事件
        signal_event = {
            "event_id": event_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": "flow_radar",
            "schema_version": self.SCHEMA_VERSION,
            "signal_type": signal_type,
            "symbol": self._normalize_symbol(symbol),
            "direction": direction,
            "data": data,
        }

        # 添加可选字段
        if confidence is not None:
            signal_event["confidence"] = confidence

        # 写入文件
        today = datetime.now().strftime("%Y-%m-%d")
        signal_path = self.output_dir / f"{today}.jsonl"

        with self._lock:
            with open(signal_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(signal_event, ensure_ascii=False) + '\n')
                f.flush()  # 立即刷盘

            self._emit_count += 1

        logger.debug(f"信号已输出: {event_id} [{signal_type}] {symbol} {direction}")

        return event_id

    def emit_iceberg_detected(
        self,
        symbol: str,
        side: str,
        price: float,
        intensity: float,
        cumulative_volume: float,
        visible_depth: float,
        refill_count: int,
        level: str = "ACTIVITY",
        confidence: float = 50.0,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        输出冰山单检测信号（便捷方法）

        Args:
            symbol: 交易对
            side: BUY 或 SELL
            price: 价格
            intensity: 强度
            cumulative_volume: 累计成交量
            visible_depth: 可见挂单深度
            refill_count: 补单次数
            level: 信号级别（ACTIVITY/CONFIRMED/CRITICAL）
            confidence: 置信度
            extra_data: 额外数据

        Returns:
            event_id
        """
        direction = "bullish" if side.upper() == "BUY" else "bearish"

        data = {
            "side": side.upper(),
            "price": price,
            "intensity": intensity,
            "cumulative_volume": cumulative_volume,
            "visible_depth": visible_depth,
            "refill_count": refill_count,
            "level": level,
        }

        if extra_data:
            data.update(extra_data)

        return self.emit(
            signal_type="iceberg_detected",
            symbol=symbol,
            direction=direction,
            data=data,
            confidence=confidence,
        )

    def emit_iceberg_absorbed(
        self,
        symbol: str,
        side: str,
        price: float,
        absorbed_volume: float,
        duration_seconds: float,
        confidence: float = 60.0,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        输出冰山单被吸收信号（便捷方法）

        冰山被吸收意味着原方向的力量被消耗，反向可能启动。

        Args:
            symbol: 交易对
            side: 原冰山的方向（BUY 或 SELL）
            price: 吸收时的价格
            absorbed_volume: 被吸收的总量
            duration_seconds: 存续时长
            confidence: 置信度
            extra_data: 额外数据

        Returns:
            event_id
        """
        # 被吸收后方向反转
        direction = "bearish" if side.upper() == "BUY" else "bullish"

        data = {
            "original_side": side.upper(),
            "price": price,
            "absorbed_volume": absorbed_volume,
            "duration_seconds": duration_seconds,
        }

        if extra_data:
            data.update(extra_data)

        return self.emit(
            signal_type="iceberg_absorbed",
            symbol=symbol,
            direction=direction,
            data=data,
            confidence=confidence,
        )

    def emit_k_god_buy(
        self,
        symbol: str,
        price: float,
        score: float,
        confidence: float = 70.0,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        输出 K 神买入信号（便捷方法）

        Args:
            symbol: 交易对
            price: 信号价格
            score: K 神评分
            confidence: 置信度
            extra_data: 额外数据

        Returns:
            event_id
        """
        data = {
            "price": price,
            "score": score,
        }

        if extra_data:
            data.update(extra_data)

        return self.emit(
            signal_type="k_god_buy",
            symbol=symbol,
            direction="bullish",
            data=data,
            confidence=confidence,
        )

    def emit_k_god_sell(
        self,
        symbol: str,
        price: float,
        score: float,
        confidence: float = 70.0,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        输出 K 神卖出信号（便捷方法）

        Args:
            symbol: 交易对
            price: 信号价格
            score: K 神评分
            confidence: 置信度
            extra_data: 额外数据

        Returns:
            event_id
        """
        data = {
            "price": price,
            "score": score,
        }

        if extra_data:
            data.update(extra_data)

        return self.emit(
            signal_type="k_god_sell",
            symbol=symbol,
            direction="bearish",
            data=data,
            confidence=confidence,
        )

    def _generate_event_id(self) -> str:
        """生成唯一事件 ID"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        random_suffix = secrets.token_hex(3)
        return f"evt_{timestamp}_{random_suffix}"

    def _normalize_symbol(self, symbol: str) -> str:
        """
        标准化交易对格式

        DOGE-USDT -> DOGE/USDT
        DOGE_USDT -> DOGE/USDT
        DOGE/USDT -> DOGE/USDT（不变）
        """
        return symbol.replace('-', '/').replace('_', '/')

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "emit_count": self._emit_count,
            "output_dir": str(self.output_dir),
        }

    def get_today_file_path(self) -> Path:
        """获取今天的信号文件路径"""
        today = datetime.now().strftime("%Y-%m-%d")
        return self.output_dir / f"{today}.jsonl"


# 全局实例（单例模式）
signal_output = SignalOutput()
