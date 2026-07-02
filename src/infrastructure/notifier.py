"""
Notification service - Send alerts via Feishu/WeCom webhooks.
Formats SignalResult to Markdown and sends system alerts.
"""
import asyncio
import traceback
from typing import List, Optional, Dict
from decimal import Decimal

import aiohttp

from src.domain.models import SignalResult, Direction
from src.infrastructure.logger import logger, mask_secret, register_secret


# ============================================================
# Message Formatter
# ============================================================

# Translation map for tag names
TAG_TRANSLATIONS = {
    'MTF': 'MTF',
    'EMA': 'EMA 趋势',
    'Source': None,  # Do not display Source tag
}

# Translation map for tag values
TAG_VALUE_TRANSLATIONS = {
    'Confirmed': '确认',
    'Rejected': '拒绝',
    'Passed': '通过',
    'Unavailable': '不可用',
    'Bullish': '看涨',
    'Bearish': '看跌',
    'Backtest': '回测',
    'Live': '实盘',
}


def translate_tag(name: str, value: str) -> Optional[str]:
    """
    Translate tag name and value to Chinese.

    Args:
        name: Tag name (e.g., "MTF", "EMA", "Source")
        value: Tag value (e.g., "Confirmed", "Bullish")

    Returns:
        Translated tag string or None if should be hidden
    """
    # Check if this tag should be hidden
    tag_name = TAG_TRANSLATIONS.get(name)
    if tag_name is None:
        return None

    # Translate value
    translated_value = TAG_VALUE_TRANSLATIONS.get(value, value)

    return f"  {tag_name}: {translated_value}"


def format_score(score: float) -> int:
    """Convert score (0-1) to integer (0-100)"""
    return int(round(score * 100))


def format_take_profit_levels(take_profit_levels: List[dict]) -> str:
    """
    Format take profit levels as single line.

    Args:
        take_profit_levels: List of TP dicts with tp_id and price_level

    Returns:
        Formatted string like "TP1: 71000 | TP2: 72000" or "无"
    """
    if not take_profit_levels or len(take_profit_levels) == 0:
        return "无"

    tp_parts = []
    for tp in take_profit_levels:
        # Support both new (tp_id, price_level) and legacy (id, price) field names
        tp_id = tp.get('tp_id', tp.get('id', 'TP'))
        price = tp.get('price_level', tp.get('price', 'N/A'))
        tp_parts.append(f"{tp_id}: {price}")

    return " | ".join(tp_parts)


def format_tags_compact(tags: List[Dict[str, str]]) -> str:
    """
    Format tags as compact string for style D.
    e.g., "MTF 确认 | EMA 趋势看跌"
    """
    if not tags:
        return "无"

    parts = []
    for tag in tags:
        name = tag.get('name', '')
        value = tag.get('value', '')
        # Skip Source tag
        if name == 'Source':
            continue
        # Translate
        translated_name = TAG_TRANSLATIONS.get(name, name)
        translated_value = TAG_VALUE_TRANSLATIONS.get(value, value)
        parts.append(f"{translated_name}{translated_value}")

    return " | ".join(parts)
def format_signal_message(
    signal: SignalResult,
    superseded_signal: Optional[dict] = None,
    opposing_signal: Optional[dict] = None,
) -> str:
    """
    Format SignalResult to Markdown message for notification.
    Using Style D (紧凑卡片风格) as default.

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

    # Default to Style D (紧凑卡片风格)
    return format_signal_message_style_d(signal)


def format_cover_signal_message(signal: SignalResult, superseded_signal: dict) -> str:
    """
    覆盖通知模板 - 包含评分对比（风格 D）

    Args:
        signal: 新信号（覆盖者）
        superseded_signal: 旧信号数据（包含 score）

    Returns:
        Markdown formatted cover notification message
    """
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "多"
    else:
        direction_icon = "🔴"
        direction_text = "空"

    # Strategy name (short)
    strategy_short = signal.strategy_name or "Pinbar"
    if len(strategy_short) > 15:
        strategy_short = strategy_short[:12] + "..."

    # Take profit
    tp_str = format_take_profit_levels(signal.take_profit_levels)

    # Tags compact
    tags_str = format_tags_compact(signal.tags) if signal.tags else "无"

    # Calculate score improvement
    new_score = signal.score
    old_score = superseded_signal.get('score', 0)
    score_improvement = ((new_score - old_score) / old_score * 100) if old_score > 0 else 0

    message = f"""
