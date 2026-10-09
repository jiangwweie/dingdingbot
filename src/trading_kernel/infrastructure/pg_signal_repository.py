"""PostgreSQL persistence for typed signals and readiness authority."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, cast

import sqlalchemy as sa
from pydantic import JsonValue
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection

from src.trading_kernel.application.ports import (
    ActiveStrategyUniverseMembershipSnapshot,
    ActiveStrategyUniverseSnapshot,
    EventSpecSnapshot,
    InstrumentRulesSnapshot,
    InstrumentSnapshot,
    ObservationScopeClaim,
    ObservationUniverseMembershipSnapshot,
    ReadinessSnapshot,
    RuntimeCapabilitySnapshot,
    RuntimeProfileSnapshot,
    RuntimeScopeSnapshot,
    StrategyGroupSnapshot,
    StrategyVersionSnapshot,
    WarmReadiness,
)
from src.trading_kernel.domain.arbitration import EntryCandidate
from src.trading_kernel.domain.authority_recovery_rebase import (
    AuthorityRecoveryCheckpoint,
    RecoveryBoundExposureEpisodeTransition,
    advance_recovery_bound_exposure_episode,
)
from src.trading_kernel.domain.cross_margin_stress import MaintenanceMarginBracket
from src.trading_kernel.domain.detector import DetectorStatus
from src.trading_kernel.domain.exposure_episode import (
    ComparisonBindingEpisodeCheckpoint,
    ComparisonBindingEpisodeState,
    ComparisonBoundExposureEpisodeTransition,
    ExposureEpisodeState,
    LockedObservationCursor,
    build_episode_domain_key,
)
from src.trading_kernel.domain.generic_selection_spec import generic_selection_spec
from src.trading_kernel.domain.product import (
    InstrumentProductProfile,
    ProductSessionSnapshot,
)
from src.trading_kernel.domain.selection_authority import (
    AuthorityGrantProof,
    AuthorityGrantProofKind,
    AuthorityOutcome,
    ContinuitySourceKind,
    GenericRecoveryAuthority,
    GenericSelectionAuthority,
    SelectionMode,
    SelectionSessionAuthority,
    generic_recovery_entry_rejection,
)
from src.trading_kernel.domain.signal import (
    SignalFactSnapshot,
    StrategySignal,
)
from src.trading_kernel.domain.strategy_registry import strategy_contract_for
from src.trading_kernel.domain.strategy_universe import (
    MAX_MANUAL_UNIVERSE_MEMBERS,
    MAX_UNIVERSE_MEMBERS,
    StrategyUniverseVersion,
)
from src.trading_kernel.infrastructure.pg_models import (
    comparison_binding_current,
    comparison_universe_definitions,
    event_required_facts,
    event_specs,
    exposure_episode_current,
    facts_current,
    instrument_certification_current,
    instrument_product_current,
    instrument_product_profiles,
    instrument_rules_current,
    instruments,
    owner_policy_current,
    owner_policy_events,
    readiness_current,
    runtime_capabilities_current,
    runtime_profiles,
    runtime_scopes_current,
    selection_authority_projection_columns,
    selection_session_authorities,
    signal_events,
    signal_fact_snapshots,
    strategy_entry_control_events,
    strategy_entry_vacuums_current,
    strategy_groups,
    strategy_trigger_suppressions,
    strategy_universe_current,
    strategy_universe_members,
    strategy_universe_versions,
    strategy_versions,
    trade_tickets,
)
from src.trading_kernel.infrastructure.pg_product_current import (
    PostgresProductCurrentRepository,
)
from src.trading_kernel.infrastructure.pg_selection_event_bindings import (
    sor_authority_pair_from_bindings,
)


class PostgresSignalRepository:
    def __init__(self, connection: AsyncConnection) -> None:
        self._connection = connection

    async def add(self, signal: StrategySignal) -> bool:
        result = await self._connection.execute(
            pg_insert(signal_events)
            .values(_signal_values(signal))
            .on_conflict_do_nothing()
        )
        if result.rowcount != 1:
            return False
        await self._connection.execute(
            sa.insert(signal_fact_snapshots),
            [_fact_snapshot_values(signal.signal_event_id, fact) for fact in signal.facts],
        )
        return True

    async def get(self, signal_event_id: str) -> StrategySignal | None:
        result = await self._connection.execute(
            sa.select(signal_events).where(
                signal_events.c.signal_event_id == signal_event_id
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        facts = await self.get_fact_snapshots(signal_event_id)
        return _signal_from_row(row, facts)

    async def get_fact_snapshots(
        self,
        signal_event_id: str,
    ) -> tuple[SignalFactSnapshot, ...]:
        result = await self._connection.execute(
            sa.select(signal_fact_snapshots)
            .where(signal_fact_snapshots.c.signal_event_id == signal_event_id)
            .order_by(signal_fact_snapshots.c.fact_definition_id)
        )
        return tuple(
            SignalFactSnapshot.model_validate(row, extra="ignore")
            for row in result.mappings()
        )

    async def upsert_current_facts(
        self,
        *,
        runtime_scope_id: str,
        facts: tuple[SignalFactSnapshot, ...],
    ) -> tuple[SignalFactSnapshot, ...]:
        persisted: list[SignalFactSnapshot] = []
        for fact in sorted(facts, key=lambda item: item.fact_definition_id):
            result = await self._connection.execute(
                sa.select(facts_current)
                .where(
                    facts_current.c.runtime_scope_id == runtime_scope_id,
                    facts_current.c.fact_definition_id
                    == fact.fact_definition_id,
                )
                .with_for_update()
            )
            row = result.mappings().one_or_none()
            if row is None:
                projection_version = 1
                await self._connection.execute(
                    sa.insert(facts_current).values(
                        fact_current_id=(
                            f"fact-current:{runtime_scope_id}:"
                            f"{fact.fact_definition_id}"
                        ),
                        runtime_scope_id=runtime_scope_id,
                        fact_definition_id=fact.fact_definition_id,
                        value=fact.value,
                        satisfied=fact.satisfied,
                        observed_at_ms=fact.observed_at_ms,
                        valid_until_ms=fact.valid_until_ms,
                        projection_version=projection_version,
                    )
                )
            elif _current_fact_matches(row, fact):
                projection_version = int(row["projection_version"])
            else:
                projection_version = int(row["projection_version"]) + 1
                await self._connection.execute(
                    sa.update(facts_current)
                    .where(
                        facts_current.c.runtime_scope_id == runtime_scope_id,
                        facts_current.c.fact_definition_id
                        == fact.fact_definition_id,
                    )
                    .values(
                        value=fact.value,
                        satisfied=fact.satisfied,
                        observed_at_ms=fact.observed_at_ms,
                        valid_until_ms=fact.valid_until_ms,
                        projection_version=projection_version,
                    )
                )
            persisted.append(
                fact.model_copy(
                    update={"projection_version": projection_version}
                )
            )
        return tuple(persisted)

    async def lock_exposure_episode(
        self,
        episode_domain_key: str,
    ) -> ExposureEpisodeState | None:
        normalized_key = str(episode_domain_key or "").strip()
        if not normalized_key:
            raise ValueError("Episode domain key must be non-blank")
        await self._connection.execute(
            sa.select(
                sa.func.pg_advisory_xact_lock(
                    sa.func.hashtextextended(normalized_key, 0)
                )
            )
        )
        row = (
            await self._connection.execute(
                sa.select(exposure_episode_current)
                .where(
                    exposure_episode_current.c.episode_domain_key
                    == normalized_key
                )
                .with_for_update()
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else ExposureEpisodeState.model_validate(row, extra="ignore")
        )

    async def lock_generic_close_coverage(self, *, event_spec_id: str,
        exchange_instrument_ids: tuple[str, ...], closed_at_ms: int) -> tuple[LockedObservationCursor, ...]:
        contract = strategy_contract_for(event_spec_id)
        spec = generic_selection_spec(contract.strategy_group_id)
        if closed_at_ms <= 0 or closed_at_ms % 3_600_000 != 0:
            raise ValueError("Generic grant coverage requires an hourly close")
        if not 1 <= len(exchange_instrument_ids) <= spec.retain_rank or (
            tuple(sorted(set(exchange_instrument_ids))) != exchange_instrument_ids
            or not set(exchange_instrument_ids).issubset(spec.candidate_ids)):
            raise ValueError("Generic grant coverage members differ from Spec")
        evidence = await self._lock_selection_observation_cursors(event_spec_id=event_spec_id,exchange_instrument_ids=exchange_instrument_ids)
        if any(cursor.last_observed_at_ms is not None and cursor.last_observed_at_ms>=closed_at_ms for cursor in evidence):
            raise RuntimeError("Generic grant close was already consumed")
        return evidence

    async def lock_recovery_close_coverage(self, *, event_spec_id: str, exchange_instrument_ids: tuple[str, ...],
        selection_mode: Literal["dynamic_selection", "static_baseline"], evaluated_at_ms: int,
    ) -> tuple[LockedObservationCursor, ...]:
        contract = strategy_contract_for(event_spec_id)
        spec = generic_selection_spec(contract.strategy_group_id)
        if selection_mode not in {"dynamic_selection","static_baseline"} or evaluated_at_ms<=0:
            raise ValueError("Recovery cursor request mode/time is invalid")
        static = selection_mode=="static_baseline"
        if not 1<=len(exchange_instrument_ids)<=(MAX_MANUAL_UNIVERSE_MEMBERS if static else spec.retain_rank) or (
            tuple(sorted(set(exchange_instrument_ids)))!=exchange_instrument_ids
            or (not static and not set(exchange_instrument_ids).issubset(spec.candidate_ids))):
            raise ValueError("Recovery coverage requires canonical bounded previous membership")
        evidence = await self._lock_selection_observation_cursors(event_spec_id=event_spec_id,exchange_instrument_ids=exchange_instrument_ids)
        if any(cursor.last_observed_at_ms is not None and cursor.last_observed_at_ms>evaluated_at_ms for cursor in evidence):
            raise RuntimeError("Recovery observation cursor is in the future")
        return evidence

    async def _lock_selection_observation_cursors(self, *, event_spec_id: str,
        exchange_instrument_ids: tuple[str, ...]) -> tuple[LockedObservationCursor, ...]:
        contract = strategy_contract_for(event_spec_id)
        evidence = []
        # Same stable per-Episode advisory lock used by formal Observation,
        # including absent rows. Canonical instrument order avoids deadlocks.
        for member in exchange_instrument_ids:
            key = build_episode_domain_key(event_spec_id=event_spec_id,
                exchange_instrument_id=member,position_side=contract.position_side)
            episode = await self.lock_exposure_episode(key)
            checkpoint = await self.get_comparison_episode_checkpoint(key)
            recovery = await self.get_authority_recovery_checkpoint(key)
            times = [x for x in (None if episode is None else episode.last_observed_at_ms,
                None if checkpoint is None else checkpoint.last_observed_at_ms,
                None if recovery is None else recovery.last_observed_close_time_ms) if x is not None]
            last = max(times) if times else None
            evidence.append(LockedObservationCursor(episode_domain_key=key,exchange_instrument_id=member,
                episode_version=0 if episode is None else episode.projection_version,
                comparison_checkpoint_version=0 if checkpoint is None else checkpoint.projection_version,
                authority_recovery_checkpoint_version=0 if recovery is None else recovery.projection_version,
                last_observed_at_ms=last))
        return tuple(evidence)

    async def save_exposure_episode(
        self,
        state: ExposureEpisodeState,
        *,
        expected_version: int,
    ) -> None:
        if expected_version < 0:
            raise ValueError("Episode expected version cannot be negative")
        if state.projection_version != expected_version + 1:
            raise ValueError("Episode projection version is not monotonic")
        values = state.model_dump(mode="python")
        if expected_version == 0:
            result = await self._connection.execute(
                pg_insert(exposure_episode_current)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[
                        exposure_episode_current.c.episode_domain_key
                    ]
                )
            )
        else:
            result = await self._connection.execute(
                sa.update(exposure_episode_current)
                .where(
                    exposure_episode_current.c.episode_domain_key
                    == state.episode_domain_key,
                    exposure_episode_current.c.projection_version
                    == expected_version,
                )
                .values(**values)
            )
        if result.rowcount != 1:
            raise RuntimeError("Exposure Episode authority changed")

    async def advance_recovery_observation(self, *, runtime_scope_id: str, selection_authority_id: str,
        observed_at_ms: int, detector_status: DetectorStatus, occurred_at_ms: int | None,
    ) -> RecoveryBoundExposureEpisodeTransition:
        """Persist an authorized Detector result, Episode and both barriers together."""
        from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
            PostgresInstrumentSelectionRepository,
        )
        from src.trading_kernel.infrastructure.pg_repositories import (
            PostgresEntryAdmissionRepository,
            PostgresOwnerControlRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )

        selection = PostgresInstrumentSelectionRepository(self._connection)
        scope = await self.get_runtime_scope(runtime_scope_id)
        if scope is None or scope.lifecycle_state!="active" or not scope.entry_enabled:
            raise RuntimeError("Recovery Observation active scope changed")
        owner = await PostgresOwnerControlRepository(self._connection).get_strategy_control(scope.strategy_group_id,for_update=True)
        control = await selection.get_selection_control(scope.strategy_group_id,for_update=True)
        if owner is None or owner.entry_state.value!="enabled" or control is None:
            raise RuntimeError("Recovery Observation Owner control blocked")
        vacuum = await selection.get_current_entry_vacuum(strategy_group_id=scope.strategy_group_id,selection_spec_id=control.selection_spec_id,for_update=True)
        current = await selection.get_current_generic_authority(control.selection_spec_id,for_update=True)
        if vacuum is not None or current is None or current.authority.selection_authority_id!=selection_authority_id:
            raise RuntimeError("Recovery Observation current authority changed")
        authority = current.authority
        if isinstance(authority,GenericRecoveryAuthority):
            origin = authority
        elif isinstance(authority,GenericSelectionAuthority) and authority.continued_from_recovery_authority_id is not None:
            loaded_origin = await selection.get_generic_recovery_authority_by_id(authority.continued_from_recovery_authority_id)
            if loaded_origin is None or loaded_origin.event_binding!=authority.event_binding or (
                loaded_origin.comparison_universe_id!=authority.comparison_universe_id
                or loaded_origin.comparison_transition_revision!=authority.comparison_transition_revision):
                raise RuntimeError("Recovery Observation successor origin changed")
            origin = loaded_origin
        else:
            raise RuntimeError("Recovery Observation current authority changed")
        proof = origin.recovery_proof
        now = await selection.read_authority_clock_ms()
        if observed_at_ms != now//3_600_000*3_600_000:
            raise RuntimeError("Recovery Observation must consume the latest close")
        if isinstance(authority,GenericRecoveryAuthority):
            rejection = generic_recovery_entry_rejection(authority=origin,selection_spec_id=control.selection_spec_id,
                selection_epoch_id=control.selection_epoch_id,selection_mode=control.selection_mode.value,
                selection_control_version=control.control_version,owner_control_version=owner.control_version,
                event_spec_id=scope.event_spec_id,position_side=scope.position_side,universe_version_id=scope.universe_version_id,
                exchange_instrument_id=scope.exchange_instrument_id,birth_selection_authority_id=selection_authority_id,
                allow_current_as_birth=False,observed_close_time_ms=observed_at_ms,now_ms=now,selection_control=control)
            if rejection is not None:
                raise RuntimeError(rejection)
        elif (authority.selection_spec_id!=control.selection_spec_id
            or authority.selection_epoch_id!=control.selection_epoch_id
            or authority.selection_control_version!=control.control_version
            or authority.owner_control_version!=owner.control_version
            or authority.event_binding.universe_version_id!=scope.universe_version_id
            or authority.event_binding.event_spec_id!=scope.event_spec_id
            or authority.event_binding.position_side!=scope.position_side
            or authority.membership_freshness is None
            or not authority.membership_freshness.allows_new_entry_at(now)
            or not authority.effective_from_ms<=now<authority.expires_at_ms
            or observed_at_ms<origin.first_eligible_close_time_ms):
            raise RuntimeError("Recovery Observation successor authority changed")
        policy = await PostgresEntryAdmissionRepository(self._connection).get_owner_policy(scope.owner_policy_id)
        if policy is None or not policy.enabled or not policy.new_entry_submit_enabled or policy.scope is None or not policy.scope.authorizes(
            event_spec_id=scope.event_spec_id,runtime_profile_id=scope.runtime_profile_id):
            raise RuntimeError("Recovery Observation Policy blocked")
        if await self.selection_authority_was_interrupted(strategy_group_id=scope.strategy_group_id,
            selection_spec_id=proof.selection_spec_id,owner_policy_id=scope.owner_policy_id,
            after_ms=authority.created_at_ms,through_ms=now):
            raise RuntimeError("Recovery Observation authority interrupted")
        universes = PostgresStrategyUniverseRepository(self._connection)
        actual = await universes.get_current(scope.event_spec_id)
        members = await self.get_observation_universe_members(event_spec_id=scope.event_spec_id,universe_version_id=scope.universe_version_id)
        from src.trading_kernel.domain.selection_authority import (
            selected_member_set_digest,
        )
        if actual is None or members is None or actual.universe_version_id!=scope.universe_version_id or (
            members.lifecycle_state!="active" or selected_member_set_digest(members.exchange_instrument_ids)!=proof.event_binding.member_set_digest):
            raise RuntimeError("Recovery Observation Universe changed")
        comparison = await selection.get_comparison_universe_binding(scope.event_spec_id,for_update=True) if proof.comparison_universe_id else None
        if proof.comparison_universe_id is not None and (comparison is None or comparison.comparison_universe_id!=proof.comparison_universe_id
            or comparison.comparison_transition_revision!=proof.comparison_transition_revision):
            raise RuntimeError("Recovery Observation comparison changed")
        key = build_episode_domain_key(event_spec_id=scope.event_spec_id,exchange_instrument_id=scope.exchange_instrument_id,position_side=scope.position_side)
        episode = await self.lock_exposure_episode(key)
        recovery = await self.get_authority_recovery_checkpoint(key)
        if recovery is None or (recovery.recovery_id,recovery.recovery_revision,recovery.effective_from_ms,recovery.first_eligible_close_time_ms)!=(
            proof.recovery_close_plan.recovery_id,proof.recovery_close_plan.recovery_revision,proof.committed_at_ms,proof.first_eligible_close_time_ms):
            raise RuntimeError("Recovery Observation pending checkpoint changed")
        checkpoint = await self.get_comparison_episode_checkpoint(key)
        transition = advance_recovery_bound_exposure_episode(contract=strategy_contract_for(scope.event_spec_id),
            current_episode=episode,current_recovery=recovery,current_comparison=checkpoint,
            recovery_id=recovery.recovery_id,recovery_revision=recovery.recovery_revision,effective_from_ms=recovery.effective_from_ms,
            first_eligible_close_time_ms=recovery.first_eligible_close_time_ms,detector_status=detector_status,occurred_at_ms=occurred_at_ms,
            observed_at_ms=observed_at_ms,exchange_instrument_id=scope.exchange_instrument_id,selection_mode=proof.selection_mode,
            universe_version_id=scope.universe_version_id,comparison_binding=comparison)
        if transition.recovery_checkpoint==recovery:
            return transition
        async with self._connection.begin_nested():
            if transition.comparison_checkpoint is not None and transition.comparison_checkpoint != checkpoint:
                await self.save_comparison_episode_transition(ComparisonBoundExposureEpisodeTransition(
                    checkpoint=transition.comparison_checkpoint,episode_transition=transition.episode_transition,
                    signal_eligible=transition.signal_eligible,suppression_reason=transition.suppression_reason),
                    event_spec_id=scope.event_spec_id,exchange_instrument_id=scope.exchange_instrument_id,position_side=scope.position_side,
                    expected_episode_version=0 if episode is None else episode.projection_version,
                    expected_checkpoint_version=0 if checkpoint is None else checkpoint.projection_version)
            elif transition.episode_transition is not None:
                await self.save_exposure_episode(transition.episode_transition.current,expected_version=0 if episode is None else episode.projection_version)
            nxt = transition.recovery_checkpoint
            placeholder_values = {}
            if transition.episode_transition is None and episode is not None and episode.state=="authority_rebase_required":
                # This is now a real suppressed Observation, unlike grant-time
                # initialization. Advance its cursor without minting an arm/ID.
                placeholder_values = {"last_observed_at_ms":observed_at_ms,"projection_version":episode.projection_version+1}
            changed = await self._connection.execute(sa.update(exposure_episode_current).where(
                exposure_episode_current.c.episode_domain_key==key,
                exposure_episode_current.c.authority_recovery_checkpoint_version==recovery.projection_version,
                exposure_episode_current.c.authority_recovery_id==recovery.recovery_id,
            ).values(**placeholder_values,authority_recovery_armed_at_ms=nxt.armed_at_close_time_ms,authority_recovery_last_observed_at_ms=nxt.last_observed_close_time_ms,
                authority_recovery_last_detector_status=None if nxt.last_detector_status is None else nxt.last_detector_status.value,
                authority_recovery_checkpoint_version=nxt.projection_version))
            if changed.rowcount!=1:
                raise RuntimeError("Recovery Observation checkpoint CAS changed")
            committed_at = await selection.read_authority_clock_ms()
            if proof.selection_mode!="static_baseline" and committed_at>=authority.expires_at_ms:
                raise RuntimeError("Recovery Observation authority expired during commit")
            if committed_at<now or observed_at_ms!=committed_at//3_600_000*3_600_000:
                raise RuntimeError("Recovery Observation latest close changed during commit")
        return transition

    async def advance_static_recovery_observation(self, *, runtime_scope_id: str, observed_at_ms: int,
        detector_status: DetectorStatus, occurred_at_ms: int | None,
    ) -> RecoveryBoundExposureEpisodeTransition:
        from src.trading_kernel.infrastructure.pg_instrument_selection_repository import (
            PostgresInstrumentSelectionRepository,
        )
        from src.trading_kernel.infrastructure.pg_repositories import (
            PostgresOwnerControlRepository,
        )
        from src.trading_kernel.infrastructure.pg_universe_repository import (
            PostgresStrategyUniverseRepository,
        )
        scope = await self.get_runtime_scope(runtime_scope_id)
        if scope is None or scope.lifecycle_state!="active":
            raise RuntimeError("Static recovery Observation scope changed")
        selection = PostgresInstrumentSelectionRepository(self._connection)
        proof = await selection.get_generic_static_activation_proof_for_universe(scope.universe_version_id)
        if proof is None or not proof.episode_rebase_required:
            raise RuntimeError("Static recovery Observation proof missing")
        now = await selection.read_authority_clock_ms()
        owner = await PostgresOwnerControlRepository(self._connection).get_strategy_control(scope.strategy_group_id,for_update=True)
        control = await selection.get_selection_control(scope.strategy_group_id,for_update=True)
        actual = await PostgresStrategyUniverseRepository(self._connection).get_current(scope.event_spec_id)
        policy = (await self._connection.execute(sa.select(owner_policy_current).where(
            owner_policy_current.c.owner_policy_id==scope.owner_policy_id))).mappings().one_or_none()
        if owner is None or owner.entry_state.value!="enabled" or control is None or (
            not proof.permits_static_control(control)
            or actual is None or actual.universe_version_id!=scope.universe_version_id
            or policy is None or not policy["enabled"] or not policy["new_entry_submit_enabled"]
            or observed_at_ms<proof.first_eligible_close_time_ms or observed_at_ms!=now//3_600_000*3_600_000):
            raise RuntimeError("Static recovery Observation authority changed")
        key = build_episode_domain_key(event_spec_id=scope.event_spec_id,exchange_instrument_id=scope.exchange_instrument_id,position_side=scope.position_side)
        episode = await self.lock_exposure_episode(key)
        recovery = await self.get_authority_recovery_checkpoint(key)
        comparison = await selection.get_comparison_universe_binding(scope.event_spec_id,for_update=True)
        checkpoint = await self.get_comparison_episode_checkpoint(key)
        transition = advance_recovery_bound_exposure_episode(contract=strategy_contract_for(scope.event_spec_id),
            current_episode=episode,current_recovery=recovery,current_comparison=checkpoint,recovery_id=proof.recovery_id,
            recovery_revision=proof.result_selection_control_version,effective_from_ms=proof.prepared_at_ms,
            first_eligible_close_time_ms=proof.first_eligible_close_time_ms,detector_status=detector_status,occurred_at_ms=occurred_at_ms,
            observed_at_ms=observed_at_ms,exchange_instrument_id=scope.exchange_instrument_id,selection_mode="static_baseline",
            universe_version_id=scope.universe_version_id,comparison_binding=comparison)
        if recovery is None:
            raise RuntimeError("Static recovery checkpoint missing")
        if transition.recovery_checkpoint==recovery:
            return transition
        async with self._connection.begin_nested():
            if transition.comparison_checkpoint is not None and transition.comparison_checkpoint!=checkpoint:
                await self.save_comparison_episode_transition(ComparisonBoundExposureEpisodeTransition(
                    checkpoint=transition.comparison_checkpoint,episode_transition=transition.episode_transition,
                    signal_eligible=transition.signal_eligible,suppression_reason=transition.suppression_reason),
                    event_spec_id=scope.event_spec_id,exchange_instrument_id=scope.exchange_instrument_id,position_side=scope.position_side,
                    expected_episode_version=0 if episode is None else episode.projection_version,
                    expected_checkpoint_version=0 if checkpoint is None else checkpoint.projection_version)
            elif transition.episode_transition is not None:
                await self.save_exposure_episode(transition.episode_transition.current,expected_version=0 if episode is None else episode.projection_version)
            nxt = transition.recovery_checkpoint
            extra = {"last_observed_at_ms":observed_at_ms,"projection_version":episode.projection_version+1} if (
                transition.episode_transition is None and episode is not None and episode.state=="authority_rebase_required") else {}
            changed = await self._connection.execute(sa.update(exposure_episode_current).where(
                exposure_episode_current.c.episode_domain_key==key,
                exposure_episode_current.c.authority_recovery_checkpoint_version==recovery.projection_version,
                exposure_episode_current.c.authority_recovery_id==proof.recovery_id).values(**extra,
                    authority_recovery_armed_at_ms=nxt.armed_at_close_time_ms,authority_recovery_last_observed_at_ms=nxt.last_observed_close_time_ms,
                    authority_recovery_last_detector_status=None if nxt.last_detector_status is None else nxt.last_detector_status.value,
                    authority_recovery_checkpoint_version=nxt.projection_version))
            if changed.rowcount!=1:
                raise RuntimeError("Static recovery checkpoint CAS changed")
            ended = await selection.read_authority_clock_ms()
            if ended<now or observed_at_ms!=ended//3_600_000*3_600_000:
                raise RuntimeError("Static recovery latest close changed")
        return transition

    async def get_authority_recovery_checkpoint(self, episode_domain_key: str) -> AuthorityRecoveryCheckpoint | None:
        row = (await self._connection.execute(sa.select(exposure_episode_current).where(
            exposure_episode_current.c.episode_domain_key == episode_domain_key))).mappings().one_or_none()
        if row is None or row["authority_recovery_checkpoint_version"] is None:
            return None
        return AuthorityRecoveryCheckpoint(episode_domain_key=episode_domain_key,
            recovery_id=row["authority_recovery_id"],recovery_revision=row["authority_recovery_revision"],
            effective_from_ms=row["authority_recovery_effective_from_ms"],
            first_eligible_close_time_ms=row["authority_recovery_first_eligible_close_time_ms"],
            state="REBASE_REQUIRED" if row["authority_recovery_armed_at_ms"] is None else "ARMED",
            armed_at_close_time_ms=row["authority_recovery_armed_at_ms"],
            last_observed_close_time_ms=row["authority_recovery_last_observed_at_ms"],
            last_detector_status=row["authority_recovery_last_detector_status"],projection_version=row["authority_recovery_checkpoint_version"])

    async def get_comparison_episode_checkpoint(self, episode_domain_key: str) -> ComparisonBindingEpisodeCheckpoint | None:
        row = (await self._connection.execute(sa.select(exposure_episode_current).where(
            exposure_episode_current.c.episode_domain_key == episode_domain_key,
        ))).mappings().one_or_none()
        if row is None or row["comparison_checkpoint_version"] is None:
            return None
        return ComparisonBindingEpisodeCheckpoint(
            episode_domain_key=episode_domain_key,
            comparison_binding_digest=row["comparison_binding_digest"],
            comparison_transition_revision=row["comparison_transition_revision"],
            state=ComparisonBindingEpisodeState.REBASE_REQUIRED if row["comparison_armed_at_ms"] is None else ComparisonBindingEpisodeState.ARMED_UNDER_BINDING,
            armed_at_ms=row["comparison_armed_at_ms"], last_observed_at_ms=row["comparison_last_observed_at_ms"],
            last_detector_status=row["comparison_last_detector_status"], projection_version=row["comparison_checkpoint_version"],
        )

    async def save_comparison_episode_transition(
        self, transition: ComparisonBoundExposureEpisodeTransition, *,
        event_spec_id: str, exchange_instrument_id: str, position_side: Literal["long", "short"],
        expected_episode_version: int, expected_checkpoint_version: int,
    ) -> None:
        checkpoint = transition.checkpoint
        key = build_episode_domain_key(event_spec_id=event_spec_id,
            exchange_instrument_id=exchange_instrument_id, position_side=position_side)
        if key != checkpoint.episode_domain_key:
            raise ValueError("comparison checkpoint domain identity differs")
        binding = (await self._connection.execute(sa.select(comparison_binding_current,
            comparison_universe_definitions.c.member_set_digest).join(comparison_universe_definitions,
                comparison_universe_definitions.c.comparison_universe_id == comparison_binding_current.c.comparison_universe_id,
            ).where(comparison_binding_current.c.event_spec_id == event_spec_id)
            .with_for_update(of=comparison_binding_current))).mappings().one_or_none()
        if binding is None or binding["comparison_transition_revision"] != checkpoint.comparison_transition_revision or binding["member_set_digest"] != checkpoint.comparison_binding_digest:
            raise RuntimeError("comparison binding authority changed")
        current = await self.lock_exposure_episode(key)
        previous = await self.get_comparison_episode_checkpoint(key)
        if (0 if current is None else current.projection_version) != expected_episode_version or (
            0 if previous is None else previous.projection_version) != expected_checkpoint_version:
            raise RuntimeError("comparison Episode version changed")
        proposed = None if transition.episode_transition is None else transition.episode_transition.current
        if checkpoint == previous:
            if proposed is not None and proposed != current:
                raise RuntimeError("comparison replay Episode differs")
            return
        if checkpoint.projection_version != expected_checkpoint_version + 1:
            raise ValueError("comparison checkpoint version is not monotonic")
        if previous is not None and checkpoint.last_observed_at_ms <= previous.last_observed_at_ms:
            raise ValueError("comparison checkpoint close is not monotonic")
        if proposed is not None:
            if proposed.episode_domain_key != key or proposed.projection_version != expected_episode_version + 1:
                raise ValueError("comparison Episode transition identity/version differs")
            state = proposed
        elif current is not None:
            state = current
        else:
            state = ExposureEpisodeState(episode_domain_key=key, event_spec_id=event_spec_id,
                exchange_instrument_id=exchange_instrument_id, position_side=position_side,
                state="comparison_rebase_required", exposure_episode_id=None, triggered_at_ms=None,
                rearmed_at_ms=None, last_observed_at_ms=checkpoint.last_observed_at_ms, projection_version=1)
        values = {**state.model_dump(mode="python"),
            "comparison_binding_digest": checkpoint.comparison_binding_digest,
            "comparison_transition_revision": checkpoint.comparison_transition_revision,
            "comparison_armed_at_ms": checkpoint.armed_at_ms,
            "comparison_last_observed_at_ms": checkpoint.last_observed_at_ms,
            "comparison_last_detector_status": checkpoint.last_detector_status.value,
            "comparison_checkpoint_version": checkpoint.projection_version}
        if current is None:
            result = await self._connection.execute(pg_insert(exposure_episode_current).values(**values)
                .on_conflict_do_nothing(index_elements=[exposure_episode_current.c.episode_domain_key]))
        else:
            result = await self._connection.execute(sa.update(exposure_episode_current).where(
                exposure_episode_current.c.episode_domain_key == key,
                exposure_episode_current.c.projection_version == expected_episode_version,
                sa.func.coalesce(exposure_episode_current.c.comparison_checkpoint_version, 0) == expected_checkpoint_version,
            ).values(**values))
        if result.rowcount != 1:
            raise RuntimeError("comparison Episode authority changed")

    async def get_next_ready(self, *, now_ms: int) -> StrategySignal | None:
        return await self._get_next_candidate_ready(
            expiry_predicate=signal_events.c.expires_at_ms > now_ms
        )

    async def get_next_stale_ready(self, *, now_ms: int) -> StrategySignal | None:
        return await self._get_next_candidate_ready(
            expiry_predicate=signal_events.c.expires_at_ms <= now_ms
        )

    async def list_ready_candidates(
        self,
        *,
        now_ms: int,
        limit: int,
    ) -> tuple[EntryCandidate, ...]:
        if limit <= 0 or limit > 64:
            raise ValueError("ready candidate limit must be between 1 and 64")
        already_ticketed = sa.exists(
            sa.select(trade_tickets.c.ticket_id).where(
                trade_tickets.c.signal_event_id == signal_events.c.signal_event_id
            )
        )
        result = await self._connection.execute(
            sa.select(
                signal_events,
                owner_policy_current.c.priority_rank.label("owner_priority"),
            )
            .join(
                readiness_current,
                readiness_current.c.signal_event_id
                == signal_events.c.signal_event_id,
            )
            .join(
                runtime_scopes_current,
                runtime_scopes_current.c.runtime_scope_id
                == signal_events.c.runtime_scope_id,
            )
            .join(
                owner_policy_current,
                owner_policy_current.c.owner_policy_id
                == runtime_scopes_current.c.owner_policy_id,
            )
            .join(
                instrument_certification_current,
                sa.and_(
                    instrument_certification_current.c.runtime_profile_id
                    == runtime_scopes_current.c.runtime_profile_id,
                    instrument_certification_current.c.exchange_instrument_id
                    == signal_events.c.exchange_instrument_id,
                ),
            )
            .join(
                strategy_universe_current,
                sa.and_(
                    strategy_universe_current.c.event_spec_id
                    == signal_events.c.event_spec_id,
                    strategy_universe_current.c.universe_version_id
                    == signal_events.c.universe_version_id,
                    strategy_universe_current.c.semantic_digest
                    == signal_events.c.universe_semantic_digest,
                ),
            )
            .join(
                strategy_universe_members,
                sa.and_(
                    strategy_universe_members.c.universe_version_id
                    == signal_events.c.universe_version_id,
                    strategy_universe_members.c.exchange_instrument_id
                    == signal_events.c.exchange_instrument_id,
                ),
            )
            .where(
                readiness_current.c.readiness_state == "candidate_ready",
                signal_events.c.expires_at_ms > now_ms,
                runtime_scopes_current.c.entry_enabled.is_(True),
                runtime_scopes_current.c.lifecycle_state == "active",
                runtime_scopes_current.c.scope_version
                == signal_events.c.runtime_scope_version,
                runtime_scopes_current.c.universe_version_id
                == signal_events.c.universe_version_id,
                runtime_scopes_current.c.universe_semantic_digest
                == signal_events.c.universe_semantic_digest,
                owner_policy_current.c.enabled.is_(True),
                owner_policy_current.c.new_entry_submit_enabled.is_(True),
                instrument_certification_current.c.status == "eligible",
                instrument_certification_current.c.blocker_code.is_(None),
                instrument_certification_current.c.valid_until_ms > now_ms,
                ~already_ticketed,
            )
            .order_by(
                owner_policy_current.c.priority_rank,
                signal_events.c.occurred_at_ms,
                signal_events.c.observed_at_ms,
                signal_events.c.signal_event_id,
            )
            .limit(limit)
        )
        candidates: list[EntryCandidate] = []
        for row in result.mappings():
            signal_event_id = str(row["signal_event_id"])
            facts = await self.get_fact_snapshots(signal_event_id)
            candidates.append(
                EntryCandidate(
                    signal=_signal_from_row(row, facts),
                    owner_policy_priority=int(row["owner_priority"]),
                )
            )
        return tuple(candidates)

    async def claim_next_observation_scope(
        self,
        *,
        worker_id: str,
        now_ms: int,
        lease_until_ms: int,
    ) -> ObservationScopeClaim | None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise ValueError("observation worker identity must be non-blank")
        if now_ms <= 0 or lease_until_ms <= now_ms:
            raise ValueError("observation lease must end after its claim time")
        result = await self._connection.execute(
            sa.select(
                runtime_scopes_current.c.runtime_scope_id,
                event_specs.c.timeframe,
            )
            .join(
                event_specs,
                event_specs.c.event_spec_id
                == runtime_scopes_current.c.event_spec_id,
            )
            .where(
                runtime_scopes_current.c.observation_enabled.is_(True),
                runtime_scopes_current.c.lifecycle_state.in_(
                    ("warming", "active")
                ),
                event_specs.c.status == "active",
                sa.or_(
                    runtime_scopes_current.c.next_observation_due_at_ms.is_(None),
                    runtime_scopes_current.c.next_observation_due_at_ms <= now_ms,
                ),
                sa.or_(
                    runtime_scopes_current.c.lease_expires_at_ms.is_(None),
                    runtime_scopes_current.c.lease_expires_at_ms <= now_ms,
                ),
            )
            .order_by(
                sa.func.coalesce(
                    runtime_scopes_current.c.next_observation_due_at_ms,
                    0,
                ),
                runtime_scopes_current.c.runtime_scope_id,
            )
            .limit(1)
            .with_for_update(of=runtime_scopes_current, skip_locked=True)
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        runtime_scope_id = str(row["runtime_scope_id"])
        timeframe = cast(Literal["15m", "1h"], str(row["timeframe"]))
        interval_ms = 900_000 if timeframe == "15m" else 3_600_000
        trigger_candle_close_time_ms = now_ms - (now_ms % interval_ms)
        generation = (
            await self._connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id
                )
                .values(
                    lease_owner=normalized_worker_id,
                    lease_expires_at_ms=lease_until_ms,
                    observation_generation=(
                        runtime_scopes_current.c.observation_generation + 1
                    ),
                )
                .returning(
                    runtime_scopes_current.c.observation_generation
                )
            )
        ).scalar_one()
        return ObservationScopeClaim(
            runtime_scope_id=runtime_scope_id,
            timeframe=timeframe,
            trigger_candle_close_time_ms=trigger_candle_close_time_ms,
            observation_generation=int(generation),
        )

    async def claim_observation_generation(
        self,
        runtime_scope_id: str,
    ) -> RuntimeScopeSnapshot | None:
        row = (
            await self._connection.execute(
                sa.update(runtime_scopes_current)
                .where(
                    runtime_scopes_current.c.runtime_scope_id
                    == runtime_scope_id
                )
                .values(
                    observation_generation=(
                        runtime_scopes_current.c.observation_generation + 1
                    )
                )
                .returning(runtime_scopes_current)
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeScopeSnapshot.model_validate(row, extra="ignore")
        )

    async def schedule_observation_scope(
        self,
        *,
        runtime_scope_id: str,
        worker_id: str,
        observation_generation: int,
        due_at_ms: int,
    ) -> None:
        if due_at_ms <= 0:
            raise ValueError("observation due time must be positive")
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id,
                runtime_scopes_current.c.lease_owner == worker_id,
                runtime_scopes_current.c.observation_generation
                == observation_generation,
            )
            .values(
                next_observation_due_at_ms=due_at_ms,
                lease_owner=None,
                lease_expires_at_ms=None,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("observation scope lease is not owned by worker")

    async def _get_next_candidate_ready(
        self,
        *,
        expiry_predicate: sa.ColumnElement[bool],
    ) -> StrategySignal | None:
        already_ticketed = sa.exists(
            sa.select(trade_tickets.c.ticket_id).where(
                trade_tickets.c.signal_event_id == signal_events.c.signal_event_id
            )
        )
        statement = (
            sa.select(signal_events)
            .join(
                readiness_current,
                readiness_current.c.signal_event_id
                == signal_events.c.signal_event_id,
            )
            .where(
                readiness_current.c.readiness_state == "candidate_ready",
                expiry_predicate,
                ~already_ticketed,
            )
            .order_by(
                signal_events.c.occurred_at_ms,
                signal_events.c.signal_event_id,
            )
            .limit(1)
            .with_for_update(of=readiness_current, skip_locked=True)
        )
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        signal_event_id = str(row["signal_event_id"])
        facts = await self.get_fact_snapshots(signal_event_id)
        return _signal_from_row(row, facts)

    async def get_readiness(
        self,
        runtime_scope_id: str,
    ) -> ReadinessSnapshot | None:
        result = await self._connection.execute(
            sa.select(readiness_current).where(
                readiness_current.c.runtime_scope_id == runtime_scope_id
            )
        )
        row = result.mappings().one_or_none()
        return None if row is None else ReadinessSnapshot.model_validate(row)

    async def save_readiness(
        self,
        *,
        runtime_scope_id: str,
        readiness_state: str,
        first_blocker: str | None,
        signal_event_id: str | None,
        fact_summary: dict[str, JsonValue],
        updated_at_ms: int,
    ) -> ReadinessSnapshot:
        await self._connection.execute(
            pg_insert(readiness_current)
            .values(
                runtime_scope_id=runtime_scope_id,
                readiness_state=readiness_state,
                first_blocker=first_blocker,
                signal_event_id=signal_event_id,
                fact_summary=fact_summary,
                updated_at_ms=updated_at_ms,
                projection_version=1,
            )
            .on_conflict_do_update(
                index_elements=[readiness_current.c.runtime_scope_id],
                set_={
                    "readiness_state": readiness_state,
                    "first_blocker": first_blocker,
                    "signal_event_id": signal_event_id,
                    "fact_summary": fact_summary,
                    "updated_at_ms": updated_at_ms,
                    "projection_version": (
                        readiness_current.c.projection_version + 1
                    ),
                },
            )
        )
        persisted = await self.get_readiness(runtime_scope_id)
        if persisted is None:
            raise RuntimeError("readiness upsert did not persist current state")
        return persisted

    async def save_warm_readiness(
        self,
        readiness: WarmReadiness,
    ) -> None:
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id
                == readiness.runtime_scope_id,
                runtime_scopes_current.c.scope_version
                == readiness.scope_version,
                runtime_scopes_current.c.observation_generation
                == readiness.observation_generation,
                runtime_scopes_current.c.event_spec_id
                == readiness.event_spec_id,
                runtime_scopes_current.c.exchange_instrument_id
                == readiness.exchange_instrument_id,
                runtime_scopes_current.c.universe_version_id
                == readiness.universe_version_id,
                runtime_scopes_current.c.universe_semantic_digest
                == readiness.universe_semantic_digest,
                runtime_scopes_current.c.lifecycle_state == "warming",
                runtime_scopes_current.c.observation_enabled.is_(True),
                runtime_scopes_current.c.entry_enabled.is_(False),
                runtime_scopes_current.c.updated_at_ms
                <= readiness.warm_completed_at_ms,
            )
            .values(
                warm_closed_bar_time_ms=readiness.warm_closed_bar_time_ms,
                warm_completed_at_ms=readiness.warm_completed_at_ms,
                warm_readiness_digest=readiness.readiness_digest,
                warm_valid_until_ms=readiness.warm_valid_until_ms,
                updated_at_ms=readiness.warm_completed_at_ms,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("warm readiness authority changed")
        await self.save_readiness(
            runtime_scope_id=readiness.runtime_scope_id,
            readiness_state="warm_ready",
            first_blocker=None,
            signal_event_id=None,
            fact_summary={
                "fact_digest": readiness.fact_digest,
                "universe_version_id": readiness.universe_version_id,
                "universe_semantic_digest": (
                    readiness.universe_semantic_digest
                ),
                "warm_readiness_digest": readiness.readiness_digest,
                "warm_closed_bar_time_ms": readiness.warm_closed_bar_time_ms,
                "warm_completed_at_ms": readiness.warm_completed_at_ms,
                "warm_valid_until_ms": readiness.warm_valid_until_ms,
            },
            updated_at_ms=readiness.warm_completed_at_ms,
        )

    async def clear_warm_readiness(
        self,
        *,
        runtime_scope_id: str,
        scope_version: int,
        observation_generation: int,
        event_spec_id: str,
        exchange_instrument_id: str,
        universe_version_id: str,
        universe_semantic_digest: str,
        blocker: str,
        updated_at_ms: int,
    ) -> None:
        result = await self._connection.execute(
            sa.update(runtime_scopes_current)
            .where(
                runtime_scopes_current.c.runtime_scope_id == runtime_scope_id,
                runtime_scopes_current.c.scope_version == scope_version,
                runtime_scopes_current.c.observation_generation
                == observation_generation,
                runtime_scopes_current.c.event_spec_id == event_spec_id,
                runtime_scopes_current.c.exchange_instrument_id
                == exchange_instrument_id,
                runtime_scopes_current.c.universe_version_id
                == universe_version_id,
                runtime_scopes_current.c.universe_semantic_digest
                == universe_semantic_digest,
                runtime_scopes_current.c.lifecycle_state == "warming",
                runtime_scopes_current.c.updated_at_ms <= updated_at_ms,
            )
            .values(
                warm_closed_bar_time_ms=None,
                warm_completed_at_ms=None,
                warm_readiness_digest=None,
                warm_valid_until_ms=None,
                updated_at_ms=updated_at_ms,
            )
        )
        if result.rowcount != 1:
            raise RuntimeError("warm readiness authority changed")
        await self.save_readiness(
            runtime_scope_id=runtime_scope_id,
            readiness_state="blocked",
            first_blocker=blocker,
            signal_event_id=None,
            fact_summary={
                "universe_version_id": universe_version_id,
                "universe_semantic_digest": universe_semantic_digest,
            },
            updated_at_ms=updated_at_ms,
        )

    async def get_strategy_group(
        self,
        strategy_group_id: str,
    ) -> StrategyGroupSnapshot | None:
        result = await self._connection.execute(
            sa.select(strategy_groups).where(
                strategy_groups.c.strategy_group_id == strategy_group_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else StrategyGroupSnapshot.model_validate(row, extra="ignore")
        )

    async def get_strategy_version(
        self,
        strategy_version_id: str,
    ) -> StrategyVersionSnapshot | None:
        result = await self._connection.execute(
            sa.select(strategy_versions).where(
                strategy_versions.c.strategy_version_id == strategy_version_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else StrategyVersionSnapshot.model_validate(row, extra="ignore")
        )

    async def get_event_spec(
        self,
        event_spec_id: str,
    ) -> EventSpecSnapshot | None:
        result = await self._connection.execute(
            sa.select(event_specs).where(event_specs.c.event_spec_id == event_spec_id)
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else EventSpecSnapshot.model_validate(row, extra="ignore")
        )

    async def get_runtime_scope(
        self,
        runtime_scope_id: str,
        *,
        for_update: bool = False,
    ) -> RuntimeScopeSnapshot | None:
        statement = sa.select(runtime_scopes_current).where(
            runtime_scopes_current.c.runtime_scope_id == runtime_scope_id
        )
        if for_update:
            statement = statement.with_for_update(of=runtime_scopes_current)
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeScopeSnapshot.model_validate(row, extra="ignore")
        )

    async def get_active_universe_member(
        self,
        *,
        event_spec_id: str,
        exchange_instrument_id: str,
        for_update: bool = False,
    ) -> ActiveStrategyUniverseSnapshot | None:
        statement = (
            sa.select(
                strategy_universe_current.c.event_spec_id,
                strategy_universe_current.c.universe_version_id,
                strategy_universe_current.c.semantic_digest,
                strategy_universe_members.c.exchange_instrument_id,
            )
            .join(
                strategy_universe_members,
                strategy_universe_members.c.universe_version_id
                == strategy_universe_current.c.universe_version_id,
            )
            .join(
                instruments,
                instruments.c.exchange_instrument_id
                == strategy_universe_members.c.exchange_instrument_id,
            )
            .where(
                strategy_universe_current.c.event_spec_id == event_spec_id,
                strategy_universe_current.c.lifecycle_state == "active",
                strategy_universe_members.c.exchange_instrument_id
                == exchange_instrument_id,
                instruments.c.status == "active",
            )
        )
        if for_update:
            statement = statement.with_for_update(
                of=(
                    strategy_universe_current,
                    strategy_universe_members,
                    instruments,
                )
            )
        result = await self._connection.execute(statement)
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else ActiveStrategyUniverseSnapshot.model_validate(row)
        )

    async def get_active_universe_members(
        self,
        *,
        event_spec_id: str,
    ) -> ActiveStrategyUniverseMembershipSnapshot | None:
        result = await self._connection.execute(
            sa.select(
                strategy_universe_current.c.event_spec_id,
                strategy_universe_current.c.universe_version_id,
                strategy_universe_current.c.semantic_digest,
                strategy_universe_members.c.exchange_instrument_id,
            )
            .join(
                strategy_universe_members,
                strategy_universe_members.c.universe_version_id
                == strategy_universe_current.c.universe_version_id,
            )
            .where(
                strategy_universe_current.c.event_spec_id == event_spec_id,
                strategy_universe_current.c.lifecycle_state == "active",
            )
            .order_by(strategy_universe_members.c.exchange_instrument_id)
        )
        rows = result.mappings().all()
        if not rows:
            return None
        first = rows[0]
        return ActiveStrategyUniverseMembershipSnapshot(
            event_spec_id=str(first["event_spec_id"]),
            universe_version_id=str(first["universe_version_id"]),
            semantic_digest=str(first["semantic_digest"]),
            exchange_instrument_ids=tuple(
                str(row["exchange_instrument_id"]) for row in rows
            ),
        )

    async def get_observation_universe_members(
        self,
        *,
        event_spec_id: str,
        universe_version_id: str,
    ) -> ObservationUniverseMembershipSnapshot | None:
        result = await self._connection.execute(
            sa.select(
                strategy_universe_versions.c.event_spec_id,
                strategy_universe_versions.c.universe_version_id,
                strategy_universe_versions.c.strategy_group_id,
                strategy_universe_versions.c.universe_version,
                strategy_universe_versions.c.semantic_digest,
                strategy_universe_versions.c.lifecycle_state,
                strategy_universe_versions.c.installed_at_ms,
                strategy_universe_versions.c.source_kind,
                strategy_universe_members.c.exchange_instrument_id,
            )
            .join(
                strategy_universe_members,
                strategy_universe_members.c.universe_version_id
                == strategy_universe_versions.c.universe_version_id,
            )
            .outerjoin(
                strategy_universe_current,
                sa.and_(
                    strategy_universe_current.c.event_spec_id
                    == strategy_universe_versions.c.event_spec_id,
                    strategy_universe_current.c.universe_version_id
                    == strategy_universe_versions.c.universe_version_id,
                    strategy_universe_current.c.semantic_digest
                    == strategy_universe_versions.c.semantic_digest,
                    strategy_universe_current.c.lifecycle_state == "active",
                ),
            )
            .where(
                strategy_universe_versions.c.event_spec_id == event_spec_id,
                strategy_universe_versions.c.universe_version_id
                == universe_version_id,
                strategy_universe_versions.c.lifecycle_state.in_(
                    ("warming", "active")
                ),
                sa.or_(
                    strategy_universe_versions.c.lifecycle_state == "warming",
                    strategy_universe_current.c.universe_version_id.is_not(None),
                ),
            )
            .order_by(strategy_universe_members.c.exchange_instrument_id)
            .limit(MAX_UNIVERSE_MEMBERS + 1)
        )
        rows = result.mappings().all()
        if not rows:
            return None
        first = rows[0]
        # Installed Dynamic membership is constrained by the trusted Spec FK
        # and database member-limit trigger; manual/Static remains capped at ten.
        maximum = (
            MAX_UNIVERSE_MEMBERS
            if first["source_kind"] == "dynamic_selection"
            else MAX_MANUAL_UNIVERSE_MEMBERS
        )
        if len(rows) > maximum:
            raise RuntimeError("observation Universe exceeds its member limit")
        if any(
            row["event_spec_id"] != first["event_spec_id"]
            or row["universe_version_id"] != first["universe_version_id"]
            or row["semantic_digest"] != first["semantic_digest"]
            or row["lifecycle_state"] != first["lifecycle_state"]
            for row in rows
        ):
            raise RuntimeError("observation Universe identity is inconsistent")
        universe = StrategyUniverseVersion(
            universe_version_id=str(first["universe_version_id"]),
            strategy_group_id=str(first["strategy_group_id"]),
            event_spec_id=str(first["event_spec_id"]),
            universe_version=int(first["universe_version"]),
            exchange_instrument_ids=tuple(
                str(row["exchange_instrument_id"]) for row in rows
            ),
            semantic_digest=str(first["semantic_digest"]),
            installed_at_ms=int(first["installed_at_ms"]),
        )
        return ObservationUniverseMembershipSnapshot(
            event_spec_id=universe.event_spec_id,
            universe_version_id=universe.universe_version_id,
            semantic_digest=universe.semantic_digest,
            lifecycle_state=cast(
                Literal["warming", "active"],
                str(first["lifecycle_state"]),
            ),
            exchange_instrument_ids=universe.exchange_instrument_ids,
        )

    async def get_runtime_profile(
        self,
        runtime_profile_id: str,
    ) -> RuntimeProfileSnapshot | None:
        result = await self._connection.execute(
            sa.select(runtime_profiles).where(
                runtime_profiles.c.runtime_profile_id == runtime_profile_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeProfileSnapshot.model_validate(row, extra="ignore")
        )

    async def get_instrument(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentSnapshot | None:
        result = await self._connection.execute(
            sa.select(instruments).where(
                instruments.c.exchange_instrument_id == exchange_instrument_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else InstrumentSnapshot.model_validate(row, extra="ignore")
        )

    async def get_product_session(
        self,
        exchange_instrument_id: str,
    ) -> ProductSessionSnapshot | None:
        row = (
            await self._connection.execute(
                sa.select(
                    instrument_product_current,
                    instrument_product_profiles.c.product_family,
                )
                .join(
                    instrument_product_profiles,
                    instrument_product_profiles.c.exchange_instrument_id
                    == instrument_product_current.c.exchange_instrument_id,
                )
                .where(
                    instrument_product_current.c.exchange_instrument_id
                    == exchange_instrument_id
                )
                .limit(1)
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else ProductSessionSnapshot.model_validate(row, extra="ignore")
        )

    async def get_product_profile(
        self,
        exchange_instrument_id: str,
    ) -> InstrumentProductProfile | None:
        row = (
            await self._connection.execute(
                sa.select(instrument_product_profiles).where(
                    instrument_product_profiles.c.exchange_instrument_id
                    == exchange_instrument_id
                )
            )
        ).mappings().one_or_none()
        return (
            None
            if row is None
            else InstrumentProductProfile.model_validate(row, extra="ignore")
        )

    async def upsert_product_sessions(
        self,
        snapshots: tuple[ProductSessionSnapshot, ...],
    ) -> int:
        return await PostgresProductCurrentRepository(
            self._connection
        ).upsert_snapshots(snapshots)

    async def get_instrument_rules(
        self,
        venue_id: str,
        exchange_instrument_id: str,
    ) -> InstrumentRulesSnapshot | None:
        result = await self._connection.execute(
            sa.select(instrument_rules_current).where(
                instrument_rules_current.c.venue_id == venue_id,
                instrument_rules_current.c.exchange_instrument_id
                == exchange_instrument_id
            )
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else InstrumentRulesSnapshot.model_validate(row, extra="ignore")
        )

    async def upsert_instrument_rules(
        self,
        *,
        venue_id: str,
        exchange_instrument_id: str,
        quantity_step: Decimal,
        price_tick: Decimal,
        min_quantity: Decimal,
        min_notional: Decimal,
        exchange_max_leverage: int,
        maintenance_margin_brackets: tuple[MaintenanceMarginBracket, ...],
        maintenance_margin_brackets_digest: str,
        notional_coefficient: Decimal,
        notional_coefficient_certified: bool,
        observed_at_ms: int,
        valid_until_ms: int,
    ) -> InstrumentRulesSnapshot:
        result = await self._connection.execute(
            sa.select(instrument_rules_current)
            .where(
                instrument_rules_current.c.venue_id == venue_id,
                instrument_rules_current.c.exchange_instrument_id
                == exchange_instrument_id
            )
            .with_for_update()
        )
        row = result.mappings().one_or_none()
        projection_version = 1 if row is None else int(row["projection_version"]) + 1
        values = {
            "venue_id": venue_id,
            "exchange_instrument_id": exchange_instrument_id,
            "quantity_step": quantity_step,
            "price_tick": price_tick,
            "min_quantity": min_quantity,
            "min_notional": min_notional,
            "exchange_max_leverage": exchange_max_leverage,
            "maintenance_margin_brackets": [
                item.model_dump(mode="json")
                for item in maintenance_margin_brackets
            ],
            "maintenance_margin_brackets_digest": maintenance_margin_brackets_digest,
            "notional_coefficient": notional_coefficient,
            "notional_coefficient_certified": notional_coefficient_certified,
            "session_and_settlement": {},
            "observed_at_ms": observed_at_ms,
            "valid_until_ms": valid_until_ms,
            "projection_version": projection_version,
        }
        if row is None:
            await self._connection.execute(
                sa.insert(instrument_rules_current).values(values)
            )
        else:
            await self._connection.execute(
                sa.update(instrument_rules_current)
                .where(
                    instrument_rules_current.c.venue_id == venue_id,
                    instrument_rules_current.c.exchange_instrument_id
                    == exchange_instrument_id
                )
                .values(values)
            )
        return InstrumentRulesSnapshot.model_validate(values, extra="ignore")

    async def get_runtime_capability(
        self,
        capability_key: str,
        *,
        for_update: bool = False,
    ) -> RuntimeCapabilitySnapshot | None:
        statement = sa.select(runtime_capabilities_current).where(
            runtime_capabilities_current.c.capability_key == capability_key
        )
        if for_update:
            statement = statement.with_for_update(of=runtime_capabilities_current)
        result = await self._connection.execute(
            statement
        )
        row = result.mappings().one_or_none()
        return (
            None
            if row is None
            else RuntimeCapabilitySnapshot.model_validate(row, extra="ignore")
        )

    async def get_required_facts(
        self,
        *,
        runtime_scope_id: str,
        event_spec_id: str,
    ) -> tuple[SignalFactSnapshot, ...] | None:
        required_result = await self._connection.execute(
            sa.select(
                event_required_facts.c.fact_definition_id,
                event_required_facts.c.role,
            )
            .where(
                event_required_facts.c.event_spec_id == event_spec_id,
                event_required_facts.c.required.is_(True),
            )
            .order_by(event_required_facts.c.fact_definition_id)
        )
        requirements = {
            str(row["fact_definition_id"]): str(row["role"])
            for row in required_result.mappings()
        }
        required_ids = tuple(requirements)
        if not required_ids:
            return ()

        facts_result = await self._connection.execute(
            sa.select(facts_current)
            .where(
                facts_current.c.runtime_scope_id == runtime_scope_id,
                facts_current.c.fact_definition_id.in_(required_ids),
            )
            .order_by(facts_current.c.fact_definition_id)
        )
        rows = tuple(facts_result.mappings())
        if len(rows) != len(required_ids):
            return None
        return tuple(
            SignalFactSnapshot(
                fact_definition_id=str(row["fact_definition_id"]),
                role=cast(
                    Literal["condition", "protection_reference", "disable"],
                    requirements[str(row["fact_definition_id"])],
                ),
                value=row["value"],
                satisfied=bool(row["satisfied"]),
                observed_at_ms=int(row["observed_at_ms"]),
                valid_until_ms=int(row["valid_until_ms"]),
                projection_version=int(row["projection_version"]),
            )
            for row in rows
        )

    async def get_selection_authority_chain(
        self,
        *,
        selection_spec_id: str,
        birth_selection_authority_id: str,
        current_selection_authority_id: str,
        max_depth: int,
    ) -> tuple[SelectionSessionAuthority, ...]:
        if not 1 <= max_depth <= 64:
            raise ValueError("Selection Authority chain depth must be in [1, 64]")
        endpoints = (
            await self._connection.execute(
                sa.select(*selection_authority_projection_columns()).where(
                    selection_session_authorities.c.selection_spec_id
                    == selection_spec_id,
                    selection_session_authorities.c.selection_authority_id.in_(
                        (
                            birth_selection_authority_id,
                            current_selection_authority_id,
                        )
                    ),
                )
            )
        ).mappings().all()
        endpoint_map = {
            str(row["selection_authority_id"]): row for row in endpoints
        }
        birth = endpoint_map.get(birth_selection_authority_id)
        current = endpoint_map.get(current_selection_authority_id)
        if birth is None or current is None:
            return ()
        if (
            int(birth["period_anchor_ms"]) != int(current["period_anchor_ms"])
            or int(birth["authority_sequence"]) > int(current["authority_sequence"])
        ):
            return ()
        rows = (
            await self._connection.execute(
                sa.select(*selection_authority_projection_columns())
                .where(
                    selection_session_authorities.c.selection_spec_id
                    == selection_spec_id,
                    selection_session_authorities.c.period_anchor_ms
                    == int(birth["period_anchor_ms"]),
                    selection_session_authorities.c.authority_sequence.between(
                        int(birth["authority_sequence"]),
                        int(current["authority_sequence"]),
                    ),
                )
                .order_by(selection_session_authorities.c.authority_sequence)
                .limit(max_depth + 1)
            )
        ).mappings().all()
        expected_count = (
            int(current["authority_sequence"])
            - int(birth["authority_sequence"])
            + 1
        )
        if len(rows) != expected_count or len(rows) > max_depth:
            return ()
        authorities = tuple(_selection_authority_from_row(row) for row in rows)
        if (
            authorities[0].selection_authority_id
            != birth_selection_authority_id
            or authorities[-1].selection_authority_id
            != current_selection_authority_id
        ):
            return ()
        return authorities

    async def selection_authority_was_interrupted(
        self,
        *,
        strategy_group_id: str,
        selection_spec_id: str,
        owner_policy_id: str,
        after_ms: int,
        through_ms: int,
        excluded_entry_vacuum_id: str | None = None,
    ) -> bool:
        """Default trading checks see every fence; planned handoff may exclude its exact own Vacuum."""
        if after_ms <= 0 or through_ms < after_ms:
            raise ValueError("Selection Authority interruption window is invalid")
        vacuum = await self._connection.scalar(
            sa.select(sa.literal(True))
            .select_from(strategy_entry_vacuums_current)
            .where(
                strategy_entry_vacuums_current.c.strategy_group_id
                == strategy_group_id,
                strategy_entry_vacuums_current.c.selection_spec_id
                == selection_spec_id,
                strategy_entry_vacuums_current.c.fenced_at_ms > after_ms,
                strategy_entry_vacuums_current.c.fenced_at_ms <= through_ms,
                (sa.true() if excluded_entry_vacuum_id is None else
                    strategy_entry_vacuums_current.c.entry_vacuum_id!=excluded_entry_vacuum_id),
            )
            .limit(1)
        )
        if vacuum is True:
            return True
        owner_pause = await self._connection.scalar(
            sa.select(sa.literal(True))
            .select_from(strategy_entry_control_events)
            .where(
                strategy_entry_control_events.c.strategy_group_id
                == strategy_group_id,
                strategy_entry_control_events.c.target_state == "paused",
                strategy_entry_control_events.c.created_at_ms > after_ms,
                strategy_entry_control_events.c.created_at_ms <= through_ms,
            )
            .limit(1)
        )
        if owner_pause is True:
            return True
        policy_pause = await self._connection.scalar(
            sa.select(sa.literal(True))
            .select_from(owner_policy_events)
            .where(
                owner_policy_events.c.owner_policy_id == owner_policy_id,
                owner_policy_events.c.operation == "owner_control_entry_pause",
                owner_policy_events.c.created_at_ms > after_ms,
                owner_policy_events.c.created_at_ms <= through_ms,
            )
            .limit(1)
        )
        return policy_pause is True

    async def is_strategy_trigger_suppressed(
        self,
        *,
        event_spec_id: str,
        exchange_instrument_id: str,
        session_reference: str,
    ) -> bool:
        return bool(
            await self._connection.scalar(
                sa.select(sa.literal(True))
                .select_from(strategy_trigger_suppressions)
                .where(
                    strategy_trigger_suppressions.c.event_spec_id
                    == event_spec_id,
                    strategy_trigger_suppressions.c.exchange_instrument_id
                    == exchange_instrument_id,
                    strategy_trigger_suppressions.c.session_reference
                    == session_reference,
                )
                .limit(1)
            )
        )

    async def selection_generation_matches_pair(
        self,
        *,
        materialization_generation_id: str,
        long_universe_version_id: str,
        short_universe_version_id: str,
    ) -> bool:
        rows = (
            await self._connection.execute(
                sa.select(
                    strategy_universe_versions.c.universe_version_id,
                    strategy_universe_versions.c.materialization_generation_id,
                    strategy_universe_versions.c.lifecycle_state,
                ).where(
                    strategy_universe_versions.c.universe_version_id.in_(
                        (long_universe_version_id, short_universe_version_id)
                    )
                )
            )
        ).mappings().all()
        return bool(
            len(rows) == 2
            and {str(row["universe_version_id"]) for row in rows}
            == {long_universe_version_id, short_universe_version_id}
            and all(
                row["materialization_generation_id"]
                == materialization_generation_id
                and row["lifecycle_state"] == "active"
                for row in rows
            )
        )


def _signal_values(signal: StrategySignal) -> dict[str, object]:
    return {
        "signal_event_id": signal.signal_event_id,
        "exposure_episode_id": signal.exposure_episode_id,
        "runtime_scope_id": signal.runtime_scope_id,
        "runtime_scope_version": signal.runtime_scope_version,
        "strategy_group_id": signal.strategy_group_id,
        "strategy_version_id": signal.strategy_version_id,
        "event_spec_id": signal.event_spec_id,
        "universe_version_id": signal.universe_version_id,
        "selection_authority_id": signal.selection_authority_id,
        "universe_semantic_digest": signal.universe_semantic_digest,
        "exchange_instrument_id": signal.exchange_instrument_id,
        "position_side": signal.position_side,
        "fact_digest": signal.fact_digest,
        "occurred_at_ms": signal.occurred_at_ms,
        "observed_at_ms": signal.observed_at_ms,
        "expires_at_ms": signal.expires_at_ms,
    }


def _selection_authority_from_row(row: RowMapping) -> SelectionSessionAuthority:
    pair = sor_authority_pair_from_bindings(row["event_bindings"])
    proof_kind = row["grant_proof_kind"]
    proof = (
        None
        if proof_kind is None
        else AuthorityGrantProof(
            kind=AuthorityGrantProofKind(str(proof_kind)),
            predecessor_authority_id=row["grant_predecessor_authority_id"],
            authority_gap_audit_id=row["authority_gap_audit_id"],
        )
    )
    return SelectionSessionAuthority(
        selection_authority_id=str(row["selection_authority_id"]),
        selection_spec_id=str(row["selection_spec_id"]),
        session_start_ms=int(row["period_anchor_ms"]),
        decision_boundary_ms=int(row["decision_boundary_ms"]),
        authority_sequence=int(row["authority_sequence"]),
        selection_mode=SelectionMode(str(row["selection_mode"])),
        selection_snapshot_id=row["selection_snapshot_id"],
        continued_from_selection_authority_id=row[
            "continued_from_selection_authority_id"
        ],
        continuity_source_kind=ContinuitySourceKind(
            str(row["continuity_source_kind"])
        ),
        authority_gap_audit_id=row["authority_gap_audit_id"],
        materialization_generation_id=row["materialization_generation_id"],
        owner_control_version=int(row["owner_control_version"]),
        authority_outcome=AuthorityOutcome(str(row["authority_outcome"])),
        authorized_pair=pair,
        grant_proof=proof,
        effective_from_ms=int(row["effective_from_ms"]),
        first_eligible_close_time_ms=(
            None
            if row["first_eligible_close_time_ms"] is None
            else int(row["first_eligible_close_time_ms"])
        ),
        expires_at_ms=int(row["expires_at_ms"]),
        reason_code=str(row["reason_code"]),
        created_at_ms=int(row["created_at_ms"]),
    )


def _fact_snapshot_values(
    signal_event_id: str,
    fact: SignalFactSnapshot,
) -> dict[str, object]:
    return {
        "signal_event_id": signal_event_id,
        "fact_definition_id": fact.fact_definition_id,
        "role": fact.role,
        "value": fact.value,
        "satisfied": fact.satisfied,
        "observed_at_ms": fact.observed_at_ms,
        "valid_until_ms": fact.valid_until_ms,
        "projection_version": fact.projection_version,
    }


def _signal_from_row(
    row: RowMapping,
    facts: tuple[SignalFactSnapshot, ...],
) -> StrategySignal:
    return StrategySignal(
        signal_event_id=str(row["signal_event_id"]),
        exposure_episode_id=str(row["exposure_episode_id"]),
        runtime_scope_id=str(row["runtime_scope_id"]),
        runtime_scope_version=int(row["runtime_scope_version"]),
        strategy_group_id=str(row["strategy_group_id"]),
        strategy_version_id=str(row["strategy_version_id"]),
        event_spec_id=str(row["event_spec_id"]),
        universe_version_id=str(row["universe_version_id"]),
        selection_authority_id=row["selection_authority_id"],
        universe_semantic_digest=str(row["universe_semantic_digest"]),
        exchange_instrument_id=str(row["exchange_instrument_id"]),
        position_side=cast(Literal["long", "short"], str(row["position_side"])),
        fact_digest=str(row["fact_digest"]),
        occurred_at_ms=int(row["occurred_at_ms"]),
        observed_at_ms=int(row["observed_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
        facts=facts,
    )


def _current_fact_matches(
    row: RowMapping,
    fact: SignalFactSnapshot,
) -> bool:
    return (
        row["value"] == fact.value
        and bool(row["satisfied"]) is fact.satisfied
        and int(row["observed_at_ms"]) == fact.observed_at_ms
        and int(row["valid_until_ms"]) == fact.valid_until_ms
    )
