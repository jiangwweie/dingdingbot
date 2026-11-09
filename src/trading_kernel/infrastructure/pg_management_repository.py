"""Current scoped observation and append-only changed-order evidence."""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.trade_management import OrderEvidence
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    trade_aggregates,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_models import (
    management_observation_current as coverage,
)
from src.trading_kernel.infrastructure.pg_models import (
    management_order_evidence as evidence,
)


class PostgresManagementRepository:
    def __init__(self, connection: AsyncConnection):
        self.c = connection
        self.new_evidence: dict[str, list[OrderEvidence]] = {}

    async def refresh_orders(self, ticket_id: str, orders: list) -> None:
        await self.c.execute(
            sa.update(trade_aggregates)
            .where(trade_aggregates.c.ticket_id == ticket_id)
            .values(management_orders=orders)
        )

    async def get_coverage(self, ticket_id: str):
        r = (
            (
                await self.c.execute(
                    sa.select(coverage).where(coverage.c.ticket_id == ticket_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if r is None else dict(r)

    async def save_evidence(self, ticket_id: str, item: OrderEvidence) -> bool:
        value = item.model_dump(mode="json")
        old = (
            (
                await self.c.execute(
                    sa.select(evidence.c.ticket_id, evidence.c.payload).where(
                        evidence.c.evidence_id == item.evidence_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if old is not None:
            if old["ticket_id"] != ticket_id or any(
                old["payload"].get(k) != value.get(k)
                for k in ("terms", "exchange_event_at_ms", "executed_quantity")
            ):
                raise ValueError("management evidence identity collision")
            return False
        await self.c.execute(
            sa.insert(evidence).values(
                evidence_id=item.evidence_id,
                ticket_id=ticket_id,
                payload=value,
                observed_at_ms=item.received_at_ms,
            )
        )
        self.new_evidence.setdefault(ticket_id, []).append(item)
        return True

    async def save_coverage(
        self,
        ticket_id: str,
        *,
        through_ms: int,
        complete: bool,
        reason: str | None,
        observed_at_ms: int,
    ):
        old = await self.get_coverage(ticket_id)
        through = max(
            through_ms if complete else 1, old["covered_until_ms"] if old else 1
        )
        values = {
            "ticket_id": ticket_id,
            "covered_until_ms": through,
            "facts_complete": complete,
            "reason": reason,
            "updated_at_ms": observed_at_ms,
        }
        stmt = (
            insert(coverage)
            .values(**values)
            .on_conflict_do_update(
                index_elements=[coverage.c.ticket_id],
                set_={k: v for k, v in values.items() if k != "ticket_id"},
            )
        )
        await self.c.execute(stmt)

    async def refresh_manual_risk(
        self,
        ticket_id: str,
        *,
        observed_at_ms: int,
        risk: Decimal | None,
        reason: str | None,
        orders: list,
    ):
        await self.c.execute(
            sa.update(trade_aggregates)
            .where(
                trade_aggregates.c.ticket_id == ticket_id,
                trade_aggregates.c.management_mode == "MANUAL",
            )
            .values(
                management_observed_at_ms=observed_at_ms,
                manual_risk_at_stop=risk,
                manual_risk_reason=reason,
                management_orders=orders,
            )
        )

    async def command_rows(self, ticket_id: str) -> list[dict]:
        rows = (
            (
                await self.c.execute(
                    sa.select(exchange_commands)
                    .where(exchange_commands.c.ticket_id == ticket_id)
                    .order_by(exchange_commands.c.created_at_ms.desc())
                    .limit(201)
                )
            )
            .mappings()
            .all()
        )
        if len(rows) > 200:
            raise ValueError("management command history exceeds bounded page")
        return [dict(r) for r in rows]

    async def account_blocker(
        self, venue_id: str, account_id: str, now_ms: int
    ) -> str | None:
        row = (
            (
                await self.c.execute(
                    sa.select(
                        trade_aggregates.c.management_mode,
                        trade_aggregates.c.manual_risk_reason,
                        trade_aggregates.c.management_observed_at_ms,
                    )
                    .join(
                        trade_tickets,
                        trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
                    )
                    .where(
                        trade_tickets.c.venue_id == venue_id,
                        trade_tickets.c.account_id == account_id,
                        trade_tickets.c.terminal_at_ms.is_(None),
                        sa.or_(
                            trade_aggregates.c.management_mode == "REVIEW_REQUIRED",
                            sa.and_(
                                trade_aggregates.c.management_mode == "MANUAL",
                                sa.or_(
                                    trade_aggregates.c.manual_risk_reason.is_not(None),
                                    trade_aggregates.c.manual_risk_at_stop.is_(None),
                                    trade_aggregates.c.management_observed_at_ms.is_(
                                        None
                                    ),
                                    trade_aggregates.c.management_observed_at_ms
                                    < now_ms - 30000,
                                ),
                            ),
                        ),
                    )
                    .limit(1)
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return "manual_management_risk_unavailable"
        gap = await self.c.scalar(
            sa.select(coverage.c.ticket_id)
            .join(trade_tickets, trade_tickets.c.ticket_id == coverage.c.ticket_id)
            .where(
                trade_tickets.c.venue_id == venue_id,
                trade_tickets.c.account_id == account_id,
                trade_tickets.c.terminal_at_ms.is_(None),
                coverage.c.facts_complete.is_(False),
            )
            .limit(1)
        )
        return "management_observation_gap" if gap is not None else None
