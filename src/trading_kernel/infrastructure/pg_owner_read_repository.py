"""Bounded read-only PostgreSQL access for Owner Console read models."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

import sqlalchemy as sa
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    create_async_engine,
)

from src.trading_kernel.application.owner_console.causality import (
    ContradictoryFacts,
)
from src.trading_kernel.application.owner_console.models import (
    EvidenceRef,
    Freshness,
    MoneyMetric,
    OverviewEvidenceGap,
    OverviewFacts,
    PageCursor,
    ProgrammaticReviewFacts,
    ReviewCenterFacts,
    ReviewCenterItemFacts,
    ReviewListQuery,
    SignalDetailFacts,
    SignalFactSnapshotFacts,
    SignalItemFacts,
    SignalListQuery,
    SignalPageFacts,
    StrategyPageFacts,
    StrategySummaryQuery,
    StrategyTicketFacts,
    StrategyTicketPageFacts,
    StrategyTicketQuery,
    StrategyVersionFacts,
    TradeCausalityAdmissionFacts,
    TradeCausalityAggregateFacts,
    TradeCausalityCommandFacts,
    TradeCausalityEventFacts,
    TradeCausalityFacts,
    TradeCausalityIncidentFacts,
    TradeCausalityReviewFacts,
    TradeCausalitySignalFacts,
    TradeItemFacts,
    TradeListQuery,
    TradePageFacts,
    decode_cursor,
)
from src.trading_kernel.application.owner_console.programmatic_review import (
    ProgrammaticReviewContradiction,
    build_programmatic_review,
    matches_review_status,
)
from src.trading_kernel.application.owner_console.signals import (
    SignalFactsContradiction,
    SignalNotFound,
)
from src.trading_kernel.application.owner_console.trades import (
    TradeFactsContradiction,
    aggregate_stage,
    build_trade_item,
)
from src.trading_kernel.infrastructure.pg_models import (
    account_exposure_current,
    admission_decisions,
    capacity_claims,
    exchange_commands,
    monitor_current,
    owner_policy_current,
    runtime_incidents,
    runtime_profiles,
    runtime_scopes_current,
    shadow_outcomes_current,
    signal_events,
    signal_fact_snapshots,
    strategy_groups,
    strategy_versions,
    trade_aggregates,
    trade_events,
    trade_reviews,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_repositories import _ticket_from_row

_VENUE_ID = "binance-usdm"
_FRESH_AGE_MS = 30_000
_STALE_MAX_AGE_MS = 300_000
_CAUSALITY_EVENT_LIMIT = 512
_CAUSALITY_COMMAND_LIMIT = 128
_CAUSALITY_INCIDENT_LIMIT = 64
_REVIEW_CENTER_INCIDENT_LIMIT = 64
_REVIEW_CENTER_FILTER_CANDIDATE_LIMIT = 512
_STRATEGY_SUMMARY_VERSION_LIMIT = 100
_STRATEGY_SUMMARY_TICKET_LIMIT = 5_000


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
        connection = await raw.execution_options(isolation_level="REPEATABLE READ")
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
            (await self._connection.execute(_overview_authority_query()))
            .mappings()
            .all()
        )
        authority = authority_rows[0] if len(authority_rows) == 1 else None
        venue_id = None if authority is None else str(authority["venue_id"])
        account_id = None if authority is None else str(authority["account_id"])
        runtime_profile_id = (
            None if authority is None else str(authority["runtime_profile_id"])
        )

        claim = (
            (
                await self._connection.execute(
                    _latest_capacity_claim_query(
                        venue_id=venue_id,
                        account_id=account_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        incident_query_rows = (
            (
                await self._connection.execute(
                    _open_incidents_query(
                        venue_id=venue_id,
                        account_id=account_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        incident_limit_reached = len(incident_query_rows) > 20
        incident_rows = incident_query_rows[:20]
        monitor_query_rows = (
            (
                await self._connection.execute(
                    _monitor_rows_query(
                        venue_id=venue_id,
                        account_id=account_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        monitor_limit_reached = len(monitor_query_rows) > 100
        monitor_rows = monitor_query_rows[:100]
        active_ticket_query_rows = (
            (
                await self._connection.execute(
                    _active_tickets_query(
                        venue_id=venue_id,
                        account_id=account_id,
                    )
                )
            )
            .mappings()
            .all()
        )
        active_ticket_limit_reached = len(active_ticket_query_rows) > 20
        active_ticket_rows = active_ticket_query_rows[:20]
        count_row = (
            (
                await self._connection.execute(
                    _today_counts_query(
                        day_start_ms=day_start_ms,
                        runtime_profile_id=runtime_profile_id,
                        venue_id=venue_id,
                        account_id=account_id,
                    )
                )
            )
            .mappings()
            .one()
        )
        review_row = (
            (
                await self._connection.execute(
                    _today_reviews_query(
                        day_start_ms=day_start_ms,
                        venue_id=venue_id,
                        account_id=account_id,
                    )
                )
            )
            .mappings()
            .one()
        )

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
            None if authority is None else int(authority["max_concurrent_tickets"])
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
            None if claim is None else Decimal(str(claim["available_margin_at_claim"]))
        )
        claim_created_at_ms = None if claim is None else int(claim["created_at_ms"])

        attention_incidents = [
            row for row in incident_rows if not bool(row["needs_intervention"])
        ]
        latest_blocking = incident_query_rows[0] if incident_query_rows else None
        if (
            latest_blocking is not None
            and latest_blocking["top_actionable_incident_id"] is None
        ):
            latest_blocking = None
        intervention_monitor = monitor_query_rows[0] if monitor_query_rows else None
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
                            identity=str(latest_blocking["top_actionable_incident_id"]),
                            occurred_at_ms=int(
                                latest_blocking["top_actionable_incident_opened_at_ms"]
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
                                intervention_monitor["needs_intervention_monitor_key"]
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
                else int(latest_blocking["top_actionable_incident_opened_at_ms"])
            ),
            attention_incident_ids=tuple(
                str(row["incident_id"]) for row in attention_incidents
            ),
            attention_incident_opened_at_ms=tuple(
                int(row["opened_at_ms"]) for row in attention_incidents
            ),
            monitor_statuses=tuple(str(row["owner_status"]) for row in monitor_rows),
            monitor_keys=tuple(str(row["monitor_key"]) for row in monitor_rows),
            monitor_updated_at_ms=tuple(
                int(row["updated_at_ms"]) for row in monitor_rows
            ),
            needs_intervention_monitor_key=(
                None
                if intervention_monitor is None
                else str(intervention_monitor["needs_intervention_monitor_key"])
            ),
            needs_intervention_monitor_updated_at_ms=(
                None
                if intervention_monitor is None
                else int(
                    intervention_monitor["needs_intervention_monitor_updated_at_ms"]
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

    async def read_signal_page_facts(
        self,
        query: SignalListQuery,
    ) -> SignalPageFacts:
        """Read one bounded limit+1 Signal page on the supplied connection."""

        cursor = None if query.cursor is None else decode_cursor(query.cursor)
        rows = (
            (
                await self._connection.execute(
                    _signal_list_query(query=query, cursor=cursor)
                )
            )
            .mappings()
            .all()
        )
        return SignalPageFacts(
            items=tuple(_signal_item_facts_from_joined_row(row) for row in rows),
            requested_limit=query.limit,
        )

    async def read_signal_detail_facts(
        self,
        signal_event_id: str,
    ) -> SignalDetailFacts:
        """Read one exact Signal, Decision, bounded facts, and optional Shadow."""

        signal_rows = (
            (await self._connection.execute(_exact_signal_query(signal_event_id)))
            .mappings()
            .all()
        )
        if not signal_rows:
            raise SignalNotFound(f"Signal not found: {signal_event_id}")
        if len(signal_rows) != 1:
            raise SignalFactsContradiction(
                "exact Signal identity returned multiple rows"
            )
        signal = signal_rows[0]
        if str(signal["signal_event_id"]) != signal_event_id:
            raise SignalFactsContradiction("exact Signal identity mismatch")

        decision_rows = (
            (await self._connection.execute(_exact_admission_query(signal_event_id)))
            .mappings()
            .all()
        )
        if len(decision_rows) != 1:
            raise SignalFactsContradiction(
                "Signal requires exactly one AdmissionDecision"
            )
        decision = decision_rows[0]

        fact_rows = (
            (await self._connection.execute(_exact_signal_facts_query(signal_event_id)))
            .mappings()
            .all()
        )

        admission_decision_id = str(decision["admission_decision_id"])
        shadow_rows = (
            (await self._connection.execute(_exact_shadow_query(admission_decision_id)))
            .mappings()
            .all()
        )
        if len(shadow_rows) > 1:
            raise SignalFactsContradiction(
                "AdmissionDecision has multiple Shadow Outcomes"
            )
        if len(fact_rows) > 256:
            raise SignalFactsContradiction("Signal has more than 256 fact snapshots")
        shadow = shadow_rows[0] if shadow_rows else None
        _validate_signal_admission_identity(signal=signal, decision=decision)
        _validate_shadow_identity(decision=decision, shadow=shadow)

        item = _signal_item_facts_from_detail_rows(
            signal=signal,
            decision=decision,
            shadow=shadow,
        )
        snapshots = tuple(
            _signal_fact_snapshot_from_row(
                row,
                expected_signal_event_id=signal_event_id,
            )
            for row in fact_rows
        )
        return SignalDetailFacts(signal=item, fact_snapshots=snapshots)

    async def read_trade_page_facts(
        self,
        query: TradeListQuery,
    ) -> TradePageFacts:
        """Read one bounded active/terminal Trade page on this connection."""

        cursor = None if query.cursor is None else decode_cursor(query.cursor)
        rows = (
            (
                await self._connection.execute(
                    _trade_list_query(query=query, cursor=cursor)
                )
            )
            .mappings()
            .all()
        )
        return TradePageFacts(
            items=tuple(_trade_item_facts_from_row(row) for row in rows),
            requested_limit=query.limit,
        )

    async def read_trade_causality_facts(
        self,
        ticket_id: str,
    ) -> TradeCausalityFacts | None:
        """Read one exact Ticket causality graph on this connection."""

        ticket_row = (
            (await self._connection.execute(_causality_ticket_query(ticket_id)))
            .mappings()
            .one_or_none()
        )
        if ticket_row is None:
            return None
        if ticket_row["aggregate_ticket_id"] is None:
            raise ContradictoryFacts("Ticket exists without Aggregate")
        signal_row = (
            (
                await self._connection.execute(
                    _causality_signal_admission_query(
                        str(ticket_row["signal_event_id"])
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if signal_row is None:
            raise ContradictoryFacts("Ticket Signal does not exist")
        if signal_row["admission_decision_id"] is None:
            raise ContradictoryFacts("Ticket AdmissionDecision does not exist")

        event_rows = (
            (await self._connection.execute(_causality_events_query(ticket_id)))
            .mappings()
            .all()
        )
        command_rows = (
            (await self._connection.execute(_causality_commands_query(ticket_id)))
            .mappings()
            .all()
        )
        incident_rows = (
            (await self._connection.execute(_causality_incidents_query(ticket_id)))
            .mappings()
            .all()
        )
        _require_history_bound(
            "Trade Events", event_rows, maximum=_CAUSALITY_EVENT_LIMIT
        )
        _require_history_bound(
            "Exchange Commands",
            command_rows,
            maximum=_CAUSALITY_COMMAND_LIMIT,
        )
        _require_history_bound(
            "Incidents", incident_rows, maximum=_CAUSALITY_INCIDENT_LIMIT
        )
        review_row: RowMapping | None = None
        aggregate_review_id = ticket_row["aggregate_review_id"]
        if aggregate_review_id is not None:
            review_row = (
                (
                    await self._connection.execute(
                        _causality_review_query(str(aggregate_review_id))
                    )
                )
                .mappings()
                .one_or_none()
            )

        events = tuple(_causality_event_facts(row) for row in event_rows)
        commands = tuple(_causality_command_facts(row) for row in command_rows)
        incidents = tuple(_causality_incident_facts(row) for row in incident_rows)
        review = None if review_row is None else _causality_review_facts(review_row)
        return TradeCausalityFacts(
            trade=_causality_trade_item_facts(
                ticket_row,
                events=events,
                incidents=incidents,
                review=review,
            ),
            ticket=_ticket_from_row(ticket_row),
            aggregate=_causality_aggregate_facts(ticket_row),
            signal=_causality_signal_facts(signal_row),
            admission=_causality_admission_facts(signal_row),
            events=events,
            commands=commands,
            incidents=incidents,
            review=review,
        )

    async def read_strategy_page_facts(
        self,
        query: StrategySummaryQuery,
    ) -> StrategyPageFacts:
        """Read bounded version-isolated strategy evidence on this snapshot."""

        version_rows = (
            (await self._connection.execute(_strategy_versions_query(query)))
            .mappings()
            .all()
        )
        if len(version_rows) > _STRATEGY_SUMMARY_VERSION_LIMIT:
            raise TradeFactsContradiction(
                "StrategyVersion page exceeded hard maximum 100"
            )
        version_ids = tuple(str(row["strategy_version_id"]) for row in version_rows)
        ticket_rows: Sequence[RowMapping] = ()
        if version_ids:
            ticket_rows = (
                (
                    await self._connection.execute(
                        _strategy_summary_ticket_query(
                            query=query,
                            strategy_version_ids=version_ids,
                        )
                    )
                )
                .mappings()
                .all()
            )
        if len(ticket_rows) > _STRATEGY_SUMMARY_TICKET_LIMIT:
            raise TradeFactsContradiction(
                "StrategyVersion summary exceeds hard maximum 5000 Tickets"
            )
        tickets_by_version: dict[str, list[StrategyTicketFacts]] = {
            strategy_version_id: [] for strategy_version_id in version_ids
        }
        for row in ticket_rows:
            strategy_version_id = str(row["strategy_version_id"])
            if strategy_version_id not in tickets_by_version:
                raise TradeFactsContradiction(
                    "StrategyVersion Ticket is outside selected version authority"
                )
            tickets_by_version[strategy_version_id].append(
                _strategy_ticket_facts_from_row(row)
            )
        return StrategyPageFacts(
            from_ms=query.from_ms,
            to_ms=query.to_ms,
            view=query.view,
            versions=tuple(
                StrategyVersionFacts(
                    strategy_group_id=str(row["strategy_group_id"]),
                    strategy_group_display_name=str(row["display_name"]),
                    strategy_version_id=str(row["strategy_version_id"]),
                    version=int(row["version"]),
                    strategy_version_status=str(row["strategy_version_status"]),
                    is_current=bool(row["is_current"]),
                    tickets=tuple(tickets_by_version[str(row["strategy_version_id"])]),
                    evidence=(
                        EvidenceRef(
                            kind="fact",
                            identity=str(row["strategy_version_id"]),
                            occurred_at_ms=int(row["version_created_at_ms"]),
                        ),
                    ),
                )
                for row in version_rows
            ),
        )

    async def read_strategy_ticket_page_facts(
        self,
        query: StrategyTicketQuery,
    ) -> StrategyTicketPageFacts:
        """Read one version/path-bounded Ticket modal page on this snapshot."""

        cursor = None if query.cursor is None else decode_cursor(query.cursor)
        rows = (
            (
                await self._connection.execute(
                    _strategy_ticket_query(query=query, cursor=cursor)
                )
            )
            .mappings()
            .all()
        )
        return StrategyTicketPageFacts(
            items=tuple(_trade_item_facts_from_row(row) for row in rows),
            requested_limit=query.limit,
        )

    async def read_review_center_facts(
        self,
        query: ReviewListQuery,
    ) -> ReviewCenterFacts:
        """Read one terminal-only limit+1 Review Center page."""

        cursor = None if query.cursor is None else decode_cursor(query.cursor)
        ticket_rows = (
            (
                await self._connection.execute(
                    _review_center_ticket_query(query=query, cursor=cursor)
                )
            )
            .mappings()
            .all()
        )
        filter_overflow = (
            query.review_status is not None
            and len(ticket_rows) > _REVIEW_CENTER_FILTER_CANDIDATE_LIMIT
        )
        candidate_rows = (
            ticket_rows[:_REVIEW_CENTER_FILTER_CANDIDATE_LIMIT]
            if query.review_status is not None
            else ticket_rows
        )
        page_ticket_ids = tuple(
            str(row["ticket_id"])
            for row in (
                candidate_rows
                if query.review_status is not None
                else candidate_rows[: query.limit]
            )
        )
        incident_rows = (
            ()
            if not page_ticket_ids
            else (
                await self._connection.execute(
                    _review_center_incidents_query(page_ticket_ids)
                )
            )
            .mappings()
            .all()
        )
        incidents_by_ticket = _review_center_incidents_by_ticket(incident_rows)
        candidate_items = tuple(
            _review_center_item_facts(
                row,
                incidents=incidents_by_ticket.get(str(row["ticket_id"]), ()),
            )
            for row in candidate_rows
        )
        if query.review_status is None:
            items = candidate_items
        else:
            items = tuple(
                item
                for item in candidate_items
                if matches_review_status(
                    build_programmatic_review(item.review),
                    query.review_status,
                )
            )[: query.limit + 1]
            if len(items) < query.limit + 1 and filter_overflow:
                raise ProgrammaticReviewContradiction(
                    "Review Center status filter exceeded candidate bound"
                )
        return ReviewCenterFacts(
            from_ms=query.from_ms,
            to_ms=query.to_ms,
            items=items,
            requested_limit=query.limit,
            requested_strategy_group_id=query.strategy_group_id,
        )


def _causality_ticket_query(ticket_id: str) -> sa.Select[Any]:
    return (
        sa.select(
            trade_tickets,
            trade_tickets.c.status.label("ticket_status"),
            trade_tickets.c.created_at_ms.label("issued_at_ms"),
            trade_aggregates.c.ticket_id.label("aggregate_ticket_id"),
            trade_aggregates.c.status.label("aggregate_status"),
            trade_aggregates.c.last_event_sequence,
            trade_aggregates.c.review_id.label("aggregate_review_id"),
            trade_aggregates.c.updated_at_ms.label("aggregate_updated_at_ms"),
        )
        .select_from(
            trade_tickets.outerjoin(
                trade_aggregates,
                trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
            )
        )
        .where(trade_tickets.c.ticket_id == ticket_id)
    )


def _causality_signal_admission_query(signal_event_id: str) -> sa.Select[Any]:
    return (
        sa.select(
            signal_events.c.signal_event_id,
            signal_events.c.exposure_episode_id,
            signal_events.c.runtime_scope_id,
            signal_events.c.runtime_scope_version,
            signal_events.c.strategy_group_id,
            signal_events.c.strategy_version_id,
            signal_events.c.event_spec_id,
            signal_events.c.universe_version_id,
            signal_events.c.universe_semantic_digest,
            signal_events.c.exchange_instrument_id,
            signal_events.c.position_side,
            signal_events.c.occurred_at_ms,
            admission_decisions.c.admission_decision_id,
            admission_decisions.c.signal_event_id.label("admission_signal_event_id"),
            admission_decisions.c.exposure_episode_id.label(
                "admission_exposure_episode_id"
            ),
            admission_decisions.c.strategy_group_id.label(
                "admission_strategy_group_id"
            ),
            admission_decisions.c.strategy_version_id.label(
                "admission_strategy_version_id"
            ),
            admission_decisions.c.event_spec_id.label("admission_event_spec_id"),
            admission_decisions.c.universe_version_id.label(
                "admission_universe_version_id"
            ),
            admission_decisions.c.universe_semantic_digest.label(
                "admission_universe_semantic_digest"
            ),
            admission_decisions.c.runtime_profile_id,
            admission_decisions.c.runtime_scope_id.label("admission_runtime_scope_id"),
            admission_decisions.c.runtime_scope_version.label(
                "admission_runtime_scope_version"
            ),
            admission_decisions.c.owner_policy_id,
            admission_decisions.c.owner_policy_version,
            admission_decisions.c.venue_id,
            admission_decisions.c.account_id,
            admission_decisions.c.exchange_instrument_id.label(
                "admission_exchange_instrument_id"
            ),
            admission_decisions.c.position_side.label("admission_position_side"),
            admission_decisions.c.decision_status,
            admission_decisions.c.capacity_claim_id,
            admission_decisions.c.ticket_id.label("admission_ticket_id"),
            admission_decisions.c.decided_at_ms,
        )
        .select_from(
            signal_events.outerjoin(
                admission_decisions,
                admission_decisions.c.signal_event_id
                == signal_events.c.signal_event_id,
            )
        )
        .where(signal_events.c.signal_event_id == signal_event_id)
    )


def _causality_events_query(ticket_id: str) -> sa.Select[Any]:
    return (
        sa.select(trade_events)
        .where(trade_events.c.ticket_id == ticket_id)
        .order_by(trade_events.c.sequence.asc())
        .limit(_CAUSALITY_EVENT_LIMIT + 1)
    )


def _causality_commands_query(ticket_id: str) -> sa.Select[Any]:
    return (
        sa.select(exchange_commands)
        .where(exchange_commands.c.ticket_id == ticket_id)
        .order_by(
            exchange_commands.c.created_at_ms.asc(),
            exchange_commands.c.command_id.asc(),
        )
        .limit(_CAUSALITY_COMMAND_LIMIT + 1)
    )


def _causality_incidents_query(ticket_id: str) -> sa.Select[Any]:
    return (
        sa.select(runtime_incidents)
        .where(runtime_incidents.c.ticket_id == ticket_id)
        .order_by(
            runtime_incidents.c.opened_at_ms.asc(),
            runtime_incidents.c.incident_id.asc(),
        )
        .limit(_CAUSALITY_INCIDENT_LIMIT + 1)
    )


def _causality_review_query(review_id: str) -> sa.Select[Any]:
    return sa.select(trade_reviews).where(trade_reviews.c.review_id == review_id)


def _require_history_bound(
    label: str,
    rows: Sequence[RowMapping],
    *,
    maximum: int,
) -> None:
    if len(rows) > maximum:
        raise ContradictoryFacts(f"{label} exceed hard maximum {maximum}")


def _causality_aggregate_facts(
    row: RowMapping,
) -> TradeCausalityAggregateFacts:
    return TradeCausalityAggregateFacts(
        ticket_id=str(row["aggregate_ticket_id"]),
        aggregate_status=str(row["aggregate_status"]),
        last_event_sequence=int(row["last_event_sequence"]),
        review_id=(
            None
            if row["aggregate_review_id"] is None
            else str(row["aggregate_review_id"])
        ),
        updated_at_ms=int(row["aggregate_updated_at_ms"]),
    )


def _causality_signal_facts(row: RowMapping) -> TradeCausalitySignalFacts:
    return TradeCausalitySignalFacts(
        signal_event_id=str(row["signal_event_id"]),
        exposure_episode_id=str(row["exposure_episode_id"]),
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        event_spec_id=str(row["event_spec_id"]),
        universe_version_id=str(row["universe_version_id"]),
        universe_semantic_digest=str(row["universe_semantic_digest"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(row["position_side"])),
        occurred_at_ms=int(row["occurred_at_ms"]),
    )


def _causality_admission_facts(
    row: RowMapping,
) -> TradeCausalityAdmissionFacts:
    return TradeCausalityAdmissionFacts(
        admission_decision_id=str(row["admission_decision_id"]),
        signal_event_id=str(row["admission_signal_event_id"]),
        exposure_episode_id=str(row["admission_exposure_episode_id"]),
        strategy_group_id=str(row["admission_strategy_group_id"]),
        strategy_version_id=str(row["admission_strategy_version_id"]),
        event_spec_id=str(row["admission_event_spec_id"]),
        universe_version_id=str(row["admission_universe_version_id"]),
        universe_semantic_digest=str(row["admission_universe_semantic_digest"]),
        runtime_profile_id=str(row["runtime_profile_id"]),
        runtime_scope_id=str(row["admission_runtime_scope_id"]),
        runtime_scope_version=int(row["admission_runtime_scope_version"]),
        owner_policy_id=str(row["owner_policy_id"]),
        owner_policy_version=int(row["owner_policy_version"]),
        venue_id=str(row["venue_id"]),
        account_id=str(row["account_id"]),
        exchange_instrument_id=str(row["admission_exchange_instrument_id"]),
        position_side=cast(
            Literal["long", "short"], str(row["admission_position_side"])
        ),
        decision_status=cast(
            Literal["admitted", "rejected"], str(row["decision_status"])
        ),
        capacity_claim_id=(
            None if row["capacity_claim_id"] is None else str(row["capacity_claim_id"])
        ),
        ticket_id=(
            None
            if row["admission_ticket_id"] is None
            else str(row["admission_ticket_id"])
        ),
        decided_at_ms=int(row["decided_at_ms"]),
    )


def _json_object(value: object, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContradictoryFacts(f"{label} is not a JSON object")
    return value


def _causality_event_facts(row: RowMapping) -> TradeCausalityEventFacts:
    return TradeCausalityEventFacts(
        event_id=str(row["event_id"]),
        ticket_id=str(row["ticket_id"]),
        sequence=int(row["sequence"]),
        event_type=str(row["event_type"]),
        payload=_json_object(row["payload"], label="Event payload"),
        occurred_at_ms=int(row["occurred_at_ms"]),
    )


def _causality_command_facts(row: RowMapping) -> TradeCausalityCommandFacts:
    result_payload = row["result_payload"]
    return TradeCausalityCommandFacts(
        command_id=str(row["command_id"]),
        ticket_id=str(row["ticket_id"]),
        command_kind=str(row["command_kind"]),
        generation=int(row["generation"]),
        status=str(row["status"]),
        request_payload=_json_object(
            row["request_payload"], label="Command request payload"
        ),
        result_payload=(
            None
            if result_payload is None
            else _json_object(result_payload, label="Command result payload")
        ),
        created_at_ms=int(row["created_at_ms"]),
        completed_at_ms=(
            None if row["completed_at_ms"] is None else int(row["completed_at_ms"])
        ),
    )


def _causality_incident_facts(row: RowMapping) -> TradeCausalityIncidentFacts:
    return TradeCausalityIncidentFacts(
        incident_id=str(row["incident_id"]),
        ticket_id=str(row["ticket_id"]),
        incident_kind=str(row["incident_kind"]),
        status=str(row["status"]),
        first_blocker=str(row["first_blocker"]),
        details=_json_object(row["details"], label="Incident details"),
        opened_at_ms=int(row["opened_at_ms"]),
        resolved_at_ms=(
            None if row["resolved_at_ms"] is None else int(row["resolved_at_ms"])
        ),
    )


def _causality_review_facts(row: RowMapping) -> TradeCausalityReviewFacts:
    return TradeCausalityReviewFacts(
        review_id=str(row["review_id"]),
        ticket_id=str(row["ticket_id"]),
        revision=int(row["revision"]),
        metrics=_json_object(row["metrics"], label="current Review metrics"),
        created_at_ms=int(row["created_at_ms"]),
    )


def _causality_trade_item_facts(
    ticket_row: RowMapping,
    *,
    events: tuple[TradeCausalityEventFacts, ...],
    incidents: tuple[TradeCausalityIncidentFacts, ...],
    review: TradeCausalityReviewFacts | None,
) -> TradeItemFacts:
    exit_event = next(
        (event for event in events if event.event_type == "ExitRequested"),
        None,
    )
    open_incident = next(
        (incident for incident in incidents if incident.status == "open"),
        None,
    )
    latest_incident = incidents[-1] if incidents else None
    return TradeItemFacts(
        ticket_id=str(ticket_row["ticket_id"]),
        strategy_group_id=str(ticket_row["strategy_group_id"]),
        event_spec_id=str(ticket_row["event_spec_id"]),
        exchange_instrument_id=str(ticket_row["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(ticket_row["position_side"])),
        ticket_status=str(ticket_row["ticket_status"]),
        aggregate_status=str(ticket_row["aggregate_status"]),
        issued_at_ms=int(ticket_row["issued_at_ms"]),
        terminal_at_ms=(
            None
            if ticket_row["terminal_at_ms"] is None
            else int(ticket_row["terminal_at_ms"])
        ),
        aggregate_review_id=(
            None
            if ticket_row["aggregate_review_id"] is None
            else str(ticket_row["aggregate_review_id"])
        ),
        review_id=None if review is None else review.review_id,
        review_ticket_id=None if review is None else review.ticket_id,
        review_revision=None if review is None else review.revision,
        review_created_at_ms=None if review is None else review.created_at_ms,
        review_metrics=None if review is None else review.metrics,
        exit_event_id=None if exit_event is None else exit_event.event_id,
        exit_event_type=None if exit_event is None else exit_event.event_type,
        exit_event_payload=None if exit_event is None else exit_event.payload,
        exit_event_occurred_at_ms=(
            None if exit_event is None else exit_event.occurred_at_ms
        ),
        open_incident_id=(None if open_incident is None else open_incident.incident_id),
        open_incident_opened_at_ms=(
            None if open_incident is None else open_incident.opened_at_ms
        ),
        latest_incident_id=(
            None if latest_incident is None else latest_incident.incident_id
        ),
        latest_incident_opened_at_ms=(
            None if latest_incident is None else latest_incident.opened_at_ms
        ),
        evidence=(
            EvidenceRef(
                kind="ticket",
                identity=str(ticket_row["ticket_id"]),
                occurred_at_ms=int(ticket_row["issued_at_ms"]),
            ),
        ),
    )


def _signal_list_query(
    *,
    query: SignalListQuery,
    cursor: PageCursor | None,
) -> sa.Select[Any]:
    conditions: list[sa.ColumnElement[bool]] = [
        signal_events.c.occurred_at_ms >= query.from_ms,
        signal_events.c.occurred_at_ms < query.to_ms,
    ]
    if query.strategy_group_id is not None:
        conditions.append(signal_events.c.strategy_group_id == query.strategy_group_id)
    if query.exchange_instrument_id is not None:
        conditions.append(
            signal_events.c.exchange_instrument_id == query.exchange_instrument_id
        )
    if query.position_side is not None:
        conditions.append(signal_events.c.position_side == query.position_side)
    if query.decision_status is not None:
        conditions.append(
            admission_decisions.c.decision_status == query.decision_status
        )
    if cursor is not None:
        conditions.append(
            sa.tuple_(
                signal_events.c.occurred_at_ms,
                signal_events.c.signal_event_id,
            )
            < sa.tuple_(
                sa.literal(cursor.sort_ms),
                sa.literal(cursor.identity),
            )
        )

    return (
        _signal_joined_select()
        .where(*conditions)
        .order_by(
            signal_events.c.occurred_at_ms.desc(),
            signal_events.c.signal_event_id.desc(),
        )
        .limit(query.limit + 1)
    )


def _trade_list_query(
    *,
    query: TradeListQuery,
    cursor: PageCursor | None,
) -> sa.Select[Any]:
    conditions: list[sa.ColumnElement[bool]] = [
        trade_tickets.c.created_at_ms >= query.from_ms,
        trade_tickets.c.created_at_ms < query.to_ms,
    ]
    if query.strategy_group_id is not None:
        conditions.append(trade_tickets.c.strategy_group_id == query.strategy_group_id)
    if query.exchange_instrument_id is not None:
        conditions.append(
            trade_tickets.c.exchange_instrument_id == query.exchange_instrument_id
        )
    if query.position_side is not None:
        conditions.append(trade_tickets.c.position_side == query.position_side)
    if query.aggregate_status is not None:
        conditions.append(trade_aggregates.c.status == query.aggregate_status)
    if cursor is not None:
        conditions.append(
            sa.tuple_(
                trade_tickets.c.created_at_ms,
                trade_tickets.c.ticket_id,
            )
            < sa.tuple_(
                sa.literal(cursor.sort_ms),
                sa.literal(cursor.identity),
            )
        )

    return _ticket_facts_select(
        conditions=conditions,
        limit=query.limit + 1,
    )


def _strategy_versions_query(query: StrategySummaryQuery) -> sa.Select[Any]:
    """Select authoritative StrategyVersions, including zero-ticket versions."""

    conditions: list[sa.ColumnElement[bool]] = []
    if query.view == "current":
        conditions.append(
            strategy_groups.c.active_version_id
            == strategy_versions.c.strategy_version_id
        )
    return (
        sa.select(
            strategy_groups.c.strategy_group_id,
            strategy_groups.c.display_name,
            strategy_groups.c.active_version_id,
            strategy_versions.c.strategy_version_id,
            strategy_versions.c.version,
            strategy_versions.c.status.label("strategy_version_status"),
            strategy_versions.c.created_at_ms.label("version_created_at_ms"),
            (
                strategy_groups.c.active_version_id
                == strategy_versions.c.strategy_version_id
            ).label("is_current"),
        )
        .select_from(
            strategy_groups.join(
                strategy_versions,
                strategy_versions.c.strategy_group_id
                == strategy_groups.c.strategy_group_id,
            )
        )
        .where(*conditions)
        .order_by(
            strategy_groups.c.display_name.asc(),
            strategy_versions.c.version.desc(),
            strategy_versions.c.strategy_version_id.asc(),
        )
        .limit(_STRATEGY_SUMMARY_VERSION_LIMIT + 1)
    )


def _strategy_summary_ticket_query(
    *,
    query: StrategySummaryQuery,
    strategy_version_ids: tuple[str, ...],
) -> sa.Select[Any]:
    return _ticket_facts_select(
        conditions=(
            trade_tickets.c.created_at_ms >= query.from_ms,
            trade_tickets.c.created_at_ms < query.to_ms,
            trade_tickets.c.strategy_version_id.in_(strategy_version_ids),
        ),
        limit=_STRATEGY_SUMMARY_TICKET_LIMIT + 1,
    )


def _strategy_ticket_query(
    *,
    query: StrategyTicketQuery,
    cursor: PageCursor | None,
) -> sa.Select[Any]:
    conditions: list[sa.ColumnElement[bool]] = [
        trade_tickets.c.created_at_ms >= query.from_ms,
        trade_tickets.c.created_at_ms < query.to_ms,
        trade_tickets.c.strategy_version_id == query.strategy_version_id,
    ]
    controlled_exit = _controlled_exit_exists()
    tp1_reached = _take_profit_filled_exists()
    natural_terminal = _natural_terminal_ticket_condition()
    if query.scope == "natural":
        conditions.append(~controlled_exit)
    if query.exit_path == "controlled_exit":
        conditions.append(controlled_exit)
    elif query.exit_path == "tp1_reached":
        conditions.extend((natural_terminal, ~controlled_exit, tp1_reached))
    elif query.exit_path == "tp1_not_reached":
        conditions.extend((natural_terminal, ~controlled_exit, ~tp1_reached))
    if cursor is not None:
        conditions.append(
            sa.tuple_(
                trade_tickets.c.created_at_ms,
                trade_tickets.c.ticket_id,
            )
            < sa.tuple_(
                sa.literal(cursor.sort_ms),
                sa.literal(cursor.identity),
            )
        )
    return _ticket_facts_select(conditions=conditions, limit=query.limit + 1)


def _ticket_facts_select(
    *,
    conditions: Sequence[sa.ColumnElement[bool]],
    limit: int,
) -> sa.Select[Any]:
    """Select one shared bounded Ticket row shape for every Owner read list."""

    open_incident = (
        sa.select(
            runtime_incidents.c.incident_id.label("open_incident_id"),
            runtime_incidents.c.opened_at_ms.label("open_incident_opened_at_ms"),
        )
        .where(
            runtime_incidents.c.ticket_id == trade_tickets.c.ticket_id,
            runtime_incidents.c.status == "open",
        )
        .order_by(
            runtime_incidents.c.opened_at_ms.asc(),
            runtime_incidents.c.incident_id.asc(),
        )
        .limit(1)
        .lateral("open_trade_incident")
    )
    latest_incident = (
        sa.select(
            runtime_incidents.c.incident_id.label("latest_incident_id"),
            runtime_incidents.c.opened_at_ms.label("latest_incident_opened_at_ms"),
        )
        .where(runtime_incidents.c.ticket_id == trade_tickets.c.ticket_id)
        .order_by(
            runtime_incidents.c.opened_at_ms.desc(),
            runtime_incidents.c.incident_id.desc(),
        )
        .limit(1)
        .lateral("latest_trade_incident")
    )
    exit_event = (
        sa.select(
            trade_events.c.event_id.label("exit_event_id"),
            trade_events.c.event_type.label("exit_event_type"),
            trade_events.c.payload.label("exit_event_payload"),
            trade_events.c.occurred_at_ms.label("exit_event_occurred_at_ms"),
        )
        .where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type == "ExitRequested",
        )
        .order_by(
            trade_events.c.sequence.asc(),
            trade_events.c.event_id.asc(),
        )
        .limit(1)
        .lateral("initial_trade_exit_event")
    )
    tp1_event = (
        sa.select(
            trade_events.c.event_id.label("tp1_event_id"),
            trade_events.c.occurred_at_ms.label("tp1_event_occurred_at_ms"),
        )
        .where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type == "TakeProfitFilled",
        )
        .order_by(
            trade_events.c.sequence.asc(),
            trade_events.c.event_id.asc(),
        )
        .limit(1)
        .lateral("first_trade_take_profit_event")
    )
    source = (
        trade_tickets.join(
            trade_aggregates,
            trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
        )
        .outerjoin(
            trade_reviews,
            trade_reviews.c.review_id == trade_aggregates.c.review_id,
        )
        .outerjoin(open_incident, sa.true())
        .outerjoin(latest_incident, sa.true())
        .outerjoin(exit_event, sa.true())
        .outerjoin(tp1_event, sa.true())
    )
    return (
        sa.select(
            trade_tickets.c.ticket_id,
            trade_tickets.c.strategy_group_id,
            trade_tickets.c.strategy_version_id,
            trade_tickets.c.event_spec_id,
            trade_tickets.c.exchange_instrument_id,
            trade_tickets.c.position_side,
            trade_tickets.c.status.label("ticket_status"),
            trade_tickets.c.created_at_ms.label("issued_at_ms"),
            trade_tickets.c.terminal_at_ms,
            trade_aggregates.c.ticket_id.label("aggregate_ticket_id"),
            trade_aggregates.c.status.label("aggregate_status"),
            trade_aggregates.c.review_id.label("aggregate_review_id"),
            trade_reviews.c.review_id,
            trade_reviews.c.ticket_id.label("review_ticket_id"),
            trade_reviews.c.revision.label("review_revision"),
            trade_reviews.c.metrics.label("review_metrics"),
            trade_reviews.c.created_at_ms.label("review_created_at_ms"),
            open_incident.c.open_incident_id,
            open_incident.c.open_incident_opened_at_ms,
            latest_incident.c.latest_incident_id,
            latest_incident.c.latest_incident_opened_at_ms,
            exit_event.c.exit_event_id,
            exit_event.c.exit_event_type,
            exit_event.c.exit_event_payload,
            exit_event.c.exit_event_occurred_at_ms,
            tp1_event.c.tp1_event_id,
            tp1_event.c.tp1_event_occurred_at_ms,
        )
        .select_from(source)
        .where(*conditions)
        .order_by(
            trade_tickets.c.created_at_ms.desc(),
            trade_tickets.c.ticket_id.desc(),
        )
        .limit(limit)
    )


def _controlled_exit_exists() -> sa.ColumnElement[bool]:
    reason = trade_events.c.payload["reason"].as_string()
    return sa.exists(
        sa.select(sa.literal(1)).where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type == "ExitRequested",
            sa.or_(
                reason.like("owner_flatten_all:%"),
                reason.like("deployment_drain:%"),
            ),
        )
    )


def _take_profit_filled_exists() -> sa.ColumnElement[bool]:
    return sa.exists(
        sa.select(sa.literal(1)).where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type == "TakeProfitFilled",
        )
    )


def _natural_terminal_ticket_condition() -> sa.ColumnElement[bool]:
    return sa.and_(
        trade_tickets.c.status == "terminal",
        trade_aggregates.c.status == "terminal",
        trade_tickets.c.terminal_at_ms.is_not(None),
    )


def _review_center_ticket_query(
    *,
    query: ReviewListQuery,
    cursor: PageCursor | None,
) -> sa.Select[Any]:
    terminal_at_ms = trade_tickets.c.terminal_at_ms
    conditions: list[sa.ColumnElement[bool]] = [
        trade_aggregates.c.status == "terminal",
        trade_tickets.c.status == "terminal",
        terminal_at_ms.is_not(None),
        terminal_at_ms >= query.from_ms,
        terminal_at_ms < query.to_ms,
    ]
    if query.strategy_group_id is not None:
        conditions.append(trade_tickets.c.strategy_group_id == query.strategy_group_id)
    if cursor is not None:
        conditions.append(
            sa.tuple_(terminal_at_ms, trade_tickets.c.ticket_id)
            < sa.tuple_(
                sa.literal(cursor.sort_ms),
                sa.literal(cursor.identity),
            )
        )

    exit_event = (
        sa.select(
            trade_events.c.event_id.label("exit_event_id"),
            trade_events.c.event_type.label("exit_event_type"),
            trade_events.c.payload.label("exit_event_payload"),
            trade_events.c.occurred_at_ms.label("exit_event_occurred_at_ms"),
        )
        .where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type == "ExitRequested",
        )
        .order_by(
            trade_events.c.sequence.asc(),
            trade_events.c.event_id.asc(),
        )
        .limit(1)
        .lateral("review_center_exit_event")
    )
    entry_event = _review_center_exact_event(
        event_types=("EntryFilled",),
        alias="review_center_entry_event",
        identity_label="entry_fill_event_id",
        occurred_at_label="entry_fill_event_at_ms",
    )
    protection_event = _review_center_exact_event(
        event_types=("InitialStopConfirmed",),
        alias="review_center_protection_event",
        identity_label="protection_confirmed_event_id",
        occurred_at_label="protection_confirmed_event_at_ms",
    )
    flat_event = _review_center_exact_event(
        event_types=("PositionFlatConfirmed", "ExternalFlatDetected"),
        alias="review_center_flat_event",
        identity_label="flat_event_id",
        occurred_at_label="flat_event_at_ms",
    )
    reconciliation_event = _review_center_exact_event(
        event_types=("ReconciliationMatched",),
        alias="review_center_reconciliation_event",
        identity_label="reconciliation_event_id",
        occurred_at_label="reconciliation_event_at_ms",
    )
    settlement_event = (
        sa.select(
            trade_events.c.event_id.label("settlement_event_id"),
            trade_events.c.occurred_at_ms.label("settlement_event_at_ms"),
        )
        .where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type == "BudgetSettled",
        )
        .order_by(trade_events.c.sequence.asc(), trade_events.c.event_id.asc())
        .limit(1)
        .lateral("review_center_settlement_event")
    )
    source = (
        trade_tickets.join(
            trade_aggregates,
            trade_aggregates.c.ticket_id == trade_tickets.c.ticket_id,
        )
        .outerjoin(
            trade_reviews,
            trade_reviews.c.review_id == trade_aggregates.c.review_id,
        )
        .outerjoin(entry_event, sa.true())
        .outerjoin(protection_event, sa.true())
        .outerjoin(exit_event, sa.true())
        .outerjoin(flat_event, sa.true())
        .outerjoin(reconciliation_event, sa.true())
        .outerjoin(settlement_event, sa.true())
    )
    return (
        sa.select(
            trade_tickets.c.ticket_id,
            trade_tickets.c.strategy_group_id,
            trade_tickets.c.event_spec_id,
            trade_tickets.c.exchange_instrument_id,
            trade_tickets.c.position_side,
            trade_tickets.c.status.label("ticket_status"),
            trade_tickets.c.created_at_ms.label("issued_at_ms"),
            terminal_at_ms,
            trade_tickets.c.risk_at_stop.label("frozen_initial_stop_risk"),
            trade_aggregates.c.actual_stop_risk,
            trade_aggregates.c.ticket_id.label("aggregate_ticket_id"),
            trade_aggregates.c.status.label("aggregate_status"),
            trade_aggregates.c.review_id.label("aggregate_review_id"),
            trade_aggregates.c.updated_at_ms.label("aggregate_updated_at_ms"),
            trade_reviews.c.review_id,
            trade_reviews.c.ticket_id.label("review_ticket_id"),
            trade_reviews.c.revision.label("review_revision"),
            trade_reviews.c.metrics.label("review_metrics"),
            trade_reviews.c.created_at_ms.label("review_created_at_ms"),
            sa.null().label("open_incident_id"),
            sa.null().label("open_incident_opened_at_ms"),
            sa.null().label("latest_incident_id"),
            sa.null().label("latest_incident_opened_at_ms"),
            entry_event.c.entry_fill_event_id,
            entry_event.c.entry_fill_event_at_ms,
            protection_event.c.protection_confirmed_event_id,
            protection_event.c.protection_confirmed_event_at_ms,
            exit_event.c.exit_event_id,
            exit_event.c.exit_event_type,
            exit_event.c.exit_event_payload,
            exit_event.c.exit_event_occurred_at_ms,
            flat_event.c.flat_event_id,
            flat_event.c.flat_event_at_ms,
            reconciliation_event.c.reconciliation_event_id,
            reconciliation_event.c.reconciliation_event_at_ms,
            settlement_event.c.settlement_event_id,
            settlement_event.c.settlement_event_at_ms,
        )
        .select_from(source)
        .where(*conditions)
        .order_by(
            terminal_at_ms.desc(),
            trade_tickets.c.ticket_id.desc(),
        )
        .limit(
            query.limit + 1
            if query.review_status is None
            else _REVIEW_CENTER_FILTER_CANDIDATE_LIMIT + 1
        )
    )


def _review_center_exact_event(
    *,
    event_types: tuple[str, ...],
    alias: str,
    identity_label: str,
    occurred_at_label: str,
) -> sa.FromClause:
    return (
        sa.select(
            trade_events.c.event_id.label(identity_label),
            trade_events.c.occurred_at_ms.label(occurred_at_label),
        )
        .where(
            trade_events.c.ticket_id == trade_tickets.c.ticket_id,
            trade_events.c.event_type.in_(event_types),
        )
        .order_by(trade_events.c.sequence.asc(), trade_events.c.event_id.asc())
        .limit(1)
        .lateral(alias)
    )


def _review_center_incidents_query(
    ticket_ids: tuple[str, ...],
) -> sa.Select[Any]:
    incident_rank = sa.func.row_number().over(
        partition_by=runtime_incidents.c.ticket_id,
        order_by=(
            runtime_incidents.c.opened_at_ms.asc(),
            runtime_incidents.c.incident_id.asc(),
        ),
    )
    ranked = (
        sa.select(
            runtime_incidents.c.incident_id,
            runtime_incidents.c.ticket_id,
            runtime_incidents.c.incident_kind,
            runtime_incidents.c.status,
            runtime_incidents.c.opened_at_ms,
            runtime_incidents.c.resolved_at_ms,
            incident_rank.label("incident_rank"),
        )
        .where(runtime_incidents.c.ticket_id.in_(ticket_ids))
        .cte("bounded_review_center_incidents")
    )
    return (
        sa.select(ranked)
        .where(ranked.c.incident_rank <= _REVIEW_CENTER_INCIDENT_LIMIT + 1)
        .order_by(
            ranked.c.ticket_id,
            ranked.c.opened_at_ms,
            ranked.c.incident_id,
        )
    )


def _trade_item_facts_from_row(row: RowMapping) -> TradeItemFacts:
    ticket_id = str(row["ticket_id"])
    if str(row["aggregate_ticket_id"]) != ticket_id:
        raise TradeFactsContradiction("Ticket and Aggregate identity mismatch")

    review_id = None if row["review_id"] is None else str(row["review_id"])
    review_metrics = row["review_metrics"]
    if review_metrics is not None and not isinstance(review_metrics, dict):
        raise TradeFactsContradiction("current Review metrics are not JSON object")
    for identity_name, time_name in (
        ("open_incident_id", "open_incident_opened_at_ms"),
        ("latest_incident_id", "latest_incident_opened_at_ms"),
    ):
        if (row[identity_name] is None) != (row[time_name] is None):
            raise TradeFactsContradiction("partial Incident summary row")
    tp1_event_id = row.get("tp1_event_id")
    tp1_event_occurred_at_ms = row.get("tp1_event_occurred_at_ms")
    if (tp1_event_id is None) != (tp1_event_occurred_at_ms is None):
        raise TradeFactsContradiction("partial TakeProfitFilled Event row")

    issued_at_ms = int(row["issued_at_ms"])
    evidence = [
        EvidenceRef(
            kind="ticket",
            identity=ticket_id,
            occurred_at_ms=issued_at_ms,
        )
    ]
    if tp1_event_id is not None:
        evidence.append(
            EvidenceRef(
                kind="event",
                identity=str(tp1_event_id),
                occurred_at_ms=int(tp1_event_occurred_at_ms),
            )
        )
    return TradeItemFacts(
        ticket_id=ticket_id,
        strategy_group_id=str(row["strategy_group_id"]),
        event_spec_id=str(row["event_spec_id"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(row["position_side"])),
        ticket_status=str(row["ticket_status"]),
        aggregate_status=str(row["aggregate_status"]),
        issued_at_ms=issued_at_ms,
        terminal_at_ms=(
            None if row["terminal_at_ms"] is None else int(row["terminal_at_ms"])
        ),
        aggregate_review_id=(
            None
            if row["aggregate_review_id"] is None
            else str(row["aggregate_review_id"])
        ),
        review_id=review_id,
        review_ticket_id=(
            None if row["review_ticket_id"] is None else str(row["review_ticket_id"])
        ),
        review_revision=(
            None if row["review_revision"] is None else int(row["review_revision"])
        ),
        review_created_at_ms=(
            None
            if row["review_created_at_ms"] is None
            else int(row["review_created_at_ms"])
        ),
        review_metrics=review_metrics,
        exit_event_id=(
            None if row["exit_event_id"] is None else str(row["exit_event_id"])
        ),
        exit_event_type=(
            None if row["exit_event_type"] is None else str(row["exit_event_type"])
        ),
        exit_event_payload=row["exit_event_payload"],
        exit_event_occurred_at_ms=(
            None
            if row["exit_event_occurred_at_ms"] is None
            else int(row["exit_event_occurred_at_ms"])
        ),
        open_incident_id=(
            None if row["open_incident_id"] is None else str(row["open_incident_id"])
        ),
        open_incident_opened_at_ms=(
            None
            if row["open_incident_opened_at_ms"] is None
            else int(row["open_incident_opened_at_ms"])
        ),
        latest_incident_id=(
            None
            if row["latest_incident_id"] is None
            else str(row["latest_incident_id"])
        ),
        latest_incident_opened_at_ms=(
            None
            if row["latest_incident_opened_at_ms"] is None
            else int(row["latest_incident_opened_at_ms"])
        ),
        tp1_reached=tp1_event_id is not None,
        evidence=tuple(evidence),
    )


def _strategy_ticket_facts_from_row(row: RowMapping) -> StrategyTicketFacts:
    """Reuse the canonical Trade builder before exposing evaluation facts."""

    trade = build_trade_item(_trade_item_facts_from_row(row))
    return StrategyTicketFacts(
        ticket_id=trade.ticket_id,
        issued_at_ms=trade.issued_at_ms,
        terminal_at_ms=trade.terminal_at_ms,
        ticket_status=trade.ticket_status,
        aggregate_status=trade.aggregate_status,
        review_id=trade.review_id,
        review_created_at_ms=(
            None
            if trade.review_id is None
            else next(
                (
                    evidence.occurred_at_ms
                    for evidence in trade.evidence
                    if evidence.kind == "review"
                    and evidence.identity == trade.review_id
                ),
                None,
            )
        ),
        economics_completeness=(trade.economics_completeness or "incomplete_evidence"),
        net_pnl=trade.net_pnl,
        net_r=trade.net_r,
        exit_reason=trade.exit_reason,
        tp1_reached=bool(row.get("tp1_event_id")),
        evidence=trade.evidence,
    )


def _review_center_incidents_by_ticket(
    rows: Sequence[RowMapping],
) -> dict[str, tuple[RowMapping, ...]]:
    grouped: dict[str, list[RowMapping]] = {}
    for row in rows:
        ticket_id = str(row["ticket_id"])
        grouped.setdefault(ticket_id, []).append(row)
    for ticket_id, incidents in grouped.items():
        if len(incidents) > _REVIEW_CENTER_INCIDENT_LIMIT:
            raise TradeFactsContradiction(
                f"Ticket {ticket_id} has more than "
                f"{_REVIEW_CENTER_INCIDENT_LIMIT} Incidents"
            )
    return {ticket_id: tuple(incidents) for ticket_id, incidents in grouped.items()}


def _review_center_item_facts(
    row: RowMapping,
    *,
    incidents: tuple[RowMapping, ...],
) -> ReviewCenterItemFacts:
    aggregate_review_id = (
        None if row["aggregate_review_id"] is None else str(row["aggregate_review_id"])
    )
    joined_review_id = None if row["review_id"] is None else str(row["review_id"])
    if aggregate_review_id is not None and joined_review_id is None:
        raise TradeFactsContradiction("Aggregate current Review pointer is dangling")
    if aggregate_review_id != joined_review_id:
        raise TradeFactsContradiction(
            "Aggregate current Review pointer identity mismatch"
        )
    trade_facts = _trade_item_facts_from_row(row)
    trade = build_trade_item(trade_facts)
    ticket_id = trade.ticket_id
    incident_ids: list[str] = []
    recovered_incident_ids: list[str] = []
    ticket_evidence = EvidenceRef(
        kind="ticket",
        identity=ticket_id,
        occurred_at_ms=int(row["issued_at_ms"]),
    )
    aggregate_evidence = EvidenceRef(
        kind="aggregate",
        identity=ticket_id,
        occurred_at_ms=int(row["aggregate_updated_at_ms"]),
    )
    evidence = [ticket_evidence, aggregate_evidence]
    exact_event_refs: dict[str, EvidenceRef | None] = {}
    for field_name, identity_name, time_name, kind in (
        (
            "entry_fill_evidence",
            "entry_fill_event_id",
            "entry_fill_event_at_ms",
            "event",
        ),
        (
            "protection_confirmed_evidence",
            "protection_confirmed_event_id",
            "protection_confirmed_event_at_ms",
            "event",
        ),
        (
            "exit_trigger_evidence",
            "exit_event_id",
            "exit_event_occurred_at_ms",
            "event",
        ),
        (
            "flat_evidence",
            "flat_event_id",
            "flat_event_at_ms",
            "event",
        ),
        (
            "reconciliation_matched_evidence",
            "reconciliation_event_id",
            "reconciliation_event_at_ms",
            "event",
        ),
        (
            "settlement_evidence",
            "settlement_event_id",
            "settlement_event_at_ms",
            "settlement",
        ),
    ):
        identity = row[identity_name]
        occurred_at_ms = row[time_name]
        if (identity is None) != (occurred_at_ms is None):
            raise TradeFactsContradiction("partial exact Review Event row")
        ref = (
            None
            if identity is None
            else EvidenceRef(
                kind=cast(Any, kind),
                identity=str(identity),
                occurred_at_ms=int(occurred_at_ms),
            )
        )
        exact_event_refs[field_name] = ref
        if ref is not None:
            evidence.append(ref)
    incident_evidence: list[EvidenceRef] = []
    for incident in incidents:
        if str(incident["ticket_id"]) != ticket_id:
            raise TradeFactsContradiction(
                "Review Center Incident Ticket identity mismatch"
            )
        incident_id = str(incident["incident_id"])
        status = str(incident["status"])
        resolved_at_ms = incident["resolved_at_ms"]
        if status == "open":
            if resolved_at_ms is not None:
                raise TradeFactsContradiction("open Incident has resolved timestamp")
        elif status == "resolved":
            if resolved_at_ms is None:
                raise TradeFactsContradiction(
                    "resolved Incident lacks resolved timestamp"
                )
            recovered_incident_ids.append(incident_id)
        else:
            raise TradeFactsContradiction(f"unknown Incident status: {status}")
        incident_ids.append(incident_id)
        incident_ref = EvidenceRef(
            kind="incident",
            identity=incident_id,
            occurred_at_ms=int(incident["opened_at_ms"]),
        )
        incident_evidence.append(incident_ref)
        evidence.append(incident_ref)

    current_review_evidence = (
        None
        if joined_review_id is None
        else EvidenceRef(
            kind="review",
            identity=joined_review_id,
            occurred_at_ms=int(row["review_created_at_ms"]),
        )
    )
    if current_review_evidence is not None:
        evidence.append(current_review_evidence)
    unavailable_runner = MoneyMetric(
        value=None,
        unit="USDT",
        unavailable_reason="runner_contribution_unavailable",
    )
    review_facts = ProgrammaticReviewFacts(
        ticket_id=ticket_id,
        ticket_status=trade.ticket_status,
        aggregate_status=trade.aggregate_status,
        lifecycle_stage=aggregate_stage(trade.aggregate_status),
        settlement_completed=exact_event_refs["settlement_evidence"] is not None,
        current_review_id=aggregate_review_id,
        entry_complete=exact_event_refs["entry_fill_evidence"] is not None,
        protection_complete=(
            exact_event_refs["protection_confirmed_evidence"] is not None
        ),
        exit_complete=(
            exact_event_refs["exit_trigger_evidence"] is not None
            and exact_event_refs["flat_evidence"] is not None
        ),
        reconciliation_complete=(
            exact_event_refs["reconciliation_matched_evidence"] is not None
        ),
        review_complete=current_review_evidence is not None,
        incident_ids=tuple(incident_ids),
        recovered_incident_ids=tuple(recovered_incident_ids),
        economics_completeness=(trade.economics_completeness or "incomplete_evidence"),
        gross_pnl=trade.gross_pnl,
        fees=trade.fees,
        funding=trade.funding,
        net_pnl=trade.net_pnl,
        net_r=trade.net_r,
        frozen_initial_stop_risk=_review_center_risk_metric(
            row["frozen_initial_stop_risk"],
            unavailable_reason="frozen_initial_stop_risk_unavailable",
        ),
        actual_stop_risk=_review_center_risk_metric(
            row["actual_stop_risk"],
            unavailable_reason="actual_stop_risk_unavailable",
        ),
        exit_reason=trade.exit_reason,
        runner_net_contribution=unavailable_runner,
        ticket_evidence=ticket_evidence,
        aggregate_evidence=aggregate_evidence,
        entry_fill_evidence=exact_event_refs["entry_fill_evidence"],
        protection_confirmed_evidence=exact_event_refs["protection_confirmed_evidence"],
        exit_trigger_evidence=exact_event_refs["exit_trigger_evidence"],
        flat_evidence=exact_event_refs["flat_evidence"],
        reconciliation_matched_evidence=exact_event_refs[
            "reconciliation_matched_evidence"
        ],
        settlement_evidence=exact_event_refs["settlement_evidence"],
        current_review_evidence=current_review_evidence,
        incident_evidence=tuple(incident_evidence),
        evidence=tuple(evidence),
    )
    terminal_at_ms = row["terminal_at_ms"]
    if terminal_at_ms is None:
        raise TradeFactsContradiction(
            "Review Center terminal Ticket lacks terminal timestamp"
        )
    return ReviewCenterItemFacts(
        strategy_group_id=trade.strategy_group_id,
        exchange_instrument_id=trade.exchange_instrument_id,
        position_side=trade.position_side,
        terminal_at_ms=int(terminal_at_ms),
        review=review_facts,
    )


def _review_center_risk_metric(
    value: object,
    *,
    unavailable_reason: str,
) -> MoneyMetric:
    if not isinstance(value, Decimal) or not value.is_finite():
        return MoneyMetric(
            value=None,
            unit="USDT",
            unavailable_reason=unavailable_reason,
        )
    return MoneyMetric(value=value, unit="USDT")


def _signal_joined_select() -> sa.Select[Any]:
    return sa.select(
        signal_events.c.signal_event_id,
        signal_events.c.exposure_episode_id,
        signal_events.c.runtime_scope_id,
        signal_events.c.runtime_scope_version,
        signal_events.c.strategy_group_id,
        signal_events.c.strategy_version_id,
        signal_events.c.event_spec_id,
        signal_events.c.universe_version_id,
        signal_events.c.universe_semantic_digest,
        signal_events.c.exchange_instrument_id,
        signal_events.c.position_side,
        signal_events.c.occurred_at_ms,
        signal_events.c.expires_at_ms,
        admission_decisions.c.admission_decision_id,
        admission_decisions.c.signal_event_id.label("decision_signal_event_id"),
        admission_decisions.c.exposure_episode_id.label("decision_exposure_episode_id"),
        admission_decisions.c.runtime_scope_id.label("decision_runtime_scope_id"),
        admission_decisions.c.runtime_scope_version.label(
            "decision_runtime_scope_version"
        ),
        admission_decisions.c.strategy_group_id.label("decision_strategy_group_id"),
        admission_decisions.c.strategy_version_id.label("decision_strategy_version_id"),
        admission_decisions.c.event_spec_id.label("decision_event_spec_id"),
        admission_decisions.c.universe_version_id.label("decision_universe_version_id"),
        admission_decisions.c.universe_semantic_digest.label(
            "decision_universe_semantic_digest"
        ),
        admission_decisions.c.exchange_instrument_id.label(
            "decision_exchange_instrument_id"
        ),
        admission_decisions.c.position_side.label("decision_position_side"),
        admission_decisions.c.decision_status,
        admission_decisions.c.first_blocker,
        admission_decisions.c.binding_constraint,
        admission_decisions.c.ticket_id,
        admission_decisions.c.decided_at_ms,
        shadow_outcomes_current.c.shadow_outcome_id,
        shadow_outcomes_current.c.admission_decision_id.label(
            "shadow_admission_decision_id"
        ),
        shadow_outcomes_current.c.exchange_instrument_id.label(
            "shadow_exchange_instrument_id"
        ),
        shadow_outcomes_current.c.position_side.label("shadow_position_side"),
        shadow_outcomes_current.c.status.label("shadow_status"),
        shadow_outcomes_current.c.mfe_r.label("shadow_mfe_r"),
        shadow_outcomes_current.c.mae_r.label("shadow_mae_r"),
        shadow_outcomes_current.c.completion_reason.label("shadow_completion_reason"),
        shadow_outcomes_current.c.observed_through_ms.label(
            "shadow_observed_through_ms"
        ),
        shadow_outcomes_current.c.completed_at_ms.label("shadow_completed_at_ms"),
    ).select_from(
        signal_events.join(
            admission_decisions,
            admission_decisions.c.signal_event_id == signal_events.c.signal_event_id,
        ).outerjoin(
            shadow_outcomes_current,
            shadow_outcomes_current.c.admission_decision_id
            == admission_decisions.c.admission_decision_id,
        )
    )


def _exact_signal_query(signal_event_id: str) -> sa.Select[Any]:
    return (
        sa.select(signal_events)
        .where(signal_events.c.signal_event_id == signal_event_id)
        .limit(2)
    )


def _exact_admission_query(signal_event_id: str) -> sa.Select[Any]:
    return (
        sa.select(admission_decisions)
        .where(admission_decisions.c.signal_event_id == signal_event_id)
        .limit(2)
    )


def _exact_signal_facts_query(signal_event_id: str) -> sa.Select[Any]:
    return (
        sa.select(signal_fact_snapshots)
        .where(signal_fact_snapshots.c.signal_event_id == signal_event_id)
        .order_by(signal_fact_snapshots.c.fact_definition_id)
        .limit(257)
    )


def _exact_shadow_query(admission_decision_id: str) -> sa.Select[Any]:
    return (
        sa.select(
            shadow_outcomes_current.c.shadow_outcome_id,
            shadow_outcomes_current.c.admission_decision_id,
            shadow_outcomes_current.c.exchange_instrument_id,
            shadow_outcomes_current.c.position_side,
            shadow_outcomes_current.c.status.label("shadow_status"),
            shadow_outcomes_current.c.mfe_r.label("shadow_mfe_r"),
            shadow_outcomes_current.c.mae_r.label("shadow_mae_r"),
            shadow_outcomes_current.c.completion_reason.label(
                "shadow_completion_reason"
            ),
            shadow_outcomes_current.c.observed_through_ms.label(
                "shadow_observed_through_ms"
            ),
            shadow_outcomes_current.c.completed_at_ms.label("shadow_completed_at_ms"),
        )
        .where(shadow_outcomes_current.c.admission_decision_id == admission_decision_id)
        .limit(2)
    )


def _signal_item_facts_from_joined_row(row: RowMapping) -> SignalItemFacts:
    _validate_joined_signal_identity(row)
    return _signal_item_facts(
        signal=row,
        decision=row,
        shadow=row if row["shadow_outcome_id"] is not None else None,
    )


def _signal_item_facts_from_detail_rows(
    *,
    signal: RowMapping,
    decision: RowMapping,
    shadow: RowMapping | None,
) -> SignalItemFacts:
    return _signal_item_facts(
        signal=signal,
        decision=decision,
        shadow=shadow,
    )


def _signal_item_facts(
    *,
    signal: RowMapping,
    decision: RowMapping,
    shadow: RowMapping | None,
) -> SignalItemFacts:
    signal_event_id = str(signal["signal_event_id"])
    admission_decision_id = str(decision["admission_decision_id"])
    occurred_at_ms = int(signal["occurred_at_ms"])
    decided_at_ms = int(decision["decided_at_ms"])
    evidence = [
        EvidenceRef(
            kind="signal",
            identity=signal_event_id,
            occurred_at_ms=occurred_at_ms,
        ),
        EvidenceRef(
            kind="admission",
            identity=admission_decision_id,
            occurred_at_ms=decided_at_ms,
        ),
    ]
    shadow_outcome_id = None
    shadow_status = None
    shadow_mfe_r = None
    shadow_mae_r = None
    shadow_completion_reason = None
    shadow_observed_through_ms = None
    shadow_completed_at_ms = None
    if shadow is not None:
        shadow_outcome_id = str(shadow["shadow_outcome_id"])
        shadow_status = str(shadow["shadow_status"])
        shadow_mfe_r = _exact_decimal_or_none(
            shadow["shadow_mfe_r"],
            field_name="shadow_mfe_r",
        )
        shadow_mae_r = _exact_decimal_or_none(
            shadow["shadow_mae_r"],
            field_name="shadow_mae_r",
        )
        shadow_completion_reason = (
            None
            if shadow["shadow_completion_reason"] is None
            else str(shadow["shadow_completion_reason"])
        )
        shadow_observed_through_ms = (
            None
            if shadow["shadow_observed_through_ms"] is None
            else int(shadow["shadow_observed_through_ms"])
        )
        shadow_completed_at_ms = (
            None
            if shadow["shadow_completed_at_ms"] is None
            else int(shadow["shadow_completed_at_ms"])
        )
        evidence.append(
            EvidenceRef(
                kind="shadow",
                identity=shadow_outcome_id,
                occurred_at_ms=shadow_completed_at_ms or decided_at_ms,
            )
        )

    return SignalItemFacts(
        signal_event_id=signal_event_id,
        exposure_episode_id=str(signal["exposure_episode_id"]),
        strategy_group_id=str(signal["strategy_group_id"]),
        strategy_version_id=str(signal["strategy_version_id"]),
        event_spec_id=str(signal["event_spec_id"]),
        exchange_instrument_id=str(signal["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(signal["position_side"])),
        occurred_at_ms=occurred_at_ms,
        expires_at_ms=int(signal["expires_at_ms"]),
        admission_decision_id=admission_decision_id,
        decision_status=cast(
            Literal["admitted", "rejected"],
            str(decision["decision_status"]),
        ),
        first_blocker=(
            None
            if decision["first_blocker"] is None
            else str(decision["first_blocker"])
        ),
        binding_constraint=(
            None
            if decision["binding_constraint"] is None
            else str(decision["binding_constraint"])
        ),
        ticket_id=(
            None if decision["ticket_id"] is None else str(decision["ticket_id"])
        ),
        decided_at_ms=decided_at_ms,
        shadow_outcome_id=shadow_outcome_id,
        shadow_status=cast(
            Literal["pending", "claimed", "completed", "unavailable"] | None,
            shadow_status,
        ),
        shadow_mfe_r=shadow_mfe_r,
        shadow_mae_r=shadow_mae_r,
        shadow_completion_reason=shadow_completion_reason,
        shadow_observed_through_ms=shadow_observed_through_ms,
        shadow_completed_at_ms=shadow_completed_at_ms,
        evidence=tuple(evidence),
    )


def _validate_joined_signal_identity(row: RowMapping) -> None:
    pairs = (
        ("signal_event_id", "decision_signal_event_id"),
        ("exposure_episode_id", "decision_exposure_episode_id"),
        ("runtime_scope_id", "decision_runtime_scope_id"),
        ("runtime_scope_version", "decision_runtime_scope_version"),
        ("strategy_group_id", "decision_strategy_group_id"),
        ("strategy_version_id", "decision_strategy_version_id"),
        ("event_spec_id", "decision_event_spec_id"),
        ("universe_version_id", "decision_universe_version_id"),
        (
            "universe_semantic_digest",
            "decision_universe_semantic_digest",
        ),
        (
            "exchange_instrument_id",
            "decision_exchange_instrument_id",
        ),
        ("position_side", "decision_position_side"),
    )
    if any(row[left] != row[right] for left, right in pairs):
        raise SignalFactsContradiction("signal and admission identity mismatch")
    if row["shadow_outcome_id"] is not None:
        shadow_pairs = (
            ("admission_decision_id", "shadow_admission_decision_id"),
            ("exchange_instrument_id", "shadow_exchange_instrument_id"),
            ("position_side", "shadow_position_side"),
        )
        if any(row[left] != row[right] for left, right in shadow_pairs):
            raise SignalFactsContradiction(
                "admission and Shadow Outcome identity mismatch"
            )


def _validate_signal_admission_identity(
    *, signal: RowMapping, decision: RowMapping
) -> None:
    names = (
        "signal_event_id",
        "exposure_episode_id",
        "runtime_scope_id",
        "runtime_scope_version",
        "strategy_group_id",
        "strategy_version_id",
        "event_spec_id",
        "universe_version_id",
        "universe_semantic_digest",
        "exchange_instrument_id",
        "position_side",
    )
    if any(signal[name] != decision[name] for name in names):
        raise SignalFactsContradiction("signal and admission identity mismatch")


def _validate_shadow_identity(
    *, decision: RowMapping, shadow: RowMapping | None
) -> None:
    if shadow is None:
        return
    if (
        shadow["admission_decision_id"] != decision["admission_decision_id"]
        or shadow["exchange_instrument_id"] != decision["exchange_instrument_id"]
        or shadow["position_side"] != decision["position_side"]
    ):
        raise SignalFactsContradiction("admission and Shadow Outcome identity mismatch")


def _signal_fact_snapshot_from_row(
    row: RowMapping,
    *,
    expected_signal_event_id: str,
) -> SignalFactSnapshotFacts:
    signal_event_id = str(row["signal_event_id"])
    if signal_event_id != expected_signal_event_id:
        raise SignalFactsContradiction("fact snapshot signal identity mismatch")
    return SignalFactSnapshotFacts(
        signal_event_id=signal_event_id,
        fact_definition_id=str(row["fact_definition_id"]),
        role=cast(
            Literal[
                "condition",
                "protection_reference",
                "identity_reference",
                "lifecycle_reference",
                "disable",
            ],
            str(row["role"]),
        ),
        value=row["value"],
        satisfied=bool(row["satisfied"]),
        observed_at_ms=int(row["observed_at_ms"]),
        valid_until_ms=int(row["valid_until_ms"]),
        projection_version=int(row["projection_version"]),
    )


def _exact_decimal_or_none(
    value: object,
    *,
    field_name: str,
) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise SignalFactsContradiction(f"{field_name} did not decode as Decimal")
    return value


def _overview_authority_query() -> sa.Select[Any]:
    runtime_profile_id = owner_policy_current.c.scope["runtime_profile_id"].as_string()
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
            account_exposure_current.c.updated_at_ms.label("exposure_updated_at_ms"),
        )
        .select_from(
            owner_policy_current.join(
                runtime_profiles,
                runtime_profiles.c.runtime_profile_id == runtime_profile_id,
            ).outerjoin(
                account_exposure_current,
                sa.and_(
                    account_exposure_current.c.venue_id == runtime_profiles.c.venue_id,
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
            actionable_incident.c.incident_id.label("top_actionable_incident_id"),
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
            actionable_monitor.c.monitor_key.label("needs_intervention_monitor_key"),
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
                actionable_incident.c.incident_id == actionable_monitor.c.incident_id,
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
        sa.and_(
            monitor.c.ticket_id.is_not(None),
            ticket.c.terminal_at_ms.is_(None),
            ticket_scope,
        ),
        sa.and_(
            monitor.c.incident_id.is_not(None),
            incident.c.status == "open",
            incident_scope,
        ),
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
    planned_r_multiple = trade_reviews.c.metrics["planned_r_multiple"].as_string()
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
    evidence_id = row["invalid_review_id"] if invalid_count else row["latest_review_id"]
    evidence_at_ms = (
        row["invalid_review_at_ms"] if invalid_count else row["latest_review_at_ms"]
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
        freshness = Freshness.CONTRADICTORY if contradictory else Freshness.UNAVAILABLE
        return freshness, "owner_policy:configured", now_ms
    account_identity = f"account:{authority['venue_id']}:{authority['account_id']}"
    required = [
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
