from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from src.application.runtime_execution_trusted_submit_fact_readers import (
    ConfiguredMarketRuleTrustedSubmitFactReader,
    LocalActivePositionTrustedSubmitFactReader,
    LocalOpenOrderTrustedSubmitFactReader,
    ReconciliationReadModelTrustedSubmitFactReader,
    RuntimeProtectionPlanTrustedSubmitFactReader,
    StartupReconciliationTrustedSubmitFactReader,
    TrialReadinessAccountTrustedSubmitFactReader,
)
from src.application.runtime_execution_trusted_submit_facts_service import (
    RuntimeExecutionTrustedSubmitFactsAssemblyService,
)
from src.application.trial_readiness_account_facts import (
    AccountFactsFreshnessStatus,
    AccountFactsReconciliationStatus,
    AccountFactsSourceType,
    TrialReadinessAccountFacts,
)
from src.domain.brc_audit_ids import BrcSemanticIds
from src.domain.runtime_execution_protection_plan import (
    RuntimeExecutionProtectionPlanStatus,
)
from src.domain.runtime_execution_trusted_submit_facts import (
    RuntimeExecutionTrustedFactFreshness,
    RuntimeExecutionTrustedSubmitFactsStatus,
    RuntimeExecutionTrustedSubmitFactSource,
)
from src.infrastructure.repository_ports import ReconciliationReadModelReport


NOW_MS = 1781000000000


def _semantic_ids() -> BrcSemanticIds:
    return BrcSemanticIds(
        runtime_instance_id="runtime-1",
        trial_binding_id="trial-1",
        strategy_family_id="CPM-RO-001",
        strategy_family_version_id="CPM-RO-001-v0",
        signal_evaluation_id="evaluation-1",
        order_candidate_id="candidate-1",
    )


class _Reader:
    def __init__(
        self,
        *,
        freshness: RuntimeExecutionTrustedFactFreshness = (
            RuntimeExecutionTrustedFactFreshness.FRESH
        ),
        owner_supplied_allow_signal: bool = False,
        trusted: bool = True,
        read_only: bool = True,
    ) -> None:
        self.calls = []
        self.freshness = freshness
        self.owner_supplied_allow_signal = owner_supplied_allow_signal
        self.trusted = trusted
        self.read_only = read_only

    async def read_trusted_submit_fact_source(
        self,
        *,
        key,
        execution_intent_id,
        runtime_instance_id,
        order_candidate_id,
        symbol,
        side,
        now_ms,
    ):
        self.calls.append(
            {
                "key": key,
                "execution_intent_id": execution_intent_id,
                "runtime_instance_id": runtime_instance_id,
                "order_candidate_id": order_candidate_id,
                "symbol": symbol,
                "side": side,
                "now_ms": now_ms,
            }
        )
        return RuntimeExecutionTrustedSubmitFactSource(
            key=key,
            source_id=f"{key}-source-1",
            source_type=f"trusted_{key}_readmodel",
            trusted=self.trusted,
            freshness=self.freshness,
            observed_at_ms=now_ms - 50,
            max_age_ms=1_000,
            owner_supplied_allow_signal=self.owner_supplied_allow_signal,
            read_only=self.read_only,
        )


class _DictReader:
    async def read_trusted_submit_fact_source(self, *, key, now_ms, **_kwargs):
        return {
            "key": key,
            "source_id": f"{key}-dict-source-1",
            "source_type": f"trusted_{key}_dict_readmodel",
            "observed_at_ms": now_ms - 50,
            "max_age_ms": 1_000,
        }


class _Repository:
    def __init__(self) -> None:
        self.created = []

    async def create(self, snapshot):
        self.created.append(snapshot)
        return snapshot


class _AccountFactsSource:
    async def read_trial_readiness_account_facts(
        self,
        *,
        candidate_id,
        symbol,
        side,
        generated_at_ms,
    ):
        return TrialReadinessAccountFacts(
            account_id="trading-console-cached-account",
            account_type="cached_snapshot",
            source_id="trading-console-account-facts",
            source_type=AccountFactsSourceType.CACHED_SNAPSHOT,
            account_equity=Decimal("30"),
            available_margin=Decimal("29"),
            timestamp_ms=generated_at_ms - 50,
            freshness_status=AccountFactsFreshnessStatus.FRESH,
            reconciliation_status=AccountFactsReconciliationStatus.CLEAN,
            read_only_guarantee=True,
            external_call_performed=False,
            external_call_type="none",
            notes=(f"candidate={candidate_id}", f"symbol={symbol}", f"side={side}"),
        )


