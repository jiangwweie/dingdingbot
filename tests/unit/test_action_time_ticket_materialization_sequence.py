from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy import text

from scripts import materialize_action_time_ticket_sequence as sequence_script
from scripts import publish_runtime_control_current_projections as publisher
from src.application.action_time.action_time_invocation import (
    load_action_time_invocation,
    start_action_time_invocation,
)
from src.application.action_time.runtime_pg_fact_snapshots import (
    write_account_safe_fact_snapshots,
)
from src.application.readmodels import strategy_live_candidate_pool as candidate_pool
from src.application.action_time.ticket_materialization_sequence import (
    materialize_action_time_ticket_sequence,
)
from src.application.action_time import promotion_action_time_lane as promotion_subject
from src.application.action_time import action_time_ticket as ticket_subject
from src.application.action_time.account_capacity_reservation import (
    AccountCapacityReservationResult,
)
from src.application.action_time.instrument_risk_facts import InstrumentRiskFacts
from src.domain.instrument_risk_identity import (
    InstrumentRiskIdentity,
    InstrumentRuleSnapshotRefV2,
    RiskClusterMembershipSnapshotRef,
    instrument_rule_snapshot_v2_semantic_hash,
)
from src.infrastructure.binance_usdm_account_risk_snapshot import (
    FullAccountRiskSnapshot,
)
from src.infrastructure.runtime_control_state_repository import (
    PgBackedRuntimeControlStateRepository,
)


def test_invocation_lane_selects_only_the_bound_capacity_fact_pair() -> None:
    blockers: list[str] = []
    surface, key = ticket_subject._lane_account_fact_pair(
        {
            "action_time_invocation_id": "invocation-1",
            "account_capacity_base_fact_snapshot_id": "capacity-fact-1",
        },
        blockers=blockers,
    )

    assert (surface, key) == (
        "account_capacity_base",
        "account_capacity_base_fact_snapshot_id",
    )
    assert blockers == []


def test_sequence_cli_requires_database_url_and_postgres_dsn(
    monkeypatch,
    capsys,
):
    monkeypatch.delenv("PG_DATABASE_URL", raising=False)
    assert sequence_script.main(["--require-database-url"]) == 2
    assert "PG_DATABASE_URL is required" in capsys.readouterr().err

    assert sequence_script.main(["--database-url", "sqlite://"]) == 2
    assert "--action-time-invocation-id is required" in capsys.readouterr().err

    assert sequence_script.main(
        [
            "--database-url",
            "sqlite://",
            "--action-time-invocation-id",
            "action_time_invocation:unit",
        ]
    ) == 2
    assert "requires PostgreSQL DSN" in capsys.readouterr().err


def test_sequence_cli_keeps_watcher_healthy_for_persisted_business_blocker(
    monkeypatch,
):
    seen = {}
    class FakeTransaction:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakeEngine:
        def begin(self):
            return FakeTransaction()

        def dispose(self):
            return None

    monkeypatch.setattr(
        sequence_script.sa,
        "create_engine",
        lambda database_url: FakeEngine(),
    )
    monkeypatch.setattr(
        sequence_script,
        "materialize_action_time_ticket_sequence",
        lambda conn, **kwargs: (
            seen.update(
                {
                    "action_time_invocation_id": kwargs[
                        "action_time_invocation_id"
                    ]
                }
            )
            or {
                "status": "action_time_ticket_sequence_rolled_back",
                "process_outcome": {
                    "process_state": "business_blocked",
                    "business_state": "temporarily_unavailable",
                    "first_blocker": "unit_engineering_blocker",
                },
            }
        ),
    )

    assert sequence_script.main(
        [
            "--database-url",
            "sqlite://",
            "--allow-non-postgres-for-test",
            "--action-time-invocation-id",
            "action_time_invocation:unit",
        ]
    ) == 0
    assert seen["action_time_invocation_id"] == "action_time_invocation:unit"


def test_sequence_cli_prefetches_full_account_snapshot_only_for_active_policy(
    monkeypatch,
):
    seen: dict[str, object] = {}

    class FakeTransaction:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def rollback(self):
            return None

    class FakeEngine:
        def connect(self):
            return FakeTransaction()

        def begin(self):
            return FakeTransaction()

        def dispose(self):
            return None

    snapshot = FullAccountRiskSnapshot(
        snapshot_ready=True,
        account_id="account-1",
        exchange_id="binance_usdm",
        total_wallet_balance=Decimal("600"),
        available_balance=Decimal("500"),
        exchange_total_initial_margin=Decimal("100"),
        can_trade=True,
        position_mode="one_way",
        source_snapshot_id="snapshot-1",
        observed_at_ms=NOW_MS,
        valid_until_ms=NOW_MS + 60_000,
    )
    monkeypatch.setattr(sequence_script.sa, "create_engine", lambda _dsn: FakeEngine())
    monkeypatch.setattr(
        sequence_script,
        "_active_account_risk_scope",
        lambda _conn, **_kwargs: sequence_script._ActiveAccountRiskScope(
            account_id="account-1",
            runtime_profile_id="profile-1",
            exchange_id="binance_usdm",
        ),
    )
    monkeypatch.setattr(
        sequence_script,
        "_fetch_account_risk_snapshot",
        lambda **kwargs: seen.update({"scope": kwargs["scope"]}) or snapshot,
    )
    monkeypatch.setattr(
        sequence_script,
        "materialize_action_time_ticket_sequence",
        lambda _conn, **kwargs: (
            seen.update(kwargs)
            or {
                "status": "action_time_ticket_sequence_rolled_back",
                "process_outcome": {
                    "process_state": "business_blocked",
                    "business_state": "temporarily_unavailable",
                    "first_blocker": "unit_blocker",
                },
            }
        ),
    )

    assert sequence_script.main(
        [
            "--database-url",
            "postgresql+psycopg://unit",
            "--action-time-invocation-id",
            "action_time_invocation:unit",
        ]
    ) == 0
    assert seen["prefetched_account_snapshot"] == snapshot
    assert seen["scope"].account_id == "account-1"
