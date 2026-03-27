"""
Signal Status Tracker - 信号状态跟踪器

跟踪信号从生成到成交的全流程状态。
"""
import asyncio
import time
import hashlib
from typing import Dict, Optional, List
from decimal import Decimal

from src.domain.models import SignalResult, SignalTrack, SignalStatus
from src.infrastructure.signal_repository import SignalRepository
from src.infrastructure.logger import logger


class SignalStatusTracker:
    """
    信号状态跟踪器

    功能:
    - 跟踪信号状态变化
    - 提供状态查询接口
    - 记录状态变更历史
    """

    def __init__(self, repository: SignalRepository):
        self._repository = repository
        self._in_memory_cache: Dict[str, SignalTrack] = {}
        self._lock = asyncio.Lock()

    async def track_signal(self, signal: SignalResult) -> str:
        """
        开始跟踪信号

        Args:
            signal: 信号结果对象

        Returns:
            signal_id: 信号唯一标识
        """
        signal_id = self._generate_signal_id(signal)

        now = int(time.time() * 1000)
        track = SignalTrack(
            signal_id=signal_id,
            original_signal=signal,
            status=SignalStatus.GENERATED,
            created_at=now,
            updated_at=now,
        )

        async with self._lock:
            self._in_memory_cache[signal_id] = track

        logger.info(f"开始跟踪信号：{signal_id} ({signal.symbol} {signal.timeframe})")
        return signal_id

    async def update_status(
        self,
        signal_id: str,
        status: SignalStatus,
        filled_price: Optional[Decimal] = None,
        reason: Optional[str] = None,
    ) -> None:
        """
        更新信号状态

        Args:
            signal_id: 信号标识
            status: 新状态
            filled_price: 成交价格（仅 FILLED 状态需要）
            reason: 状态变更原因
        """
        async with self._lock:
            if signal_id not in self._in_memory_cache:
                logger.warning(f"信号不存在：{signal_id}")
                return

            track = self._in_memory_cache[signal_id]
            track.status = status
            track.updated_at = int(time.time() * 1000)

            if status == SignalStatus.FILLED:
                track.filled_price = filled_price
                track.filled_at = track.updated_at
            elif status == SignalStatus.REJECTED:
                track.reject_reason = reason
            elif status == SignalStatus.CANCELLED:
                track.cancel_reason = reason

            logger.info(f"信号状态更新：{signal_id} -> {status.value}")

    async def get_signal_status(self, signal_id: str) -> Optional[SignalTrack]:
        """
        查询信号状态

        Args:
            signal_id: 信号标识

        Returns:
            SignalTrack 对象或 None
        """
        async with self._lock:
            return self._in_memory_cache.get(signal_id)

    async def list_statuses(
        self,
        status_filter: Optional[SignalStatus] = None,
        limit: int = 50,
    ) -> List[SignalTrack]:
        """
        批量查询信号状态

        Args:
            status_filter: 状态过滤
            limit: 结果数量限制

        Returns:
            SignalTrack 列表
        """
        async with self._lock:
            tracks = list(self._in_memory_cache.values())

        if status_filter:
            tracks = [t for t in tracks if t.status == status_filter]

        # 按创建时间倒序
        tracks.sort(key=lambda t: t.created_at, reverse=True)

        return tracks[:limit]

    def _generate_signal_id(self, signal: SignalResult) -> str:
        """生成信号唯一 ID"""
        unique_str = f"{signal.symbol}{signal.timeframe}{signal.kline_timestamp}{time.time()}"
        return hashlib.sha256(unique_str.encode()).hexdigest()[:16]
