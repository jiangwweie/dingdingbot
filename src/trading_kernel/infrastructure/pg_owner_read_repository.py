"""Bounded read-only PostgreSQL access for Owner Console read models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    Freshness,
    MoneyMetric,
    OverviewEvidenceGap,
    OverviewFacts,
)
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    admission_decisions,
    capacity_claims,
    monitor_current,
    owner_policy_current,
    runtime_incidents,
    runtime_profiles,
    runtime_scopes_current,
    signal_events,
    trade_aggregates,
    trade_reviews,
    trade_tickets,
)

_VENUE_ID = "binance-usdm"
_FRESH_AGE_MS = 30_000
_STALE_MAX_AGE_MS = 300_000


def create_owner_read_engine(dsn: str) -> AsyncEngine:
    return create_async_engine(
        dsn,
        pool_size=1,
        max_overflow=1,
        pool_pre_ping=True,
        connect_args={
            "server_settings": {
                "application_name": "brc_owner_console",
                "default_transaction_read_only": "on",
                "statement_timeout": "3000",
            }
        },
    )


@asynccontextmanager
async def owner_read_transaction(
    engine: AsyncEngine,
) -> AsyncIterator[AsyncConnection]:
    async with engine.connect() as raw:
        connection = await raw.execution_options(
            isolation_level="REPEATABLE READ"
        )
        transaction = await connection.begin()
        try:
            await connection.execute(sa.text("SET TRANSACTION READ ONLY"))
            yield connection
            await transaction.commit()
        except BaseException:
            await transaction.rollback()
            raise


class PostgresOwnerReadRepository:
    __slots__ = ("_connection",)

    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def read_overview_facts(
        self,
        day_start_ms: int,
        now_ms: int,
    ) -> OverviewFacts:
        """Read one bounded overview snapshot on the caller's transaction."""

        authority_rows = (
            await self._connection.execute(_overview_authority_query())
        ).mappings().all()
        authority = authority_rows[0] if len(authority_rows) == 1 else None
        venue_id = None if authority is None else str(authority["venue_id"])
        account_id = None if authority is None else str(authority["account_id"])
        runtime_profile_id = (
            None if authority is None else str(authority["runtime_profile_id"])
        )

        claim = (
            await self._connection.execute(
                _latest_capacity_claim_query(
                    venue_id=venue_id,
                    account_id=account_id,
                )
            )
        ).mappings().one_or_none()
        incident_query_rows = (
            await self._connection.execute(
                _open_incidents_query(
                    venue_id=venue_id,
                    account_id=account_id,
                )
            )
        ).mappings().all()
        incident_limit_reached = len(incident_query_rows) > 20
        incident_rows = incident_query_rows[:20]
        monitor_query_rows = (
            await self._connection.execute(
                _monitor_rows_query(
                    venue_id=venue_id,
                    account_id=account_id,
                )
            )
        ).mappings().all()
        monitor_limit_reached = len(monitor_query_rows) > 100
        monitor_rows = monitor_query_rows[:100]
        active_ticket_query_rows = (
            await self._connection.execute(
                _active_tickets_query(
                    venue_id=venue_id,
                    account_id=account_id,
                )
            )
        ).mappings().all()
        active_ticket_limit_reached = len(active_ticket_query_rows) > 20
        active_ticket_rows = active_ticket_query_rows[:20]
        count_row = (
            await self._connection.execute(
                _today_counts_query(
                    day_start_ms=day_start_ms,
                    runtime_profile_id=runtime_profile_id,
                    venue_id=venue_id,
                    account_id=account_id,
                )
            )
        ).mappings().one()
        review_row = (
            await self._connection.execute(
                _today_reviews_query(
                    day_start_ms=day_start_ms,
                    venue_id=venue_id,
                    account_id=account_id,
                )
            )
        ).mappings().one()

        contradictory_reasons: list[str] = []
        evidence_gaps: list[OverviewEvidenceGap] = []
        if len(authority_rows) > 1:
            contradictory_reasons.append("multiple_configured_owner_authorities")
        if not authority_rows:
            evidence_gaps.append(
                _evidence_gap(
                    reason="configured_owner_authority_missing",
                    kind="event",
                    identity="owner_policy:configured",
                    occurred_at_ms=now_ms,
                )
            )
        elif authority is not None and authority["exposure_venue_id"] is None:
            evidence_gaps.append(
                _evidence_gap(
                    reason="account_exposure_current_missing",
                    kind="event",
                    identity=(
                        f"account:{authority['venue_id']}:{authority['account_id']}"
                    ),
                    occurred_at_ms=now_ms,
                )
            )

        max_concurrent_tickets = (
            None
            if authority is None
            else int(authority["max_concurrent_tickets"])
        )
        active_ticket_count = (
            None
            if authority is None or authority["active_ticket_count"] is None
            else int(authority["active_ticket_count"])
        )
        active_ticket_total = len(active_ticket_rows)
        if (
            not active_ticket_limit_reached
            and active_ticket_count is not None
            and active_ticket_total != active_ticket_count
        ):
            contradictory_reasons.append("active_ticket_count_mismatch")
        if (
            max_concurrent_tickets is not None
            and active_ticket_count is not None
            and active_ticket_count > max_concurrent_tickets
        ):
            contradictory_reasons.append("active_ticket_count_exceeds_policy")

        if active_ticket_limit_reached:
            boundary = active_ticket_query_rows[20]
            evidence_gaps.append(
                _evidence_gap(
                    reason="active_ticket_limit_reached",
                    kind="ticket",
                    identity=str(boundary["ticket_id"]),
                    occurred_at_ms=int(boundary["updated_at_ms"]),
                )
            )
        incident_total = None if incident_limit_reached else len(incident_rows)
        if incident_limit_reached:
            boundary = incident_query_rows[20]
            evidence_gaps.append(
                _evidence_gap(
                    reason="open_incident_limit_reached",
                    kind="incident",
                    identity=str(boundary["incident_id"]),
                    occurred_at_ms=int(boundary["opened_at_ms"]),
                )
            )
        if monitor_limit_reached:
            boundary = monitor_query_rows[100]
            evidence_gaps.append(
                _evidence_gap(
                    reason="monitor_limit_reached",
                    kind="event",
                    identity=str(boundary["monitor_key"]),
                    occurred_at_ms=int(boundary["updated_at_ms"]),
                )
            )

        claim_id = None if claim is None else str(claim["capacity_claim_id"])
        wallet_balance = (
            None
            if claim is None
            else Decimal(str(claim["total_wallet_balance_at_claim"]))
        )
        available_margin = (
            None
            if claim is None
            else Decimal(str(claim["available_margin_at_claim"]))
        )
        claim_created_at_ms = (
            None if claim is None else int(claim["created_at_ms"])
        )

        attention_incidents = [
            row for row in incident_rows if not bool(row["needs_intervention"])
        ]
        latest_blocking = incident_query_rows[0] if incident_query_rows else None
        if (
            latest_blocking is not None
            and latest_blocking["top_actionable_incident_id"] is None
        ):
            latest_blocking = None
        intervention_monitor = (
            monitor_query_rows[0] if monitor_query_rows else None
        )
        if (
            intervention_monitor is not None
            and intervention_monitor["needs_intervention_monitor_key"] is None
        ):
            intervention_monitor = None

        today_net_pnl, today_net_r, review_gap, review_evidence = (
            _review_aggregate_metrics(review_row)
        )
        if review_gap is not None:
            review_gap_evidence = (
                review_evidence[0]
                if review_evidence
                else EvidenceRef(
                    kind="review",
                    identity="review:current",
                    occurred_at_ms=now_ms,
                )
            )
            evidence_gaps.append(
                OverviewEvidenceGap(
                    reason=review_gap,
                    evidence=review_gap_evidence,
                )
            )
        freshness, freshness_identity, freshness_at_ms = _overview_freshness(
            authority=authority,
            monitor_rows=monitor_rows,
            now_ms=now_ms,
            contradictory=bool(contradictory_reasons),
        )
        evidence = _unique_evidence(
            (
                *(
                    EvidenceRef(
                        kind="incident",
                        identity=str(row["incident_id"]),
                        occurred_at_ms=int(row["opened_at_ms"]),
                    )
                    for row in incident_rows
                ),
                *(
                    ()
                    if latest_blocking is None
                    else (
                        EvidenceRef(
                            kind="incident",
                            identity=str(
                                latest_blocking["top_actionable_incident_id"]
                            ),
                            occurred_at_ms=int(
                                latest_blocking[
                                    "top_actionable_incident_opened_at_ms"
                                ]
                            ),
                        ),
                    )
                ),
                *(
                    EvidenceRef(
                        kind="event",
                        identity=str(row["monitor_key"]),
                        occurred_at_ms=int(row["updated_at_ms"]),
                    )
                    for row in monitor_rows
                ),
                *(
                    ()
                    if intervention_monitor is None
                    else (
                        EvidenceRef(
                            kind="event",
                            identity=str(
                                intervention_monitor[
                                    "needs_intervention_monitor_key"
                                ]
                            ),
                            occurred_at_ms=int(
                                intervention_monitor[
                                    "needs_intervention_monitor_updated_at_ms"
                                ]
                            ),
                        ),
                    )
                ),
                *(
                    EvidenceRef(
                        kind="ticket",
                        identity=str(row["ticket_id"]),
                        occurred_at_ms=int(row["updated_at_ms"]),
                    )
                    for row in active_ticket_rows
                ),
                *review_evidence,
            )
        )

        return OverviewFacts(
            observed_at_ms=now_ms,
            runtime_freshness=freshness,
            freshness_evidence_identity=freshness_identity,
            freshness_evidence_at_ms=freshness_at_ms,
            max_concurrent_tickets=max_concurrent_tickets,
            active_ticket_count=active_ticket_count,
            active_ticket_ids=tuple(
                str(row["ticket_id"]) for row in active_ticket_rows
            ),
            latest_capacity_claim_id=claim_id,
            latest_wallet_balance_at_claim=wallet_balance,
            latest_available_margin_at_claim=available_margin,
            latest_claim_created_at_ms=claim_created_at_ms,
            open_owner_incident_id=(
                None
                if latest_blocking is None
                else str(latest_blocking["top_actionable_incident_id"])
            ),
            open_owner_incident_opened_at_ms=(
                None
                if latest_blocking is None
                else int(
                    latest_blocking["top_actionable_incident_opened_at_ms"]
                )
            ),
            attention_incident_ids=tuple(
                str(row["incident_id"]) for row in attention_incidents
            ),
            attention_incident_opened_at_ms=tuple(
                int(row["opened_at_ms"]) for row in attention_incidents
            ),
            monitor_statuses=tuple(
                str(row["owner_status"]) for row in monitor_rows
            ),
            monitor_keys=tuple(
                str(row["monitor_key"]) for row in monitor_rows
            ),
            monitor_updated_at_ms=tuple(
                int(row["updated_at_ms"]) for row in monitor_rows
            ),
            needs_intervention_monitor_key=(
                None
                if intervention_monitor is None
                else str(
                    intervention_monitor["needs_intervention_monitor_key"]
                )
            ),
            needs_intervention_monitor_updated_at_ms=(
                None
                if intervention_monitor is None
                else int(
                    intervention_monitor[
                        "needs_intervention_monitor_updated_at_ms"
                    ]
                )
            ),
            contradictory_fact_reasons=tuple(contradictory_reasons),
            contradictory_evidence_identity=(
                freshness_identity if contradictory_reasons else None
            ),
            evidence_gaps=tuple(evidence_gaps),
            today_net_pnl=today_net_pnl,
            today_net_r=today_net_r,
            today_signal_count=int(count_row["signal_count"]),
            admitted_signal_count=int(count_row["admitted_count"]),
            rejected_signal_count=int(count_row["rejected_count"]),
            execution_incident_count=incident_total,
            evidence=evidence,
        )