📡 盯盘狗 🐶 交易决策雷达
━━━━━━━━━━━━━━━━━━━
📢【信号覆盖】⚡

📊 {strategy_short} · {format_score(new_score)}分
#{signal.symbol} | {signal.timeframe} | {direction_icon} {direction_text}

💰 入场：`{signal.entry_price}`（更新）
🛑 止损：`{signal.suggested_stop_loss}`（更新）
🎯 止盈：`{tp_str}`
🔧 杠杆：`{signal.current_leverage}x`

【覆盖原因】
新评分：{format_score(new_score)}分 | 原评分：{format_score(old_score)}分
提升：{score_improvement:+.0f}%

📐 {tags_str}
⚖️ {signal.risk_reward_info}
━━━━━━━━━━━━━━━━━━━
"""
    return message


def format_opposing_signal_message(signal: SignalResult, opposing_signal: dict) -> str:
    """
    反向信号通知模板 - 包含市场分歧提示（风格 D）

    Args:
        signal: 当前信号
        opposing_signal: 反向信号数据（包含 direction, score）

    Returns:
        Markdown formatted opposing signal notification message
    """
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "多"
    else:
        direction_icon = "🔴"
        direction_text = "空"

    # Strategy name (short)
    strategy_short = signal.strategy_name or "Pinbar"
    if len(strategy_short) > 15:
        strategy_short = strategy_short[:12] + "..."

    # Take profit
    tp_str = format_take_profit_levels(signal.take_profit_levels)

    # Tags compact
    tags_str = format_tags_compact(signal.tags) if signal.tags else "无"

    # Opposing signal info
    opp_direction = opposing_signal.get('direction', 'UNKNOWN')
    opp_score = opposing_signal.get('score', 0)

    if opp_direction == Direction.LONG.value:
        opp_icon = "🟢"
        opp_text = "多"
    else:
        opp_icon = "🔴"
        opp_text = "空"

    # Determine if opposing signal has higher score
    current_score = signal.score
    is_opposing_higher = opp_score > current_score

    # Build message
    if is_opposing_higher:
        warning_section = f"""
【市场分歧提示】
当前信号：{format_score(current_score)}分
反向信号：{format_score(opp_score)}分 ⚠️ 更高

注意：存在更优的反向信号 ({opp_icon}{opp_text})
"""
    else:
        warning_section = f"""
【市场分歧提示】
当前信号：{format_score(current_score)}分
反向信号：{format_score(opp_score)}分 ({opp_icon}{opp_text})
"""

    message = f"""
📡 盯盘狗 🐶 交易决策雷达
━━━━━━━━━━━━━━━━━━━
📢【反向信号】⚠️

📊 {strategy_short} · {format_score(current_score)}分
#{signal.symbol} | {signal.timeframe} | {direction_icon} {direction_text} ← 与原信号相反

💰 入场：`{signal.entry_price}`
🛑 止损：`{signal.suggested_stop_loss}`
🎯 止盈：`{tp_str}`
🔧 杠杆：`{signal.current_leverage}x`

{warning_section}
📐 {tags_str}
⚖️ {signal.risk_reward_info}
━━━━━━━━━━━━━━━━━━━
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

