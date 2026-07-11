from __future__ import annotations

from sqlalchemy import text

from src.application.action_time.netting_domain_hold import (
    resolve_netting_domain_hold_source,
    upsert_netting_domain_hold,
)
from tests.unit.test_action_time_ticket_materialization import NOW_MS
from tests.unit.test_ticket_bound_runtime_safety_state_materialization import (
    pg_control_connection,
)


def test_resolving_one_domain_hold_never_clears_another_source(
    pg_control_connection,
):
    domain = "account-1|instrument-1|one_way|BOTH"
    for source_id in ("source-a", "source-b"):
        upsert_netting_domain_hold(
            pg_control_connection,
            account_id="account-1",
            runtime_profile_id="profile-1",
            exchange_id="binance_usdm",
            exchange_instrument_id="instrument-1",
            position_mode="one_way",
            position_bucket="BOTH",
            netting_domain_key=domain,
            source_ticket_id="ticket-1",
            strategy_group_id="SOR-001",
            symbol="ETHUSDT",
            side="long",
            source_kind="unit",
            source_id=source_id,
            blockers=["unknown_risk"],
            next_action="reconcile",
            authority_boundary="unit",
            now_ms=NOW_MS,
        )

    resolved = resolve_netting_domain_hold_source(
        pg_control_connection,
        netting_domain_key=domain,
        source_kind="unit",
        source_id="source-a",
        resolution_source="unit-proof",
        now_ms=NOW_MS + 1,
    )

    rows = list(
        pg_control_connection.execute(
            text(
                "SELECT source_id, status FROM brc_ticket_bound_scope_freezes "
                "ORDER BY source_id"
            )
        ).mappings()
    )
    assert resolved == 1
    assert [(row["source_id"], row["status"]) for row in rows] == [
        ("source-a", "resolved"),
        ("source-b", "active"),
    ]