def _overview_authority_query() -> sa.Select[Any]:
    runtime_profile_id = owner_policy_current.c.scope[
        "runtime_profile_id"
    ].as_string()
    return (
        sa.select(
            owner_policy_current.c.owner_policy_id,
            owner_policy_current.c.max_concurrent_tickets,
            owner_policy_current.c.updated_at_ms.label("policy_updated_at_ms"),
            runtime_profiles.c.runtime_profile_id,
            runtime_profiles.c.updated_at_ms.label("profile_updated_at_ms"),
            runtime_profiles.c.venue_id,
            runtime_profiles.c.account_id,
            account_exposure_current.c.venue_id.label("exposure_venue_id"),
            account_exposure_current.c.account_id.label("exposure_account_id"),
            account_exposure_current.c.active_ticket_count,
            account_exposure_current.c.updated_at_ms.label(
                "exposure_updated_at_ms"
            ),
        )
        .select_from(
            owner_policy_current.join(
                runtime_profiles,
                runtime_profiles.c.runtime_profile_id == runtime_profile_id,
            ).outerjoin(
                account_exposure_current,
                sa.and_(
                    account_exposure_current.c.venue_id
                    == runtime_profiles.c.venue_id,
                    account_exposure_current.c.account_id
                    == runtime_profiles.c.account_id,
                ),
            )
        )
        .where(
            owner_policy_current.c.enabled.is_(True),
            runtime_profiles.c.status == "active",
            runtime_profiles.c.venue_id == _VENUE_ID,
        )
        .order_by(
            owner_policy_current.c.priority_rank,
            owner_policy_current.c.owner_policy_id,
        )
        .limit(2)
    )


