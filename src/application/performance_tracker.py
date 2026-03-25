"""
Performance Tracker - Track PENDING signals and check if price hits take-profit or stop-loss.
"""
from decimal import Decimal
from typing import TYPE_CHECKING

from src.domain.models import KlineData
from src.infrastructure.logger import logger

if TYPE_CHECKING:
    from src.infrastructure.signal_repository import SignalRepository


class PerformanceTracker:
    """
    Performance tracker for monitoring PENDING signals.
    Checks if latest K-line's high/low hits take-profit or stop-loss levels.
    """

    async def check_pending_signals(
        self,
        kline: KlineData,
        repository: "SignalRepository",
    ) -> None:
        """
        Check all PENDING signals for the given symbol and update status if hit.

        Args:
            kline: Latest closed K-line data
            repository: Signal repository instance
        """
        try:
            # Get all PENDING signals for this symbol
            pending_signals = await repository.get_pending_signals(kline.symbol)

            if not pending_signals:
                return

            for signal in pending_signals:
                await self._check_signal(signal, kline, repository)

        except Exception as e:
            logger.error(f"Error checking pending signals: {e}")

    async def _check_signal(
        self,
        signal: dict,
        kline: KlineData,
        repository: "SignalRepository",
    ) -> None:
        """
        Check a single signal and update status if price hit TP/SL.

        Args:
            signal: Signal dict with id, direction, entry_price, stop_loss, take_profit_1
            kline: Latest K-line data
            repository: Signal repository instance
        """
        signal_id = signal["id"]
        direction = signal["direction"]
        entry_price = signal["entry_price"]
        stop_loss = signal["stop_loss"]
        take_profit_1 = signal["take_profit_1"]

        # Skip if no take-profit level is set
        if take_profit_1 is None:
            return

        kline_high = kline.high
        kline_low = kline.low

        # From risk-first perspective: check stop-loss first (more conservative)
        if direction == "long":
            # LONG signal: price goes up to TP, down to SL
            # Check if low <= stop_loss (hit stop-loss)
            if kline_low <= stop_loss:
                await repository.update_signal_status(signal_id, "LOST", Decimal("-1.0"))
                logger.info(
                    f"Signal #{signal_id} LOST: {kline.symbol} LONG hit stop-loss "
                    f"(SL={stop_loss}, K-line low={kline_low})"
                )
            # Check if high >= take_profit (hit take-profit)
            elif kline_high >= take_profit_1:
                # Calculate PnL ratio: (TP - entry) / (entry - SL)
                pnl_ratio = (take_profit_1 - entry_price) / (entry_price - stop_loss)
                await repository.update_signal_status(signal_id, "WON", pnl_ratio)
                logger.info(
                    f"Signal #{signal_id} WON: {kline.symbol} LONG hit take-profit "
                    f"(TP={take_profit_1}, K-line high={kline_high}, PnL={pnl_ratio:.2f})"
                )

        elif direction == "short":
            # SHORT signal: price goes down to TP, up to SL
            # Check if high >= stop_loss (hit stop-loss)
            if kline_high >= stop_loss:
                await repository.update_signal_status(signal_id, "LOST", Decimal("-1.0"))
                logger.info(
                    f"Signal #{signal_id} LOST: {kline.symbol} SHORT hit stop-loss "
                    f"(SL={stop_loss}, K-line high={kline_high})"
                )
            # Check if low <= take_profit (hit take-profit)
            elif kline_low <= take_profit_1:
                # Calculate PnL ratio: (entry - TP) / (SL - entry)
                pnl_ratio = (entry_price - take_profit_1) / (stop_loss - entry_price)
                await repository.update_signal_status(signal_id, "WON", pnl_ratio)
                logger.info(
                    f"Signal #{signal_id} WON: {kline.symbol} SHORT hit take-profit "
                    f"(TP={take_profit_1}, K-line low={kline_low}, PnL={pnl_ratio:.2f})"
                )
