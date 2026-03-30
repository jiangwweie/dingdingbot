"""
Feishu (Lark) Webhook Notification Service - Phase 5

Supports 6 alert event types:
- ORDER_FILLED: Order execution notification
- ORDER_FAILED: Order failure alert
- CAPITAL_PROTECTION_TRIGGERED: Capital protection triggered
- RECONCILIATION_MISMATCH: Reconciliation discrepancy
- CONNECTION_LOST: WebSocket connection lost
- DAILY_LOSS_LIMIT: Daily loss limit exceeded

Reference: docs/designs/phase5-detailed-design.md (v1.1) - Section 3.6
"""
import asyncio
import time
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

import aiohttp

from src.domain.models import Order, ReconciliationReport, Direction
from src.infrastructure.logger import logger


# ============================================================
# Alert Event Types and Levels
# ============================================================

class AlertEventType:
    """Alert event type constants"""
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_FAILED = "ORDER_FAILED"
    CAPITAL_PROTECTION_TRIGGERED = "CAPITAL_PROTECTION_TRIGGERED"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    CONNECTION_LOST = "CONNECTION_LOST"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"


class AlertLevel:
    """Alert level constants"""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# Event type to level mapping
EVENT_LEVEL_MAP = {
    AlertEventType.ORDER_FILLED: AlertLevel.INFO,
    AlertEventType.ORDER_FAILED: AlertLevel.WARNING,
    AlertEventType.CAPITAL_PROTECTION_TRIGGERED: AlertLevel.WARNING,
    AlertEventType.RECONCILIATION_MISMATCH: AlertLevel.ERROR,
    AlertEventType.CONNECTION_LOST: AlertLevel.ERROR,
    AlertEventType.DAILY_LOSS_LIMIT: AlertLevel.ERROR,
}


# Level to color template mapping (Feishu card header colors)
LEVEL_COLOR_MAP = {
    AlertLevel.INFO: "blue",
    AlertLevel.WARNING: "orange",
    AlertLevel.ERROR: "red",
}


# Level to title prefix mapping
LEVEL_PREFIX_MAP = {
    AlertLevel.INFO: "ℹ️",
    AlertLevel.WARNING: "⚠️",
    AlertLevel.ERROR: "🚨",
}


# ============================================================
# Feishu Card Message Templates
# ============================================================

def format_feishu_card(
    title: str,
    elements: List[Dict[str, Any]],
    level: str = AlertLevel.INFO,
) -> Dict[str, Any]:
    """
    Format Feishu interactive card message.

    Args:
        title: Card title
        elements: Card elements (div, markdown, etc.)
        level: Alert level (INFO, WARNING, ERROR)

    Returns:
        Feishu card payload dict
    """
    color = LEVEL_COLOR_MAP.get(level, "blue")
    prefix = LEVEL_PREFIX_MAP.get(level, "")

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"{prefix} {title}"
                },
                "template": color
            },
            "elements": elements
        }
    }


def format_div_element(text: str) -> Dict[str, Any]:
    """Format a div element with markdown text"""
    return {
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": text
        }
    }


def format_hr_element() -> Dict[str, Any]:
    """Format a horizontal rule element"""
    return {"tag": "hr"}


def format_note_element(text: str, note_type: str = "info") -> Dict[str, Any]:
    """Format a note element"""
    return {
        "tag": "note",
        "elements": [
            {
                "tag": "plain_text",
                "content": text
            }
        ]
    }


# ============================================================
# Message Formatters for Each Event Type
# ============================================================

def format_order_filled_message(order: Order, pnl: Decimal) -> Dict[str, Any]:
    """
    Format order filled notification message.

    Args:
        order: Order object with execution details
        pnl: Realized PnL in USDT

    Returns:
        Feishu card payload
    """
    # Direction formatting
    if order.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "做多"
    else:
        direction_icon = "🔴"
        direction_text = "做空"

    # Order role formatting
    role_map = {
        "ENTRY": "开仓",
        "TP1": "止盈 1",
        "TP2": "止盈 2",
        "TP3": "止盈 3",
        "SL": "止损",
    }
    role_text = role_map.get(order.order_role.value, order.order_role.value)

    # PnL formatting
    pnl_sign = "+" if pnl >= 0 else ""
    pnl_color = "green" if pnl >= 0 else "red"

    content = f"""**订单角色**: {role_text}
**币种**: {order.symbol}
**方向**: {direction_icon} {direction_text}
**订单类型**: {order.order_type.value}
**成交数量**: `{order.filled_qty}`
**成交均价**: `{order.average_exec_price}`
**实现盈亏**: <font color="{pnl_color}">{pnl_sign}{pnl:.2f} USDT</font>
**手续费**: `{order.fee_paid if hasattr(order, 'fee_paid') else Decimal('0')}`
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    elements = [format_div_element(content)]

    return format_feishu_card(
        title="订单成交通知",
        elements=elements,
        level=AlertLevel.INFO
    )


def format_order_failed_message(order: Order, reason: str) -> Dict[str, Any]:
    """
    Format order failed alert message.

    Args:
        order: Order object
        reason: Failure reason

    Returns:
        Feishu card payload
    """
    if order.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "做多"
    else:
        direction_icon = "🔴"
        direction_text = "做空"

    content = f"""**订单 ID**: `{order.id}`
