#!/usr/bin/env python3
"""
Flow Radar - Derivatives Data Module
流动性雷达 - 合约数据模块

获取资金费率、持仓量、爆仓数据、多空比等
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class FundingRateData:
    """资金费率数据"""
    symbol: str
    funding_rate: float          # 当前资金费率
    next_funding_time: datetime  # 下次结算时间
    predicted_rate: float        # 预测资金费率

    @property
    def is_overheated_long(self) -> bool:
        """多头过热 (费率 > 0.1%)"""
        return self.funding_rate > 0.001

    @property
    def is_overheated_short(self) -> bool:
        """空头过热 (费率 < -0.1%)"""
        return self.funding_rate < -0.001

    @property
    def sentiment(self) -> str:
        """市场情绪"""
        if self.funding_rate > 0.001:
            return "极度贪婪"
        elif self.funding_rate > 0.0005:
            return "贪婪"
        elif self.funding_rate > 0:
            return "偏多"
        elif self.funding_rate > -0.0005:
            return "偏空"
        elif self.funding_rate > -0.001:
            return "恐惧"
        else:
            return "极度恐惧"


@dataclass
class OpenInterestData:
    """持仓量数据"""
    symbol: str
    open_interest: float         # 持仓量 (张)
    open_interest_value: float   # 持仓价值 (USD)
    oi_change_24h: float         # 24h变化百分比

    @property
    def leverage_warning(self) -> str:
        """杠杆警告"""
        if self.oi_change_24h > 20:
            return "高杠杆风险"
        elif self.oi_change_24h > 10:
            return "杠杆上升"
        elif self.oi_change_24h < -20:
            return "去杠杆中"
        elif self.oi_change_24h < -10:
            return "杠杆下降"
        return "正常"


@dataclass
class LongShortRatioData:
    """多空比数据"""
    symbol: str
    long_ratio: float            # 多头占比
    short_ratio: float           # 空头占比
    long_short_ratio: float      # 多空比
    timestamp: datetime

    @property
    def contrarian_signal(self) -> str:
        """反向信号 (散户多则看空)"""
        if self.long_short_ratio > 2.0:
            return "散户极度看多, 警惕下跌"
        elif self.long_short_ratio > 1.5:
            return "散户偏多, 谨慎"
        elif self.long_short_ratio < 0.5:
            return "散户极度看空, 可能反弹"
        elif self.long_short_ratio < 0.67:
            return "散户偏空, 关注反弹"
        return "多空均衡"


@dataclass
class LiquidationData:
    """爆仓数据"""
    symbol: str
    long_liquidations_24h: float    # 24h多头爆仓 (USD)
    short_liquidations_24h: float   # 24h空头爆仓 (USD)
    total_liquidations_24h: float   # 24h总爆仓 (USD)
    largest_single: float           # 最大单笔爆仓
    recent_liquidations: List[Dict] = field(default_factory=list)

    @property
    def liquidation_bias(self) -> str:
        """爆仓偏向"""
        if self.total_liquidations_24h == 0:
            return "无数据"
        long_pct = self.long_liquidations_24h / self.total_liquidations_24h
        if long_pct > 0.7:
            return "多头血洗"
        elif long_pct > 0.55:
            return "多头承压"
        elif long_pct < 0.3:
            return "空头血洗"
        elif long_pct < 0.45:
            return "空头承压"
        return "双向爆仓"


@dataclass
class BinnedCVD:
    """分级CVD - 按交易规模分类"""
    whale_cvd: float = 0.0       # 鲸鱼 CVD (>$50k)
    shark_cvd: float = 0.0       # 鲨鱼 CVD ($10k-$50k)
    retail_cvd: float = 0.0      # 散户 CVD (<$10k)

    @property
    def whale_direction(self) -> str:
        if self.whale_cvd > 5000:
            return "鲸鱼买入"
        elif self.whale_cvd < -5000:
            return "鲸鱼卖出"
        return "鲸鱼观望"

    @property
    def retail_direction(self) -> str:
        if self.retail_cvd > 3000:
            return "散户买入"
        elif self.retail_cvd < -3000:
            return "散户卖出"
        return "散户观望"

    @property
    def smart_money_signal(self) -> str:
        """聪明钱信号 - 鲸鱼和散户反向时"""
        if self.whale_cvd > 5000 and self.retail_cvd < -3000:
            return "聪明钱买入, 散户恐慌"
        elif self.whale_cvd < -5000 and self.retail_cvd > 3000:
            return "聪明钱出货, 散户接盘"
        return ""


class DerivativesDataFetcher:
    """合约数据获取器"""

    def __init__(self, exchange: str = "okx"):
        self.exchange = exchange
        self.session: Optional[aiohttp.ClientSession] = None

        # API endpoints
        self.endpoints = {
            "okx": {
                "funding_rate": "https://www.okx.com/api/v5/public/funding-rate",
                "open_interest": "https://www.okx.com/api/v5/public/open-interest",
                "long_short_ratio": "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio",
                "liquidations": "https://www.okx.com/api/v5/public/liquidation-orders",
            }
        }

    async def initialize(self):
        """初始化HTTP会话"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """关闭HTTP会话"""
        if self.session:
            await self.session.close()
            self.session = None

    def _get_swap_symbol(self, symbol: str) -> str:
        """转换为合约交易对格式"""
        # DOGE/USDT -> DOGE-USDT-SWAP
        base = symbol.replace("/", "-")
        return f"{base}-SWAP"

    async def fetch_funding_rate(self, symbol: str) -> Optional[FundingRateData]:
        """获取资金费率"""
        try:
            await self.initialize()
            swap_symbol = self._get_swap_symbol(symbol)

            url = self.endpoints[self.exchange]["funding_rate"]
            params = {"instId": swap_symbol}

            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "0" and data.get("data"):
                        item = data["data"][0]
                        return FundingRateData(
                            symbol=symbol,
                            funding_rate=float(item.get("fundingRate", 0)),
                            next_funding_time=datetime.fromtimestamp(
                                int(item.get("nextFundingTime", 0)) / 1000
                            ),
                            predicted_rate=float(item.get("nextFundingRate", 0) or 0)
                        )
        except Exception as e:
            pass
        return None

    async def fetch_open_interest(self, symbol: str) -> Optional[OpenInterestData]:
        """获取持仓量"""
        try:
            await self.initialize()
            swap_symbol = self._get_swap_symbol(symbol)

            url = self.endpoints[self.exchange]["open_interest"]
            params = {"instType": "SWAP", "instId": swap_symbol}

            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "0" and data.get("data"):
                        item = data["data"][0]
                        return OpenInterestData(
                            symbol=symbol,
                            open_interest=float(item.get("oi", 0)),
                            open_interest_value=float(item.get("oiCcy", 0)),
                            oi_change_24h=0  # OKX API doesn't provide this directly
                        )
        except Exception as e:
            pass
        return None

    async def fetch_long_short_ratio(self, symbol: str) -> Optional[LongShortRatioData]:
        """获取多空比"""
        try:
            await self.initialize()
            # OKX uses base currency for this endpoint
            base_ccy = symbol.split("/")[0]

            url = self.endpoints[self.exchange]["long_short_ratio"]
            params = {"ccy": base_ccy, "period": "5m"}

            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "0" and data.get("data"):
                        item = data["data"][0]
                        ls_ratio = float(item.get("longShortRatio", 1))
                        long_ratio = ls_ratio / (1 + ls_ratio)
                        short_ratio = 1 / (1 + ls_ratio)
                        return LongShortRatioData(
                            symbol=symbol,
                            long_ratio=long_ratio * 100,
                            short_ratio=short_ratio * 100,
                            long_short_ratio=ls_ratio,
                            timestamp=datetime.fromtimestamp(
                                int(item.get("ts", 0)) / 1000
                            )
                        )
        except Exception as e:
            pass
        return None

    async def fetch_liquidations(self, symbol: str) -> Optional[LiquidationData]:
        """获取爆仓数据"""
        try:
            await self.initialize()
            swap_symbol = self._get_swap_symbol(symbol)

            url = self.endpoints[self.exchange]["liquidations"]
            params = {
                "instType": "SWAP",
                "instId": swap_symbol,
                "state": "filled",
                "limit": "100"
            }

            async with self.session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") == "0" and data.get("data"):
                        items = data["data"]

                        long_liq = 0.0
                        short_liq = 0.0
                        largest = 0.0
                        recent = []

                        for item in items:
                            details = item.get("details", [])
                            for d in details:
                                side = d.get("side", "")
                                sz = float(d.get("sz", 0))
                                px = float(d.get("bkPx", 0))
                                value = sz * px

                                if side == "buy":  # Short position liquidated
                                    short_liq += value
                                else:  # Long position liquidated
                                    long_liq += value

                                largest = max(largest, value)
                                recent.append({
                                    "side": "空" if side == "buy" else "多",
                                    "value": value,
                                    "price": px
                                })

                        return LiquidationData(
                            symbol=symbol,
                            long_liquidations_24h=long_liq,
                            short_liquidations_24h=short_liq,
                            total_liquidations_24h=long_liq + short_liq,
                            largest_single=largest,
                            recent_liquidations=recent[:10]
                        )
        except Exception as e:
            pass
        return None

    async def fetch_all(self, symbol: str) -> Dict:
        """获取所有合约数据"""
        funding, oi, ls_ratio, liquidations = await asyncio.gather(
            self.fetch_funding_rate(symbol),
            self.fetch_open_interest(symbol),
            self.fetch_long_short_ratio(symbol),
            self.fetch_liquidations(symbol),
            return_exceptions=True
        )

        return {
            "funding_rate": funding if not isinstance(funding, Exception) else None,
            "open_interest": oi if not isinstance(oi, Exception) else None,
            "long_short_ratio": ls_ratio if not isinstance(ls_ratio, Exception) else None,
            "liquidations": liquidations if not isinstance(liquidations, Exception) else None
        }


def calculate_binned_cvd(trades: List[Dict], price: float) -> BinnedCVD:
    """计算分级CVD"""
    binned = BinnedCVD()

    for trade in trades:
        value = trade['price'] * trade['quantity']
        is_buy = not trade.get('is_buyer_maker', True)
        delta = value if is_buy else -value

        if value >= 50000:  # 鲸鱼 > $50k
            binned.whale_cvd += delta
        elif value >= 10000:  # 鲨鱼 $10k-$50k
            binned.shark_cvd += delta
        else:  # 散户 < $10k
            binned.retail_cvd += delta

    return binned


def predict_liquidation_cascade(
    funding_rate: Optional[FundingRateData],
    oi: Optional[OpenInterestData],
    ls_ratio: Optional[LongShortRatioData],
    price_change_pct: float
) -> Tuple[str, str]:
    """
    预测爆仓瀑布
    返回: (风险等级, 描述)
    """
    if not funding_rate or not oi:
        return "", ""

    risk_score = 0
    direction = ""

    # 资金费率极端
    if funding_rate.is_overheated_long:
        risk_score += 30
        direction = "多头"
    elif funding_rate.is_overheated_short:
        risk_score += 30
        direction = "空头"

    # 持仓量高
    if oi and oi.oi_change_24h > 15:
        risk_score += 20

    # 多空比极端
    if ls_ratio:
        if ls_ratio.long_short_ratio > 2.0:
            risk_score += 25
            direction = "多头"
        elif ls_ratio.long_short_ratio < 0.5:
            risk_score += 25
            direction = "空头"

    # 价格剧烈波动
    if abs(price_change_pct) > 5:
        risk_score += 25

    # 生成警告
    if risk_score >= 70:
        return "极高", f"⚠️ {direction}爆仓瀑布风险极高! 建议减仓避险"
    elif risk_score >= 50:
        return "高", f"⚡ {direction}爆仓风险上升, 注意止损"
    elif risk_score >= 30:
        return "中", f"📊 市场杠杆偏高, 保持警惕"

    return "", ""
