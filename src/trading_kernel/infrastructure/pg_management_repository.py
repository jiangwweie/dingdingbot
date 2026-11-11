"""Current scoped observation and append-only changed-order evidence."""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.trade_management import OrderEvidence, OrderTerms
from src.trading_kernel.infrastructure.pg_management_feed import PostgresManagementFeed
from src.trading_kernel.infrastructure.pg_models import (
    exchange_commands,
    order_command_baselines,
    trade_aggregates,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_models import (
    management_observation_current as coverage,
)
from src.trading_kernel.infrastructure.pg_models import (
    management_order_evidence as evidence,
)


class PostgresManagementRepository(PostgresManagementFeed):
    def __init__(self, connection: AsyncConnection):
        super().__init__(connection)
        self.new_evidence: dict[str, list[OrderEvidence]] = {}

    async def verified_exit_references(self, ticket_id: str, *, entry_time_ms: int, exit_time_ms: int,
        system_references: tuple) -> tuple:
        from src.trading_kernel.domain.order_attribution import (
            ExternalExitOrderReference,
        )
        from src.trading_kernel.domain.trade_management import ManagementMode

        ticket = (await self.c.execute(sa.select(trade_tickets).where(trade_tickets.c.ticket_id == ticket_id))).mappings().one()
        mode = await self.c.scalar(sa.select(trade_aggregates.c.management_mode).where(trade_aggregates.c.ticket_id == ticket_id))
        if mode != ManagementMode.MANUAL.value:
            return ()
        rows = (await self.c.execute(sa.select(evidence.c.payload).where(evidence.c.ticket_id == ticket_id,
            evidence.c.observed_at_ms >= entry_time_ms).order_by(evidence.c.observed_at_ms.desc()).limit(257))).scalars().all()
        if len(rows) > 256:
            raise ValueError("external exit evidence exceeds bounded review scope")
        own = {(r.namespace.value,r.submitted_exchange_order_id) for r in system_references}
        selected = {}
        for raw in rows:
            item = OrderEvidence.model_validate(raw)
            terms = item.terms
            key = (terms.order_namespace,terms.exchange_order_id)
            if key in own or key in selected or not terms.reduces_position:
                continue
            if (terms.identity[:4] != (ticket['venue_id'],ticket['account_id'],ticket['exchange_instrument_id'],ticket['position_side'])
                or not item.coverage_complete or item.known_command_outcome_pending
                or item.created_at_ms is None
                or not entry_time_ms <= item.created_at_ms <= item.exchange_event_at_ms <= exit_time_ms):
                continue
            if terms.order_namespace == 'conditional' and terms.order_type not in {'STOP_MARKET','TAKE_PROFIT_MARKET'}:
                continue
            selected[key] = ExternalExitOrderReference(ticket_id=ticket_id,
                exposure_episode_id=ticket['exposure_episode_id'], evidence_id=item.evidence_id,
                terms=terms,order_created_at_ms=item.created_at_ms,evidence_at_ms=item.exchange_event_at_ms)
        return tuple(selected[key] for key in sorted(selected))

    async def has_evidence(self, ticket_id, evidence_id):
        return bool(
            await self.c.scalar(
                sa.select(sa.literal(True)).where(
                    sa.exists(
                        sa.select(evidence.c.evidence_id).where(
                            evidence.c.ticket_id == ticket_id,
                            evidence.c.evidence_id == evidence_id,
                        )
                    )
                )
            )
        )

    async def has_conditional_child_link(self, ticket_id, item):
        from src.trading_kernel.infrastructure.pg_models import management_stream_events

        t = item.terms
        return bool(
            await self.c.scalar(
                sa.select(sa.literal(True)).where(
                    sa.or_(
                        sa.exists(
                            sa.select(evidence.c.evidence_id).where(
                                evidence.c.ticket_id == ticket_id,
                                evidence.c.payload["child_exchange_order_id"].astext
                                == t.exchange_order_id,
                            )
                        ),
                        sa.exists(
                            sa.select(management_stream_events.c.event_id).where(
                                management_stream_events.c.scope_key
                                == f"brc-app-manual-v1:{t.venue_id}:{t.account_id}",
                                management_stream_events.c.safe_payload["o"][
                                    "ai"
                                ].astext
                                == t.exchange_order_id,
                            )
                        ),
                    )
                )
            )
        )

    async def child_system_intents(self, ticket_id, item):
        from src.trading_kernel.application.management_intents import system_intents_for
        from src.trading_kernel.domain.trade_management import (
            OrderAction,
            SystemOrderIntent,
        )
        from src.trading_kernel.infrastructure.binance_management_observation import (
            parse_order_update,
        )
        from src.trading_kernel.infrastructure.pg_models import management_stream_events

        t = item.terms
        if t.order_namespace != "regular":
            return ()
        parents = (
            (
                await self.c.execute(
                    sa.select(evidence.c.payload)
                    .where(
                        evidence.c.ticket_id == ticket_id,
                        evidence.c.payload["child_exchange_order_id"].astext
                        == t.exchange_order_id,
                    )
                    .limit(9)
                )
            )
            .scalars()
            .all()
        )
        raw = (
            (
                await self.c.execute(
                    sa.select(management_stream_events)
                    .where(
                        management_stream_events.c.scope_key
                        == f"brc-app-manual-v1:{t.venue_id}:{t.account_id}",
                        management_stream_events.c.safe_payload["e"].astext
                        == "ALGO_UPDATE",
                        management_stream_events.c.safe_payload["o"]["ai"].astext
                        == t.exchange_order_id,
                    )
                    .limit(9)
                )
            )
            .mappings()
            .all()
        )
        if len(parents) > 8 or len(raw) > 8:
            raise ValueError("conditional child proof ambiguous")
        parsed = [OrderEvidence.model_validate(p) for p in parents]
        parsed.extend(
            parse_order_update(
                r["safe_payload"],
                account_id=t.account_id,
                received_at_ms=r["received_at_ms"],
                coverage_complete=True,
            )
            for r in raw
        )
        for parent in parsed:
            pt = parent.terms
            if (
                pt.identity[:4] != t.identity[:4]
                or pt.side != t.side
                or pt.quantity != t.quantity
                or pt.order_type not in {'STOP_MARKET','TAKE_PROFIT_MARKET'}
                or t.order_type!='MARKET' or t.price is not None or t.trigger_price is not None
            ):
                continue
            rows = await self.command_rows_for_order(
                ticket_id, "conditional", pt.exchange_order_id
            )
            matched = system_intents_for(parent, rows)
            if any(intent.terms == pt for intent in matched):
                return (
                    SystemOrderIntent(
                        command_id=matched[0].command_id,
                        action=OrderAction.NEW,
                        terms=t,
                        exchange_event_at_ms=item.created_at_ms
                        or item.exchange_event_at_ms,
                    ),
                )
        return ()

    async def pending_command_rows(self, ticket_id):
        rows = (
            (
                await self.c.execute(
                    sa.select(exchange_commands)
                    .where(
                        exchange_commands.c.ticket_id == ticket_id,
                        exchange_commands.c.status.in_(
                            (
                                "prepared",
                                "claimed",
                                "dispatch_started",
                                "outcome_unknown",
                            )
                        ),
                    )
                    .order_by(exchange_commands.c.created_at_ms)
                    .limit(129)
                )
            )
            .mappings()
            .all()
        )
        if len(rows) > 128:
            raise ValueError("active command work exceeds bounded safety scope")
        return [dict(r) for r in rows]

    async def accepted_orders_confirmed(self, ticket_id):
        missing = await self.c.scalar(
            sa.select(exchange_commands.c.command_id)
            .where(
                exchange_commands.c.ticket_id == ticket_id,
                exchange_commands.c.status.in_(("accepted", "reconciled_accepted")),
                exchange_commands.c.command_kind != "cancel_order",
                ~sa.exists(
                    sa.select(order_command_baselines.c.command_id).where(
                        order_command_baselines.c.command_id
                        == exchange_commands.c.command_id
                    )
                ),
            )
            .limit(1)
        )
        return missing is None

    async def ticket_stream_is_applied(self, ticket_id):
        from src.trading_kernel.domain.product_identity import PRODUCT_ID
        from src.trading_kernel.infrastructure.pg_models import management_stream_events

        ticket = (
            (
                await self.c.execute(
                    sa.select(trade_tickets).where(
                        trade_tickets.c.ticket_id == ticket_id
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        current = await self.get_coverage(ticket_id)
        if ticket is None or current is None or not current["continuity_complete"]:
            return False
        latest = await self.c.scalar(
            sa.select(management_stream_events.c.received_at_ms)
            .where(
                management_stream_events.c.scope_key
                == f"{PRODUCT_ID}:{ticket['venue_id']}:{ticket['account_id']}",
                management_stream_events.c.safe_payload["o"]["s"].astext
                == ticket["exchange_instrument_id"].split(":")[1],
                sa.func.lower(management_stream_events.c.safe_payload["o"]["ps"].astext)
                == ticket["position_side"],
            )
            .order_by(management_stream_events.c.received_at_ms.desc())
            .limit(1)
        )
        return latest is None or latest <= current["covered_until_ms"]

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
            persisted = OrderEvidence.model_validate(old["payload"])
            if (
                old["ticket_id"] != ticket_id
                or persisted.terms != item.terms
                or persisted.exchange_event_at_ms != item.exchange_event_at_ms
                or persisted.executed_quantity != item.executed_quantity
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
        current_complete: bool = False,
        attribution_complete: bool = False,
        proof_refs: dict | None = None,
    ):
        old = await self.get_coverage(ticket_id)
        through = max(
            through_ms if complete else 1, old["covered_until_ms"] if old else 1
        )
        values = {
            "ticket_id": ticket_id,
            "covered_until_ms": through,
            "continuity_complete": complete,
            "current_complete": current_complete,
            "attribution_complete": attribution_complete,
            "proof_refs": proof_refs or {},
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

    async def save_baseline(self, ticket_id, evidence, command_rows):
        from src.trading_kernel.application.management_intents import system_intents_for
        from src.trading_kernel.domain.trade_management import OrderAction

        intents = system_intents_for(evidence, command_rows)
        for intent in intents:
            if intent.action is not OrderAction.NEW or intent.terms != evidence.terms:
                continue
            values = {
                "baseline_id": f"baseline:{intent.command_id}",
                "command_id": intent.command_id,
                "scope_key": f"{evidence.terms.venue_id}:{evidence.terms.account_id}",
                "order_namespace": evidence.terms.order_namespace,
                "exchange_order_id": evidence.terms.exchange_order_id,
                "confirmed_terms": evidence.terms.model_dump(mode="json"),
                "evidence_id": evidence.evidence_id,
                "confirmed_at_ms": evidence.received_at_ms,
            }
            old = (
                (
                    await self.c.execute(
                        sa.select(order_command_baselines).where(
                            order_command_baselines.c.command_id == intent.command_id
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if old is not None:
                # JSON preserves Decimal scale; order identity depends on exact
                # numeric values, not whether the venue sent 2135.9 or 2135.90.
                if any(
                    old[k] != values[k]
                    for k in (
                        "scope_key",
                        "order_namespace",
                        "exchange_order_id",
                    )
                ) or OrderTerms.model_validate(old["confirmed_terms"]) != evidence.terms:
                    raise ValueError("command baseline identity collision")
                continue
            await self.c.execute(insert(order_command_baselines).values(**values))

    async def command_rows(self, ticket_id: str) -> list[dict]:
        # Keep candidate work bounded. Exact older order matching is fetched by
        # its namespace/order ID when that evidence is actually observed.
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
        return await self._with_baselines(rows[:200])

    async def command_rows_for_order(self, ticket_id, namespace, order_id):
        rows = (
            (
                await self.c.execute(
                    sa.select(exchange_commands)
                    .where(
                        exchange_commands.c.ticket_id == ticket_id,
                        sa.case(
                            (
                                exchange_commands.c.command_kind == "cancel_order",
                                exchange_commands.c.request_payload[
                                    "order_namespace"
                                ].astext,
                            ),
                            (
                                exchange_commands.c.request_payload[
                                    "order_type"
                                ].astext.in_(("stop_market", "take_profit_market")),
                                "conditional",
                            ),
                            else_="regular",
                        )
                        == namespace,
                        sa.or_(
                            exchange_commands.c.result_payload[
                                "exchange_order_id"
                            ].astext
                            == order_id,
                            exchange_commands.c.request_payload[
                                "exchange_order_id"
                            ].astext
                            == order_id,
                        ),
                    )
                    .limit(20)
                )
            )
            .mappings()
            .all()
        )
        return await self._with_baselines(rows)

    async def _with_baselines(self, rows):
        if not rows:
            return []
        ids = [r["command_id"] for r in rows]
        baselines = (
            (
                await self.c.execute(
                    sa.select(order_command_baselines).where(
                        order_command_baselines.c.command_id.in_(ids)
                    )
                )
            )
            .mappings()
            .all()
        )
        by_command = {r["command_id"]: r["confirmed_terms"] for r in baselines}
        result = []
        for r in rows:
            row = dict(r)
            if r["command_id"] in by_command:
                row["result_payload"] = {
                    **(r["result_payload"] or {}),
                    "management_baseline": by_command[r["command_id"]],
                }
            result.append(row)
        return result

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
                coverage.c.continuity_complete.is_(False),
                trade_tickets.c.ticket_id.in_(
                    sa.select(trade_aggregates.c.ticket_id).where(
                        trade_aggregates.c.management_mode != "MANUAL"
                    )
                ),
            )
            .limit(1)
        )
        return "management_observation_gap" if gap is not None else None
