"""Prepare a requested phone preview from current venue observations, without writes."""

import asyncio
from decimal import Decimal

from src.trading_kernel.application.owner_operation_facts import (
    OwnerOperationFactsSource,
)
from src.trading_kernel.application.ports import UnitOfWorkFactory
from src.trading_kernel.domain.owner_position_operation import (
    OwnerPositionPreview,
    preview_position_operation,
)
from src.trading_kernel.domain.owner_reduction import (
    OwnerReductionPreview,
    preview_owner_reduction,
)


async def prepare_owner_position_preview(
    factory: UnitOfWorkFactory,
    source: OwnerOperationFactsSource,
    row: dict,
    *,
    now_ms: int,
    timeout_seconds: float,
) -> str:
    async with factory() as u:
        a = await u.aggregates.get(row["ticket_id"])
        if a is None:
            return "ticket_missing"
        rules = await u.signals.get_instrument_rules(
            a.identity.netting_domain.venue_id,
            a.identity.netting_domain.exchange_instrument_id,
        )
        commands = tuple(await u.exchange_commands.list_for_ticket(row["ticket_id"]))
        refs = {
            r.command_id: r.submitted_exchange_order_id
            for r in await u.exchange_commands.list_order_references(row["ticket_id"])
        }
        active = await u.owner_position_operations.active_for_ticket(row["ticket_id"])
    preview: OwnerReductionPreview | OwnerPositionPreview | None
    if rules is None or active is not None or now_ms >= row["created_at_ms"] + 30000:
        reason = "preview_unavailable_or_expired"
        preview = None
    else:
        try:
            observed = await asyncio.wait_for(
                source.read_owner_position(
                    aggregate=a,
                    commands=commands,
                    accepted_order_ids=refs,
                    operation_id=None,
                ),
                timeout=timeout_seconds,
            )
            now_ms = max(now_ms, observed.facts.observed_at_ms)
            params = row["payload"]["request"]
            if row["kind"] == "position_reduce":
                preview = preview_owner_reduction(
                    aggregate=a,
                    facts=observed.facts,
                    quantity_step=rules.quantity_step,
                    minimum_quantity=rules.min_quantity,
                    minimum_notional=rules.min_notional,
                    now_ms=now_ms,
                    requested_quantity=Decimal(params["quantity"]),
                )
            else:
                preview = preview_position_operation(
                    aggregate=a,
                    facts=observed.facts,
                    quantity_step=rules.quantity_step,
                    minimum_quantity=rules.min_quantity,
                    minimum_notional=rules.min_notional,
                    now_ms=now_ms,
                    kind=row["kind"],
                    price_tick=rules.price_tick,
                    price=None
                    if params.get("price") is None
                    else Decimal(params["price"]),
                    quantity=None
                    if params.get("quantity") is None
                    else Decimal(params["quantity"]),
                )
            reason = None
        except (ValueError, TypeError, TimeoutError) as exc:
            reason = f"preview:{str(exc) if isinstance(exc, ValueError) else type(exc).__name__}"[
                :200
            ]
            preview = None
    async with factory() as u:
        latest = await u.owner_position_operations.get(
            row["operation_id"], for_update=True
        )
        current = await u.aggregates.get_for_update(row["ticket_id"])
        if latest is None or latest["version"] != row["version"]:
            return "preview_changed"
        if preview is None or current is None or current.version != a.version:
            await u.owner_position_operations.transition(
                operation_id=row["operation_id"],
                expected_version=row["version"],
                state="rejected",
                payload=row["payload"],
                reason=reason or "source_changed",
                now_ms=now_ms,
                completed=True,
            )
            return "rejected"
        await u.owner_position_operations.ready_preview(latest, preview, now_ms=now_ms)
        return "previewed"
