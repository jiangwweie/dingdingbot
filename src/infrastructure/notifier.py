"""
Notification service - Send alerts via Feishu/WeCom webhooks.
Formats SignalResult to Markdown and sends system alerts.
"""
import asyncio
import traceback
from typing import List, Optional
from decimal import Decimal

import aiohttp

from src.domain.models import SignalResult, Direction
from src.infrastructure.logger import logger, mask_secret


# ============================================================
# Message Formatter
# ============================================================
def format_signal_message(
    signal: SignalResult,
    superseded_signal: Optional[dict] = None,
    opposing_signal: Optional[dict] = None,
) -> str:
    """
    Format SignalResult to Markdown message for notification.

    Args:
        signal: SignalResult object
        superseded_signal: Optional dict with old signal data (for cover notifications)
        opposing_signal: Optional dict with opposing signal data

    Returns:
        Markdown formatted message string
    """
    # Use specialized templates if applicable
    if superseded_signal:
        return format_cover_signal_message(signal, superseded_signal)
    if opposing_signal:
        return format_opposing_signal_message(signal, opposing_signal)

    # Standard signal notification
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_text = "🟢 看多 (LONG)"
    else:
        direction_text = "🔴 看空 (SHORT)"

    # Build tags section dynamically
    tags_section = ""
    if signal.tags:
        tags_section = "\n".join([f"  {tag.get('name', 'Unknown')}: {tag.get('value', 'N/A')}" for tag in signal.tags])
        tags_section = f"\n指标标签:\n{tags_section}\n"
    else:
        tags_section = "\n指标标签：无\n"

    # Build take profit section (S6-3)
    tp_section = ""
    if signal.take_profit_levels and len(signal.take_profit_levels) > 0:
        tp_lines = [f"  {tp['id']}: {tp['price']} ({tp['position_ratio']} @ 1:{tp['risk_reward']})" for tp in signal.take_profit_levels]
        tp_section = "\n止盈目标:\n" + "\n".join(tp_lines) + "\n"
    else:
        tp_section = "\n止盈目标：无\n"

    # Build message
    message = f"""【交易信号提醒】

币种：{signal.symbol}
周期：{signal.timeframe}
方向：{direction_text}
入场价：{signal.entry_price}
止损位：{signal.suggested_stop_loss}
{tp_section}建议仓位：{signal.suggested_position_size}
当前杠杆：{signal.current_leverage}x
{tags_section}
风控信息：{signal.risk_reward_info}

---
⚠️ 本系统仅为观测与通知工具，不构成投资建议
"""
    return message


def format_cover_signal_message(signal: SignalResult, superseded_signal: dict) -> str:
    """
    覆盖通知模板 - 包含评分对比

    Args:
        signal: 新信号（覆盖者）
        superseded_signal: 旧信号数据（包含 score）

    Returns:
        Markdown formatted cover notification message
    """
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_text = "🟢 看多 (LONG)"
    else:
        direction_text = "🔴 看空 (SHORT)"

    # Build take profit section (S6-3)
    tp_section = ""
    if signal.take_profit_levels and len(signal.take_profit_levels) > 0:
        tp_lines = [f"  {tp['id']}: {tp['price']} ({tp['position_ratio']} @ 1:{tp['risk_reward']})" for tp in signal.take_profit_levels]
        tp_section = "\n止盈目标:\n" + "\n".join(tp_lines) + "\n"
    else:
        tp_section = "\n止盈目标：无\n"

    # Build tags section dynamically
    tags_section = ""
    if signal.tags:
        tags_section = "\n".join([f"  {tag.get('name', 'Unknown')}: {tag.get('value', 'N/A')}" for tag in signal.tags])
        tags_section = f"\n指标标签:\n{tags_section}\n"
    else:
        tags_section = "\n指标标签：无\n"

    # Calculate score improvement
    new_score = signal.score
    old_score = superseded_signal.get('score', 0)
    score_improvement = ((new_score - old_score) / old_score * 100) if old_score > 0 else 0

    # Build message
    message = f"""【信号覆盖提醒】⚡

币种：{signal.symbol}
周期：{signal.timeframe}
方向：{direction_text}
入场价：{signal.entry_price}（更新）
止损位：{signal.suggested_stop_loss}（更新）
{tp_section}建议仓位：{signal.suggested_position_size}
当前杠杆：{signal.current_leverage}x

【覆盖原因】
新信号评分：{new_score:.2f}（原信号评分：{old_score:.2f}）
评分提升：{score_improvement:+.0f}%

{tags_section}
风控信息：{signal.risk_reward_info}

---
⚡ 此信号覆盖了之前的信号 (ID: {superseded_signal.get('signal_id', 'unknown')}),因为形态质量更优
⚠️ 本系统仅为观测与通知工具，不构成投资建议
"""
    return message