**币种**: {order.symbol}
**方向**: {direction_icon} {direction_text}
**订单类型**: {order.order_type.value}
**委托数量**: `{order.requested_qty}`
**失败原因**: {reason}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    elements = [format_div_element(content)]

    return format_feishu_card(
        title="订单失败告警",
        elements=elements,
        level=AlertLevel.WARNING
    )


def format_capital_protection_message(reason: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Format capital protection triggered alert.

    Args:
        reason: Reason code (e.g., "SINGLE_TRADE_LOSS_LIMIT")
        details: Optional detailed information

    Returns:
        Feishu card payload
    """
    reason_map = {
        "SINGLE_TRADE_LOSS_LIMIT": "单笔交易损失超限",
        "POSITION_LIMIT": "仓位占比超限",
        "DAILY_LOSS_LIMIT": "每日亏损超限",
        "DAILY_TRADE_COUNT_LIMIT": "每日交易次数超限",
        "INSUFFICIENT_BALANCE": "账户余额不足",
    }

    reason_text = reason_map.get(reason, reason)

    content = f"""**保护类型**: 资金保护触发
**拒绝原因**: {reason_text}
**详细说明**: {details.get('message', '无') if details else '无'}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    elements = [format_div_element(content)]

    if details:
        detail_lines = []
        for key, value in details.items():
            if key != 'message':
                detail_lines.append(f"**{key}**: {value}")
        if detail_lines:
            elements.append(format_div_element("\n".join(detail_lines)))

    return format_feishu_card(
        title="资金保护触发告警",
        elements=elements,
        level=AlertLevel.WARNING
    )


def format_reconciliation_mismatch_message(report: ReconciliationReport) -> Dict[str, Any]:
    """
    Format reconciliation mismatch alert.

    Args:
        report: ReconciliationReport object

    Returns:
        Feishu card payload
    """
    mismatch_count = len(report.position_mismatches) + len(report.order_mismatches)
    missing_count = len(report.missing_positions) + len(report.orphan_orders)

    content = f"""**币种**: {report.symbol}
**对账时间**: {datetime.fromtimestamp(report.reconciliation_time / 1000).strftime('%Y-%m-%d %H:%M:%S')}
**宽限期**: {report.grace_period_seconds}秒

**差异统计**:
- 仓位不匹配：{len(report.position_mismatches)} 笔
- 订单不匹配：{len(report.order_mismatches)} 笔
- 缺失仓位：{len(report.missing_positions)} 笔
- 孤儿订单：{len(report.orphan_orders)} 笔

**总差异数**: {report.total_discrepancies}
**需要介入**: {"是" if report.requires_attention else "否"}
**结论**: {report.summary}"""

    elements = [format_div_element(content)]

    # Add position mismatches details if any
    if report.position_mismatches:
        elements.append(format_hr_element())
        elements.append(format_div_element("**仓位不匹配详情:**"))
        for mismatch in report.position_mismatches[:3]:  # Limit to first 3
            elements.append(format_div_element(
                f"• {mismatch.symbol}: 本地={mismatch.local_qty}, 交易所={mismatch.exchange_qty}, 差异={mismatch.discrepancy}"
            ))

    # Add order mismatches details if any
    if report.order_mismatches:
        elements.append(format_hr_element())
        elements.append(format_div_element("**订单不匹配详情:**"))
        for mismatch in report.order_mismatches[:3]:  # Limit to first 3
            elements.append(format_div_element(
                f"• {mismatch.order_id}: 本地={mismatch.local_status}, 交易所={mismatch.exchange_status}"
            ))

    return format_feishu_card(
        title="对账差异告警",
        elements=elements,
        level=AlertLevel.ERROR
    )


def format_connection_lost_message(reconnect_attempts: int, last_error: str) -> Dict[str, Any]:
    """
    Format WebSocket connection lost alert.

    Args:
        reconnect_attempts: Number of reconnection attempts
        last_error: Last error message

    Returns:
        Feishu card payload
    """
    content = f"""**事件类型**: WebSocket 断连
**重连尝试**: {reconnect_attempts} 次
**最后错误**: {last_error}
**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ 请尽快检查网络连接和交易所状态"""

    elements = [format_div_element(content)]

    return format_feishu_card(
        title="WebSocket 断连告警",
        elements=elements,
        level=AlertLevel.ERROR
    )


def format_daily_loss_limit_message(
    daily_pnl: Decimal,
    max_allowed_loss: Decimal,
    balance: Decimal
) -> Dict[str, Any]:
    """
    Format daily loss limit exceeded alert.

    Args:
        daily_pnl: Current daily PnL (negative for loss)
        max_allowed_loss: Maximum allowed daily loss
        balance: Current account balance

    Returns:
        Feishu card payload
    """
    loss_percent = (abs(daily_pnl) / balance * 100) if balance > 0 else Decimal('0')

    content = f"""**事件类型**: 每日亏损超限
**当日盈亏**: {daily_pnl:.2f} USDT
**最大允许损失**: {max_allowed_loss:.2f} USDT
**当前余额**: {balance:.2f} USDT
**亏损比例**: {loss_percent:.2f}%

🚫 已暂停交易，请检查风险控制参数"""

    elements = [format_div_element(content)]

    return format_feishu_card(
        title="每日亏损超限告警",
        elements=elements,
        level=AlertLevel.ERROR
    )


# ============================================================
# FeishuNotifier Class
# ============================================================

class FeishuConfig:
    """Feishu notification configuration"""

    def __init__(
        self,
        silent_hours_start: Optional[int] = None,
        silent_hours_end: Optional[int] = None,
        skip_silent_for_errors: bool = True,
    ):
        """
        Initialize Feishu configuration.

        Args:
            silent_hours_start: Silent period start hour (0-23), e.g., 2 for 02:00
            silent_hours_end: Silent period end hour (0-23), e.g., 8 for 08:00
            skip_silent_for_errors: If True, ERROR level alerts bypass silent hours
        """
        self.silent_hours_start = silent_hours_start
        self.silent_hours_end = silent_hours_end
        self.skip_silent_for_errors = skip_silent_for_errors


class FeishuNotifier:
    """
    Feishu (Lark) Webhook Notification Service

    Supports 6 alert event types:
    - ORDER_FILLED: Order execution notification
    - ORDER_FAILED: Order failure alert
    - CAPITAL_PROTECTION_TRIGGERED: Capital protection triggered
    - RECONCILIATION_MISMATCH: Reconciliation discrepancy
    - CONNECTION_LOST: WebSocket connection lost
    - DAILY_LOSS_LIMIT: Daily loss limit exceeded
    """

    def __init__(
        self,
        webhook_url: str,
        config: Optional[FeishuConfig] = None,
        session: Optional[aiohttp.ClientSession] = None,
    ):
        """
        Initialize Feishu notifier.

        Args:
            webhook_url: Feishu webhook URL
            config: FeishuConfig object (optional, for silent hours)
            session: Optional shared aiohttp ClientSession
        """
        self._webhook_url = webhook_url
        self._config = config or FeishuConfig()
        self._session = session
        self._pending_alerts: List[Dict[str, Any]] = []

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp ClientSession"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the session"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _is_silent_period(self) -> bool:
        """
        Check if current time is within silent period.

        Returns:
            True if in silent period, False otherwise
        """
        if self._config.silent_hours_start is None or self._config.silent_hours_end is None:
            return False

        current_hour = datetime.now().hour

        if self._config.silent_hours_start < self._config.silent_hours_end:
            # Normal range (e.g., 2-8)
            return self._config.silent_hours_start <= current_hour < self._config.silent_hours_end
        else:
            # Cross-midnight range (e.g., 22-6)
            return (
                current_hour >= self._config.silent_hours_start or
                current_hour < self._config.silent_hours_end
            )

    async def send_alert(
        self,
        event_type: str,
        title: str,
        message: str,
        level: Optional[str] = None,
    ) -> bool:
        """
        Send general alert.

        Args:
            event_type: Alert event type (ORDER_FILLED, ORDER_FAILED, etc.)
            title: Alert title
            message: Alert message content
            level: Alert level (INFO, WARNING, ERROR). Defaults based on event_type.

        Returns:
            True if sent successfully, False otherwise
        """
        # Determine level
        if level is None:
            level = EVENT_LEVEL_MAP.get(event_type, AlertLevel.INFO)

        # Check silent period
        if self._is_silent_period() and level != AlertLevel.ERROR:
            # Queue for later delivery
            self._pending_alerts.append({
                "event_type": event_type,
                "title": title,
                "message": message,
                "level": level,
                "queued_at": int(time.time() * 1000)
            })
            logger.info(f"Alert '{title}' queued for later delivery (silent period)")
            return True

        # Build simple card payload
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": f"{LEVEL_PREFIX_MAP.get(level, '')} {title}"
                    },
                    "template": LEVEL_COLOR_MAP.get(level, "blue")
                },
                "elements": [
                    format_div_element(message)
                ]
            }
        }

        return await self._send_payload(payload)

    async def _send_payload(self, payload: Dict[str, Any]) -> bool:
        """
        Send payload to Feishu webhook.

        Args:
            payload: Feishu card payload dict

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            session = await self._get_session()
            async with session.post(
                self._webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    # Feishu returns {"StatusCode": 0, "StatusMessage": "success"} on success
                    if result.get("StatusCode") == 0 or result.get("code") == 0:
                        logger.info("Feishu alert sent successfully")
                        return True
                    # Some webhooks return 200 with no body
                    logger.info("Feishu alert sent successfully")
                    return True
                else:
                    logger.error(f"Feishu webhook returned {response.status}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send Feishu alert: {e}")
            return False

    async def send_order_filled(self, order: Order, pnl: Decimal) -> bool:
        """
        Send order filled notification.

        Args:
            order: Order object with execution details
            pnl: Realized PnL in USDT

        Returns:
            True if sent successfully
        """
        payload = format_order_filled_message(order, pnl)
        return await self._send_payload(payload)

    async def send_order_failed(self, order: Order, reason: str) -> bool:
        """
        Send order failed alert.

        Args:
            order: Order object
            reason: Failure reason

        Returns:
            True if sent successfully
        """
        payload = format_order_failed_message(order, reason)
        return await self._send_payload(payload)

    async def send_capital_protection_triggered(
        self,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send capital protection triggered alert.

        Args:
            reason: Reason code (e.g., "SINGLE_TRADE_LOSS_LIMIT")
            details: Optional detailed information

        Returns:
            True if sent successfully
        """
        payload = format_capital_protection_message(reason, details)
        return await self._send_payload(payload)

    async def send_reconciliation_mismatch(self, report: ReconciliationReport) -> bool:
        """
        Send reconciliation mismatch alert.

        Args:
            report: ReconciliationReport object

        Returns:
            True if sent successfully
        """
        payload = format_reconciliation_mismatch_message(report)
        return await self._send_payload(payload)

    async def send_connection_lost(
        self,
        reconnect_attempts: int,
        last_error: str,
    ) -> bool:
        """
        Send WebSocket connection lost alert.

        Args:
            reconnect_attempts: Number of reconnection attempts
            last_error: Last error message

        Returns:
            True if sent successfully
        """
        payload = format_connection_lost_message(reconnect_attempts, last_error)
        return await self._send_payload(payload)

    async def send_daily_loss_limit(
        self,
        daily_pnl: Decimal,
        max_allowed_loss: Decimal,
        balance: Decimal,
    ) -> bool:
        """
        Send daily loss limit exceeded alert.

        Args:
            daily_pnl: Current daily PnL
            max_allowed_loss: Maximum allowed daily loss
            balance: Current account balance

        Returns:
            True if sent successfully
        """
        payload = format_daily_loss_limit_message(daily_pnl, max_allowed_loss, balance)
        return await self._send_payload(payload)

    async def flush_pending_alerts(self) -> int:
        """
        Flush all pending alerts (queued during silent period).

        Returns:
            Number of alerts flushed
        """
        if not self._pending_alerts:
            return 0

        count = 0
        for alert in self._pending_alerts:
            if await self.send_alert(
                event_type=alert["event_type"],
                title=alert["title"],
                message=alert["message"],
                level=alert["level"],
            ):
                count += 1

        self._pending_alerts.clear()
        logger.info(f"Flushed {count} pending alerts")
        return count


# ============================================================
# Factory Function
# ============================================================

def create_feishu_notifier(
    webhook_url: str,
    silent_hours_start: Optional[int] = None,
    silent_hours_end: Optional[int] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> FeishuNotifier:
    """
    Create Feishu notifier with optional silent hours.

    Args:
        webhook_url: Feishu webhook URL
        silent_hours_start: Silent period start hour (0-23)
        silent_hours_end: Silent period end hour (0-23)
        session: Optional shared aiohttp ClientSession

    Returns:
        FeishuNotifier instance
    """
    config = FeishuConfig(
        silent_hours_start=silent_hours_start,
        silent_hours_end=silent_hours_end,
    )
    return FeishuNotifier(webhook_url, config=config, session=session)