def _latest_capacity_claim_query(
    *, venue_id: str | None, account_id: str | None
) -> sa.Select[Any]:
    scope = _exact_scope(
        venue_column=capacity_claims.c.venue_id,
        account_column=capacity_claims.c.account_id,
        venue_id=venue_id,
        account_id=account_id,
    )
    return (
        sa.select(
            capacity_claims.c.capacity_claim_id,
            capacity_claims.c.total_wallet_balance_at_claim,
            capacity_claims.c.available_margin_at_claim,
            capacity_claims.c.created_at_ms,
        )
        .where(scope)
        .order_by(capacity_claims.c.created_at_ms.desc())
        .limit(1)
    )


def _open_incidents_query(
    *, venue_id: str | None, account_id: str | None
) -> sa.Select[Any]:
    ticket = trade_tickets.alias("incident_ticket")
    scope = _incident_scope(
        incident=runtime_incidents,
        ticket=ticket,
        venue_id=venue_id,
        account_id=account_id,
    )
    needs_intervention = _incident_needs_intervention(runtime_incidents)
    actionable_incident = runtime_incidents.alias("actionable_incident")
    actionable_ticket = trade_tickets.alias("actionable_incident_ticket")
    actionable_scope = _incident_scope(
        incident=actionable_incident,
        ticket=actionable_ticket,
        venue_id=venue_id,
        account_id=account_id,
    )
    top_actionable = (
        sa.select(
            actionable_incident.c.incident_id.label(
                "top_actionable_incident_id"
            ),
            actionable_incident.c.opened_at_ms.label(
                "top_actionable_incident_opened_at_ms"
            ),
        )
        .select_from(
            actionable_incident.outerjoin(
                actionable_ticket,
                actionable_ticket.c.ticket_id == actionable_incident.c.ticket_id,
            )
        )
        .where(
            actionable_incident.c.status == "open",
            actionable_scope,
            _incident_needs_intervention(actionable_incident),
        )
        .order_by(
            actionable_incident.c.opened_at_ms.desc(),
            actionable_incident.c.incident_id,
        )
        .limit(1)
        .lateral("top_actionable_incident")
    )
    return (
        sa.select(
            runtime_incidents.c.incident_id,
            runtime_incidents.c.entry_block_scope,
            runtime_incidents.c.opened_at_ms,
            needs_intervention.label("needs_intervention"),
            top_actionable.c.top_actionable_incident_id,
            top_actionable.c.top_actionable_incident_opened_at_ms,
        )
        .select_from(
            runtime_incidents.outerjoin(
                ticket,
                ticket.c.ticket_id == runtime_incidents.c.ticket_id,
            ).outerjoin(top_actionable, sa.true())
        )
        .where(runtime_incidents.c.status == "open", scope)
        .order_by(
            runtime_incidents.c.opened_at_ms.desc(),
            runtime_incidents.c.incident_id,
        )
        .limit(21)
    )