⚠️ 请尽快检查系统状态
"""
    return message


# ============================================================
# Style C: 区块分隔风格
# ============================================================
def format_signal_message_style_c(signal: SignalResult) -> str:
    """
    Style C: 区块分隔风格 - 使用分隔线和区块

    ═══════════════════════════════
         🚨 交易信号提醒
    ═══════════════════════════════
    """
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "看多"
    else:
        direction_icon = "🔴"
        direction_text = "看空"

    # Take profit
    tp_str = format_take_profit_levels(signal.take_profit_levels)

    # Tags compact
    tags_str = format_tags_compact(signal.tags) if signal.tags else "无"

    message = f"""
═══════════════════════════════
     🚨 交易信号提醒
═══════════════════════════════

🪙 {signal.symbol}
⏱️ {signal.timeframe} | 📊 {format_score(signal.score)}分

{direction_icon} {direction_text}

───────────────────────────────
💰 入场价：{signal.entry_price}
🛑 止损位：{signal.suggested_stop_loss}
🎯 止盈：{tp_str}
───────────────────────────────

📊 仓位：{signal.suggested_position_size}
🔧 杠杆：{signal.current_leverage}x

📐 指标：{tags_str}
⚖️ 风控：{signal.risk_reward_info}

═══════════════════════════════
"""
    return message


# ============================================================
# Style D: 紧凑卡片风格
# ============================================================
def format_signal_message_style_d(signal: SignalResult) -> str:
    """
    Style D: 紧凑卡片风格 - 类似 CryptoRadar

    📡 盯盘狗 🐶 交易信号雷达
    ━━━━━━━━━━━━━━━━━━━
    """
    # Direction emoji and text
    if signal.direction == Direction.LONG:
        direction_icon = "🟢"
        direction_text = "多"
    else:
        direction_icon = "🔴"
        direction_text = "空"

    # Strategy name (short)
    strategy_short = signal.strategy_name or "Pinbar"
    if len(strategy_short) > 15:
        strategy_short = strategy_short[:12] + "..."

    # Take profit
    tp_str = format_take_profit_levels(signal.take_profit_levels)

    # Tags compact
    tags_str = format_tags_compact(signal.tags) if signal.tags else "无"

    # Risk info short
    risk_short = signal.risk_reward_info
    if "Risk" in risk_short:
        # Extract percentage and USDT amount
        risk_short = risk_short.replace("Risk ", "").replace(" = ", " = ")
        if "USDT" in risk_short:
            risk_short = risk_short.replace(" USDT", "U")

    message = f"""
📡 盯盘狗 🐶 交易决策雷达
━━━━━━━━━━━━━━━━━━━
📢【普通信号】

📊 {strategy_short} · {format_score(signal.score)}分
#{signal.symbol} | {signal.timeframe} | {direction_icon} {direction_text}

💰 入场：`{signal.entry_price}`
🛑 止损：`{signal.suggested_stop_loss}`
🎯 止盈：`{tp_str}`
🔧 杠杆：`{signal.current_leverage}x`

📐 {tags_str}
⚖️ {signal.risk_reward_info}
━━━━━━━━━━━━━━━━━━━
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

            # Register webhook URL for secret masking
            register_secret(webhook_url)

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


# ============================================================
# Helper functions for testing styles
# ============================================================
def send_style_c(signal: SignalResult, webhook_url: str) -> bool:
    """Send style C notification"""
    import asyncio

    async def _send():
        service = NotificationService()
        service.add_channel(FeishuWebhook(webhook_url))
        message = format_signal_message_style_c(signal)
        result = await service._broadcast(message)
        await service.close()
        return result

    return asyncio.run(_send())


def send_style_d(signal: SignalResult, webhook_url: str) -> bool:
    """Send style D notification"""
    import asyncio

    async def _send():
        service = NotificationService()
        service.add_channel(FeishuWebhook(webhook_url))
        message = format_signal_message_style_d(signal)
        result = await service._broadcast(message)
        await service.close()
        return result

    return asyncio.run(_send())
