"""Durable receiver/current lease inside the existing Reconciliation ownership."""

from __future__ import annotations

from hashlib import sha256

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.infrastructure.binance_management_observation import (
    parse_order_update,
)
from src.trading_kernel.infrastructure.pg_models import failure_diagnostics
from src.trading_kernel.infrastructure.pg_models import (
    management_coverage_events as coverage,
)
from src.trading_kernel.infrastructure.pg_models import management_feed_current as feeds
from src.trading_kernel.infrastructure.pg_models import (
    management_stream_events as raw_events,
)
from src.trading_kernel.infrastructure.runtime_identity import CURRENT_SCHEMA_REVISION

FEED_LEASE_MS = 15000


class _ObservationDeferred(Exception):
    """A callback declined application; no partial effect may be committed."""


class PostgresManagementFeed:
    def __init__(self, connection):
        self.c = connection
        self.application_checkpoint = connection.begin_nested

    async def lock_receiver(self, scope_key):
        await self.c.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": "management-feed:" + scope_key},
        )

    async def get_feed(self, scope_key, *, for_update=False):
        statement = sa.select(feeds).where(feeds.c.scope_key == scope_key)
        if for_update:
            statement = statement.with_for_update()
        row = (await self.c.execute(statement)).mappings().one_or_none()
        return None if row is None else dict(row)

    async def current_gap_started_at(self, scope_key, epoch_id):
        return await self.c.scalar(
            sa.select(coverage.c.occurred_at_ms)
            .where(
                coverage.c.scope_key == scope_key,
                coverage.c.epoch_id == epoch_id,
                coverage.c.kind.in_(("gap", "epoch_started")),
            )
            .order_by(
                coverage.c.occurred_at_ms.desc(), coverage.c.coverage_event_id.desc()
            )
            .limit(1)
        )

    async def start_feed(
        self, *, scope_key, epoch_id, worker_id, runtime_commit, now_ms
    ):
        await self.c.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:scope,0))"),
            {"scope": "management-feed:" + scope_key},
        )
        old = (
            (
                await self.c.execute(
                    sa.select(feeds)
                    .where(feeds.c.scope_key == scope_key)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            old is not None
            and old["epoch_id"] != epoch_id
            and old["lease_until_ms"] > now_ms
            and old["owner_worker_id"] != worker_id
        ):
            raise ValueError("management receiver already owns a live epoch")
        if (
            old is not None
            and old["epoch_id"] != epoch_id
            and old["applied_watermark"] < old["persisted_watermark"]
        ):
            raise ValueError("previous management epoch has unapplied events")
        if (
            old is not None
            and old["connected_at_ms"] is not None
            and old["last_successful_at_ms"] is not None
        ):
            await self.c.execute(
                insert(coverage)
                .values(
                    coverage_event_id=f"closed:{old['epoch_id']}",
                    scope_key=scope_key,
                    epoch_id=old["epoch_id"],
                    kind="epoch_closed",
                    from_ms=old["connected_at_ms"],
                    to_ms=old["last_successful_at_ms"],
                    receive_watermark=old["persisted_watermark"],
                    reason=None,
                    occurred_at_ms=now_ms,
                )
                .on_conflict_do_nothing()
            )
        values = {
            "scope_key": scope_key,
            "epoch_id": epoch_id,
            "owner_worker_id": worker_id,
            "runtime_commit": runtime_commit,
            "schema_revision": CURRENT_SCHEMA_REVISION,
            "lease_until_ms": now_ms + FEED_LEASE_MS,
            "connection_state": "connecting",
            "persisted_watermark": 0,
            "applied_watermark": 0,
            "connected_at_ms": None,
            "last_successful_at_ms": None,
            "health_reason": "stream_not_ready",
            "revision": 1 if old is None else old["revision"] + 1,
        }
        await self.c.execute(
            insert(feeds)
            .values(**values)
            .on_conflict_do_update(index_elements=["scope_key"], set_=values)
        )
        await self.c.execute(
            insert(coverage)
            .values(
                coverage_event_id=f"epoch:{epoch_id}",
                scope_key=scope_key,
                epoch_id=epoch_id,
                kind="epoch_started",
                from_ms=now_ms,
                to_ms=now_ms,
                receive_watermark=0,
                reason="new_process_or_transport",
                occurred_at_ms=now_ms,
            )
            .on_conflict_do_nothing()
        )

    async def persist_stream_batch(
        self,
        *,
        scope_key,
        epoch_id,
        events: list,
        connected_at_ms,
        now_ms,
        gap_reason=None,
        worker_id=None,
        backlog_pending=False,
        apply_observer=None,
        account_id=None,
        application_runtime_commit=None,
    ):
        row = (
            (
                await self.c.execute(
                    sa.select(feeds)
                    .where(feeds.c.scope_key == scope_key)
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row["epoch_id"] != epoch_id
            or (worker_id is not None and row["owner_worker_id"] != worker_id)
        ):
            raise ValueError("management epoch ownership differs")
        apply_commit = application_runtime_commit or row["runtime_commit"]
        watermark = row["persisted_watermark"]
        applied = row["applied_watermark"]
        for event in sorted(events, key=lambda e: e["sequence"]):
            sequence = event["sequence"]
            payload = event["payload"]
            digest = canonical_digest(payload)
            if sequence <= watermark:
                old = (
                    (
                        await self.c.execute(
                            sa.select(
                                raw_events.c.payload_digest, raw_events.c.received_at_ms
                            ).where(
                                raw_events.c.scope_key == scope_key,
                                raw_events.c.epoch_id == epoch_id,
                                raw_events.c.receive_sequence == sequence,
                            )
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    old is None
                    or old["payload_digest"] != digest
                    or old["received_at_ms"] != event["received_at_ms"]
                ):
                    raise ValueError("management receive identity collision")
                continue
            if sequence != watermark + 1:
                gap_reason = "management_receive_sequence_gap"
            await self.c.execute(
                insert(raw_events)
                .values(
                    event_id="stream:"
                    + sha256(f"{scope_key}:{epoch_id}:{sequence}".encode()).hexdigest(),
                    scope_key=scope_key,
                    epoch_id=epoch_id,
                    receive_sequence=sequence,
                    received_at_ms=event["received_at_ms"],
                    exchange_event_at_ms=None,
                    message_kind=str(payload.get("e", "unknown"))[:96],
                    safe_payload=payload,
                    payload_digest=digest,
                )
                .on_conflict_do_nothing()
            )
            watermark = sequence
            try:
                parsed = parse_order_update(
                    payload,
                    account_id=event.get("account_id", "account"),
                    received_at_ms=event["received_at_ms"],
                    coverage_complete=True,
                )
                if (
                    parsed.exchange_event_at_ms > parsed.received_at_ms
                    or parsed.received_at_ms > now_ms
                ):
                    raise ValueError("management event clock differs")

            except (ValueError, TypeError, KeyError):
                gap_reason = "management_stream_protocol_invalid"
        # A receipt can be acknowledged once raw input is durable; authority waits
        # for ordered canonical application, including attribution to active Tickets.
        pending = (
            (
                await self.c.execute(
                    sa.select(raw_events)
                    .where(
                        raw_events.c.scope_key == scope_key,
                        raw_events.c.epoch_id == epoch_id,
                        raw_events.c.receive_sequence > applied,
                    )
                    .order_by(raw_events.c.receive_sequence)
                    .limit(129)
                )
            )
            .mappings()
            .all()
        )
        for saved in pending[:128]:
            if saved["receive_sequence"] != applied + 1:
                break
            try:
                parsed = parse_order_update(
                    saved["safe_payload"],
                    account_id=account_id or scope_key.rsplit(":", 1)[-1],
                    received_at_ms=saved["received_at_ms"],
                    coverage_complete=True,
                )
                if (
                    parsed.exchange_event_at_ms > parsed.received_at_ms
                    or parsed.received_at_ms > now_ms
                ):
                    raise ValueError("management event clock differs")
            except (ValueError, TypeError, KeyError):
                gap_reason = "management_stream_protocol_invalid"
                break
            parsed = parsed.model_copy(
                update={
                    "source_event_id": saved["event_id"],
                    "source_kind": "stream",
                    "source_digest": saved["payload_digest"],
                }
            )
            from src.trading_kernel.infrastructure.pg_models import trade_tickets

            ticket_id = await self.c.scalar(
                sa.select(trade_tickets.c.ticket_id)
                .where(
                    trade_tickets.c.venue_id == parsed.terms.venue_id,
                    trade_tickets.c.account_id == parsed.terms.account_id,
                    trade_tickets.c.exchange_instrument_id
                    == parsed.terms.exchange_instrument_id,
                    trade_tickets.c.position_side == parsed.terms.position_side,
                    trade_tickets.c.terminal_at_ms.is_(None),
                )
                .limit(1)
            )
            if ticket_id is not None:
                if apply_observer is None:
                    break
                # Retry diagnostics survive the failed observer savepoint. Never
                # ACK canonical application or skip the first failed sequence.
                previous = (
                    (
                        await self.c.execute(
                            sa.select(failure_diagnostics)
                            .where(
                                failure_diagnostics.c.stage
                                == "management_stream_apply",
                                failure_diagnostics.c.subject_id == saved["event_id"],
                            )
                            .order_by(
                                failure_diagnostics.c.occurred_at_ms.desc(),
                                failure_diagnostics.c.diagnostic_id.desc(),
                            )
                            .limit(1)
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                basis = previous["basis"] if previous is not None else {}
                same_runtime = (
                    basis.get("runtime_commit") == apply_commit
                    and basis.get("schema_revision") == row["schema_revision"]
                )
                attempts = int(basis.get("attempt", 0)) if same_runtime else 0
                if (
                    same_runtime
                    and previous["reason_code"] != "resolved"
                    and (attempts >= 3 or now_ms < int(basis.get("retry_at_ms", 0)))
                ):
                    gap_reason = "management_event_apply_blocked"
                    break
                try:
                    async with self.application_checkpoint():
                        if not await apply_observer(ticket_id, parsed):
                            raise _ObservationDeferred
                except _ObservationDeferred:
                    break
                except (ValueError, TypeError, KeyError, RuntimeError, AssertionError) as exc:
                    attempt = attempts + 1
                    await self.c.execute(
                        insert(failure_diagnostics)
                        .values(
                            diagnostic_id="feed-apply:"
                            + canonical_digest(
                                {
                                    "event": saved["event_id"],
                                    "runtime": apply_commit,
                                    "schema": row["schema_revision"],
                                    "attempt": attempt,
                                }
                            ).split(":")[-1],
                            stage="management_stream_apply",
                            subject_id=saved["event_id"],
                            reason_code=type(exc).__name__,
                            occurred_at_ms=now_ms,
                            basis={
                                "ticket_id": ticket_id,
                                "epoch_id": epoch_id,
                                "sequence": saved["receive_sequence"],
                                "payload_digest": saved["payload_digest"],
                                "runtime_commit": apply_commit,
                                "schema_revision": row["schema_revision"],
                                "attempt": attempt,
                                "retry_at_ms": now_ms
                                + (5000 if attempt == 1 else 30000),
                                "resolution": "blocked"
                                if attempt >= 3
                                else "retry_due",
                            },
                        )
                        .on_conflict_do_nothing()
                    )
                    gap_reason = "management_event_apply_blocked"
                    break
                if previous is not None and previous["reason_code"] != "resolved":
                    await self.c.execute(
                        insert(failure_diagnostics)
                        .values(
                            diagnostic_id="feed-resolved:"
                            + canonical_digest(
                                {
                                    "event": saved["event_id"],
                                    "runtime": apply_commit,
                                    "schema": row["schema_revision"],
                                }
                            ).split(":")[-1],
                            stage="management_stream_apply",
                            subject_id=saved["event_id"],
                            reason_code="resolved",
                            occurred_at_ms=now_ms,
                            basis={
                                "ticket_id": ticket_id,
                                "sequence": saved["receive_sequence"],
                                "runtime_commit": apply_commit,
                                "schema_revision": row["schema_revision"],
                                "attempt": attempts,
                                "resolution": "applied_in_order",
                            },
                        )
                        .on_conflict_do_nothing()
                    )
            applied = saved["receive_sequence"]
        connected = (
            row["connected_at_ms"]
            if row["connected_at_ms"] is not None
            else connected_at_ms
        )
        ready = (
            connected is not None
            and gap_reason is None
            and not backlog_pending
            and applied == watermark
        )
        reason = (
            gap_reason
            if gap_reason is not None
            else (
                None
                if ready
                else "receiver_backlog"
                if backlog_pending or applied < watermark
                else "stream_not_ready"
            )
        )
        # A gap cannot be erased in the same connection epoch by a later healthy poll.
        if row["health_reason"] not in (
            None,
            "stream_not_ready",
            "receiver_backlog",
            "management_event_apply_blocked",
        ):
            ready = False
            reason = row["health_reason"]
        await self.c.execute(
            sa.update(feeds)
            .where(feeds.c.scope_key == scope_key)
            .values(
                persisted_watermark=watermark,
                applied_watermark=applied,
                lease_until_ms=now_ms + FEED_LEASE_MS,
                connection_state="ready" if ready else "gap",
                connected_at_ms=connected,
                last_successful_at_ms=now_ms if ready else row["last_successful_at_ms"],
                health_reason=reason,
                revision=row["revision"] + 1,
            )
        )
        # Checkpoints are coalesced in the current row. Only durable connection/gap
        # transitions append coverage events; an idle tick produces no history rows.
        if row["connection_state"] != ("ready" if ready else "gap"):
            await self.c.execute(
                insert(coverage)
                .values(
                    coverage_event_id=f"coverage:{epoch_id}:{row['revision'] + 1}",
                    scope_key=scope_key,
                    epoch_id=epoch_id,
                    kind="connected" if ready else "gap",
                    from_ms=connected or now_ms,
                    to_ms=now_ms,
                    receive_watermark=watermark,
                    reason=reason,
                    occurred_at_ms=now_ms,
                )
                .on_conflict_do_nothing()
            )
        return watermark

    @staticmethod
    def _row_ready(row, *, now_ms, runtime_commit=None):
        return bool(
            row
            and row["connection_state"] == "ready"
            and row["health_reason"] is None
            and row["lease_until_ms"] > now_ms
            and row["persisted_watermark"] == row["applied_watermark"]
            and row["last_successful_at_ms"] is not None
            and now_ms - FEED_LEASE_MS <= row["last_successful_at_ms"] <= now_ms
            and row["connected_at_ms"] is not None
            and row["connected_at_ms"] <= now_ms
            and row["schema_revision"] == CURRENT_SCHEMA_REVISION
            and (runtime_commit is None or row["runtime_commit"] == runtime_commit)
        )

    async def feed_ready(self, scope_key, *, now_ms, runtime_commit=None):
        return self._row_ready(
            await self.get_feed(scope_key), now_ms=now_ms, runtime_commit=runtime_commit
        )

    async def read_readiness(self, scope_key, *, required, now_ms, runtime_commit=None):
        from src.trading_kernel.application.management_health import (
            ManagementFeedReadiness,
        )

        feed = await self.get_feed(scope_key)
        ready = self._row_ready(feed, now_ms=now_ms, runtime_commit=runtime_commit)
        reason = None
        if required and not ready:
            reason = (
                "management_feed_missing"
                if feed is None
                else (
                    "management_receiver_lease_expired"
                    if feed["lease_until_ms"] <= now_ms
                    else "management_runtime_identity_differs"
                    if feed["schema_revision"] != CURRENT_SCHEMA_REVISION
                    or (
                        runtime_commit is not None
                        and feed["runtime_commit"] != runtime_commit
                    )
                    else feed["health_reason"] or "management_receiver_not_ready"
                )
            )
        since = None
        if reason and feed:
            since = await self.current_gap_started_at(scope_key, feed["epoch_id"])
            if reason == "management_receiver_lease_expired":
                since = feed["lease_until_ms"]
        return ManagementFeedReadiness(
            required=required,
            ready=ready,
            connection_state="missing" if feed is None else feed["connection_state"],
            blocker_code=reason,
            blocked_since_ms=since,
            last_successful_at_ms=None
            if feed is None
            else feed["last_successful_at_ms"],
            lease_until_ms=None if feed is None else feed["lease_until_ms"],
            epoch_id=None if feed is None else feed["epoch_id"],
            persisted_watermark=None if feed is None else feed["persisted_watermark"],
            applied_watermark=None if feed is None else feed["applied_watermark"],
        )

    async def stream_events(self, scope_key, start_ms, end_ms):
        rows = (
            (
                await self.c.execute(
                    sa.select(raw_events)
                    .where(
                        raw_events.c.scope_key == scope_key,
                        raw_events.c.received_at_ms >= start_ms,
                        raw_events.c.received_at_ms <= end_ms,
                    )
                    .order_by(
                        raw_events.c.received_at_ms, raw_events.c.receive_sequence
                    )
                    .limit(4097)
                )
            )
            .mappings()
            .all()
        )
        if len(rows) > 4096:
            raise ValueError("durable stream page requires bounded continuation")
        return [dict(r) for r in rows]

    async def continuity_covers(self, scope_key, start_ms, end_ms):
        row = (
            (
                await self.c.execute(
                    sa.select(feeds).where(feeds.c.scope_key == scope_key)
                )
            )
            .mappings()
            .one_or_none()
        )
        if not row or not await self.feed_ready(
            scope_key, now_ms=max(end_ms, row["last_successful_at_ms"] or end_ms)
        ):
            return False
        intervals = []
        if (
            row["connected_at_ms"] is not None
            and row["last_successful_at_ms"] is not None
        ):
            intervals.append((row["connected_at_ms"], row["last_successful_at_ms"]))
        closed = (
            await self.c.execute(
                sa.select(coverage.c.from_ms, coverage.c.to_ms)
                .where(
                    coverage.c.scope_key == scope_key,
                    coverage.c.kind == "epoch_closed",
                    coverage.c.reason.is_(None),
                    coverage.c.to_ms >= start_ms,
                    coverage.c.from_ms <= end_ms,
                )
                .order_by(coverage.c.from_ms)
                .limit(1025)
            )
        ).all()
        if len(closed) > 1024:
            return False
        intervals.extend((r[0], r[1]) for r in closed)
        through = start_ms
        for lower, upper in sorted(intervals):
            if lower > through:
                break
            through = max(through, upper)
            if through >= end_ms:
                return True
        return False