def _incident_needs_intervention(
    incident: sa.FromClause,
) -> sa.ColumnElement[bool]:
    return sa.or_(
        incident.c.entry_block_scope == "runtime",
        incident.c.first_blocker == "hard_safety_stop",
        sa.exists(
            sa.select(sa.literal(1)).where(
                monitor_current.c.incident_id == incident.c.incident_id,
                monitor_current.c.owner_status == "needs_intervention",
            )
        ),
    )


def _monitor_rows_query(
    *, venue_id: str | None, account_id: str | None
) -> sa.Select[Any]:
    ticket = trade_tickets.alias("monitor_ticket")
    incident = runtime_incidents.alias("monitor_incident")
    incident_ticket = trade_tickets.alias("monitor_incident_ticket")
    scope = _monitor_scope(
        monitor=monitor_current,
        ticket=ticket,
        incident=incident,
        incident_ticket=incident_ticket,
        venue_id=venue_id,
        account_id=account_id,
    )
    actionable_monitor = monitor_current.alias("actionable_monitor")
    actionable_ticket = trade_tickets.alias("actionable_monitor_ticket")
    actionable_incident = runtime_incidents.alias("actionable_monitor_incident")
    actionable_incident_ticket = trade_tickets.alias(
        "actionable_monitor_incident_ticket"
    )
    actionable_scope = _monitor_scope(
        monitor=actionable_monitor,
        ticket=actionable_ticket,
        incident=actionable_incident,
        incident_ticket=actionable_incident_ticket,
        venue_id=venue_id,
        account_id=account_id,
    )
    top_intervention = (
        sa.select(
            actionable_monitor.c.monitor_key.label(
                "needs_intervention_monitor_key"
            ),
            actionable_monitor.c.updated_at_ms.label(
                "needs_intervention_monitor_updated_at_ms"
            ),
        )
        .select_from(
            actionable_monitor.outerjoin(
                actionable_ticket,
                actionable_ticket.c.ticket_id == actionable_monitor.c.ticket_id,
            )
            .outerjoin(
                actionable_incident,
                actionable_incident.c.incident_id
                == actionable_monitor.c.incident_id,
            )
            .outerjoin(
                actionable_incident_ticket,
                actionable_incident_ticket.c.ticket_id
                == actionable_incident.c.ticket_id,
            )
        )
        .where(
            actionable_scope,
            actionable_monitor.c.owner_status == "needs_intervention",
        )
        .order_by(
            actionable_monitor.c.updated_at_ms.desc(),
            actionable_monitor.c.monitor_key,
        )
        .limit(1)
        .lateral("top_intervention_monitor")
    )
    return (
        sa.select(
            monitor_current.c.monitor_key,
            monitor_current.c.owner_status,
            monitor_current.c.updated_at_ms,
            top_intervention.c.needs_intervention_monitor_key,
            top_intervention.c.needs_intervention_monitor_updated_at_ms,
        )
        .select_from(
            monitor_current.outerjoin(
                ticket,
                ticket.c.ticket_id == monitor_current.c.ticket_id,
            )
            .outerjoin(
                incident,
                incident.c.incident_id == monitor_current.c.incident_id,
            )
            .outerjoin(
                incident_ticket,
                incident_ticket.c.ticket_id == incident.c.ticket_id,
            )
            .outerjoin(top_intervention, sa.true())
        )
        .where(scope)
        .order_by(
            monitor_current.c.updated_at_ms.desc(),
            monitor_current.c.monitor_key,
        )
        .limit(101)
    )


