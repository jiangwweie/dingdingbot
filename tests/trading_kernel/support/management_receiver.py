"""Explicit empty connected receiver proof for current-schema local readiness tests."""

from src.trading_kernel.infrastructure.pg_unit_of_work import PostgresKernelUnitOfWork


async def ready_management_receiver(
    engine,
    *,
    now_ms,
    venue_id="binance-usdm",
    account_id=None,
    runtime_commit=None,
    ticket_id=None,
):
    import sqlalchemy as sa

    async with PostgresKernelUnitOfWork(engine) as u:
        c = u._require_connection()
        if account_id is None:
            account_id = await c.scalar(
                sa.text(
                    "SELECT account_id FROM brc_runtime_profiles WHERE runtime_profile_id='tiny-live-v1'"
                )
            )
        if runtime_commit is None:
            runtime_commit = await c.scalar(
                sa.text(
                    "SELECT certified_commit FROM brc_runtime_capabilities_current WHERE capability_key='exchange_commands'"
                )
            )
        scope = f"brc-app-manual-v1:{venue_id}:{account_id}"
        epoch = f"test-receiver:{runtime_commit}"
        current = await u.management.get_feed(scope)
        if current is None or current["epoch_id"] != epoch:
            await u.management.start_feed(
                scope_key=scope,
                epoch_id=epoch,
                worker_id="test-receiver",
                runtime_commit=runtime_commit,
                now_ms=now_ms,
            )
        await u.management.persist_stream_batch(
            scope_key=scope,
            epoch_id=epoch,
            events=[],
            connected_at_ms=now_ms,
            now_ms=now_ms,
            worker_id="test-receiver",
        )
        if ticket_id is not None:
            await u.management.save_coverage(
                ticket_id,
                through_ms=now_ms,
                complete=True,
                reason=None,
                observed_at_ms=now_ms,
                current_complete=True,
                attribution_complete=True,
                proof_refs={
                    "fixture": "recording venue has no external orders or intervention"
                },
            )


async def dispatch_with_recorded_management(uow_factory, venue, request, **kwargs):
    """Selection-only recording venues model a healthy empty external stream.

    Their scenarios exercise Selection/cancel/unknown authority, while dedicated
    management suites exercise missing, stale, queued and contradictory evidence.
    This helper persists the explicit receiver precondition without changing any
    capability, Ticket management mode, Owner policy or command result.
    """
    import sqlalchemy as sa

    from src.trading_kernel.application.dispatch_exchange_command import (
        dispatch_one_command,
    )

    async with uow_factory() as u:
        c = u._require_connection()
        commit = await c.scalar(
            sa.text(
                "SELECT certified_commit FROM brc_runtime_capabilities_current WHERE capability_key='exchange_commands'"
            )
        )
        if request.ticket_id is not None:
            a = await u.aggregates.get(request.ticket_id)
            if a is not None:
                d = a.identity.netting_domain
                scope = f"brc-app-manual-v1:{d.venue_id}:{d.account_id}"
                epoch = f"test-receiver:{commit}"
                current = await u.management.get_feed(scope)
                if current is None or current["epoch_id"] != epoch:
                    await u.management.start_feed(
                        scope_key=scope,
                        epoch_id=epoch,
                        worker_id="test-receiver",
                        runtime_commit=commit,
                        now_ms=request.now_ms,
                    )
                await u.management.persist_stream_batch(
                    scope_key=scope,
                    epoch_id=epoch,
                    events=[],
                    connected_at_ms=request.now_ms,
                    now_ms=request.now_ms,
                    worker_id="test-receiver",
                )
                await u.management.save_coverage(
                    request.ticket_id,
                    through_ms=request.now_ms,
                    complete=True,
                    reason=None,
                    observed_at_ms=request.now_ms,
                    current_complete=True,
                    attribution_complete=True,
                    proof_refs={
                        "fixture": "Selection recording venue with no external actor"
                    },
                )
    if request.runtime_commit is None:
        from src.trading_kernel.infrastructure.runtime_identity import (
            CURRENT_SCHEMA_REVISION,
        )

        request = request.model_copy(
            update={
                "runtime_commit": commit,
                "schema_revision": CURRENT_SCHEMA_REVISION,
            }
        )
    return await dispatch_one_command(uow_factory, venue, request, **kwargs)