from tests.unit.test_pg_promotion_action_time_lane_materialization import (
    NOW_MS,
    _candidate_runtime_row,
    _fact_values,
    _insert_ready_fresh_signal,
    pg_control_connection,
)
from tests.unit.test_action_time_invocation import invocation_pg_control_connection


def _bind_fresh_invocation_account_facts(
    conn,
    *,
    action_time_invocation_id: str,
    observed_at_ms: int,
    enable_account_capacity_base: bool = False,
) -> list[str]:
    observed_at = datetime.fromtimestamp(
        observed_at_ms / 1000,
        tz=timezone.utc,
    ).isoformat()
    return write_account_safe_fact_snapshots(
        conn,
        artifact={
            "generated_at_utc": observed_at,
            "source_status": "unit_readonly_account_fact",
            "checks": {
                "account_safe_facts_ready": True,
                "account_safe": True,
                "account_trade_permission": True,
                "account_capacity_base_ready": enable_account_capacity_base,
                "account_capacity_base_safe": enable_account_capacity_base,
                "open_orders_clear": True,
                "active_position_or_open_order_clear": True,
                "action_time_available_balance": True,
                "source_signed_get_only": True,
                "source_exchange_write_called": False,
                "source_order_created": False,
            },
            "facts": {
                "total_wallet_balance": "100",
                "available_balance": "100",
                "account_capacity_base": {
                    "account_capacity_source_snapshot_id": "account-snapshot-1",
                    "observed_at_ms": observed_at_ms,
                    "valid_until_ms": observed_at_ms + 600_000,
                    "snapshot_complete": True,
                    "can_trade": True,
                    "total_wallet_balance": "100",
                    "available_balance": "100",
                },
                "account_capacity_base_safe": enable_account_capacity_base,
                "exchange_max_leverage_by_symbol": {"ETHUSDT": 100},
            },
            "account_mode": {
                "status": "fresh",
                "account_id": "owner-subaccount-runtime-v0",
                "exchange_id": "binance_usdm",
                "runtime_profile_id": "owner-runtime-console-v1",
                "account_mode": "one_way",
                "dual_side_position": False,
                "position_mode_safe": True,
                "observed_at": observed_at,
                "source": "binance_usdm_signed_get:/fapi/v1/positionSide/dual",
            },
        },
        source_ref="unit:invocation-bound-account-facts",
        action_time_invocation_id=action_time_invocation_id,
    )


