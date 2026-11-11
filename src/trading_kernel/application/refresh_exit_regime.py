"""One bounded public-data refresh owned by the existing Observation worker."""

from __future__ import annotations

import asyncio

from src.trading_kernel.application.market_ports import (
    ClosedCandleRequest,
    PublicMarketSource,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.exit_regime import (
    BTC_USDM,
    FOUR_HOURS_MS,
    BtcMa50Snapshot,
)


async def refresh_exit_regime(
    uow_factory: UnitOfWorkFactory,
    source: PublicMarketSource,
    *,
    now_ms: int,
    timeout_seconds: float,
    runtime_commit: str,
    schema_revision: str,
) -> None:
    async with uow_factory() as uow:
        capability = await uow.signals.get_runtime_capability("strategy_signal_ingest")
        if (
            capability is None
            or capability.certified_commit != runtime_commit
            or capability.schema_revision != schema_revision
        ):
            return
        profile = await uow.signals.get_runtime_profile("tiny-live-v1")
        configuration = (
            None
            if profile is None
            else await uow.exit_profiles.get_current_configuration(
                venue_id=profile.venue_id, account_id=profile.account_id
            )
        )
        if configuration is None or not any(
            e.ma50_enabled for e in configuration.intent.events
        ):
            return
        snapshot = await uow.exit_profiles.get_ma50_snapshot()
        if (
            snapshot is not None
            and snapshot.observed_at_ms <= now_ms < snapshot.valid_until_ms
        ):
            return
        monitor = await uow.monitors.get("btc-ma50-refresh")
        if monitor is not None and now_ms - monitor.updated_at_ms < 30_000:
            return
        from src.trading_kernel.application.ports import (
            MonitorOwnerStatus,
            MonitorStateRecord,
        )

        await uow.monitors.save_if_changed(
            monitor.model_copy(update={"updated_at_ms": now_ms})
            if monitor is not None
            else MonitorStateRecord(
                monitor_key="btc-ma50-refresh",
                owner_status=MonitorOwnerStatus.PROCESSING,
                summary="BTC MA50 refresh pending",
                intervention="none",
                ticket_id=None,
                incident_id=None,
                updated_at_ms=now_ms,
            )
        )
    latest = now_ms // FOUR_HOURS_MS * FOUR_HOURS_MS
    try:
        rows = await asyncio.wait_for(
            source.fetch_closed_candles(
                ClosedCandleRequest(
                    exchange_instrument_id=BTC_USDM,
                    timeframe="4h",
                    limit=50,
                    since_ms=latest - 50 * FOUR_HOURS_MS,
                    closed_at_ms=latest,
                )
            ),
            timeout=timeout_seconds,
        )
        snapshot = BtcMa50Snapshot.create(candles=rows, observed_at_ms=now_ms)
    except Exception as exc:  # noqa: BLE001 - absent/stale fact fails closed only for configured Events.
        async with uow_factory() as uow:
            capability = await uow.signals.get_runtime_capability(
                "strategy_signal_ingest"
            )
            if (
                capability is not None
                and capability.certified_commit == runtime_commit
                and capability.schema_revision == schema_revision
            ):
                await uow.monitors.save_if_changed(
                    MonitorStateRecord(
                        monitor_key="btc-ma50-refresh",
                        owner_status=MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
                        summary="BTC MA50 facts unavailable: " + type(exc).__name__,
                        intervention="三LONG等待准确闭合行情",
                        updated_at_ms=now_ms,
                    )
                )
        return
    async with uow_factory() as uow:
        capability = await uow.signals.get_runtime_capability("strategy_signal_ingest")
        if (
            capability is None
            or capability.certified_commit != runtime_commit
            or capability.schema_revision != schema_revision
        ):
            return
        saved = await uow.exit_profiles.save_ma50_snapshot(snapshot)
        if not saved:
            await uow.monitors.save_if_changed(
                MonitorStateRecord(
                    monitor_key="btc-ma50-refresh",
                    owner_status=MonitorOwnerStatus.TEMPORARILY_UNAVAILABLE,
                    summary="BTC MA50 closed window conflict",
                    intervention="三LONG等待准确闭合行情",
                    updated_at_ms=now_ms,
                )
            )
            return
        await uow.monitors.save_if_changed(
            MonitorStateRecord(
                monitor_key="btc-ma50-refresh",
                owner_status=MonitorOwnerStatus.RUNNING,
                summary="BTC MA50 closed facts current",
                intervention="none",
                updated_at_ms=now_ms,
            )
        )