def _monitor_scope(
    *,
    monitor: sa.FromClause,
    ticket: sa.FromClause,
    incident: sa.FromClause,
    incident_ticket: sa.FromClause,
    venue_id: str | None,
    account_id: str | None,
) -> sa.ColumnElement[bool]:
    incident_scope = _incident_scope(
        incident=incident,
        ticket=incident_ticket,
        venue_id=venue_id,
        account_id=account_id,
    )
    ticket_scope = _exact_scope(
        venue_column=ticket.c.venue_id,
        account_column=ticket.c.account_id,
        venue_id=venue_id,
        account_id=account_id,
    )
    return sa.or_(
        sa.and_(monitor.c.ticket_id.is_(None), monitor.c.incident_id.is_(None)),
        sa.and_(monitor.c.ticket_id.is_not(None), ticket_scope),
        sa.and_(monitor.c.incident_id.is_not(None), incident_scope),
    )


def _active_tickets_query(
    *, venue_id: str | None, account_id: str | None
) -> sa.Select[Any]:
    scope = _exact_scope(
        venue_column=trade_tickets.c.venue_id,
        account_column=trade_tickets.c.account_id,
        venue_id=venue_id,
        account_id=account_id,
    )
    return (
        sa.select(
            trade_tickets.c.ticket_id,
            trade_aggregates.c.updated_at_ms,
        )
        .select_from(
            trade_tickets.join(
                trade_aggregates,
                trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
            )
        )
        .where(scope, trade_tickets.c.terminal_at_ms.is_(None))
        .order_by(
            trade_aggregates.c.updated_at_ms.desc(),
            trade_tickets.c.ticket_id,
        )
        .limit(21)
    )


