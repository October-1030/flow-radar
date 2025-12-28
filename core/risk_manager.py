"""
Shell Market Watcher - Risk Manager
风险管理模块

职责: 仓位管理、止损控制、风控熔断、账户风险监控
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import json
from pathlib import Path

from config.settings import CONFIG_RISK, LOG_DIR


logger = logging.getLogger('RiskManager')


class RiskLevel(Enum):
    """风险等级"""
    LOW = "低风险"
    MEDIUM = "中等风险"
    HIGH = "高风险"
    CRITICAL = "危险"


class PositionStatus(Enum):
    """持仓状态"""
    OPEN = "持仓中"
    CLOSED = "已平仓"
    STOPPED_OUT = "止损出场"
    TAKE_PROFIT = "止盈出场"


@dataclass
class Position:
    """持仓记录"""
    id: str
    symbol: str
    direction: str                  # 'LONG' or 'SHORT'
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: float
    take_profit: Optional[float] = None
    status: PositionStatus = PositionStatus.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl: float = 0.0
    r_multiple: float = 0.0
    notes: str = ""

    @property
    def initial_risk(self) -> float:
        """初始风险（1R）"""
        if self.direction == 'LONG':
            return (self.entry_price - self.stop_loss) * self.quantity
        else:
            return (self.stop_loss - self.entry_price) * self.quantity

    def calculate_pnl(self, current_price: float) -> float:
        """计算当前盈亏"""
        if self.direction == 'LONG':
            return (current_price - self.entry_price) * self.quantity
        else:
            return (self.entry_price - current_price) * self.quantity

    def calculate_r_multiple(self, current_price: float) -> float:
        """计算R倍数"""
        if self.initial_risk == 0:
            return 0
        pnl = self.calculate_pnl(current_price)
        return pnl / self.initial_risk


@dataclass
class AccountState:
    """账户状态"""
    balance: float
    equity: float
    margin_used: float
    margin_available: float
    unrealized_pnl: float
    realized_pnl_today: float
    daily_trades: int
    consecutive_losses: int
    peak_equity: float              # 历史最高净值
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def margin_ratio(self) -> float:
        """保证金使用率"""
        if self.equity == 0:
            return 0
        return self.margin_used / self.equity

    @property
    def risk_ratio(self) -> float:
        """风险率 = 已用保证金 / 总权益"""
        if self.equity == 0:
            return 1.0
        return self.margin_used / self.equity

    @property
    def drawdown(self) -> float:
        """当前回撤"""
        if self.peak_equity == 0:
            return 0
        return (self.peak_equity - self.equity) / self.peak_equity

    @property
    def daily_pnl_pct(self) -> float:
        """当日盈亏百分比"""
        if self.balance == 0:
            return 0
        return self.realized_pnl_today / self.balance


class CircuitBreaker:
    """熔断机制"""

    def __init__(self):
        self.triggered = False
        self.trigger_time: Optional[datetime] = None
        self.trigger_reason: str = ""
        self.resume_time: Optional[datetime] = None

    def trigger(self, reason: str):
        """触发熔断"""
        self.triggered = True
        self.trigger_time = datetime.now()
        self.trigger_reason = reason
        self.resume_time = self.trigger_time + timedelta(
            seconds=CONFIG_RISK['circuit_breaker_duration']
        )
        logger.warning(f"[熔断触发] 原因: {reason} | 预计恢复: {self.resume_time}")

    def check_resume(self) -> bool:
        """检查是否可以恢复"""
        if not self.triggered:
            return True

        if datetime.now() >= self.resume_time:
            self.triggered = False
            self.trigger_reason = ""
            logger.info("[熔断解除] 交易已恢复")
            return True

        return False

    @property
    def remaining_seconds(self) -> int:
        """剩余熔断时间"""
        if not self.triggered or not self.resume_time:
            return 0
        remaining = (self.resume_time - datetime.now()).total_seconds()
        return max(0, int(remaining))


class RiskManager:
    """风险管理器"""

    def __init__(self, initial_balance: float = 10000):
        self.positions: List[Position] = []
        self.position_history: List[Position] = []
        self.position_counter = 0

        # 账户状态
        self.account = AccountState(
            balance=initial_balance,
            equity=initial_balance,
            margin_used=0,
            margin_available=initial_balance,
            unrealized_pnl=0,
            realized_pnl_today=0,
            daily_trades=0,
            consecutive_losses=0,
            peak_equity=initial_balance
        )

        # 熔断机制
        self.circuit_breaker = CircuitBreaker()

        # 冷却状态
        self.cooldown_until: Optional[datetime] = None

    def _generate_position_id(self) -> str:
        """生成持仓ID"""
        self.position_counter += 1
        return f"POS_{datetime.now().strftime('%Y%m%d')}_{self.position_counter:04d}"

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        confidence: float = 50
    ) -> Tuple[float, float]:
        """
        计算仓位大小
        返回: (数量, 风险金额)
        """
        # 基础风险 = 账户净值 * 单笔最大风险
        base_risk = self.account.equity * CONFIG_RISK['max_risk_per_trade']

        # 根据置信度调整风险
        confidence_multiplier = 0.5 + (confidence / 100) * 0.5  # 0.5 - 1.0
        adjusted_risk = base_risk * confidence_multiplier

        # 计算每单位风险
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return 0, 0

        # 计算数量
        quantity = adjusted_risk / risk_per_unit

        # 检查最大仓位限制
        max_position_value = self.account.equity * CONFIG_RISK['max_position_size']
        max_quantity = max_position_value / entry_price
        quantity = min(quantity, max_quantity)

        # 检查杠杆限制
        required_margin = entry_price * quantity / CONFIG_RISK['max_leverage']
        if required_margin > self.account.margin_available:
            quantity = self.account.margin_available * CONFIG_RISK['max_leverage'] / entry_price

        actual_risk = quantity * risk_per_unit

        return quantity, actual_risk

    def can_open_position(self) -> Tuple[bool, str]:
        """检查是否可以开仓"""
        # 检查熔断
        if self.circuit_breaker.triggered:
            if not self.circuit_breaker.check_resume():
                return False, f"熔断中，剩余 {self.circuit_breaker.remaining_seconds}s"

        # 检查冷却
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now()).total_seconds()
            return False, f"冷却中，剩余 {int(remaining)}s"

        # 检查保证金
        if self.account.margin_ratio >= CONFIG_RISK['margin_call_threshold']:
            return False, "保证金不足"

        # 检查最大回撤
        if self.account.drawdown >= CONFIG_RISK['max_drawdown']:
            return False, f"回撤超限 ({self.account.drawdown:.1%})"

        # 检查日亏损
        if abs(self.account.daily_pnl_pct) >= CONFIG_RISK['max_daily_loss']:
            if self.account.daily_pnl_pct < 0:
                return False, f"日亏损超限 ({self.account.daily_pnl_pct:.1%})"

        # 检查连续亏损
        if self.account.consecutive_losses >= CONFIG_RISK['max_consecutive_losses']:
            self.cooldown_until = datetime.now() + timedelta(
                seconds=CONFIG_RISK['cooldown_after_loss_streak']
            )
            return False, f"连续亏损 {self.account.consecutive_losses} 次，进入冷却"

        return True, "OK"

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        confidence: float = 50
    ) -> Optional[Position]:
        """开仓"""
        # 检查是否可以开仓
        can_open, reason = self.can_open_position()
        if not can_open:
            logger.warning(f"无法开仓: {reason}")
            return None

        # 计算仓位
        quantity, risk_amount = self.calculate_position_size(entry_price, stop_loss, confidence)
        if quantity <= 0:
            logger.warning("计算仓位为0，无法开仓")
            return None

        # 验证盈亏比
        if take_profit:
            if direction == 'LONG':
                potential_profit = (take_profit - entry_price) * quantity
            else:
                potential_profit = (entry_price - take_profit) * quantity

            r_ratio = potential_profit / risk_amount if risk_amount > 0 else 0
            if r_ratio < CONFIG_RISK['min_r_multiple']:
                logger.warning(f"盈亏比不足: {r_ratio:.2f}R < {CONFIG_RISK['min_r_multiple']}R")
                return None

        # 创建持仓
        position = Position(
            id=self._generate_position_id(),
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        self.positions.append(position)
        self.account.daily_trades += 1

        # 更新保证金
        margin_required = entry_price * quantity / CONFIG_RISK['max_leverage']
        self.account.margin_used += margin_required
        self.account.margin_available -= margin_required

        logger.info(f"[开仓] {position.id} | {direction} {symbol} @ {entry_price} | "
                   f"数量: {quantity:.4f} | 止损: {stop_loss} | 风险: ${risk_amount:.2f}")

        return position

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        reason: str = ""
    ) -> Optional[Position]:
        """平仓"""
        position = None
        for p in self.positions:
            if p.id == position_id:
                position = p
                break

        if not position:
            logger.warning(f"未找到持仓: {position_id}")
            return None

        # 计算盈亏
        position.exit_price = exit_price
        position.exit_time = datetime.now()
        position.pnl = position.calculate_pnl(exit_price)
        position.r_multiple = position.calculate_r_multiple(exit_price)
        position.notes = reason

        # 确定平仓类型
        if position.direction == 'LONG':
            if exit_price <= position.stop_loss:
                position.status = PositionStatus.STOPPED_OUT
            elif position.take_profit and exit_price >= position.take_profit:
                position.status = PositionStatus.TAKE_PROFIT
            else:
                position.status = PositionStatus.CLOSED
        else:
            if exit_price >= position.stop_loss:
                position.status = PositionStatus.STOPPED_OUT
            elif position.take_profit and exit_price <= position.take_profit:
                position.status = PositionStatus.TAKE_PROFIT
            else:
                position.status = PositionStatus.CLOSED

        # 更新账户
        self.account.realized_pnl_today += position.pnl
        self.account.balance += position.pnl
        self.account.equity += position.pnl

        # 更新峰值
        if self.account.equity > self.account.peak_equity:
            self.account.peak_equity = self.account.equity

        # 释放保证金
        margin_released = position.entry_price * position.quantity / CONFIG_RISK['max_leverage']
        self.account.margin_used -= margin_released
        self.account.margin_available += margin_released

        # 更新连续亏损
        if position.pnl < 0:
            self.account.consecutive_losses += 1
        else:
            self.account.consecutive_losses = 0

        # 检查是否触发熔断
        if CONFIG_RISK['circuit_breaker_enabled']:
            if abs(self.account.daily_pnl_pct) >= CONFIG_RISK['circuit_breaker_loss_pct']:
                if self.account.daily_pnl_pct < 0:
                    self.circuit_breaker.trigger(f"日亏损 {self.account.daily_pnl_pct:.1%}")

        # 移动到历史
        self.positions.remove(position)
        self.position_history.append(position)

        logger.info(f"[平仓] {position.id} | {position.status.value} @ {exit_price} | "
                   f"盈亏: ${position.pnl:.2f} ({position.r_multiple:.2f}R) | {reason}")

        return position

    def check_stop_losses(self, current_price: float) -> List[Position]:
        """检查止损"""
        stopped = []
        for position in self.positions[:]:
            should_stop = False

            if position.direction == 'LONG' and current_price <= position.stop_loss:
                should_stop = True
            elif position.direction == 'SHORT' and current_price >= position.stop_loss:
                should_stop = True

            if should_stop:
                self.close_position(position.id, current_price, "触发止损")
                stopped.append(position)

        return stopped

    def check_take_profits(self, current_price: float) -> List[Position]:
        """检查止盈"""
        profits = []
        for position in self.positions[:]:
            if not position.take_profit:
                continue

            should_profit = False

            if position.direction == 'LONG' and current_price >= position.take_profit:
                should_profit = True
            elif position.direction == 'SHORT' and current_price <= position.take_profit:
                should_profit = True

            if should_profit:
                self.close_position(position.id, current_price, "触发止盈")
                profits.append(position)

        return profits

    def update_unrealized_pnl(self, current_prices: Dict[str, float]):
        """更新未实现盈亏"""
        total_unrealized = 0
        for position in self.positions:
            price = current_prices.get(position.symbol, position.entry_price)
            total_unrealized += position.calculate_pnl(price)

        self.account.unrealized_pnl = total_unrealized
        self.account.equity = self.account.balance + total_unrealized
        self.account.last_updated = datetime.now()

    def get_risk_level(self) -> RiskLevel:
        """获取当前风险等级"""
        # 综合评估
        risk_score = 0

        # 保证金使用率
        if self.account.margin_ratio > 0.8:
            risk_score += 3
        elif self.account.margin_ratio > 0.6:
            risk_score += 2
        elif self.account.margin_ratio > 0.4:
            risk_score += 1

        # 回撤
        if self.account.drawdown > 0.1:
            risk_score += 3
        elif self.account.drawdown > 0.05:
            risk_score += 2
        elif self.account.drawdown > 0.02:
            risk_score += 1

        # 日亏损
        if self.account.daily_pnl_pct < -0.03:
            risk_score += 3
        elif self.account.daily_pnl_pct < -0.02:
            risk_score += 2
        elif self.account.daily_pnl_pct < -0.01:
            risk_score += 1

        # 连续亏损
        risk_score += min(3, self.account.consecutive_losses)

        # 判定等级
        if risk_score >= 8:
            return RiskLevel.CRITICAL
        elif risk_score >= 5:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def get_status_summary(self) -> Dict:
        """获取状态摘要"""
        return {
            'balance': self.account.balance,
            'equity': self.account.equity,
            'unrealized_pnl': self.account.unrealized_pnl,
            'realized_pnl_today': self.account.realized_pnl_today,
            'margin_ratio': self.account.margin_ratio,
            'risk_ratio': self.account.risk_ratio,
            'drawdown': self.account.drawdown,
            'risk_level': self.get_risk_level().value,
            'open_positions': len(self.positions),
            'daily_trades': self.account.daily_trades,
            'consecutive_losses': self.account.consecutive_losses,
            'circuit_breaker_active': self.circuit_breaker.triggered,
            'can_trade': self.can_open_position()[0]
        }

    def reset_daily_stats(self):
        """重置每日统计"""
        self.account.realized_pnl_today = 0
        self.account.daily_trades = 0
        logger.info("每日统计已重置")

    def get_performance_stats(self) -> Dict:
        """获取绩效统计"""
        if not self.position_history:
            return {'message': '暂无历史交易'}

        wins = [p for p in self.position_history if p.pnl > 0]
        losses = [p for p in self.position_history if p.pnl < 0]

        total_profit = sum(p.pnl for p in wins)
        total_loss = abs(sum(p.pnl for p in losses))

        win_rate = len(wins) / len(self.position_history) * 100 if self.position_history else 0
        profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')

        avg_win = total_profit / len(wins) if wins else 0
        avg_loss = total_loss / len(losses) if losses else 0

        avg_r = sum(p.r_multiple for p in self.position_history) / len(self.position_history)

        return {
            'total_trades': len(self.position_history),
            'winning_trades': len(wins),
            'losing_trades': len(losses),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'net_profit': total_profit - total_loss,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_r_multiple': avg_r,
            'best_trade': max(self.position_history, key=lambda p: p.pnl).pnl if self.position_history else 0,
            'worst_trade': min(self.position_history, key=lambda p: p.pnl).pnl if self.position_history else 0
        }
