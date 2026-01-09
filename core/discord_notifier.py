#!/usr/bin/env python3
"""
Flow Radar - Discord Notifier
流动性雷达 - Discord 通知器

通过 Webhook 发送交易警报到 Discord
"""

import asyncio
import time
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from collections import deque

import aiohttp
from rich.console import Console

console = Console()


@dataclass
class AlertMessage:
    """警报消息"""
    timestamp: datetime
    symbol: str
    level: str           # 警报级别: BUY, SELL, WARNING, OPPORTUNITY, INFO
    message: str         # 警报内容
    alert_type: str      # 类型: buy, sell, warning, opportunity, normal
    price: float
    confidence: float    # 置信度 0-100
    state: str = ""      # 市场状态
    score: int = 50      # 综合评分
    extra_fields: Dict = None  # 额外字段


class DiscordNotifier:
    """
    Discord 通知器

    使用 Webhook 发送 Embed 消息到 Discord 频道
    """

    def __init__(self, config: Optional[Dict] = None):
        # 加载配置
        if config is None:
            try:
                from config.settings import CONFIG_DISCORD
                config = CONFIG_DISCORD
            except ImportError:
                config = {}

        self.enabled = config.get('enabled', False)
        self.webhook_url = config.get('webhook_url', '')
        self.min_confidence = config.get('min_confidence', 50)
        self.rate_limit_per_minute = config.get('rate_limit_per_minute', 10)
        self.include_fields = config.get('include_fields', True)

        # 颜色映射
        self.embed_colors = config.get('embed_colors', {
            'buy': 0x00FF00,      # 绿色
            'sell': 0xFF0000,     # 红色
            'warning': 0xFFFF00,  # 黄色
            'opportunity': 0x00BFFF,  # 天蓝色
            'normal': 0x808080,   # 灰色
        })

        # 表情映射
        self.level_emojis = {
            'BUY': ':chart_with_upwards_trend:',
            'SELL': ':chart_with_downwards_trend:',
            'WARNING': ':warning:',
            'OPPORTUNITY': ':loudspeaker:',
            'INFO': ':information_source:',
        }

        # HTTP 会话
        self.session: Optional[aiohttp.ClientSession] = None

        # 速率限制
        self._send_times: deque = deque(maxlen=self.rate_limit_per_minute)

        # 状态
        self._initialized = False
        self._last_error: Optional[str] = None

    async def initialize(self):
        """初始化 HTTP 会话"""
        if not self._initialized and self.enabled:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
            self._initialized = True

    async def close(self):
        """关闭 HTTP 会话"""
        if self.session:
            await self.session.close()
            self.session = None
            self._initialized = False

    def _rate_limit_ok(self) -> bool:
        """检查是否超过速率限制"""
        now = time.time()

        # 清理 1 分钟前的记录
        while self._send_times and now - self._send_times[0] > 60:
            self._send_times.popleft()

        # 检查是否超限
        if len(self._send_times) >= self.rate_limit_per_minute:
            return False

        return True

    def should_notify(self, confidence: float) -> bool:
        """
        判断是否应该发送通知

        Args:
            confidence: 警报置信度

        Returns:
            bool: 是否发送
        """
        if not self.enabled:
            return False

        if not self.webhook_url:
            return False

        if confidence < self.min_confidence:
            return False

        if not self._rate_limit_ok():
            return False

        return True

    def _build_embed(self, alert: AlertMessage) -> Dict:
        """构建 Discord Embed 消息"""
        # 获取颜色
        color = self.embed_colors.get(alert.alert_type, 0x808080)

        # 获取表情
        emoji = self.level_emojis.get(alert.level, ':bell:')

        # 标题
        title = f"{emoji} {alert.level} | {alert.symbol}"

        # 描述
        description = alert.message

        # 构建 embed
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": alert.timestamp.isoformat(),
            "footer": {
                "text": "Flow Radar"
            }
        }

        # 添加字段
        if self.include_fields:
            fields = [
                {
                    "name": ":money_with_wings: 价格",
                    "value": f"${alert.price:.6f}",
                    "inline": True
                },
                {
                    "name": ":dart: 置信度",
                    "value": f"{alert.confidence:.0f}%",
                    "inline": True
                },
                {
                    "name": ":bar_chart: 评分",
                    "value": f"{alert.score}",
                    "inline": True
                },
            ]

            if alert.state:
                fields.append({
                    "name": ":cyclone: 状态",
                    "value": alert.state,
                    "inline": True
                })

            # 添加额外字段
            if alert.extra_fields:
                for key, value in alert.extra_fields.items():
                    fields.append({
                        "name": key,
                        "value": str(value),
                        "inline": True
                    })

            embed["fields"] = fields

        return embed

    async def send(self, alert: AlertMessage) -> bool:
        """
        发送 Discord 通知

        Args:
            alert: 警报消息

        Returns:
            bool: 是否发送成功
        """
        if not self.should_notify(alert.confidence):
            return False

        try:
            await self.initialize()

            embed = self._build_embed(alert)

            payload = {
                "embeds": [embed]
            }

            async with self.session.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 204:  # Discord 成功响应
                    self._send_times.append(time.time())
                    self._last_error = None
                    return True
                elif resp.status == 429:  # 被限速
                    self._last_error = "Rate limited by Discord"
                    console.print("[yellow]Discord 限速，稍后重试[/yellow]")
                    return False
                else:
                    error_text = await resp.text()
                    self._last_error = f"HTTP {resp.status}: {error_text}"
                    console.print(f"[red]Discord 发送失败: {self._last_error}[/red]")
                    return False

        except asyncio.TimeoutError:
            self._last_error = "Request timeout"
            console.print("[yellow]Discord 请求超时[/yellow]")
            return False
        except Exception as e:
            self._last_error = str(e)
            console.print(f"[red]Discord 发送错误: {e}[/red]")
            return False

    async def send_simple(
        self,
        symbol: str,
        level: str,
        message: str,
        alert_type: str = "normal",
        price: float = 0.0,
        confidence: float = 50.0,
        **kwargs
    ) -> bool:
        """
        简化的发送接口

        Args:
            symbol: 交易对
            level: 警报级别
            message: 消息内容
            alert_type: 警报类型
            price: 当前价格
            confidence: 置信度
            **kwargs: 额外参数

        Returns:
            bool: 是否成功
        """
        alert = AlertMessage(
            timestamp=datetime.now(),
            symbol=symbol,
            level=level,
            message=message,
            alert_type=alert_type,
            price=price,
            confidence=confidence,
            state=kwargs.get('state', ''),
            score=kwargs.get('score', 50),
            extra_fields=kwargs.get('extra_fields'),
        )
        return await self.send(alert)

    async def send_bundle_alert(
        self,
        symbol: str,
        signals: List,
        advice: Dict,
        market_state: Optional[Dict] = None
    ) -> bool:
        """
        P3-2 Phase 2: 发送 Bundle 综合告警

        Args:
            symbol: 交易对
            signals: 处理后的 SignalEvent 列表
            advice: 综合建议数据（来自 BundleAdvisor）
            market_state: 市场状态（可选）

        Returns:
            bool: 是否发送成功
        """
        if not self.enabled or not self.webhook_url:
            return False

        try:
            await self.initialize()

            # 使用 BundleAdvisor 格式化消息
            from core.bundle_advisor import BundleAdvisor
            advisor = BundleAdvisor()
            formatted_message = advisor.format_bundle_alert(advice, signals)

            # 添加市场状态信息
            if market_state:
                formatted_message += "\n\n📊 **市场状态**:\n"
                if 'current_price' in market_state:
                    formatted_message += f"当前价格: ${market_state['current_price']:.6f}\n"
                if 'cvd_total' in market_state:
                    formatted_message += f"CVD: {market_state['cvd_total']:.2f}\n"
                if 'whale_flow' in market_state:
                    formatted_message += f"鲸鱼流: ${market_state['whale_flow']:.2f}\n"

            # 确定颜色（根据建议级别）
            advice_level = advice.get('advice', 'WATCH')
            if advice_level == 'STRONG_BUY':
                color = 0x00FF00  # 绿色
            elif advice_level == 'BUY':
                color = 0x7FFF00  # 黄绿色
            elif advice_level == 'WATCH':
                color = 0xFFFF00  # 黄色
            elif advice_level == 'SELL':
                color = 0xFF8C00  # 橙色
            elif advice_level == 'STRONG_SELL':
                color = 0xFF0000  # 红色
            else:
                color = 0x808080  # 灰色

            # 构建 embed
            embed = {
                "title": f"🔔 综合信号告警 - {symbol}",
                "description": formatted_message,
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "footer": {
                    "text": f"Flow Radar - P3-2 Phase 2 | 信号数: {len(signals)}"
                }
            }

            payload = {
                "embeds": [embed]
            }

            # 发送
            async with self.session.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status == 204:
                    self._send_times.append(time.time())
                    self._last_error = None
                    console.print(f"[green]Bundle 告警已发送: {advice_level}[/green]")
                    return True
                elif resp.status == 429:
                    self._last_error = "Rate limited by Discord"
                    console.print("[yellow]Discord 限速，Bundle 告警未发送[/yellow]")
                    return False
                else:
                    error_text = await resp.text()
                    self._last_error = f"HTTP {resp.status}: {error_text}"
                    console.print(f"[red]Bundle 告警发送失败: {self._last_error}[/red]")
                    return False

        except Exception as e:
            self._last_error = str(e)
            console.print(f"[red]Bundle 告警发送错误: {e}[/red]")
            return False

    @property
    def status(self) -> Dict:
        """获取通知器状态"""
        return {
            'enabled': self.enabled,
            'configured': bool(self.webhook_url),
            'sends_in_last_minute': len(self._send_times),
            'rate_limit': self.rate_limit_per_minute,
            'last_error': self._last_error,
        }


# 全局实例 (可选)
_notifier: Optional[DiscordNotifier] = None


def get_discord_notifier() -> DiscordNotifier:
    """获取全局 Discord 通知器实例"""
    global _notifier
    if _notifier is None:
        _notifier = DiscordNotifier()
    return _notifier


# 测试代码
async def _test_discord():
    """测试 Discord 通知"""
    notifier = DiscordNotifier()

    if not notifier.enabled:
        print("Discord 通知未启用，请设置 DISCORD_WEBHOOK_URL 环境变量")
        return

    success = await notifier.send_simple(
        symbol="DOGE/USDT",
        level="INFO",
        message="这是一条测试消息",
        alert_type="normal",
        price=0.12345,
        confidence=75.0,
        state="测试状态",
        score=65,
    )

    print(f"发送结果: {'成功' if success else '失败'}")
    print(f"状态: {notifier.status}")

    await notifier.close()


if __name__ == "__main__":
    asyncio.run(_test_discord())