def _today_counts_query(
    *,
    day_start_ms: int,
    runtime_profile_id: str | None,
    venue_id: str | None,
    account_id: str | None,
) -> sa.Select[Any]:
    signal_scope = (
        sa.false()
        if runtime_profile_id is None
        else runtime_scopes_current.c.runtime_profile_id == runtime_profile_id
    )
    admission_scope = _exact_scope(
        venue_column=admission_decisions.c.venue_id,
        account_column=admission_decisions.c.account_id,
        venue_id=venue_id,
        account_id=account_id,
    )
    signal_count = (
        sa.select(sa.func.count())
        .select_from(
            signal_events.join(
                runtime_scopes_current,
                runtime_scopes_current.c.runtime_scope_id
                == signal_events.c.runtime_scope_id,
            )
        )
        .where(
            signal_scope,
            signal_events.c.occurred_at_ms >= day_start_ms,
        )
        .scalar_subquery()
    )
    admitted_count = (
        sa.select(sa.func.count())
        .select_from(admission_decisions)
        .where(
            admission_scope,
            admission_decisions.c.decided_at_ms >= day_start_ms,
            admission_decisions.c.decision_status == "admitted",
        )
        .scalar_subquery()
    )
    rejected_count = (
        sa.select(sa.func.count())
        .select_from(admission_decisions)
        .where(
            admission_scope,
            admission_decisions.c.decided_at_ms >= day_start_ms,
            admission_decisions.c.decision_status == "rejected",
        )
        .scalar_subquery()
    )
    return sa.select(
        signal_count.label("signal_count"),
        admitted_count.label("admitted_count"),
        rejected_count.label("rejected_count"),
    )


