"""PG repository for BRC admission gate Phase 1 facts."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.domain.brc_admission import (
    AdmissionAuditLog,
    AdmissionDecision,
    AdmissionEvidence,
    AdmissionRequest,
    AdmissionRuleConfig,
    AdmissionTrialBinding,
    OwnerMarketRegimeInput,
    OwnerRiskAcceptance,
    StrategyFamily,
    StrategyFamilyVersion,
    TrialTradeIntent,
    TrialConstraintSnapshot,
)
from src.infrastructure.database import get_pg_session_maker, init_pg_core_db
from src.infrastructure.pg_models import (
    PGBrcAdmissionAuditLogORM,
    PGBrcAdmissionDecisionORM,
    PGBrcAdmissionEvidenceORM,
    PGBrcAdmissionRequestORM,
    PGBrcAdmissionRuleConfigORM,
    PGBrcAdmissionTrialBindingORM,
    PGBrcOwnerMarketRegimeInputORM,
    PGBrcOwnerRiskAcceptanceORM,
    PGBrcStrategyFamilyORM,
    PGBrcStrategyFamilyVersionORM,
    PGBrcTrialTradeIntentORM,
    PGBrcTrialConstraintSnapshotORM,
)


class PgBrcAdmissionRepository:
    """Persistence for BRC admission facts, decisions, and audit events."""

    def __init__(
        self,
        session_maker: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._session_maker = session_maker or get_pg_session_maker()
        self._uses_injected_session_maker = session_maker is not None

    async def initialize(self) -> None:
        if self._uses_injected_session_maker:
            return
        await init_pg_core_db()

    async def create_strategy_family(self, family: StrategyFamily) -> StrategyFamily:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcStrategyFamilyORM(**family.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_strategy_family(row)

    async def get_strategy_family(self, strategy_family_id: str) -> Optional[StrategyFamily]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcStrategyFamilyORM, strategy_family_id)
            return self._to_strategy_family(row) if row is not None else None

    async def list_strategy_families(self, *, limit: int = 100) -> list[StrategyFamily]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcStrategyFamilyORM)
                .order_by(PGBrcStrategyFamilyORM.updated_at_ms.desc())
                .limit(limit)
            )
            return [self._to_strategy_family(row) for row in result.scalars().all()]

    async def create_strategy_family_version(
        self,
        version: StrategyFamilyVersion,
    ) -> StrategyFamilyVersion:
        async with self._session_maker() as session:
            async with session.begin():
                payload = version.model_dump(mode="json")
                row = PGBrcStrategyFamilyVersionORM(
                    strategy_family_version_id=payload["strategy_family_version_id"],
                    strategy_family_id=payload["strategy_family_id"],
                    version=payload["version"],
                    hypothesis=payload["hypothesis"],
                    market_structure=payload["market_structure"],
                    entry_logic_family=payload["entry_logic_family"],
                    exit_logic_family=payload["exit_logic_family"],
                    risk_model=payload["risk_model"],
                    supported_symbols_json=list(payload["supported_symbols"]),
                    supported_timeframes_json=list(payload["supported_timeframes"]),
                    required_data_json=list(payload["required_data"]),
                    required_execution_capabilities_json=list(
                        payload["required_execution_capabilities"]
                    ),
                    known_failure_modes_json=list(payload["known_failure_modes"]),
                    regime_contract_json=dict(payload["regime_contract_json"]),
                    safeguards_json=dict(payload["safeguards_json"]),
                    degradation_policy_json=dict(payload["degradation_policy_json"]),
                    playbook_id=payload.get("playbook_id"),
                    playbook_catalog_snapshot_json=dict(
                        payload["playbook_catalog_snapshot_json"]
                    ),
                    created_at_ms=payload["created_at_ms"],
                    created_by=payload["created_by"],
                    is_current=payload["is_current"],
                )
                session.add(row)
                await session.flush()
                return self._to_strategy_family_version(row)

    async def get_strategy_family_version(
        self,
        strategy_family_version_id: str,
    ) -> Optional[StrategyFamilyVersion]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcStrategyFamilyVersionORM, strategy_family_version_id)
            return self._to_strategy_family_version(row) if row is not None else None

    async def create_rule_config(self, config: AdmissionRuleConfig) -> AdmissionRuleConfig:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcAdmissionRuleConfigORM(**config.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_rule_config(row)

    async def get_rule_config(self, admission_rule_config_id: str) -> Optional[AdmissionRuleConfig]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcAdmissionRuleConfigORM, admission_rule_config_id)
            return self._to_rule_config(row) if row is not None else None

    async def get_latest_rule_config(self) -> Optional[AdmissionRuleConfig]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcAdmissionRuleConfigORM)
                .where(PGBrcAdmissionRuleConfigORM.status == "active")
                .order_by(
                    PGBrcAdmissionRuleConfigORM.version.desc(),
                    PGBrcAdmissionRuleConfigORM.created_at_ms.desc(),
                )
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return self._to_rule_config(row) if row is not None else None

    async def create_admission_evidence(
        self,
        admission_evidence: AdmissionEvidence,
    ) -> AdmissionEvidence:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcAdmissionEvidenceORM(
                    **_admission_storage_payload(admission_evidence)
                )
                session.add(row)
                await session.flush()
                return self._to_admission_evidence(row)

    async def get_admission_evidence(
        self,
        admission_evidence_id: str,
    ) -> Optional[AdmissionEvidence]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcAdmissionEvidenceORM, admission_evidence_id)
            return self._to_admission_evidence(row) if row is not None else None

    async def create_owner_regime_input(
        self,
        regime_input: OwnerMarketRegimeInput,
    ) -> OwnerMarketRegimeInput:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcOwnerMarketRegimeInputORM(**regime_input.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_owner_regime_input(row)

    async def get_owner_regime_input(
        self,
        owner_market_regime_input_id: str,
    ) -> Optional[OwnerMarketRegimeInput]:
        async with self._session_maker() as session:
            row = await session.get(
                PGBrcOwnerMarketRegimeInputORM,
                owner_market_regime_input_id,
            )
            return self._to_owner_regime_input(row) if row is not None else None

    async def create_admission_request(self, request: AdmissionRequest) -> AdmissionRequest:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcAdmissionRequestORM(
                    **_admission_storage_payload(request)
                )
                session.add(row)
                await session.flush()
                return self._to_admission_request(row)

    async def get_admission_request(self, admission_request_id: str) -> Optional[AdmissionRequest]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcAdmissionRequestORM, admission_request_id)
            return self._to_admission_request(row) if row is not None else None

    async def create_trial_constraint_snapshot(
        self,
        snapshot: TrialConstraintSnapshot,
    ) -> TrialConstraintSnapshot:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcTrialConstraintSnapshotORM(**snapshot.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_trial_constraint_snapshot(row)

    async def get_trial_constraint_snapshot(
        self,
        trial_constraint_snapshot_id: str,
    ) -> Optional[TrialConstraintSnapshot]:
        async with self._session_maker() as session:
            row = await session.get(
                PGBrcTrialConstraintSnapshotORM,
                trial_constraint_snapshot_id,
            )
            return self._to_trial_constraint_snapshot(row) if row is not None else None

    async def create_admission_decision(self, decision: AdmissionDecision) -> AdmissionDecision:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcAdmissionDecisionORM(
                    **_admission_storage_payload(decision)
                )
                session.add(row)
                await session.flush()
                return self._to_admission_decision(row)

    async def get_admission_decision(self, admission_decision_id: str) -> Optional[AdmissionDecision]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcAdmissionDecisionORM, admission_decision_id)
            return self._to_admission_decision(row) if row is not None else None

    async def list_admission_decisions(self, *, limit: int = 100) -> list[AdmissionDecision]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcAdmissionDecisionORM)
                .order_by(PGBrcAdmissionDecisionORM.created_at_ms.desc())
                .limit(limit)
            )
            return [self._to_admission_decision(row) for row in result.scalars().all()]

    async def create_owner_risk_acceptance(
        self,
        acceptance: OwnerRiskAcceptance,
    ) -> OwnerRiskAcceptance:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcOwnerRiskAcceptanceORM(**acceptance.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_owner_risk_acceptance(row)

    async def get_owner_risk_acceptance(
        self,
        owner_risk_acceptance_id: str,
    ) -> Optional[OwnerRiskAcceptance]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcOwnerRiskAcceptanceORM, owner_risk_acceptance_id)
            return self._to_owner_risk_acceptance(row) if row is not None else None

    async def append_audit_log(self, log: AdmissionAuditLog) -> AdmissionAuditLog:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcAdmissionAuditLogORM(**log.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_admission_audit_log(row)

    async def create_admission_trial_binding(
        self,
        binding: AdmissionTrialBinding,
    ) -> AdmissionTrialBinding:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcAdmissionTrialBindingORM(**binding.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_admission_trial_binding(row)

    async def get_admission_trial_binding(
        self,
        binding_id: str,
    ) -> Optional[AdmissionTrialBinding]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcAdmissionTrialBindingORM, binding_id)
            return self._to_admission_trial_binding(row) if row is not None else None

    async def list_admission_trial_bindings(
        self,
        *,
        limit: int = 100,
    ) -> list[AdmissionTrialBinding]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcAdmissionTrialBindingORM)
                .order_by(PGBrcAdmissionTrialBindingORM.created_at_ms.desc())
                .limit(limit)
            )
            return [self._to_admission_trial_binding(row) for row in result.scalars().all()]

    async def list_admission_trial_bindings_by_decision(
        self,
        admission_decision_id: str,
    ) -> list[AdmissionTrialBinding]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcAdmissionTrialBindingORM)
                .where(
                    PGBrcAdmissionTrialBindingORM.admission_decision_id
                    == admission_decision_id
                )
                .order_by(PGBrcAdmissionTrialBindingORM.created_at_ms.desc())
            )
            return [self._to_admission_trial_binding(row) for row in result.scalars().all()]

    async def list_admission_trial_bindings_by_operation(
        self,
        operation_id: str,
    ) -> list[AdmissionTrialBinding]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcAdmissionTrialBindingORM)
                .where(PGBrcAdmissionTrialBindingORM.created_by_operation_id == operation_id)
                .order_by(PGBrcAdmissionTrialBindingORM.created_at_ms.desc())
            )
            return [self._to_admission_trial_binding(row) for row in result.scalars().all()]

    async def update_admission_trial_binding(
        self,
        binding: AdmissionTrialBinding,
    ) -> AdmissionTrialBinding:
        async with self._session_maker() as session:
            async with session.begin():
                row = await session.get(PGBrcAdmissionTrialBindingORM, binding.binding_id)
                if row is None:
                    raise ValueError(f"admission trial binding not found: {binding.binding_id}")
                for key, value in binding.model_dump(mode="json").items():
                    setattr(row, key, value)
                await session.flush()
                return self._to_admission_trial_binding(row)

    async def create_trial_trade_intent(
        self,
        intent: TrialTradeIntent,
    ) -> TrialTradeIntent:
        async with self._session_maker() as session:
            async with session.begin():
                row = PGBrcTrialTradeIntentORM(**intent.model_dump(mode="json"))
                session.add(row)
                await session.flush()
                return self._to_trial_trade_intent(row)

    async def get_trial_trade_intent(self, intent_id: str) -> Optional[TrialTradeIntent]:
        async with self._session_maker() as session:
            row = await session.get(PGBrcTrialTradeIntentORM, intent_id)
            return self._to_trial_trade_intent(row) if row is not None else None

    async def list_trial_trade_intents_by_campaign(
        self,
        campaign_id: str,
        *,
        limit: int = 100,
    ) -> list[TrialTradeIntent]:
        async with self._session_maker() as session:
            result = await session.execute(
                select(PGBrcTrialTradeIntentORM)
                .where(PGBrcTrialTradeIntentORM.campaign_id == campaign_id)
                .order_by(PGBrcTrialTradeIntentORM.created_at_ms.desc())
                .limit(limit)
            )
            return [self._to_trial_trade_intent(row) for row in result.scalars().all()]

    @staticmethod
    def _to_strategy_family(row: PGBrcStrategyFamilyORM) -> StrategyFamily:
        return StrategyFamily.model_validate(_row_dict(row))

    @staticmethod
    def _to_strategy_family_version(row: PGBrcStrategyFamilyVersionORM) -> StrategyFamilyVersion:
        return StrategyFamilyVersion(
            strategy_family_version_id=row.strategy_family_version_id,
            strategy_family_id=row.strategy_family_id,
            version=row.version,
            hypothesis=row.hypothesis,
            market_structure=row.market_structure,
            entry_logic_family=row.entry_logic_family,
            exit_logic_family=row.exit_logic_family,
            risk_model=row.risk_model,
            supported_symbols=list(row.supported_symbols_json),
            supported_timeframes=list(row.supported_timeframes_json),
            required_data=list(row.required_data_json),
            required_execution_capabilities=list(row.required_execution_capabilities_json),
            known_failure_modes=list(row.known_failure_modes_json),
            regime_contract_json=dict(row.regime_contract_json),
            safeguards_json=dict(row.safeguards_json),
            degradation_policy_json=dict(row.degradation_policy_json),
            playbook_id=row.playbook_id,
            playbook_catalog_snapshot_json=dict(row.playbook_catalog_snapshot_json),
            created_at_ms=row.created_at_ms,
            created_by=row.created_by,
            is_current=row.is_current,
        )

    @staticmethod
    def _to_rule_config(row: PGBrcAdmissionRuleConfigORM) -> AdmissionRuleConfig:
        return AdmissionRuleConfig.model_validate(_row_dict(row))

    @staticmethod
    def _to_admission_evidence(row: PGBrcAdmissionEvidenceORM) -> AdmissionEvidence:
        return AdmissionEvidence.model_validate(_row_dict(row))

    @staticmethod
    def _to_owner_regime_input(row: PGBrcOwnerMarketRegimeInputORM) -> OwnerMarketRegimeInput:
        return OwnerMarketRegimeInput.model_validate(_row_dict(row))

    @staticmethod
    def _to_admission_request(row: PGBrcAdmissionRequestORM) -> AdmissionRequest:
        return AdmissionRequest.model_validate(_row_dict(row))

    @staticmethod
    def _to_trial_constraint_snapshot(
        row: PGBrcTrialConstraintSnapshotORM,
    ) -> TrialConstraintSnapshot:
        return TrialConstraintSnapshot.model_validate(_row_dict(row))

    @staticmethod
    def _to_admission_decision(row: PGBrcAdmissionDecisionORM) -> AdmissionDecision:
        return AdmissionDecision.model_validate(_row_dict(row))

    @staticmethod
    def _to_owner_risk_acceptance(row: PGBrcOwnerRiskAcceptanceORM) -> OwnerRiskAcceptance:
        return OwnerRiskAcceptance.model_validate(_row_dict(row))

    @staticmethod
    def _to_admission_audit_log(row: PGBrcAdmissionAuditLogORM) -> AdmissionAuditLog:
        return AdmissionAuditLog.model_validate(_row_dict(row))

    @staticmethod
    def _to_admission_trial_binding(
        row: PGBrcAdmissionTrialBindingORM,
    ) -> AdmissionTrialBinding:
        return AdmissionTrialBinding.model_validate(_row_dict(row))

    @staticmethod
    def _to_trial_trade_intent(row: PGBrcTrialTradeIntentORM) -> TrialTradeIntent:
        return TrialTradeIntent.model_validate(_row_dict(row))


def _row_dict(row: Any) -> dict[str, Any]:
    return {
        attr.key: getattr(row, attr.key)
        for attr in row.__mapper__.column_attrs
    }


def _admission_storage_payload(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")