class _PositionSource:
    async def list_active(self, *, symbol, limit):
        return []


class _OrderSource:
    async def get_open_orders(self, symbol):
        return []


class _ProtectionPlanRepo:
    async def get(self, protection_plan_id):
        return SimpleNamespace(
            protection_plan_id=protection_plan_id,
            status=RuntimeExecutionProtectionPlanStatus.READY_FOR_SUBMIT_ADAPTER,
            requires_protection=True,
            stop_price_reference=Decimal("585"),
            take_profit_references=[{"kind": "tp1", "r_multiple": "1"}],
            blockers=[],
            created_at_ms=NOW_MS - 50,
        )


class _ReconciliationReadModelRepo:
    def __init__(self, reports=None) -> None:
        self.reports = list(reports or [])
        self.calls = []

    async def get_recent_reports(self, *, symbol, limit):
        self.calls.append({"symbol": symbol, "limit": limit})
        return self.reports[:limit]


def _reconciliation_report(
    *,
    report_id: str = "reconciliation-report-1",
    symbol: str = "BNB/USDT:USDT",
    checked_at_ms: int | None = NOW_MS - 50,
    is_consistent: bool = True,
    severe_count: int = 0,
    warning_count: int = 0,
    is_fetch_failure: bool = False,
):
    return ReconciliationReadModelReport(
        report_id=report_id,
        symbol=symbol,
        checked_at_ms=checked_at_ms,
        is_consistent=is_consistent,
        total_count=severe_count + warning_count,
        severe_count=severe_count,
        warning_count=warning_count,
        is_fetch_failure=is_fetch_failure,
        fetch_failure_reason="fetch failed" if is_fetch_failure else None,
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        created_at=NOW_MS - 40,
    )


def _controlled_submit_plan():
    return SimpleNamespace(
        plan_id="runtime-controlled-submit-plan-auth-1",
        status=SimpleNamespace(value="ready_for_controlled_submit_adapter"),
        execution_intent_id="intent-1",
        source_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
    )


def _readers(reader=None):
    selected = reader or _Reader()
    return {
        "account_fact_reader": selected,
        "active_position_reader": selected,
        "open_order_reader": selected,
        "protection_state_reader": selected,
        "market_rule_reader": selected,
        "reconciliation_reader": selected,
    }