def format_opposing_signal_message(signal: SignalResult, opposing_signal: dict) -> str:
    """
    反向信号通知模板 - 包含市场分歧提示

    Args:
        signal: 当前信号
        opposing_signal: 反向信号数据（包含 direction, score）

    Returns:
        Markdown formatted opposing signal notification message
    """
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_text = "🟢 看多 (LONG)"
    else:
        direction_text = "🔴 看空 (SHORT)"

    # Build tags section dynamically
    tags_section = ""
    if signal.tags:
        tags_section = "\n".join([f"  {tag.get('name', 'Unknown')}: {tag.get('value', 'N/A')}" for tag in signal.tags])
        tags_section = f"\n指标标签:\n{tags_section}\n"
    else:
        tags_section = "\n指标标签：无\n"

    # Opposing signal info
    opp_direction = opposing_signal.get('direction', 'UNKNOWN')
    opp_score = opposing_signal.get('score', 0)

    if opp_direction == Direction.LONG.value:
        opp_direction_text = "🟢 看多 (LONG)"
    else:
        opp_direction_text = "🔴 看空 (SHORT)"

    # Determine if opposing signal has higher score
    current_score = signal.score
    is_opposing_higher = opp_score > current_score

    # Build message
    if is_opposing_higher:
        warning_section = f"""【市场分歧提示】
当前方向信号评分：{current_score:.2f}
反向方向信号评分：{opp_score:.2f}（更高）

⚠️ 注意：存在更优的反向信号，市场可能出现分歧
"""
    else:
        warning_section = f"""【市场分歧提示】
当前方向信号评分：{current_score:.2f}
反向方向信号评分：{opp_score:.2f}

⚠️ 市场存在反向信号，请谨慎判断
"""

    message = f"""【反向信号提醒】⚠️

币种：{signal.symbol}
周期：{signal.timeframe}
方向：{direction_text} ← 与原信号相反
入场价：{signal.entry_price}
止损位：{signal.suggested_stop_loss}
建议仓位：{signal.suggested_position_size}
当前杠杆：{signal.current_leverage}x

{warning_section}
{tags_section}
风控信息：{signal.risk_reward_info}

---
⚠️ 市场存在反向信号，请谨慎判断
⚠️ 本系统仅为观测与通知工具，不构成投资建议
"""
    return message


def format_system_alert(error_code: str, error_message: str, traceback_str: Optional[str] = None) -> str:
    """
    Format system alert for critical errors.

    Args:
        error_code: Error code (e.g., "C-001")
        error_message: Error message
        traceback_str: Optional truncated traceback

    Returns:
        Markdown formatted alert message
    """
    # Truncate traceback if too long
    max_tb_length = 1000
    if traceback_str and len(traceback_str) > max_tb_length:
        traceback_str = traceback_str[:max_tb_length] + "\n...(truncated)"

    message = f"""【系统告警】

错误码：{error_code}
错误信息：{error_message}
"""

    if traceback_str:
        message += f"""
堆栈摘要:
```
{traceback_str}
```
"""

    message += """
---
⚠️ 请尽快检查系统状态
"""
    return message


# ============================================================
# Notification Channels
# ============================================================
class NotificationChannel:
    """Base class for notification channels"""

    async def send(self, message: str) -> bool:
        """
        Send notification message.

        Args:
            message: Markdown formatted message

        Returns:
            True if sent successfully
        """
        raise NotImplementedError