def _install_allowed_atomic_capacity(
    conn,
    *,
    exchange_instrument_id: str,
) -> AccountCapacityReservationResult:
    conn.execute(text("""
      UPDATE brc_exchange_instruments
      SET instrument_type = 'perpetual', settlement_asset = 'USDT',
          margin_asset = 'USDT', instrument_identity_schema_version = 'v1'
      WHERE exchange_instrument_id = :exchange_instrument_id
    """), {"exchange_instrument_id": exchange_instrument_id})
    conn.execute(text("""
      INSERT INTO brc_instrument_rule_snapshots (
        instrument_rule_snapshot_id, exchange_instrument_id, rule_schema_version,
        price_tick, quantity_step, min_qty, min_notional, contract_multiplier,
        exchange_max_leverage_for_claim_notional, source_fact_snapshot_id,
        valid_until_ms, risk_calculation_kind, semantic_hash, status, created_at_ms
      ) VALUES (
        'rule-eth-v2', :exchange_instrument_id, 'v2', .01, .001, .001, 5, 1,
        100, 'rule-source-eth', :valid_until_ms, 'linear_quote_settled', :semantic_hash,
        'current', :now_ms
      )
    """), {
        "exchange_instrument_id": exchange_instrument_id,
        "valid_until_ms": NOW_MS + 600_000,
        "now_ms": NOW_MS,
        "semantic_hash": instrument_rule_snapshot_v2_semantic_hash({
            "instrument_rule_snapshot_id": "rule-eth-v2",
            "rule_schema_version": "v2",
            "price_tick": Decimal(".01"),
            "quantity_step": Decimal(".001"),
            "min_qty": Decimal(".001"),
            "min_notional": Decimal("5"),
            "contract_multiplier": Decimal("1"),
            "exchange_max_leverage_for_claim_notional": 100,
            "source_fact_snapshot_id": "rule-source-eth",
            "valid_until_ms": NOW_MS + 600_000,
            "risk_calculation_kind": "linear_quote_settled",
        }),
    })
    conn.execute(text("""
      INSERT INTO brc_risk_cluster_membership_snapshots (
        cluster_membership_snapshot_id, risk_policy_version,
        primary_risk_cluster_id, semantic_hash, status, created_at_ms
      ) VALUES (
        'cluster-eth-v1', 'risk-policy-v1', 'crypto_usd_beta',
        'cluster-hash-eth', 'current', :now_ms
      )
    """), {"now_ms": NOW_MS})
    instrument_row = conn.execute(text("""
      SELECT exchange_id, exchange_symbol, asset_class
      FROM brc_exchange_instruments
      WHERE exchange_instrument_id = :exchange_instrument_id
    """), {"exchange_instrument_id": exchange_instrument_id}).mappings().one()
    facts = InstrumentRiskFacts(
        identity=InstrumentRiskIdentity(
            exchange_instrument_id=exchange_instrument_id,
            exchange_id=str(instrument_row["exchange_id"]),
            exchange_symbol=str(instrument_row["exchange_symbol"]),
            asset_class=str(instrument_row["asset_class"]),
            instrument_type="perpetual",
            settlement_asset="USDT",
            margin_asset="USDT",
            instrument_identity_schema_version="v1",
        ),
        rule_snapshot=InstrumentRuleSnapshotRefV2(
            instrument_rule_snapshot_id="rule-eth-v2",
            rule_schema_version="v2",
            price_tick=Decimal(".01"),
            quantity_step=Decimal(".001"),
            min_qty=Decimal(".001"),
            min_notional=Decimal("5"),
            contract_multiplier=Decimal("1"),
            exchange_max_leverage_for_claim_notional=100,
            source_fact_snapshot_id="rule-source-eth",
            valid_until_ms=NOW_MS + 600_000,
            risk_calculation_kind="linear_quote_settled",
            semantic_hash=instrument_rule_snapshot_v2_semantic_hash({
                "instrument_rule_snapshot_id": "rule-eth-v2",
                "rule_schema_version": "v2",
                "price_tick": Decimal(".01"),
                "quantity_step": Decimal(".001"),
                "min_qty": Decimal(".001"),
                "min_notional": Decimal("5"),
                "contract_multiplier": Decimal("1"),
                "exchange_max_leverage_for_claim_notional": 100,
                "source_fact_snapshot_id": "rule-source-eth",
                "valid_until_ms": NOW_MS + 600_000,
                "risk_calculation_kind": "linear_quote_settled",
            }),
        ),
        cluster_snapshot=RiskClusterMembershipSnapshotRef(
            cluster_membership_snapshot_id="cluster-eth-v1",
            primary_risk_cluster_id="crypto_usd_beta",
            semantic_hash="cluster-hash-eth",
        ),
    )
    return AccountCapacityReservationResult(
        allowed=True,
        allocated_risk=Decimal(".6"),
        intended_qty=Decimal(".003"),
        selected_leverage=10,
        reserved_margin=Decimal(".6"),
        claimed_projection_version=2,
        account_risk_policy_version="risk-policy-v1",
        account_risk_policy_event_id="risk-policy-event-1",
        risk_cluster_id="crypto_usd_beta",
        exchange_instrument_id=exchange_instrument_id,
        instrument_rule_snapshot_id="rule-eth-v2",
        cluster_membership_snapshot_id="cluster-eth-v1",
        instrument_facts=facts,
        account_source_fact_snapshot_id="account-snapshot-1",
        account_fact_schema_version="brc.account-risk-snapshot.v1",
    )


def test_sequence_commits_fact_reservation_lane_and_ticket_as_one_unit(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=publisher.publish_action_time_pretrade_readiness,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_committed"
    assert payload["projection"]["status"] == (
        "action_time_pretrade_readiness_published"
    )
    assert payload["ticket"]["status"] == "action_time_ticket_created"
    assert _count(
        pg_control_connection,
        "brc_runtime_fact_snapshots",
        "fact_surface = 'action_time'",
    ) == 1
    assert _count(pg_control_connection, "brc_promotion_candidates") == 1
    assert _count(pg_control_connection, "brc_budget_reservations") == 1
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1
    budget = pg_control_connection.execute(
        text(
            """
            SELECT status, ticket_id, intended_qty, risk_at_stop
            FROM brc_budget_reservations
            """
        )
    ).mappings().one()
    assert budget["status"] == "consumed"
    assert budget["ticket_id"] == payload["ticket"]["ticket_id"]
    assert float(budget["intended_qty"]) > 0
    assert float(budget["risk_at_stop"]) > 0


def test_invocation_sequence_uses_exact_post_opening_facts_and_ignores_other_signal(
    invocation_pg_control_connection,
):
    """The Ticket path must never reselect from generic readiness at action time."""

    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    signal_a = "signal:SOR-001:ETHUSDT:long:unit"
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id=signal_a,
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )

    # Remove A's generic read-model row.  B remains a fresh eligible signal
    # with a generic readiness row, so a global selector would deterministically
    # be able to choose the wrong source instead of A.
    candidate_a = _candidate_runtime_row(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
    )
    invocation_pg_control_connection.execute(
        text(
            """
            DELETE FROM brc_pretrade_readiness_rows
            WHERE candidate_scope_id = :candidate_scope_id
            """
        ),
        {"candidate_scope_id": candidate_a["candidate_scope_id"]},
    )
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "BRF2-001",
        "BTCUSDT",
        "short",
        insert_action_time_fact=False,
    )

    report = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
    )

    assert report["status"] == "action_time_ticket_sequence_committed", report[
        "blockers"
    ]
    assert report["projection"] == {}
    assert report["ticket"]["ticket_id"]
    assert invocation_pg_control_connection.execute(
        text(
            """
            SELECT signal_event_id
            FROM brc_action_time_tickets
            """
        )
    ).scalar_one() == signal_a
    assert invocation_pg_control_connection.execute(
        text(
            """
            SELECT COUNT(*)
            FROM brc_promotion_candidates
            WHERE signal_event_id = 'signal:BRF2-001:BTCUSDT:short:unit'
            """
        )
    ).scalar_one() == 0
    bound_invocation = load_action_time_invocation(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
    )
    assert bound_invocation.action_time_fact_snapshot_id
    assert bound_invocation.ticket_id == report["ticket"]["ticket_id"]
    outcome = invocation_pg_control_connection.execute(
        text(
            """
            SELECT scope_kind, action_time_invocation_id, lane_identity_key,
                   source_watermark, runtime_profile_id, policy_current_id,
                   time_authority
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence'
            """
        )
    ).mappings().one()
    assert outcome == {
        "scope_kind": "runtime_lane",
        "action_time_invocation_id": invocation.action_time_invocation_id,
        "lane_identity_key": invocation.lane_identity.identity_key,
        "source_watermark": invocation.source_watermark,
        "runtime_profile_id": invocation.lane_identity.runtime_profile_id,
        "policy_current_id": invocation.lane_identity.policy_current_id,
        "time_authority": invocation.lane_identity.time_authority,
    }