async def test_trusted_submit_facts_assembler_builds_ready_snapshot_from_readers():
    reader = _Reader()
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        **_readers(reader),
    )

    snapshot = await service.assemble_snapshot(
        trusted_submit_fact_snapshot_id="trusted-submit-facts-intent-1",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert (
        snapshot.status
        == RuntimeExecutionTrustedSubmitFactsStatus.READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert snapshot.blockers == []
    assert len(reader.calls) == 6
    assert snapshot.account_fact_source is not None
    assert snapshot.reconciliation_source is not None
    assert snapshot.metadata["assembled_from_read_only_source_ports"] is True
    assert snapshot.metadata["missing_readers"] == []
    assert snapshot.not_execution_authority is True
    assert snapshot.order_created is False
    assert snapshot.exchange_called is False
    assert snapshot.order_lifecycle_called is False


async def test_trusted_submit_facts_assembler_blocks_missing_reader():
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        account_fact_reader=_Reader(),
        active_position_reader=_Reader(),
        open_order_reader=None,
        protection_state_reader=_Reader(),
        market_rule_reader=_Reader(),
        reconciliation_reader=_Reader(),
    )

    snapshot = await service.assemble_snapshot(
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert snapshot.status == RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
    assert "trusted_open_order_source_missing" in snapshot.blockers
    assert "trusted_submit_facts_not_fresh_enough" in snapshot.blockers
    assert snapshot.metadata["missing_readers"] == ["open_order"]
    assert snapshot.exchange_called is False


async def test_trusted_submit_facts_assembler_rejects_owner_supplied_allow_reader():
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        **_readers(_Reader(owner_supplied_allow_signal=True)),
    )

    snapshot = await service.assemble_snapshot(
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert snapshot.status == RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
    assert "trusted_account_fact_owner_supplied_allow_signal_rejected" in (
        snapshot.blockers
    )
    assert "trusted_reconciliation_owner_supplied_allow_signal_rejected" in (
        snapshot.blockers
    )
    assert snapshot.owner_supplied_allow_facts_rejected is True


async def test_trusted_submit_facts_assembler_records_snapshot():
    repository = _Repository()
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        repository=repository,
        **_readers(_DictReader()),
    )

    snapshot = await service.assemble_and_record_snapshot(
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        semantic_ids=_semantic_ids(),
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert repository.created == [snapshot]
    assert snapshot.status == (
        RuntimeExecutionTrustedSubmitFactsStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert snapshot.market_rule_source is not None
    assert snapshot.market_rule_source.source_id == "market_rule-dict-source-1"


async def test_trusted_submit_facts_assembler_uses_local_readonly_sources():
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        account_fact_reader=TrialReadinessAccountTrustedSubmitFactReader(
            _AccountFactsSource(),
        ),
        active_position_reader=LocalActivePositionTrustedSubmitFactReader(
            _PositionSource(),
        ),
        open_order_reader=LocalOpenOrderTrustedSubmitFactReader(_OrderSource()),
        protection_state_reader=RuntimeProtectionPlanTrustedSubmitFactReader(
            _ProtectionPlanRepo(),
        ),
        market_rule_reader=ConfiguredMarketRuleTrustedSubmitFactReader(
            {
                "BNB/USDT:USDT": {
                    "source_id": "configured-market-rule-bnb",
                    "source_type": "configured_market_rule_snapshot",
                    "observed_at_ms": NOW_MS - 50,
                    "min_qty": "0.001",
                    "tick_size": "0.01",
                    "quantity_precision": "0.001",
                }
            }
        ),
        reconciliation_reader=StartupReconciliationTrustedSubmitFactReader(
            {
                "report_id": "startup-reconciliation-clean-1",
                "status": "clean",
                "checked_at_ms": NOW_MS - 50,
                "failed_reconciliations_count": 0,
            }
        ),
    )

    snapshot = await service.assemble_snapshot_for_controlled_submit_plan(
        plan=_controlled_submit_plan(),
        now_ms=NOW_MS,
    )

    assert (
        snapshot.status
        == RuntimeExecutionTrustedSubmitFactsStatus.READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert snapshot.blockers == []
    assert snapshot.account_fact_source is not None
    assert snapshot.account_fact_source.source_id == "trading-console-account-facts"
    assert snapshot.active_position_source is not None
    assert snapshot.active_position_source.metadata["active_position_count"] == 0
    assert snapshot.open_order_source is not None
    assert snapshot.open_order_source.metadata["open_order_count"] == 0
    assert snapshot.protection_state_source is not None
    assert snapshot.protection_state_source.source_id == (
        "runtime-protection-plan-intent-1"
    )
    assert snapshot.market_rule_source is not None
    assert snapshot.market_rule_source.source_id == "configured-market-rule-bnb"
    assert snapshot.reconciliation_source is not None
    assert snapshot.reconciliation_source.source_id == (
        "startup-reconciliation-clean-1"
    )
    assert snapshot.metadata["controlled_submit_plan_id"] == (
        "runtime-controlled-submit-plan-auth-1"
    )
    assert snapshot.exchange_called is False
    assert snapshot.order_lifecycle_called is False


async def test_reconciliation_read_model_reader_marks_clean_report_fresh():
    repo = _ReconciliationReadModelRepo([_reconciliation_report()])
    reader = ReconciliationReadModelTrustedSubmitFactReader(repo)

    source = await reader.read_trusted_submit_fact_source(
        key="reconciliation",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert repo.calls == [{"symbol": "BNB/USDT:USDT", "limit": 1}]
    assert source.source_id == "reconciliation-report-1"
    assert source.source_type == "reconciliation_read_model"
    assert source.freshness == RuntimeExecutionTrustedFactFreshness.FRESH
    assert source.observed_at_ms == NOW_MS - 50
    assert source.metadata["clean"] is True
    assert source.metadata["runtime_instance_id"] == "runtime-1"
    assert source.exchange_called is False


async def test_reconciliation_read_model_reader_blocks_missing_report():
    reader = ReconciliationReadModelTrustedSubmitFactReader(
        _ReconciliationReadModelRepo([]),
    )

    source = await reader.read_trusted_submit_fact_source(
        key="reconciliation",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert source.freshness == RuntimeExecutionTrustedFactFreshness.MISSING
    assert source.source_id == "reconciliation-readmodel:BNB/USDT:USDT:missing"
    assert source.metadata["reason"] == "reconciliation_read_model_report_not_found"
    assert source.exchange_called is False


async def test_reconciliation_read_model_reader_marks_unclean_report_stale():
    reader = ReconciliationReadModelTrustedSubmitFactReader(
        _ReconciliationReadModelRepo(
            [_reconciliation_report(is_consistent=False, warning_count=1)],
        ),
    )

    source = await reader.read_trusted_submit_fact_source(
        key="reconciliation",
        execution_intent_id="intent-1",
        runtime_instance_id="runtime-1",
        order_candidate_id="candidate-1",
        symbol="BNB/USDT:USDT",
        side="long",
        now_ms=NOW_MS,
    )

    assert source.freshness == RuntimeExecutionTrustedFactFreshness.STALE
    assert source.metadata["clean"] is False
    assert source.metadata["warning_count"] == 1
    assert source.exchange_called is False


async def test_trusted_submit_facts_assembler_uses_reconciliation_read_model():
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        account_fact_reader=TrialReadinessAccountTrustedSubmitFactReader(
            _AccountFactsSource(),
        ),
        active_position_reader=LocalActivePositionTrustedSubmitFactReader(
            _PositionSource(),
        ),
        open_order_reader=LocalOpenOrderTrustedSubmitFactReader(_OrderSource()),
        protection_state_reader=RuntimeProtectionPlanTrustedSubmitFactReader(
            _ProtectionPlanRepo(),
        ),
        market_rule_reader=ConfiguredMarketRuleTrustedSubmitFactReader(
            {
                "BNB/USDT:USDT": {
                    "source_id": "configured-market-rule-bnb",
                    "source_type": "configured_market_rule_snapshot",
                    "observed_at_ms": NOW_MS - 50,
                    "min_qty": "0.001",
                    "tick_size": "0.01",
                    "quantity_precision": "0.001",
                }
            }
        ),
        reconciliation_reader=ReconciliationReadModelTrustedSubmitFactReader(
            _ReconciliationReadModelRepo([_reconciliation_report()]),
        ),
    )

    snapshot = await service.assemble_snapshot_for_controlled_submit_plan(
        plan=_controlled_submit_plan(),
        now_ms=NOW_MS,
    )

    assert snapshot.status == (
        RuntimeExecutionTrustedSubmitFactsStatus
        .READY_FOR_FIRST_REAL_SUBMIT_CONFIRMATION
    )
    assert snapshot.blockers == []
    assert snapshot.reconciliation_source is not None
    assert snapshot.reconciliation_source.source_type == "reconciliation_read_model"
    assert snapshot.reconciliation_source.metadata["clean"] is True


async def test_trusted_submit_facts_local_reader_missing_market_rule_blocks():
    service = RuntimeExecutionTrustedSubmitFactsAssemblyService(
        account_fact_reader=TrialReadinessAccountTrustedSubmitFactReader(
            _AccountFactsSource(),
        ),
        active_position_reader=LocalActivePositionTrustedSubmitFactReader(
            _PositionSource(),
        ),
        open_order_reader=LocalOpenOrderTrustedSubmitFactReader(_OrderSource()),
        protection_state_reader=RuntimeProtectionPlanTrustedSubmitFactReader(
            _ProtectionPlanRepo(),
        ),
        market_rule_reader=ConfiguredMarketRuleTrustedSubmitFactReader(None),
        reconciliation_reader=StartupReconciliationTrustedSubmitFactReader(
            {
                "report_id": "startup-reconciliation-clean-1",
                "status": "clean",
                "checked_at_ms": NOW_MS - 50,
                "failed_reconciliations_count": 0,
            }
        ),
    )

    snapshot = await service.assemble_snapshot_for_controlled_submit_plan(
        plan=_controlled_submit_plan(),
        now_ms=NOW_MS,
    )

    assert snapshot.status == RuntimeExecutionTrustedSubmitFactsStatus.BLOCKED
    assert "trusted_market_rule_fact_missing" in snapshot.blockers
    assert "trusted_submit_facts_not_fresh_enough" in snapshot.blockers
    assert snapshot.market_rule_source is not None
    assert snapshot.market_rule_source.freshness == (
        RuntimeExecutionTrustedFactFreshness.MISSING
    )
    assert snapshot.metadata["missing_readers"] == []
