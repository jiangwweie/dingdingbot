"""Short-transaction Owner control and final ENTRY send authorization."""

from __future__ import annotations

from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.domain.directional_risk import (
    ENTRY_SEND_WINDOW_MS,
    RULE_DIGEST,
    RULE_ID,
    RULE_LIMITS,
    SCOPED_EVENTS,
    DirectionalChangeRequest,
    DirectionalControl,
    DirectionalView,
)
from src.trading_kernel.domain.entry_admission_snapshot import canonical_digest
from src.trading_kernel.domain.risk_budget import (
    BUDGET_CONTRACT,
    RiskBudget,
    RiskBudgetChangeRequest,
    RiskBudgetReceipt,
)
from src.trading_kernel.infrastructure.pg_models import (
    directional_risk_admissions,
    directional_risk_controls,
    directional_risk_events,
    directional_risk_rules,
    entry_send_authorizations,
    exchange_commands,
    owner_policy_current,
    owner_policy_events,
    trade_tickets,
)


class PostgresDirectionalRiskRepository:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def lock(self, venue_id: str, account_id: str) -> None:
        key = f"directional-risk:{venue_id}:{account_id}"
        await self._connection.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": key},
        )

    async def initialize(self, *, venue_id: str, account_id: str, now_ms: int) -> None:
        await self._connection.execute(
            pg_insert(directional_risk_controls)
            .values(
                venue_id=venue_id,
                account_id=account_id,
                version=1,
                view="unset",
                rule_id=RULE_ID,
                rule_digest=RULE_DIGEST,
                effective_at_ms=now_ms,
            )
            .on_conflict_do_nothing()
        )
        await self.get(venue_id, account_id)

    async def get(
        self, venue_id: str, account_id: str, *, for_update: bool = False
    ) -> DirectionalControl | None:
        if for_update:
            await self.lock(venue_id, account_id)
        rule = (
            (
                await self._connection.execute(
                    sa.select(directional_risk_rules).where(
                        directional_risk_rules.c.rule_id == RULE_ID
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            rule is None
            or rule["rule_digest"] != RULE_DIGEST
            or rule["limits"] != {k: list(v) for k, v in RULE_LIMITS.items()}
            or rule["event_spec_ids"] != sorted(SCOPED_EVENTS)
            or rule["budget_contract"] != BUDGET_CONTRACT
        ):
            raise ValueError("directional_rule_mismatch")
        row = (
            (
                await self._connection.execute(
                    sa.select(directional_risk_controls).where(
                        directional_risk_controls.c.venue_id == venue_id,
                        directional_risk_controls.c.account_id == account_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else DirectionalControl.model_validate(dict(row))

    async def request_change(
        self, request: DirectionalChangeRequest
    ) -> DirectionalControl:
        current = await self.get(request.venue_id, request.account_id, for_update=True)
        if current is None:
            raise ValueError("directional_control_missing")
        event_id = (
            "directional:"
            + canonical_digest(
                [request.venue_id, request.account_id, request.idempotency_key]
            )[7:]
        )
        fingerprint = canonical_digest(
            request.model_dump(mode="json", exclude={"requested_at_ms"})
        )
        previous = (
            await self._connection.execute(
                sa.select(directional_risk_events.c.payload).where(
                    directional_risk_events.c.event_id == event_id
                )
            )
        ).scalar_one_or_none()
        if previous is not None:
            if previous["fingerprint"] != fingerprint:
                raise ValueError("directional_idempotency_conflict")
            # Return the original mutation result, never apply a stale request again.
            return DirectionalControl.model_validate(previous["result"])
        if current.version != request.expected_version:
            raise ValueError("directional_version_conflict")
        if current.pending_view is not None or current.pending_baseline is not None:
            raise ValueError("directional_transition_pending")
        if request.requested_at_ms < current.effective_at_ms:
            raise ValueError("directional_clock_moved_backwards")
        in_flight = await self.has_in_flight(request.venue_id, request.account_id)
        updated = DirectionalControl(
            venue_id=current.venue_id,
            account_id=current.account_id,
            version=current.version + 1,
            view=current.view if in_flight else DirectionalView(request.view),
            effective_at_ms=current.effective_at_ms
            if in_flight
            else request.requested_at_ms,
            pending_view=DirectionalView(request.view) if in_flight else None,
            pending_request_id=event_id if in_flight else None,
            requested_at_ms=request.requested_at_ms,
        )
        await self._save(updated)
        await self._event(
            event_id,
            updated,
            "requested",
            request.requested_at_ms,
            {
                "request": request.model_dump(mode="json"),
                "fingerprint": fingerprint,
                "result": updated.model_dump(mode="json"),
                "authentication_strength": "totp_step_up",
            },
        )
        return updated

    async def budget_receipt(
        self, venue_id: str, account_id: str, idempotency_key: str
    ) -> RiskBudgetReceipt | None:
        event_id = (
            "risk-budget:"
            + canonical_digest([venue_id, account_id, idempotency_key])[7:]
        )
        for identity in (event_id + ":effective", event_id):
            payload = await self._connection.scalar(
                sa.select(directional_risk_events.c.payload).where(
                    directional_risk_events.c.event_id == identity
                )
            )
            if payload is not None:
                return RiskBudgetReceipt.model_validate(payload["result"])
        return None

    async def request_budget_change(
        self, request: RiskBudgetChangeRequest
    ) -> RiskBudgetReceipt:
        current = await self.get(request.venue_id, request.account_id, for_update=True)
        if current is None:
            raise ValueError("directional_control_missing")
        event_id = (
            "risk-budget:"
            + canonical_digest(
                [request.venue_id, request.account_id, request.idempotency_key]
            )[7:]
        )
        fingerprint = canonical_digest(
            request.model_dump(mode="json", exclude={"requested_at_ms"})
        )
        previous = await self._connection.scalar(
            sa.select(directional_risk_events.c.payload).where(
                directional_risk_events.c.event_id == event_id
            )
        )
        if previous is not None:
            if previous["fingerprint"] != fingerprint:
                raise ValueError("risk_budget_idempotency_conflict")
            receipt = await self.budget_receipt(
                request.venue_id, request.account_id, request.idempotency_key
            )
            assert receipt is not None
            return receipt
        row = (
            (
                await self._connection.execute(
                    sa.select(owner_policy_current)
                    .where(
                        owner_policy_current.c.owner_policy_id
                        == request.owner_policy_id
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one()
        )
        if (
            row["policy_version"] != request.expected_policy_version
            or current.version != request.expected_directional_version
        ):
            raise ValueError("risk_budget_version_conflict")
        if current.pending_view is not None or current.pending_baseline is not None:
            raise ValueError("risk_budget_transition_pending")
        if request.requested_at_ms < max(row["updated_at_ms"], current.effective_at_ms):
            raise ValueError("risk_budget_clock_moved_backwards")
        budget = RiskBudget(baseline=row["max_ticket_stop_risk_fraction"])
        if (
            row["max_gross_stop_risk_fraction"] != budget.gross
            or row["directional_stop_risk_limit_fraction"] != budget.directional
            or row["min_materialization_ratio"] != Decimal(".5")
        ):
            raise ValueError("risk_budget_policy_inconsistent")
        unchanged = budget.baseline == request.baseline
        result = RiskBudgetReceipt(
            request_id=event_id,
            status="unchanged" if unchanged else "pending",
            baseline=str(request.baseline),
            requested_at_ms=request.requested_at_ms,
        )
        await self._event(
            event_id,
            current,
            "budget_requested",
            request.requested_at_ms,
            {
                "fingerprint": fingerprint,
                "request": request.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
                "authentication_strength": "totp_step_up",
            },
        )
        if unchanged:
            return result
        pending = current.model_copy(
            update={
                "version": current.version + 1,
                "pending_baseline": request.baseline,
                "pending_budget_request_id": event_id,
                "pending_policy_version": request.expected_policy_version,
                "requested_at_ms": request.requested_at_ms,
            }
        )
        await self._save(pending)
        if not await self.has_in_flight(request.venue_id, request.account_id):
            return await self._apply_budget(pending, request.requested_at_ms)
        return result

    async def _apply_budget(self, current: DirectionalControl, now_ms: int):
        payload = await self._connection.scalar(
            sa.select(directional_risk_events.c.payload).where(
                directional_risk_events.c.event_id == current.pending_budget_request_id
            )
        )
        if payload is None:
            raise ValueError("risk_budget_request_missing")
        request = RiskBudgetChangeRequest.model_validate(payload["request"])
        row = (
            (
                await self._connection.execute(
                    sa.select(owner_policy_current)
                    .where(
                        owner_policy_current.c.owner_policy_id
                        == request.owner_policy_id
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one()
        )
        if current.pending_baseline is None:
            raise ValueError("risk_budget_pending_missing")
        budget = RiskBudget(baseline=current.pending_baseline)
        version = row["policy_version"] + 1
        effective_at = max(now_ms, row["updated_at_ms"], request.requested_at_ms)
        result = RiskBudgetReceipt(
            request_id=str(current.pending_budget_request_id),
            status="effective",
            baseline=str(budget.baseline),
            policy_version=version,
            effective_at_ms=effective_at,
            requested_at_ms=request.requested_at_ms,
        )
        previous_event = (
            (
                await self._connection.execute(
                    sa.select(owner_policy_events).where(
                        owner_policy_events.c.owner_policy_id
                        == request.owner_policy_id,
                        owner_policy_events.c.policy_version == row["policy_version"],
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        resume_id = None
        resume_version = None
        if previous_event is not None and row["new_entry_submit_enabled"]:
            if previous_event["operation"] == "owner_control_entry_resume":
                resume_id = previous_event["payload"].get("authorization_id")
                resume_version = previous_event["policy_version"]
            elif previous_event["operation"] == "owner_control_risk_budget":
                resume_id = previous_event["payload"].get("resume_authorization_id")
                resume_version = previous_event["payload"].get("resume_policy_version")
        await self._connection.execute(
            sa.insert(owner_policy_events).values(
                owner_policy_event_id=current.pending_budget_request_id,
                owner_policy_id=request.owner_policy_id,
                policy_version=version,
                operation="owner_control_risk_budget",
                payload={
                    "request_id": current.pending_budget_request_id,
                    "source_policy_version": row["policy_version"],
                    "resume_authorization_id": resume_id,
                    "resume_policy_version": resume_version,
                    "baseline": str(budget.baseline),
                    "owner_identity": request.owner_identity,
                    "reason": request.reason,
                    "rule_id": RULE_ID,
                    "rule_digest": RULE_DIGEST,
                },
                created_at_ms=effective_at,
            )
        )
        await self._connection.execute(
            sa.update(owner_policy_current)
            .where(owner_policy_current.c.owner_policy_id == request.owner_policy_id)
            .values(
                policy_version=version,
                max_ticket_stop_risk_fraction=budget.baseline,
                max_gross_stop_risk_fraction=budget.gross,
                directional_stop_risk_limit_fraction=budget.directional,
                updated_at_ms=effective_at,
            )
        )
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "pending_baseline": None,
                "pending_budget_request_id": None,
                "pending_policy_version": None,
                "effective_at_ms": effective_at,
            }
        )
        await self._save(updated)
        await self._event(
            str(current.pending_budget_request_id) + ":effective",
            updated,
            "budget_effective",
            effective_at,
            {"result": result.model_dump(mode="json")},
        )
        return result

    async def request_receipt(
        self, venue_id: str, account_id: str, idempotency_key: str
    ) -> DirectionalControl | None:
        event_id = (
            "directional:"
            + canonical_digest([venue_id, account_id, idempotency_key])[7:]
        )
        payload = await self._connection.scalar(
            sa.select(directional_risk_events.c.payload).where(
                directional_risk_events.c.event_id == event_id
            )
        )
        return (
            None
            if payload is None
            else DirectionalControl.model_validate(payload["result"])
        )

    async def has_in_flight(self, venue_id: str, account_id: str) -> bool:
        return bool(
            await self._connection.scalar(
                sa.select(
                    sa.exists().where(
                        entry_send_authorizations.c.venue_id == venue_id,
                        entry_send_authorizations.c.account_id == account_id,
                        entry_send_authorizations.c.completed_at_ms.is_(None),
                    )
                )
            )
        )

    async def progress(
        self, venue_id: str, account_id: str, now_ms: int
    ) -> DirectionalControl | None:
        current = await self.get(venue_id, account_id, for_update=True)
        if current is None or await self.has_in_flight(venue_id, account_id):
            return current
        if current.pending_baseline is not None:
            await self._apply_budget(current, now_ms)
            return await self.get(venue_id, account_id)
        if current.pending_view is None:
            return current
        updated = DirectionalControl(
            venue_id=venue_id,
            account_id=account_id,
            version=current.version + 1,
            view=current.pending_view,
            effective_at_ms=max(
                now_ms, current.requested_at_ms or current.effective_at_ms
            ),
            requested_at_ms=current.requested_at_ms,
        )
        await self._save(updated)
        await self._event(
            f"{current.pending_request_id}:effective",
            updated,
            "effective",
            now_ms,
            {"result": updated.model_dump(mode="json")},
        )
        return updated

    async def authorize_send(
        self,
        *,
        command_id: str,
        venue_id: str,
        account_id: str,
        worker_id: str,
        now_ms: int,
        deadline_at_ms: int,
        valid_until_ms: int,
        control: DirectionalControl | None,
    ) -> int:
        await self.lock(venue_id, account_id)
        actual = await self.get(venue_id, account_id)
        if actual is None or actual.pending_baseline is not None:
            raise ValueError("risk_budget_transition_pending")
        if control is not None and (
            actual != control or actual.pending_view is not None
        ):
            raise ValueError("directional_authority_changed")
        command = (
            (
                await self._connection.execute(
                    sa.select(exchange_commands)
                    .where(exchange_commands.c.command_id == command_id)
                    .with_for_update()
                )
            )
            .mappings()
            .one()
        )
        ticket = (
            (
                await self._connection.execute(
                    sa.select(
                        trade_tickets.c.venue_id,
                        trade_tickets.c.account_id,
                        trade_tickets.c.event_spec_id,
                        trade_tickets.c.owner_policy_id,
                        trade_tickets.c.owner_policy_version,
                    ).where(trade_tickets.c.ticket_id == command["ticket_id"])
                )
            )
            .mappings()
            .one()
        )
        if (
            command["command_kind"] != "entry"
            or ticket["venue_id"] != venue_id
            or ticket["account_id"] != account_id
            or command["deadline_at_ms"] != deadline_at_ms
        ):
            raise ValueError("entry_send_scope_mismatch")
        policy_version = await self._connection.scalar(
            sa.select(owner_policy_current.c.policy_version).where(
                owner_policy_current.c.owner_policy_id == ticket["owner_policy_id"]
            )
        )
        if policy_version != ticket["owner_policy_version"]:
            raise ValueError("entry_send_policy_changed")
        if ticket["event_spec_id"] in SCOPED_EVENTS and control is None:
            raise ValueError("directional_control_missing")
        if (
            command["status"] != "claimed"
            or command["claim_owner"] != worker_id
            or command["lease_until_ms"] <= now_ms
        ):
            raise ValueError("entry_send_claim_changed")
        if min(deadline_at_ms, valid_until_ms) <= now_ms:
            raise ValueError("entry_send_window_expired")
        await self._connection.execute(
            sa.insert(entry_send_authorizations).values(
                command_id=command_id,
                venue_id=venue_id,
                account_id=account_id,
                worker_id=worker_id,
                authorized_at_ms=now_ms,
                expires_at_ms=min(
                    now_ms + ENTRY_SEND_WINDOW_MS, deadline_at_ms, valid_until_ms
                ),
                control=sa.null()
                if control is None
                else control.model_dump(mode="json"),
            )
        )
        return now_ms

    async def finish_send(self, command_id: str, now_ms: int) -> None:
        # Only the caller that actually completed network I/O can acknowledge here.
        await self._connection.execute(
            sa.update(entry_send_authorizations)
            .where(
                entry_send_authorizations.c.command_id == command_id,
                entry_send_authorizations.c.completed_at_ms.is_(None),
            )
            .values(completed_at_ms=now_ms)
        )

    async def send_expiry(self, command_id: str) -> int | None:
        return await self._connection.scalar(
            sa.select(entry_send_authorizations.c.expires_at_ms).where(
                entry_send_authorizations.c.command_id == command_id
            )
        )

    async def next_pending_budget(self) -> tuple[str, str] | None:
        row = (
            await self._connection.execute(
                sa.select(
                    directional_risk_controls.c.venue_id,
                    directional_risk_controls.c.account_id,
                )
                .where(directional_risk_controls.c.pending_baseline.is_not(None))
                .order_by(directional_risk_controls.c.requested_at_ms)
                .limit(1)
            )
        ).first()
        return None if row is None else (row[0], row[1])

    async def next_resolved_send(self) -> str | None:
        """A bounded cleanup selector for outcomes resolved by another safety path."""
        return await self._connection.scalar(
            sa.select(entry_send_authorizations.c.command_id)
            .join(
                exchange_commands,
                exchange_commands.c.command_id
                == entry_send_authorizations.c.command_id,
            )
            .where(
                entry_send_authorizations.c.completed_at_ms.is_(None),
                exchange_commands.c.status.in_(
                    (
                        "accepted",
                        "rejected",
                        "reconciled_accepted",
                        "reconciled_absent",
                        "superseded",
                    )
                ),
            )
            .order_by(
                entry_send_authorizations.c.authorized_at_ms,
                entry_send_authorizations.c.command_id,
            )
            .limit(1)
        )

    async def recover_resolved_sends(
        self,
        venue_id: str,
        account_id: str,
        *,
        exchange_time_ms: int,
        observed_at_ms: int,
        command_id: str,
    ) -> None:
        resolved = sa.select(exchange_commands.c.command_id).where(
            exchange_commands.c.status.in_(
                (
                    "accepted",
                    "rejected",
                    "reconciled_accepted",
                    "reconciled_absent",
                    "superseded",
                )
            )
        )
        conditions = [
            entry_send_authorizations.c.venue_id == venue_id,
            entry_send_authorizations.c.account_id == account_id,
            entry_send_authorizations.c.command_id.in_(resolved),
            entry_send_authorizations.c.expires_at_ms < exchange_time_ms,
            entry_send_authorizations.c.completed_at_ms.is_(None),
        ]
        conditions.append(entry_send_authorizations.c.command_id == command_id)
        await self._connection.execute(
            sa.update(entry_send_authorizations)
            .where(*conditions)
            .values(completed_at_ms=observed_at_ms)
        )

    async def record_admission(
        self,
        *,
        signal_event_id: str,
        ticket_id: str | None,
        control: DirectionalControl,
        directional_risk: Decimal,
        effective_limit: Decimal,
        wallet_balance: Decimal,
        outcome: str,
        now_ms: int,
    ) -> None:
        await self._connection.execute(
            sa.insert(directional_risk_admissions).values(
                signal_event_id=signal_event_id,
                ticket_id=ticket_id,
                control=control.model_dump(mode="json"),
                directional_risk=directional_risk,
                effective_limit=effective_limit,
                wallet_balance=wallet_balance,
                outcome=outcome,
                observed_at_ms=now_ms,
            )
        )

    async def _save(self, control: DirectionalControl) -> None:
        await self._connection.execute(
            sa.update(directional_risk_controls)
            .where(
                directional_risk_controls.c.venue_id == control.venue_id,
                directional_risk_controls.c.account_id == control.account_id,
            )
            .values(**control.model_dump(mode="python"))
        )

    async def _event(self, event_id, control, kind, now_ms, payload):
        await self._connection.execute(
            sa.insert(directional_risk_events).values(
                event_id=event_id,
                venue_id=control.venue_id,
                account_id=control.account_id,
                event_kind=kind,
                payload=payload,
                occurred_at_ms=now_ms,
            )
        )