def _today_reviews_query(
    *, day_start_ms: int, venue_id: str | None, account_id: str | None
) -> sa.Select[Any]:
    scope = _exact_scope(
        venue_column=trade_tickets.c.venue_id,
        account_column=trade_tickets.c.account_id,
        venue_id=venue_id,
        account_id=account_id,
    )
    economics_completeness = trade_reviews.c.metrics[
        "economics_completeness"
    ].as_string()
    net_pnl_quote = trade_reviews.c.metrics["net_pnl_quote"].as_string()
    planned_r_multiple = trade_reviews.c.metrics[
        "planned_r_multiple"
    ].as_string()
    numeric_text = r"^-?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$"
    valid_economics = sa.func.coalesce(
        sa.and_(
            economics_completeness == "complete",
            net_pnl_quote.op("~")(numeric_text),
            planned_r_multiple.op("~")(numeric_text),
        ),
        sa.false(),
    )
    review_facts = (
        sa.select(
            trade_reviews.c.review_id,
            trade_reviews.c.created_at_ms,
            net_pnl_quote.label("net_pnl_quote"),
            planned_r_multiple.label("planned_r_multiple"),
            valid_economics.label("valid_economics"),
        )
        .select_from(
            trade_aggregates.join(
                trade_reviews,
                trade_aggregates.c.review_id == trade_reviews.c.review_id,
            ).join(
                trade_tickets,
                trade_tickets.c.ticket_id == trade_aggregates.c.ticket_id,
            )
        )
        .where(scope, trade_reviews.c.created_at_ms >= day_start_ms)
        .cte("current_review_facts")
    )
    latest_review_id = (
        sa.select(review_facts.c.review_id)
        .order_by(
            review_facts.c.created_at_ms.desc(),
            review_facts.c.review_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    latest_review_at_ms = (
        sa.select(review_facts.c.created_at_ms)
        .order_by(
            review_facts.c.created_at_ms.desc(),
            review_facts.c.review_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    invalid_review_id = (
        sa.select(review_facts.c.review_id)
        .where(review_facts.c.valid_economics.is_(False))
        .order_by(
            review_facts.c.created_at_ms.desc(),
            review_facts.c.review_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    invalid_review_at_ms = (
        sa.select(review_facts.c.created_at_ms)
        .where(review_facts.c.valid_economics.is_(False))
        .order_by(
            review_facts.c.created_at_ms.desc(),
            review_facts.c.review_id,
        )
        .limit(1)
        .scalar_subquery()
    )
    net_pnl_sum = sa.func.coalesce(
        sa.func.sum(
            sa.case(
                (
                    review_facts.c.valid_economics.is_(True),
                    sa.cast(review_facts.c.net_pnl_quote, sa.Numeric()),
                ),
                else_=sa.literal(0),
            )
        ),
        0,
    )
    net_r_sum = sa.func.coalesce(
        sa.func.sum(
            sa.case(
                (
                    review_facts.c.valid_economics.is_(True),
                    sa.cast(review_facts.c.planned_r_multiple, sa.Numeric()),
                ),
                else_=sa.literal(0),
            )
        ),
        0,
    )
    return sa.select(
        sa.func.count().label("review_count"),
        sa.func.count()
        .filter(review_facts.c.valid_economics.is_(False))
        .label("incomplete_review_count"),
        net_pnl_sum.label("net_pnl_sum"),
        net_r_sum.label("net_r_sum"),
        latest_review_id.label("latest_review_id"),
        latest_review_at_ms.label("latest_review_at_ms"),
        invalid_review_id.label("invalid_review_id"),
        invalid_review_at_ms.label("invalid_review_at_ms"),
    ).select_from(review_facts)


def _review_aggregate_metrics(
    row: sa.RowMapping,
) -> tuple[MoneyMetric, MoneyMetric, str | None, tuple[EvidenceRef, ...]]:
    invalid_count = int(row["incomplete_review_count"])
    evidence_id = (
        row["invalid_review_id"]
        if invalid_count
        else row["latest_review_id"]
    )
    evidence_at_ms = (
        row["invalid_review_at_ms"]
        if invalid_count
        else row["latest_review_at_ms"]
    )
    evidence = (
        ()
        if evidence_id is None or evidence_at_ms is None
        else (
            EvidenceRef(
                kind="review",
                identity=str(evidence_id),
                occurred_at_ms=int(evidence_at_ms),
            ),
        )
    )
    if invalid_count:
        reason = "incomplete_review_economics"
        return (
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
            MoneyMetric(value=None, unit="R", unavailable_reason=reason),
            reason,
            evidence,
        )
    net_pnl = row["net_pnl_sum"]
    net_r = row["net_r_sum"]
    if not isinstance(net_pnl, Decimal) or not isinstance(net_r, Decimal):
        reason = "incomplete_review_economics"
        return (
            MoneyMetric(value=None, unit="USDT", unavailable_reason=reason),
            MoneyMetric(value=None, unit="R", unavailable_reason=reason),
            reason,
            evidence,
        )
    return (
        MoneyMetric(value=net_pnl, unit="USDT"),
        MoneyMetric(value=net_r, unit="R"),
        None,
        evidence,
    )


def _exact_scope(
    *,
    venue_column: sa.ColumnElement[Any],
    account_column: sa.ColumnElement[Any],
    venue_id: str | None,
    account_id: str | None,
) -> sa.ColumnElement[bool]:
    if venue_id is None or account_id is None:
        return sa.false()
    return sa.and_(venue_column == venue_id, account_column == account_id)


def _incident_scope(
    *,
    incident: sa.FromClause,
    ticket: sa.FromClause,
    venue_id: str | None,
    account_id: str | None,
) -> sa.ColumnElement[bool]:
    runtime_global = sa.and_(
        incident.c.entry_block_scope == "runtime",
        incident.c.entry_block_key == "global",
    )
    if venue_id is None or account_id is None:
        return runtime_global
    account_key = f"{venue_id}:{account_id}"
    leverage_prefix = f"{account_key}:%"
    return sa.or_(
        runtime_global,
        sa.and_(
            incident.c.entry_block_scope == "account_capacity",
            incident.c.entry_block_key == account_key,
        ),
        sa.and_(
            incident.c.entry_block_scope == "leverage_domain",
            incident.c.entry_block_key.like(leverage_prefix),
        ),
        sa.and_(
            incident.c.entry_block_scope == "none",
            ticket.c.venue_id == venue_id,
            ticket.c.account_id == account_id,
        ),
    )


def _review_metrics(
    rows: Sequence[sa.RowMapping],
) -> tuple[MoneyMetric, MoneyMetric, str | None, tuple[EvidenceRef, ...]]:
    if not rows:
        return (
            MoneyMetric(value=Decimal(0), unit="USDT"),
            MoneyMetric(value=Decimal(0), unit="R"),
            None,
            (),
        )
    net_pnl = Decimal(0)
    net_r = Decimal(0)
    evidence: list[EvidenceRef] = []
    try:
        for row in rows:
            evidence.append(
                EvidenceRef(
                    kind="review",
                    identity=str(row["review_id"]),
                    occurred_at_ms=int(row["created_at_ms"]),
                )
            )
            if (
                row["economics_completeness"] != "complete"
                or not isinstance(row["net_pnl_quote"], str)
                or not isinstance(row["planned_r_multiple"], str)
            ):
                raise InvalidOperation
            net_pnl += Decimal(row["net_pnl_quote"])
            net_r += Decimal(row["planned_r_multiple"])
    except (InvalidOperation, ValueError, TypeError):
        return (
            MoneyMetric(
                value=None,
                unit="USDT",
                unavailable_reason="incomplete_review_economics",
            ),
            MoneyMetric(
                value=None,
                unit="R",
                unavailable_reason="incomplete_review_economics",
            ),
            "incomplete_review_economics",
            tuple(evidence),
        )
    return (
        MoneyMetric(value=net_pnl, unit="USDT"),
        MoneyMetric(value=net_r, unit="R"),
        None,
        tuple(evidence),
    )


def _overview_freshness(
    *,
    authority: sa.RowMapping | None,
    monitor_rows: Sequence[sa.RowMapping],
    now_ms: int,
    contradictory: bool,
) -> tuple[Freshness, str, int]:
    if authority is None:
        freshness = (
            Freshness.CONTRADICTORY
            if contradictory
            else Freshness.UNAVAILABLE
        )
        return freshness, "owner_policy:configured", now_ms
    account_identity = (
        f"account:{authority['venue_id']}:{authority['account_id']}"
    )
    required = [
        (
            f"owner_policy:{authority['owner_policy_id']}",
            int(authority["policy_updated_at_ms"]),
        ),
        (
            f"runtime_profile:{authority['runtime_profile_id']}",
            int(authority["profile_updated_at_ms"]),
        ),
        (
            account_identity,
            (
                None
                if authority["exposure_updated_at_ms"] is None
                else int(authority["exposure_updated_at_ms"])
            ),
        ),
    ]
    if monitor_rows:
        latest_monitor = max(
            monitor_rows,
            key=lambda row: (int(row["updated_at_ms"]), str(row["monitor_key"])),
        )
        required.append(
            (
                str(latest_monitor["monitor_key"]),
                int(latest_monitor["updated_at_ms"]),
            )
        )
    else:
        required.append(("monitor:current", None))

    classified = [
        (*_classify_freshness(timestamp, now_ms=now_ms), identity)
        for identity, timestamp in required
    ]
    if contradictory:
        return Freshness.CONTRADICTORY, account_identity, now_ms
    precedence = {
        Freshness.FRESH: 0,
        Freshness.STALE: 1,
        Freshness.UNAVAILABLE: 2,
        Freshness.CONTRADICTORY: 3,
    }
    freshness, occurred_at_ms, identity = max(
        classified,
        key=lambda item: (precedence[item[0]], -item[1]),
    )
    return freshness, identity, occurred_at_ms


def _classify_freshness(
    timestamp_ms: int | None,
    *,
    now_ms: int,
) -> tuple[Freshness, int]:
    if timestamp_ms is None:
        return Freshness.UNAVAILABLE, now_ms
    if timestamp_ms > now_ms:
        return Freshness.CONTRADICTORY, timestamp_ms
    age_ms = now_ms - timestamp_ms
    if age_ms <= _FRESH_AGE_MS:
        return Freshness.FRESH, timestamp_ms
    if age_ms <= _STALE_MAX_AGE_MS:
        return Freshness.STALE, timestamp_ms
    return Freshness.UNAVAILABLE, timestamp_ms


def _unique_evidence(evidence: tuple[EvidenceRef, ...]) -> tuple[EvidenceRef, ...]:
    seen: set[tuple[str, str, int]] = set()
    unique: list[EvidenceRef] = []
    for item in evidence:
        key = (item.kind, item.identity, item.occurred_at_ms)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _evidence_gap(
    *,
    reason: str,
    kind: Literal[
        "signal",
        "admission",
        "ticket",
        "event",
        "command",
        "incident",
        "settlement",
        "review",
    ],
    identity: str,
    occurred_at_ms: int,
) -> OverviewEvidenceGap:
    return OverviewEvidenceGap(
        reason=reason,
        evidence=EvidenceRef(
            kind=kind,
            identity=identity,
            occurred_at_ms=occurred_at_ms,
        ),
    )
