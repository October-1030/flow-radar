#!/usr/bin/env python3
"""
Flow Radar - WebSocket Manager
流动性雷达 - WebSocket 连接管理器

实时数据流管理，支持自动重连和 REST 降级
"""

import asyncio
import json
import time
import gzip
from datetime import datetime
from typing import Optional, Dict, List, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    import websockets
    from websockets.exceptions import ConnectionClosed, WebSocketException
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

import aiohttp
from rich.console import Console

console = Console()


class ConnectionState(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class HealthStatus(Enum):
    """健康状态 (P2-5)"""
    HEALTHY = "healthy"           # 数据流正常
    WARNING = "warning"           # 数据有延迟，但未超阈值
    STALE = "stale"               # 数据过期
    DISCONNECTED = "disconnected" # 未连接


@dataclass
class WebSocketConfig:
    """WebSocket 配置"""
    enabled: bool = True
    ws_url: str = "wss://ws.okx.com:8443/ws/v5/public"
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 10
    heartbeat_interval: int = 25  # OKX 要求 30s 内发送 ping
    fallback_to_rest: bool = True
    channels: List[str] = field(default_factory=lambda: ["trades", "books5", "tickers"])


@dataclass
class HealthCheckConfig:
    """健康检查配置 (P2-5)"""
    enabled: bool = True
    data_stale_threshold: int = 60       # 数据过期阈值（秒）
    warning_threshold: int = 30          # 预警阈值（秒）
    check_interval: int = 10             # 检查间隔（秒）
    auto_reconnect_on_stale: bool = True # 数据过期时自动重连
    max_stale_count_before_alert: int = 2 # 连续过期次数后告警
    recovery_grace_period: int = 5        # 恢复观察期（秒）


@dataclass
class MarketSnapshot:
    """市场数据快照"""
    timestamp: float
    ticker: Optional[Dict] = None
    orderbook: Optional[Dict] = None
    trades: List[Dict] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """检查快照是否有效"""
        return self.ticker is not None and self.orderbook is not None


class WebSocketManager:
    """
    WebSocket 连接管理器

    功能:
    - 连接 OKX WebSocket 获取实时数据
    - 自动重连机制
    - 回调模式传递数据
    - 数据快照供轮询兼容
    """

    def __init__(self, symbol: str, config: Optional[WebSocketConfig] = None,
                 health_config: Optional[HealthCheckConfig] = None):
        self.symbol = symbol
        self.config = config or WebSocketConfig()
        self.health_config = health_config or HealthCheckConfig()

        # 连接状态
        self.state = ConnectionState.DISCONNECTED
        self.ws = None
        self.reconnect_count = 0
        self.last_message_time = 0

        # 数据存储
        self._snapshot = MarketSnapshot(timestamp=time.time())
        self._trades_buffer: List[Dict] = []
        self._max_trades_buffer = 200

        # P2-5: 健康检查状态
        self._health_status = HealthStatus.DISCONNECTED
        self._stale_count = 0                # 连续过期计数
        self._last_health_check = 0          # 上次健康检查时间
        self._stale_alert_sent = False       # 是否已发送过期告警
        self._recovery_start_time = 0        # 恢复开始时间

        # 回调函数
        self._callbacks: Dict[str, List[Callable]] = {
            'ticker': [],
            'orderbook': [],
            'trades': [],
            'connected': [],
            'disconnected': [],
            'data_stale': [],      # P2-5: 数据过期回调
            'data_recovered': [],  # P2-5: 数据恢复回调
            'health_warning': [],  # P2-5: 健康预警回调
        }

        # 任务句柄
        self._receive_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None  # P2-5

        # OKX 频道格式
        self._inst_id = symbol.replace('/', '-')  # DOGE/USDT -> DOGE-USDT

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self.state == ConnectionState.CONNECTED

    @property
    def health_status(self) -> HealthStatus:
        """P2-5: 获取健康状态"""
        return self._health_status

    @property
    def snapshot(self) -> MarketSnapshot:
        """获取当前市场快照"""
        return self._snapshot

    def get_health_status(self) -> Dict[str, Any]:
        """
        P2-5: 获取详细健康状态报告

        Returns:
            Dict: 包含健康状态、数据延迟、连接信息的字典
        """
        now = time.time()
        data_age = now - self.last_message_time if self.last_message_time > 0 else -1

        return {
            'status': self._health_status.value,
            'connected': self.is_connected,
            'data_age_seconds': round(data_age, 1) if data_age >= 0 else None,
            'stale_count': self._stale_count,
            'reconnect_count': self.reconnect_count,
            'last_message_time': self.last_message_time,
            'snapshot_valid': self._snapshot.is_valid,
            'thresholds': {
                'warning': self.health_config.warning_threshold,
                'stale': self.health_config.data_stale_threshold,
            }
        }

    def on(self, event: str, callback: Callable):
        """
        注册事件回调

        Args:
            event: 事件类型 (ticker, orderbook, trades, connected, disconnected)
            callback: 回调函数
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def off(self, event: str, callback: Callable):
        """移除事件回调"""
        if event in self._callbacks and callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)

    async def _emit(self, event: str, data: Any = None):
        """触发事件回调"""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                console.print(f"[red]Callback error for {event}: {e}[/red]")

    async def connect(self) -> bool:
        """
        建立 WebSocket 连接

        Returns:
            bool: 连接是否成功
        """
        if not WEBSOCKETS_AVAILABLE:
            console.print("[yellow]websockets 库未安装，使用 REST 模式[/yellow]")
            return False

        if not self.config.enabled:
            return False

        self.state = ConnectionState.CONNECTING

        try:
            console.print(f"[cyan]连接 WebSocket: {self.config.ws_url}[/cyan]")

            self.ws = await asyncio.wait_for(
                websockets.connect(
                    self.config.ws_url,
                    ping_interval=None,  # 我们自己处理心跳
                    ping_timeout=None,
                    close_timeout=10,
                ),
                timeout=15.0
            )

            # 订阅频道
            await self._subscribe()

            self.state = ConnectionState.CONNECTED
            self.reconnect_count = 0
            self.last_message_time = time.time()

            # P2-5: 初始化健康状态
            self._health_status = HealthStatus.HEALTHY
            self._stale_count = 0
            self._stale_alert_sent = False

            console.print(f"[green]WebSocket 已连接[/green]")
            await self._emit('connected')

            # 启动接收和心跳任务
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            # P2-5: 启动健康检查任务
            if self.health_config.enabled:
                self._health_check_task = asyncio.create_task(self._health_check_loop())

            return True

        except asyncio.TimeoutError:
            console.print("[red]WebSocket 连接超时[/red]")
            self.state = ConnectionState.DISCONNECTED
            return False
        except Exception as e:
            console.print(f"[red]WebSocket 连接失败: {e}[/red]")
            self.state = ConnectionState.DISCONNECTED
            return False

    async def _subscribe(self):
        """订阅数据频道"""
        # OKX 订阅格式
        subscribe_msg = {
            "op": "subscribe",
            "args": []
        }

        # 添加订阅频道
        for channel in self.config.channels:
            if channel == "trades":
                subscribe_msg["args"].append({
                    "channel": "trades",
                    "instId": self._inst_id
                })
            elif channel == "books5":
                subscribe_msg["args"].append({
                    "channel": "books5",
                    "instId": self._inst_id
                })
            elif channel == "tickers":
                subscribe_msg["args"].append({
                    "channel": "tickers",
                    "instId": self._inst_id
                })

        await self.ws.send(json.dumps(subscribe_msg))
        console.print(f"[dim]已订阅: {self.config.channels}[/dim]")

    async def _receive_loop(self):
        """接收消息循环"""
        try:
            async for message in self.ws:
                try:
                    # OKX 可能发送 gzip 压缩的消息
                    if isinstance(message, bytes):
                        try:
                            message = gzip.decompress(message).decode('utf-8')
                        except:
                            message = message.decode('utf-8')

                    data = json.loads(message)
                    self.last_message_time = time.time()

                    await self._handle_message(data)

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    console.print(f"[yellow]消息处理错误: {e}[/yellow]")

        except ConnectionClosed:
            console.print("[yellow]WebSocket 连接关闭[/yellow]")
        except Exception as e:
            console.print(f"[red]接收循环错误: {e}[/red]")
        finally:
            await self._handle_disconnect()

    async def _handle_message(self, data: Dict):
        """处理接收到的消息"""
        # 处理 pong 响应
        if data.get("op") == "pong" or data.get("event") == "pong":
            return

        # 处理订阅确认
        if data.get("event") == "subscribe":
            channel = data.get("arg", {}).get("channel", "unknown")
            console.print(f"[dim]订阅确认: {channel}[/dim]")
            return

        # 处理错误
        if data.get("event") == "error":
            console.print(f"[red]WebSocket 错误: {data.get('msg')}[/red]")
            return

        # 处理数据推送
        arg = data.get("arg", {})
        channel = arg.get("channel")
        push_data = data.get("data", [])

        if not push_data:
            return

        if channel == "tickers":
            await self._handle_ticker(push_data[0])
        elif channel == "books5":
            await self._handle_orderbook(push_data[0])
        elif channel == "trades":
            await self._handle_trades(push_data)

    async def _handle_ticker(self, data: Dict):
        """处理 Ticker 数据"""
        ticker = {
            'symbol': self.symbol,
            'last': float(data.get('last', 0)),
            'bid': float(data.get('bidPx', 0)),
            'ask': float(data.get('askPx', 0)),
            'high': float(data.get('high24h', 0)),
            'low': float(data.get('low24h', 0)),
            'baseVolume': float(data.get('vol24h', 0)),
            'quoteVolume': float(data.get('volCcy24h', 0)),
            'percentage': float(data.get('change24h', 0)) * 100 if data.get('change24h') else 0,
            'timestamp': int(data.get('ts', time.time() * 1000)),
        }

        self._snapshot.ticker = ticker
        self._snapshot.timestamp = time.time()

        await self._emit('ticker', ticker)

    async def _handle_orderbook(self, data: Dict):
        """处理订单簿数据"""
        bids = [[float(p), float(q)] for p, q, _, _ in data.get('bids', [])]
        asks = [[float(p), float(q)] for p, q, _, _ in data.get('asks', [])]

        orderbook = {
            'symbol': self.symbol,
            'bids': bids,
            'asks': asks,
            'timestamp': int(data.get('ts', time.time() * 1000)),
        }

        self._snapshot.orderbook = orderbook
        self._snapshot.timestamp = time.time()

        await self._emit('orderbook', orderbook)

    async def _handle_trades(self, trades_data: List[Dict]):
        """处理成交数据"""
        trades = []
        for t in trades_data:
            trade = {
                'id': t.get('tradeId'),
                'symbol': self.symbol,
                'price': float(t.get('px', 0)),
                'amount': float(t.get('sz', 0)),
                'side': 'buy' if t.get('side') == 'buy' else 'sell',
                'timestamp': int(t.get('ts', time.time() * 1000)),
            }
            trades.append(trade)

            # 添加到缓冲区
            self._trades_buffer.append(trade)

        # 限制缓冲区大小
        if len(self._trades_buffer) > self._max_trades_buffer:
            self._trades_buffer = self._trades_buffer[-self._max_trades_buffer:]

        # 更新快照
        self._snapshot.trades = self._trades_buffer.copy()
        self._snapshot.timestamp = time.time()

        await self._emit('trades', trades)

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.config.heartbeat_interval)

                if self.ws and self.state == ConnectionState.CONNECTED:
                    # OKX 心跳格式
                    await self.ws.send("ping")

            except Exception as e:
                console.print(f"[yellow]心跳发送失败: {e}[/yellow]")
                break

    async def _health_check_loop(self):
        """
        P2-5: 健康检查循环

        定期检查数据流活跃度，检测异常并触发回调
        """
        while self.state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self.health_config.check_interval)

                if self.state != ConnectionState.CONNECTED:
                    break

                now = time.time()
                data_age = now - self.last_message_time if self.last_message_time > 0 else float('inf')
                prev_status = self._health_status

                # 判断健康状态
                if data_age >= self.health_config.data_stale_threshold:
                    # 数据过期
                    self._health_status = HealthStatus.STALE
                    self._stale_count += 1
                    self._recovery_start_time = 0

                    # 检查是否需要发送告警
                    if self._stale_count >= self.health_config.max_stale_count_before_alert:
                        if not self._stale_alert_sent:
                            self._stale_alert_sent = True
                            console.print(f"[red]⚠️ 数据流异常: {data_age:.1f}秒无数据[/red]")
                            await self._emit('data_stale', {
                                'data_age': data_age,
                                'stale_count': self._stale_count,
                                'threshold': self.health_config.data_stale_threshold,
                            })

                            # 可选: 自动重连
                            if self.health_config.auto_reconnect_on_stale:
                                console.print("[yellow]触发自动重连...[/yellow]")
                                await self._handle_disconnect()
                                return

                elif data_age >= self.health_config.warning_threshold:
                    # 预警状态
                    self._health_status = HealthStatus.WARNING

                    if prev_status == HealthStatus.HEALTHY:
                        console.print(f"[yellow]⚠️ 数据延迟: {data_age:.1f}秒[/yellow]")
                        await self._emit('health_warning', {
                            'data_age': data_age,
                            'threshold': self.health_config.warning_threshold,
                        })

                else:
                    # 健康状态
                    self._health_status = HealthStatus.HEALTHY

                    # 检查是否从异常恢复
                    if prev_status in (HealthStatus.STALE, HealthStatus.WARNING):
                        if self._recovery_start_time == 0:
                            self._recovery_start_time = now
                        elif now - self._recovery_start_time >= self.health_config.recovery_grace_period:
                            # 恢复稳定，重置计数
                            self._stale_count = 0
                            self._stale_alert_sent = False
                            console.print(f"[green]✓ 数据流已恢复正常[/green]")
                            await self._emit('data_recovered', {
                                'data_age': data_age,
                                'recovery_time': now - self._recovery_start_time,
                            })
                            self._recovery_start_time = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                console.print(f"[yellow]健康检查错误: {e}[/yellow]")

    async def _handle_disconnect(self):
        """处理断开连接"""
        if self.state == ConnectionState.DISCONNECTED:
            return

        self.state = ConnectionState.DISCONNECTED
        self._health_status = HealthStatus.DISCONNECTED  # P2-5
        await self._emit('disconnected')

        # 取消任务
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()

        # P2-5: 取消健康检查任务
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()

        # 尝试重连
        if self.config.fallback_to_rest:
            await self._try_reconnect()

    async def _try_reconnect(self):
        """尝试重连"""
        if self.reconnect_count >= self.config.max_reconnect_attempts:
            console.print("[red]达到最大重连次数，切换到 REST 模式[/red]")
            return

        self.reconnect_count += 1
        self.state = ConnectionState.RECONNECTING

        delay = self.config.reconnect_delay * min(self.reconnect_count, 5)
        console.print(f"[yellow]{delay}秒后尝试重连 ({self.reconnect_count}/{self.config.max_reconnect_attempts})[/yellow]")

        await asyncio.sleep(delay)

        if await self.connect():
            console.print("[green]重连成功[/green]")
        else:
            await self._try_reconnect()

    async def disconnect(self):
        """断开连接"""
        self.state = ConnectionState.DISCONNECTED
        self._health_status = HealthStatus.DISCONNECTED  # P2-5

        # 取消任务 (P2-5: 包含健康检查任务)
        for task in [self._receive_task, self._heartbeat_task, self._health_check_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 关闭 WebSocket
        if self.ws:
            try:
                await self.ws.close()
            except:
                pass
            self.ws = None

        console.print("[dim]WebSocket 已断开[/dim]")

    def get_snapshot(self) -> Optional[Dict]:
        """
        获取兼容 REST 格式的数据快照

        Returns:
            Dict 或 None: 包含 ticker, orderbook, trades 的字典
        """
        if not self._snapshot.is_valid:
            return None

        # 检查数据新鲜度 (超过 30 秒视为过期)
        if time.time() - self._snapshot.timestamp > 30:
            return None

        return {
            'ticker': self._snapshot.ticker,
            'orderbook': self._snapshot.orderbook,
            'trades': self._snapshot.trades[-100:],  # 最近 100 条
        }

    def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        """获取最近的成交记录"""
        return self._trades_buffer[-limit:]

    def clear_trades_buffer(self):
        """清空成交缓冲区"""
        self._trades_buffer.clear()
        self._snapshot.trades.clear()


# 配置加载函数
def load_websocket_config() -> WebSocketConfig:
    """从 settings 加载 WebSocket 配置"""
    try:
        from config.settings import CONFIG_WEBSOCKET
        return WebSocketConfig(
            enabled=CONFIG_WEBSOCKET.get('enabled', True),
            ws_url=CONFIG_WEBSOCKET.get('ws_url', "wss://ws.okx.com:8443/ws/v5/public"),
            reconnect_delay=CONFIG_WEBSOCKET.get('reconnect_delay', 5),
            max_reconnect_attempts=CONFIG_WEBSOCKET.get('max_reconnect_attempts', 10),
            heartbeat_interval=CONFIG_WEBSOCKET.get('heartbeat_interval', 25),
            fallback_to_rest=CONFIG_WEBSOCKET.get('fallback_to_rest', True),
            channels=CONFIG_WEBSOCKET.get('channels', ["trades", "books5", "tickers"]),
        )
    except ImportError:
        return WebSocketConfig()


def load_health_check_config() -> HealthCheckConfig:
    """P2-5: 从 settings 加载健康检查配置"""
    try:
        from config.settings import CONFIG_HEALTH_CHECK
        return HealthCheckConfig(
            enabled=CONFIG_HEALTH_CHECK.get('enabled', True),
            data_stale_threshold=CONFIG_HEALTH_CHECK.get('data_stale_threshold', 60),
            warning_threshold=CONFIG_HEALTH_CHECK.get('warning_threshold', 30),
            check_interval=CONFIG_HEALTH_CHECK.get('check_interval', 10),
            auto_reconnect_on_stale=CONFIG_HEALTH_CHECK.get('auto_reconnect_on_stale', True),
            max_stale_count_before_alert=CONFIG_HEALTH_CHECK.get('max_stale_count_before_alert', 2),
            recovery_grace_period=CONFIG_HEALTH_CHECK.get('recovery_grace_period', 5),
        )
    except ImportError:
        return HealthCheckConfig()


# 测试代码
async def _test_websocket():
    """测试 WebSocket 连接"""
    ws_config = load_websocket_config()
    health_config = load_health_check_config()
    manager = WebSocketManager("DOGE/USDT", config=ws_config, health_config=health_config)

    # 注册回调
    manager.on('ticker', lambda t: print(f"Ticker: {t['last']}"))
    manager.on('trades', lambda ts: print(f"Trades: {len(ts)} new"))

    # P2-5: 健康检查回调
    manager.on('data_stale', lambda d: print(f"⚠️ Data stale: {d['data_age']:.1f}s"))
    manager.on('data_recovered', lambda d: print(f"✓ Data recovered"))
    manager.on('health_warning', lambda d: print(f"⚡ Health warning: {d['data_age']:.1f}s"))

    if await manager.connect():
        try:
            await asyncio.sleep(30)
            # P2-5: 打印健康状态
            print(f"Health status: {manager.get_health_status()}")
        finally:
            await manager.disconnect()
    else:
        print("连接失败")


if __name__ == "__main__":
    asyncio.run(_test_websocket())