def test_invocation_sequence_rolls_back_before_lane_when_prefetched_capacity_blocks(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection, "SOR-001", "ETHUSDT", "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )

    report = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
        prefetched_account_capacity=AccountCapacityReservationResult(
            allowed=False,
            first_blocker="account_budget_current_stale",
        ),
    )

    assert report["status"] == "action_time_ticket_sequence_rolled_back"
    assert report["blockers"] == ["account_budget_current_stale"]
    assert _count(invocation_pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(invocation_pg_control_connection, "brc_budget_reservations") == 0
    assert _count(invocation_pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(invocation_pg_control_connection, "brc_action_time_tickets") == 0


def test_capacity_fact_without_active_policy_reports_policy_gap_not_legacy_account_failure(
    invocation_pg_control_connection,
):
    """Capacity observations cannot silently become legacy account authority."""

    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
        enable_account_capacity_base=True,
    )

    report = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
    )

    assert report["status"] == "action_time_ticket_sequence_rolled_back"
    assert report["blockers"] == ["account_risk_policy_missing_or_changed"]
    assert _count(invocation_pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(invocation_pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(invocation_pg_control_connection, "brc_action_time_tickets") == 0


def test_invocation_sequence_commits_one_sealed_claim_ticket_and_episode(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )
    capacity = _install_allowed_atomic_capacity(
        invocation_pg_control_connection,
        exchange_instrument_id=invocation.lane_identity.exchange_instrument_id,
    )

    report = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
        prefetched_account_capacity=capacity,
    )

    assert report["status"] == "action_time_ticket_sequence_committed", report[
        "blockers"
    ]
    claim = invocation_pg_control_connection.execute(text("""
      SELECT budget_reservation_id, ticket_id, exposure_episode_id,
             action_time_invocation_id, capacity_claim_hash
      FROM brc_budget_reservations
    """)).mappings().one()
    ticket = invocation_pg_control_connection.execute(text("""
      SELECT ticket_id, budget_reservation_id, exposure_episode_id,
             action_time_invocation_id, capacity_claim_hash
      FROM brc_action_time_tickets
    """)).mappings().one()
    assert claim["ticket_id"] == ticket["ticket_id"]
    assert claim["budget_reservation_id"] == ticket["budget_reservation_id"]
    assert claim["exposure_episode_id"] == ticket["exposure_episode_id"]
    assert claim["action_time_invocation_id"] == ticket["action_time_invocation_id"]
    assert claim["capacity_claim_hash"] == ticket["capacity_claim_hash"]
    assert claim["capacity_claim_hash"]


def test_ticket_insert_failure_rolls_back_claim_and_lineage(
    invocation_pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )
    capacity = _install_allowed_atomic_capacity(
        invocation_pg_control_connection,
        exchange_instrument_id=invocation.lane_identity.exchange_instrument_id,
    )
    monkeypatch.setattr(
        promotion_subject,
        "materialize_action_time_ticket",
        lambda *_args, **_kwargs: {
            "status": "action_time_ticket_materialization_blocked",
            "blockers": ["forced_ticket_composite_lineage_failure"],
        },
    )

    report = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
        prefetched_account_capacity=capacity,
    )

    assert report["status"] == "action_time_ticket_sequence_rolled_back"
    assert report["blockers"] == ["forced_ticket_composite_lineage_failure"]
    assert _count(invocation_pg_control_connection, "brc_budget_reservations") == 0
    assert _count(invocation_pg_control_connection, "brc_action_time_tickets") == 0
    assert _count(invocation_pg_control_connection, "brc_action_time_lane_inputs") == 0


def test_repeated_sealed_invocation_reuses_single_claim_and_ticket(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )
    capacity = _install_allowed_atomic_capacity(
        invocation_pg_control_connection,
        exchange_instrument_id=invocation.lane_identity.exchange_instrument_id,
    )

    first = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
        prefetched_account_capacity=capacity,
    )
    repeated = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 3,
        completion_clock_ms=lambda: NOW_MS + 4,
        prefetched_account_capacity=capacity,
    )

    assert first["status"] == "action_time_ticket_sequence_committed"
    assert repeated["status"] == "action_time_ticket_sequence_committed"
    assert _count(invocation_pg_control_connection, "brc_budget_reservations") == 1
    assert _count(invocation_pg_control_connection, "brc_action_time_tickets") == 1
    assert _count(invocation_pg_control_connection, "brc_action_time_lane_inputs") == 1
    sealed = invocation_pg_control_connection.execute(text("""
      SELECT action_time_invocation_id, capacity_claim_hash
      FROM brc_budget_reservations
    """)).mappings().one()
    assert sealed["action_time_invocation_id"] == invocation.action_time_invocation_id
    assert sealed["capacity_claim_hash"]


