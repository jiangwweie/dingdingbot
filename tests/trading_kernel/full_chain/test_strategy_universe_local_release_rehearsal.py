from __future__ import annotations

import asyncio
from collections.abc import Mapping
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from scripts.trading_kernel.certify_readonly import _certify
from scripts.trading_kernel.promote_entry import promote_entry
from src.trading_kernel.application.strategy_universe_batch_manifest import (
    APPROVED_UNIVERSE_EVENT_SPECS,
)
from tests.trading_kernel.integration.test_entry_promotion_gate import (
    RecordingPromotionBackend,
    _cleanup,
    _seed_and_bootstrap,
)
from tests.trading_kernel.integration.test_strategy_universe_batch_bootstrap import (
    SAFE_DATABASE,
    _database_url,
)
from tests.trading_kernel.unit.detectors.fixtures import NOW_MS


def test_empty_database_rehearsal_reaches_six_active_universes_then_fenced_entry_promotion() -> None:
    """Run the production-shaped local release path without Tokyo or exchange writes."""

    database_name = f"brc_kernel_test_{uuid4().hex[:12]}"
    assert SAFE_DATABASE.fullmatch(database_name)
    database_url = _database_url(database_name)
    promotion_now_ms = NOW_MS + 10_000
    asyncio.run(_seed_and_bootstrap(database_name, database_url))
    try:
        backend = RecordingPromotionBackend(
            database_url=database_url,
            now_ms=promotion_now_ms,
        )

        assert promote_entry(backend) == "promoted"
        certification = asyncio.run(
            _certify(
                database_url,
                require_flat=True,
                now_ms=promotion_now_ms,
            )
        )
        owner_policy = certification["owner_policy"]
        capabilities = certification["capabilities"]
        universe = certification["strategy_universe"]
        universe_identities = asyncio.run(_universe_identity_snapshot(database_url))

        assert certification["status"] == "pass"
        assert certification["universe_bootstrap_pass"] is True
        assert certification["flatness_pass"] is True
        assert isinstance(owner_policy, Mapping)
        assert isinstance(capabilities, Mapping)
        assert isinstance(universe, Mapping)
        assert owner_policy["new_entry_submit_enabled"] is True
        assert capabilities["exchange_commands"] is True
        assert universe["current_count"] == 6
        assert universe["scope_lifecycle_counts"] == {
            "active": 42,
            "warming": 0,
            "retired": 0,
        }
        assert universe_identities == {
            event_spec_id: 7
            for _event_id, event_spec_id in APPROVED_UNIVERSE_EVENT_SPECS
        }
        assert backend.exchange_mutations == []
        assert backend.calls == [
            "preflight",
            "certification",
            "external",
            "safety",
            "arm",
            "start",
            "active_fenced",
            "certification",
            "external",
            "safety",
            "unfence",
            "active",
        ]
    finally:
        asyncio.run(_cleanup(database_name))


async def _universe_identity_snapshot(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    sa.text(
                        "SELECT current.event_spec_id, count(scope.runtime_scope_id) "
                        "FROM brc_strategy_universe_current AS current "
                        "JOIN brc_runtime_scopes_current AS scope "
                        "ON scope.universe_version_id = current.universe_version_id "
                        "AND scope.lifecycle_state = 'active' "
                        "GROUP BY current.event_spec_id "
                        "ORDER BY current.event_spec_id"
                    )
                )
            ).all()
        return {str(event_spec_id): int(scope_count) for event_spec_id, scope_count in rows}
    finally:
        await engine.dispose()
