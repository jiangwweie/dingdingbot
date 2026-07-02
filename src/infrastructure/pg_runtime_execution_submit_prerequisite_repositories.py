"""PG repositories for first-real-submit prerequisite evidence."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.runtime_execution_protection_failure_policy import (
    RuntimeExecutionProtectionFailurePolicy,
)
from src.domain.runtime_execution_submit_idempotency import (
    RuntimeExecutionSubmitIdempotencySnapshot,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedSubmitFactsSnapshot,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGRuntimeExecutionProtectionFailurePolicyORM,
    PGRuntimeExecutionSubmitIdempotencySnapshotORM,
    PGRuntimeExecutionTrustedSubmitFactsSnapshotORM,
)


class PgRuntimeExecutionTrustedSubmitFactsRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        snapshot: RuntimeExecutionTrustedSubmitFactsSnapshot,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(snapshot))
            await session.commit()
        return snapshot

    async def get(
        self,
        trusted_submit_fact_snapshot_id: str,
    ) -> RuntimeExecutionTrustedSubmitFactsSnapshot | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionTrustedSubmitFactsSnapshotORM,
                trusted_submit_fact_snapshot_id,
            )
            if row is None:
                return None
            return RuntimeExecutionTrustedSubmitFactsSnapshot.model_validate(
                dict(row.payload_json or {})
            )

    @staticmethod
    def _to_orm(
        snapshot: RuntimeExecutionTrustedSubmitFactsSnapshot,
    ) -> PGRuntimeExecutionTrustedSubmitFactsSnapshotORM:
        return PGRuntimeExecutionTrustedSubmitFactsSnapshotORM(
            trusted_submit_fact_snapshot_id=(
                snapshot.trusted_submit_fact_snapshot_id
            ),
            execution_intent_id=snapshot.execution_intent_id,
            runtime_instance_id=snapshot.runtime_instance_id,
            order_candidate_id=snapshot.order_candidate_id,
            status=snapshot.status.value,
            symbol=snapshot.symbol,
            side=snapshot.side,
            facts_fresh_enough=snapshot.facts_fresh_enough,
            missing_or_stale_facts_block=snapshot.missing_or_stale_facts_block,
            owner_supplied_allow_facts_rejected=(
                snapshot.owner_supplied_allow_facts_rejected
            ),
            read_only_sources_only=snapshot.read_only_sources_only,
            execution_intent_status_changed=(
                snapshot.execution_intent_status_changed
            ),
            runtime_state_mutated=snapshot.runtime_state_mutated,
            order_created=snapshot.order_created,
            exchange_called=snapshot.exchange_called,
            owner_bounded_execution_called=snapshot.owner_bounded_execution_called,
            order_lifecycle_called=snapshot.order_lifecycle_called,
            withdrawal_instruction_created=snapshot.withdrawal_instruction_created,
            transfer_instruction_created=snapshot.transfer_instruction_created,
            blockers_json=list(snapshot.blockers),
            warnings_json=list(snapshot.warnings),
            payload_json=snapshot.model_dump(mode="json"),
            created_at_ms=snapshot.created_at_ms,
        )


class PgRuntimeExecutionSubmitIdempotencyRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        snapshot: RuntimeExecutionSubmitIdempotencySnapshot,
    ) -> RuntimeExecutionSubmitIdempotencySnapshot:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(snapshot))
            await session.commit()
        return snapshot

    async def get(
        self,
        submit_idempotency_policy_id: str,
    ) -> RuntimeExecutionSubmitIdempotencySnapshot | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionSubmitIdempotencySnapshotORM,
                submit_idempotency_policy_id,
            )
            if row is None:
                return None
            return RuntimeExecutionSubmitIdempotencySnapshot.model_validate(
                dict(row.payload_json or {})
            )

    @staticmethod
    def _to_orm(
        snapshot: RuntimeExecutionSubmitIdempotencySnapshot,
    ) -> PGRuntimeExecutionSubmitIdempotencySnapshotORM:
        return PGRuntimeExecutionSubmitIdempotencySnapshotORM(
            submit_idempotency_policy_id=snapshot.submit_idempotency_policy_id,
            authorization_id=snapshot.authorization_id,
            execution_intent_id=snapshot.execution_intent_id,
            runtime_execution_intent_draft_id=(
                snapshot.runtime_execution_intent_draft_id
            ),
            runtime_instance_id=snapshot.runtime_instance_id,
            source_type=snapshot.source_type,
            source_id=snapshot.source_id,
            status=snapshot.status.value,
            symbol=snapshot.symbol,
            side=snapshot.side,
            stable_submit_key=snapshot.stable_submit_key,
            replay_lock_key=snapshot.replay_lock_key,
            adapter_result_store_implemented=(
                snapshot.adapter_result_store_implemented
            ),
            real_adapter_boundary_implemented=(
                snapshot.real_adapter_boundary_implemented
            ),
            execution_intent_status_changed=(
                snapshot.execution_intent_status_changed
            ),
            runtime_state_mutated=snapshot.runtime_state_mutated,
            order_created=snapshot.order_created,
            exchange_called=snapshot.exchange_called,
            owner_bounded_execution_called=snapshot.owner_bounded_execution_called,
            order_lifecycle_called=snapshot.order_lifecycle_called,
            withdrawal_instruction_created=snapshot.withdrawal_instruction_created,
            transfer_instruction_created=snapshot.transfer_instruction_created,
            blockers_json=list(snapshot.blockers),
            warnings_json=list(snapshot.warnings),
            payload_json=snapshot.model_dump(mode="json"),
            created_at_ms=snapshot.created_at_ms,
        )


class PgRuntimeExecutionProtectionFailurePolicyRepository:
    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()

    async def initialize(self) -> None:
        await init_pg_core_db()

    async def create(
        self,
        policy: RuntimeExecutionProtectionFailurePolicy,
    ) -> RuntimeExecutionProtectionFailurePolicy:
        async with self._session_maker() as session:
            await session.merge(self._to_orm(policy))
            await session.commit()
        return policy

    async def get(
        self,
        policy_id: str,
    ) -> RuntimeExecutionProtectionFailurePolicy | None:
        async with self._session_maker() as session:
            row = await session.get(
                PGRuntimeExecutionProtectionFailurePolicyORM,
                policy_id,
            )
            if row is None:
                return None
            return RuntimeExecutionProtectionFailurePolicy.model_validate(
                dict(row.payload_json or {})
            )

    @staticmethod
    def _to_orm(
        policy: RuntimeExecutionProtectionFailurePolicy,
    ) -> PGRuntimeExecutionProtectionFailurePolicyORM:
        return PGRuntimeExecutionProtectionFailurePolicyORM(
            policy_id=policy.policy_id,
            protection_plan_id=policy.protection_plan_id,
            execution_intent_id=policy.execution_intent_id,
            runtime_instance_id=policy.runtime_instance_id,
            source_type=policy.source_type,
            source_id=policy.source_id,
            status=policy.status.value,
            symbol=policy.symbol,
            side=policy.side,
            block_new_entries_until_resolved=(
                policy.block_new_entries_until_resolved
            ),
            mark_position_unprotected_until_verified=(
                policy.mark_position_unprotected_until_verified
            ),
            require_owner_recovery_review=policy.require_owner_recovery_review,
            require_reduce_only_recovery_mode=(
                policy.require_reduce_only_recovery_mode
            ),
            require_reconciliation_before_retry=(
                policy.require_reconciliation_before_retry
            ),
            consume_attempt_on_any_fill=policy.consume_attempt_on_any_fill,
            hold_or_reconcile_budget_until_position_resolved=(
                policy.hold_or_reconcile_budget_until_position_resolved
            ),
            must_not_mark_unprotected_position_as_protected=(
                policy.must_not_mark_unprotected_position_as_protected
            ),
            order_created=policy.order_created,
            order_lifecycle_called=policy.order_lifecycle_called,
            exchange_called=policy.exchange_called,
            exchange_order_submitted=policy.exchange_order_submitted,
            owner_bounded_execution_called=policy.owner_bounded_execution_called,
            execution_intent_status_changed=(
                policy.execution_intent_status_changed
            ),
            runtime_state_mutated=policy.runtime_state_mutated,
            withdrawal_instruction_created=policy.withdrawal_instruction_created,
            transfer_instruction_created=policy.transfer_instruction_created,
            blockers_json=list(policy.blockers),
            warnings_json=list(policy.warnings),
            payload_json=policy.model_dump(mode="json"),
            created_at_ms=policy.created_at_ms,
        )