def test_repeated_invocation_after_ticket_exists_is_terminal_noop(
    invocation_pg_control_connection,
):
    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )
    first = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
    )
    assert first["status"] == "action_time_ticket_sequence_committed"
    invocation_pg_control_connection.execute(
        text(
            "UPDATE brc_action_time_tickets "
            "SET status = 'expired', expires_at_ms = :expired_at_ms"
        ),
        {"expired_at_ms": NOW_MS + 2},
    )
    invocation_pg_control_connection.execute(
        text(
            "UPDATE brc_action_time_lane_inputs "
            "SET status = 'expired', expires_at_ms = :expired_at_ms, "
            "closed_at_ms = :closed_at_ms"
        ),
        {"expired_at_ms": NOW_MS + 2, "closed_at_ms": NOW_MS + 3},
    )

    repeated = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 3,
        completion_clock_ms=lambda: NOW_MS + 4,
    )

    assert repeated["status"] == (
        "action_time_ticket_sequence_signal_already_processed"
    ), repeated
    assert repeated["blockers"] == []
    assert repeated["process_outcome"]["process_state"] == "noop"
    assert repeated["process_outcome"]["first_blocker"] is None
    assert _count(invocation_pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(invocation_pg_control_connection, "brc_action_time_tickets") == 1


def test_invocation_sequence_rejects_coverage_from_a_different_runtime_lane(
    invocation_pg_control_connection,
):
    """Display-level coverage cannot certify an Invocation after lane drift."""

    _insert_ready_fresh_signal(
        invocation_pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    invocation = start_action_time_invocation(
        invocation_pg_control_connection,
        signal_event_id="signal:SOR-001:ETHUSDT:long:unit",
        opened_at_ms=NOW_MS,
    )
    _bind_fresh_invocation_account_facts(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        observed_at_ms=NOW_MS + 1,
    )
    mismatched_identity = invocation.lane_identity.model_copy(
        update={"runtime_instance_id": "runtime:unit:wrong-lane"}
    )
    invocation_pg_control_connection.execute(
        text(
            """
            UPDATE brc_watcher_runtime_coverage
            SET runtime_instance_id = :runtime_instance_id,
                lane_identity_key = :lane_identity_key
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
              AND is_current = true
            """
        ),
        {
            "runtime_instance_id": mismatched_identity.runtime_instance_id,
            "lane_identity_key": mismatched_identity.identity_key,
        },
    )

    report = materialize_action_time_ticket_sequence(
        invocation_pg_control_connection,
        action_time_invocation_id=invocation.action_time_invocation_id,
        stage_at_ms=NOW_MS + 1,
        completion_clock_ms=lambda: NOW_MS + 2,
    )

    assert report["status"] == "action_time_ticket_sequence_rolled_back"
    assert "runtime_lane_identity_mismatch:invocation_to_coverage" in report[
        "blockers"
    ]
    assert _count(invocation_pg_control_connection, "brc_action_time_tickets") == 0


def test_sequence_rolls_back_all_action_rows_when_ticket_blocks(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_ticket_blocker"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == ["unit_ticket_blocker"]
    assert _count(
        pg_control_connection,
        "brc_runtime_fact_snapshots",
        "fact_surface = 'action_time'",
    ) == 0
    assert _count(pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_action_time_tickets") == 0
    outcome = _sequence_outcome(pg_control_connection)
    assert outcome["scope_key"] == "lane:SOR-001:ETHUSDT:long"
    assert outcome["first_blocker"] == "unit_ticket_blocker"
    assert outcome["business_state"] == "temporarily_unavailable"


def test_fresh_signal_can_recertify_and_clear_previous_lane_engineering_blocker(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    blocked = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=lambda conn: (
            publisher.publish_runtime_control_current_projections(
                conn,
                target_runtime_head="a" * 40,
            )
        ),
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_repairable_ticket_blocker"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )
    assert blocked["status"] == "action_time_ticket_sequence_rolled_back"
    owner_projection = publisher.publish_runtime_control_current_projections(
        pg_control_connection,
        target_runtime_head="a" * 40,
    )
    assert owner_projection["status"] == "current_projections_published"
    visible_blocker = pg_control_connection.execute(
        text(
            """
            SELECT first_blocker_class, first_blocker_detail
            FROM brc_pretrade_readiness_rows
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).mappings().one()
    assert visible_blocker["first_blocker_class"] == (
        "action_time_boundary_not_reproduced"
    )
    assert "unit_repairable_ticket_blocker" in visible_blocker[
        "first_blocker_detail"
    ]
    control_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 2,
    ).read_monitor_control_state()
    assert len(control_state["live_signal_events"]) == 1
    assert set(candidate_pool._unresolved_action_time_sequence_outcomes(control_state)) == {
        ("SOR-001", "ETHUSDT", "long")
    }
    monkeypatch.setattr(publisher.time, "time", lambda: (NOW_MS + 2) / 1000)

    repaired = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS + 2,
        projection_publisher=lambda conn: (
            publisher.publish_runtime_control_current_projections(
                conn,
                target_runtime_head="a" * 40,
            )
        ),
        completion_clock_ms=lambda: NOW_MS + 3,
    )

    assert repaired["status"] == "action_time_ticket_sequence_committed", repaired
    outcome = _sequence_outcome(pg_control_connection)
    assert outcome["process_state"] == "succeeded"
    assert outcome["first_blocker"] is None


def test_sequence_persists_each_blocked_lane_when_multiple_signals_fail_facts(
    pg_control_connection,
    monkeypatch,
):
    cases = [
        ("CPM-RO-001", "ETHUSDT", "long", "ask_price"),
        ("BRF2-001", "BTCUSDT", "short", "bid_price"),
    ]
    for strategy_group_id, symbol, side, missing_quote in cases:
        row = _candidate_runtime_row(
            pg_control_connection,
            strategy_group_id,
            symbol,
            side,
        )
        values = _fact_values(pg_control_connection, row)
        values.update(
            {
                "public_facts_ready": True,
                "mark_price_fresh": True,
                "spread_ok": True,
                "min_notional_ok": True,
                "qty_step_ok": True,
                "facts": {
                    "mark_price": "100",
                    "bid_price": "99.9",
                    "ask_price": "100.1",
                    "qty_step": "0.001",
                    "min_notional": "5",
                },
            }
        )
        values["facts"][missing_quote] = None
        _insert_ready_fresh_signal(
            pg_control_connection,
            strategy_group_id,
            symbol,
            side,
            insert_action_time_fact=False,
            fact_values=values,
        )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    outcomes = pg_control_connection.execute(
        text(
            """
            SELECT scope_key, first_blocker
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence_batch'
              AND scope_key LIKE 'lane:%'
            ORDER BY scope_key
            """
        )
    ).mappings().all()
    assert {row["scope_key"] for row in outcomes} == {
        "lane:CPM-RO-001:ETHUSDT:long",
        "lane:BRF2-001:BTCUSDT:short",
    }
    assert len(payload["process_outcomes"]) == 2
    monkeypatch.setattr(publisher.time, "time", lambda: NOW_MS / 1000)
    owner_projection = publisher.publish_runtime_control_current_projections(
        pg_control_connection,
        target_runtime_head="a" * 40,
    )
    assert owner_projection["status"] == "current_projections_published"
    readiness_details = {
        (
            row["strategy_group_id"],
            row["symbol"],
            row["side"],
        ): row["first_blocker_detail"]
        for row in pg_control_connection.execute(
            text(
                """
                SELECT strategy_group_id, symbol, side, first_blocker_detail
                FROM brc_pretrade_readiness_rows
                WHERE strategy_group_id IN ('CPM-RO-001', 'BRF2-001')
                """
            )
        ).mappings()
    }
    assert "action_time_ask_price_invalid" in readiness_details[
        ("CPM-RO-001", "ETHUSDT", "long")
    ]
    assert "action_time_bid_price_invalid" in readiness_details[
        ("BRF2-001", "BTCUSDT", "short")
    ]


def test_sequence_clears_repaired_arbitration_loser_without_opening_second_lane(
    pg_control_connection,
):
    cases = [
        ("CPM-RO-001", "ETHUSDT", "long"),
        ("BRF2-001", "BTCUSDT", "short"),
    ]
    for strategy_group_id, symbol, side in cases:
        _insert_ready_fresh_signal(
            pg_control_connection,
            strategy_group_id,
            symbol,
            side,
            insert_action_time_fact=False,
        )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_committed"
    outcomes = {
        row["scope_key"]: row
        for row in payload["process_outcomes"]
        if row["scope_key"].startswith("lane:")
    }
    assert set(outcomes) == {
        "lane:CPM-RO-001:ETHUSDT:long",
        "lane:BRF2-001:BTCUSDT:short",
    }
    assert {row["process_state"] for row in outcomes.values()} == {"succeeded"}
    assert {row["business_state"] for row in outcomes.values()} == {
        "completed",
        "processing",
    }
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 1
    assert _count(pg_control_connection, "brc_action_time_tickets") == 1


def test_terminal_promotion_blocker_cannot_be_hidden_by_candidate_success_outcomes(
    pg_control_connection,
):
    terminal_blocker = "terminal_promotion_identity_reuse:promotion-existing"
    candidates = [
        {
            "strategy_group_id": "CPM-RO-001",
            "symbol": "SUIUSDT",
            "side": "long",
            "signal_event_id": "signal-cpm-sui",
            "status": "arbitration_lost",
            "blockers": [],
        },
        {
            "strategy_group_id": "MPG-001",
            "symbol": "SUIUSDT",
            "side": "long",
            "signal_event_id": "signal-mpg-sui",
            "status": "arbitration_lost",
            "blockers": [],
        },
    ]

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        fact_materializer=lambda conn, now_ms: {
            "status": "action_time_fact_snapshots_materialized",
            "materialized": candidates,
            "blocked": [],
            "blockers": [],
        },
        promotion_materializer=lambda conn, now_ms: {
            "status": "terminal_action_time_identity_not_reopened",
            "blockers": [terminal_blocker],
            "per_candidate_results": candidates,
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    outcomes = {
        row["scope_key"]: row
        for row in payload["process_outcomes"]
        if row["scope_key"].startswith("lane:")
    }
    assert set(outcomes) == {
        "lane:CPM-RO-001:SUIUSDT:long",
        "lane:MPG-001:SUIUSDT:long",
    }
    assert {row["process_state"] for row in outcomes.values()} == {
        "business_blocked"
    }
    assert {row["business_state"] for row in outcomes.values()} == {
        "temporarily_unavailable"
    }
    assert {row["first_blocker"] for row in outcomes.values()} == {
        terminal_blocker
    }


def test_sequence_rolls_back_when_shortest_ttl_expires_before_commit(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "short",
        insert_action_time_fact=False,
    )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 600_000,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == [
        "action_time_sequence_ttl_expired_before_ticket_commit"
    ]
    assert _count(pg_control_connection, "brc_promotion_candidates") == 0
    assert _count(pg_control_connection, "brc_budget_reservations") == 0
    assert _count(pg_control_connection, "brc_action_time_lane_inputs") == 0
    assert _count(pg_control_connection, "brc_action_time_tickets") == 0
    assert _sequence_outcome(pg_control_connection)["first_blocker"] == (
        "action_time_sequence_ttl_expired_before_ticket_commit"
    )


def test_sequence_exception_outcome_masks_exception_message(
    pg_control_connection,
):
    def fail_with_sensitive_detail(conn, *, now_ms):
        _ = conn, now_ms
        raise RuntimeError("secret-token-must-not-enter-runtime-state")

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        fact_materializer=fail_with_sensitive_detail,
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == ["action_time_sequence_exception:RuntimeError"]
    assert payload["process_outcome"]["process_state"] == "retryable_failure"
    assert "secret-token" not in json.dumps(payload, default=str)


def test_readiness_projection_failure_is_process_failure_not_business_blocker(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )

    payload = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=lambda conn: {"status": "unit_projection_failed"},
        completion_clock_ms=lambda: NOW_MS + 1,
    )

    assert payload["status"] == "action_time_ticket_sequence_rolled_back"
    assert payload["blockers"] == [
        "action_time_current_projection_publish_failed"
    ]
    assert payload["process_outcome"]["process_state"] == "retryable_failure"


def test_expired_signal_preserves_unresolved_action_time_engineering_blocker(
    pg_control_connection,
    monkeypatch,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    blocked = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_persisted_engineering_blocker"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )
    assert blocked["status"] == "action_time_ticket_sequence_rolled_back"
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET freshness_state = 'expired', expires_at_ms = :expired_at_ms
            """
        ),
        {"expired_at_ms": NOW_MS - 1},
    )

    waiting = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS + 2,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 3,
    )

    assert waiting["status"] == "no_current_fresh_live_signal"
    outcomes = pg_control_connection.execute(
        text(
            """
            SELECT scope_key, business_state, first_blocker
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence_batch'
            ORDER BY scope_key
            """
        )
    ).mappings().all()
    assert [row["scope_key"] for row in outcomes] == [
        "global",
        "lane:SOR-001:ETHUSDT:long",
    ]
    lane_outcome = next(row for row in outcomes if row["scope_key"].startswith("lane:"))
    assert lane_outcome["first_blocker"] == "unit_persisted_engineering_blocker"
    assert lane_outcome["business_state"] == "temporarily_unavailable"

    monkeypatch.setattr(publisher.time, "time", lambda: (NOW_MS + 4) / 1000)
    projection = publisher.publish_runtime_control_current_projections(
        pg_control_connection,
        target_runtime_head="a" * 40,
    )
    assert projection["status"] == "current_projections_published"
    readiness = pg_control_connection.execute(
        text(
            """
            SELECT first_blocker_class, first_blocker_detail
            FROM brc_pretrade_readiness_rows
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).mappings().one()
    assert readiness["first_blocker_class"] == (
        "action_time_boundary_not_reproduced"
    )
    assert readiness["first_blocker_detail"] == (
        "unit_persisted_engineering_blocker"
    )

    snapshots = pg_control_connection.execute(
        text(
            """
            SELECT model_type, payload
            FROM brc_control_read_model_snapshots
            WHERE model_type IN (
              'candidate_pool', 'daily_live_enablement_table', 'goal_status'
            )
              AND is_current = true
            """
        )
    ).mappings().all()
    assert {row["model_type"] for row in snapshots} == {
        "candidate_pool",
        "daily_live_enablement_table",
        "goal_status",
    }
    for row in snapshots:
        payload = row["payload"]
        while isinstance(payload, str):
            payload = json.loads(payload)
        rendered = json.dumps(payload, sort_keys=True)
        assert "unit_persisted_engineering_blocker" in rendered, row["model_type"]


def test_distinct_same_lane_signal_keeps_blocker_until_new_sequence_succeeds(
    pg_control_connection,
):
    _insert_ready_fresh_signal(
        pg_control_connection,
        "SOR-001",
        "ETHUSDT",
        "long",
        insert_action_time_fact=False,
    )
    old_signal = pg_control_connection.execute(
        text(
            """
            SELECT signal_event_id, runtime_instance_id, signal_payload
            FROM brc_live_signal_events
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).mappings().one()
    old_signal_id = str(old_signal["signal_event_id"])
    blocked = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS,
        projection_publisher=_projection_ready,
        ticket_materializer=lambda conn, now_ms: {
            "status": "blocked",
            "blockers": ["unit_signal_a_ticket_failure"],
            "strategy_group_id": "SOR-001",
            "symbol": "ETHUSDT",
            "side": "long",
        },
        completion_clock_ms=lambda: NOW_MS + 1,
    )
    assert blocked["status"] == "action_time_ticket_sequence_rolled_back"
    lane_outcome = next(
        row
        for row in blocked["process_outcomes"]
        if row["scope_key"] == "lane:SOR-001:ETHUSDT:long"
    )
    assert lane_outcome["source_watermark"] == old_signal_id

    new_signal_id = f"{old_signal_id}:distinct"
    new_event_time_ms = NOW_MS + 1_000
    source_watermark = (
        f"{old_signal['runtime_instance_id']}:{new_event_time_ms}"
    )
    signal_payload = old_signal["signal_payload"]
    while isinstance(signal_payload, str):
        signal_payload = json.loads(signal_payload)
    signal_payload = dict(signal_payload)
    signal_payload["source_watermark"] = source_watermark
    pg_control_connection.execute(
        text(
            """
            INSERT INTO brc_live_signal_events (
              signal_event_id, candidate_scope_id, candidate_scope_event_binding_id,
              runtime_scope_binding_id, runtime_instance_id, runtime_profile_id,
              policy_current_id, strategy_group_version_id, asset_class,
              exchange_instrument_id,
              event_spec_id, event_spec_version, event_id, timeframe, time_authority,
              lane_identity_key, source_watermark,
              strategy_group_id, symbol, side, detector_key, signal_type,
              source_kind, status, freshness_state, confidence,
              fact_snapshot_id, reason_codes, signal_payload,
              signal_grade, required_execution_mode, execution_eligible,
              authority_source_ref,
              event_time_ms, trigger_candle_close_time_ms, observed_at_ms,
              expires_at_ms, invalidated_at_ms, created_at_ms
            )
            SELECT
              :new_signal_id, candidate_scope_id, candidate_scope_event_binding_id,
              runtime_scope_binding_id, runtime_instance_id, runtime_profile_id,
              policy_current_id, strategy_group_version_id, asset_class,
              exchange_instrument_id,
              event_spec_id, event_spec_version, event_id, timeframe, time_authority,
              lane_identity_key, :source_watermark,
              strategy_group_id, symbol, side, detector_key, signal_type,
              source_kind, 'facts_validated', 'fresh', confidence,
              fact_snapshot_id, reason_codes, :signal_payload,
              signal_grade, required_execution_mode, execution_eligible,
              authority_source_ref,
              :event_time_ms, :event_time_ms, :observed_at_ms,
              :expires_at_ms, NULL, :created_at_ms
            FROM brc_live_signal_events
            WHERE signal_event_id = :old_signal_id
            """
        ),
        {
            "new_signal_id": new_signal_id,
            "old_signal_id": old_signal_id,
            "event_time_ms": new_event_time_ms,
            "observed_at_ms": NOW_MS + 2_000,
            "created_at_ms": NOW_MS + 2_000,
            "expires_at_ms": NOW_MS + 600_000,
            "source_watermark": source_watermark,
            "signal_payload": json.dumps(signal_payload, sort_keys=True),
        },
    )
    pg_control_connection.execute(
        text(
            """
            UPDATE brc_live_signal_events
            SET status = 'stale',
                freshness_state = 'expired',
                expires_at_ms = :expires_at_ms
            WHERE signal_event_id = :old_signal_id
            """
        ),
        {"old_signal_id": old_signal_id, "expires_at_ms": NOW_MS - 1},
    )

    control_state = PgBackedRuntimeControlStateRepository(
        pg_control_connection,
        now_ms=NOW_MS + 10_000,
    ).read_monitor_control_state()
    unresolved = candidate_pool._unresolved_action_time_sequence_outcomes(
        control_state
    )
    assert unresolved[("SOR-001", "ETHUSDT", "long")]["first_blocker"] == (
        "unit_signal_a_ticket_failure"
    )

    resumed = materialize_action_time_ticket_sequence(
        pg_control_connection,
        now_ms=NOW_MS + 10_000,
        projection_publisher=_projection_ready,
        completion_clock_ms=lambda: NOW_MS + 10_001,
    )

    assert resumed["status"] == "action_time_ticket_sequence_committed", resumed[
        "blockers"
    ]
    assert pg_control_connection.execute(
        text(
            """
            SELECT signal_event_id
            FROM brc_action_time_tickets
            WHERE strategy_group_id = 'SOR-001'
              AND symbol = 'ETHUSDT'
              AND side = 'long'
            """
        )
    ).scalar_one() == new_signal_id


def _projection_ready(conn):
    _ = conn
    return {"status": "current_projections_published"}


def _sequence_outcome(conn):
    return conn.execute(
        text(
            """
            SELECT scope_key, process_state, business_state, first_blocker
            FROM brc_runtime_process_outcomes
            WHERE process_name = 'action_time_ticket_sequence_batch'
              AND scope_key LIKE 'lane:%'
            """
        )
    ).mappings().one()


def _count(conn, table_name: str, where: str = "1 = 1") -> int:
    assert table_name in {
        "brc_runtime_fact_snapshots",
        "brc_promotion_candidates",
        "brc_budget_reservations",
        "brc_action_time_lane_inputs",
        "brc_action_time_tickets",
    }
    assert where in {"1 = 1", "fact_surface = 'action_time'"}
    return int(
        conn.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {where}")
        ).scalar_one()
    )