class FeishuWebhook(NotificationChannel):
    """Feishu (Lark) webhook notification channel"""

    def __init__(self, webhook_url: str, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize Feishu webhook.

        Args:
            webhook_url: Feishu webhook URL
            session: Optional shared aiohttp ClientSession
        """
        self.webhook_url = webhook_url
        self._session = session

    async def send(self, message: str, session: Optional[aiohttp.ClientSession] = None) -> bool:
        """
        Send message via Feishu webhook.

        Args:
            message: Markdown formatted message
            session: Optional shared session to use

        Returns:
            True if sent successfully
        """
        payload = {
            "msg_type": "text",
            "content": {
                "text": message
            }
        }

        try:
            use_session = session or self._session
            if use_session is None:
                async with aiohttp.ClientSession() as use_session:
                    async with use_session.post(
                        self.webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        if response.status == 200:
                            logger.info("Feishu notification sent successfully")
                            return True
                        else:
                            logger.error(f"Feishu webhook returned {response.status}")
                            return False
            else:
                async with use_session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 200:
                        logger.info("Feishu notification sent successfully")
                        return True
                    else:
                        logger.error(f"Feishu webhook returned {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send Feishu notification: {e}")
            return False


class WeComWebhook(NotificationChannel):
    """WeCom (Enterprise WeChat) webhook notification channel"""

    def __init__(self, webhook_url: str, session: Optional[aiohttp.ClientSession] = None):
        """
        Initialize WeCom webhook.

        Args:
            webhook_url: WeCom webhook URL
            session: Optional shared aiohttp ClientSession
        """
        self.webhook_url = webhook_url
        self._session = session

    async def send(self, message: str, session: Optional[aiohttp.ClientSession] = None) -> bool:
        """
        Send message via WeCom webhook.

        Args:
            message: Markdown formatted message
            session: Optional shared session to use

        Returns:
            True if sent successfully
        """
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": message
            }
        }

        try:
            use_session = session or self._session
            if use_session is None:
                async with aiohttp.ClientSession() as use_session:
                    async with use_session.post(
                        self.webhook_url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    ) as response:
                        if response.status == 200:
                            logger.info("WeCom notification sent successfully")
                            return True
                        else:
                            logger.error(f"WeCom webhook returned {response.status}")
                            return False
            else:
                async with use_session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status == 200:
                        logger.info("WeCom notification sent successfully")
                        return True
                    else:
                        logger.error(f"WeCom webhook returned {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Failed to send WeCom notification: {e}")
            return False


# ============================================================
# Notification Service
# ============================================================
class NotificationService:
    """
    Unified notification service supporting multiple channels.
    """

    def __init__(self):
        """Initialize NotificationService"""
        self._channels: List[NotificationChannel] = []
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create shared aiohttp ClientSession"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close the shared session"""
        if self._session and not self._session.closed:
            await self._session.close()

    def add_channel(self, channel: NotificationChannel) -> None:
        """
        Add a notification channel.

        Args:
            channel: NotificationChannel instance
        """
        self._channels.append(channel)
        logger.info(f"Added notification channel: {type(channel).__name__}")

    def setup_channels(
        self,
        channels_config: List[dict],
    ) -> None:
        """
        Set up notification channels from configuration.

        Args:
            channels_config: List of channel configs from user.yaml
        """
        for channel_cfg in channels_config:
            channel_type = channel_cfg.get('type')
            webhook_url = channel_cfg.get('webhook_url')

            if not channel_type or not webhook_url:
                logger.warning(f"Invalid channel config: {channel_cfg}")
                continue

            if channel_type == 'feishu':
                self.add_channel(FeishuWebhook(webhook_url))
            elif channel_type == 'wecom':
                self.add_channel(WeComWebhook(webhook_url))
            else:
                logger.warning(f"Unknown channel type: {channel_type}")

    async def send_signal(
        self,
        signal: SignalResult,
        superseded_signal: Optional[dict] = None,
        opposing_signal: Optional[dict] = None,
    ) -> None:
        """
        Send signal notification to all channels.

        Args:
            signal: SignalResult to send
            superseded_signal: Optional dict with old signal data (for cover notifications)
            opposing_signal: Optional dict with opposing signal data
        """
        message = format_signal_message(signal, superseded_signal, opposing_signal)
        await self._broadcast(message)

    async def send_system_alert(
        self,
        error_code: str,
        error_message: str,
        exc_info: Optional[Exception] = None,
    ) -> None:
        """
        Send system alert to all channels.

        Args:
            error_code: Error code
            error_message: Error message
            exc_info: Optional exception for traceback
        """
        # Get truncated traceback
        traceback_str = None
        if exc_info:
            traceback_str = traceback.format_exc()

        message = format_system_alert(error_code, error_message, traceback_str)
        await self._broadcast(message)

    async def _broadcast(self, message: str) -> None:
        """
        Broadcast message to all channels.

        Args:
            message: Message to broadcast
        """
        if not self._channels:
            logger.warning("No notification channels configured")
            return

        session = await self._get_session()
        tasks = [channel.send(message, session=session) for channel in self._channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        logger.info(f"Notification broadcast: {success_count}/{len(self._channels)} channels succeeded")


# ============================================================
# Global instance
# ============================================================
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create global NotificationService instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service
