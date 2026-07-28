from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from src.trading_kernel.application.advance_strategy_universe import (
    UniverseActivationRequest,
    advance_strategy_universe,
)
from src.trading_kernel.infrastructure.pg_unit_of_work import (
    PostgresKernelUnitOfWork,
)
from tests.trading_kernel.integration.universe_activation_support import (
    DIRECT_CONTRACT,
    NOW_MS,
    activation_snapshot,
    make_warming_ready,
    prepare_active_and_warming,
)


@pytest.mark.parametrize(
    "failure_stage",
    ("old_scopes", "new_scopes", "current_pointer"),
)
@pytest.mark.asyncio
async def test_injected_activation_step_failure_rolls_back_every_state_change(
    activation_engine: AsyncEngine,
    failure_stage: str,
) -> None:
    """Catches any partial activation commit after a step-level DB exception."""

    old_version_id, new_version_id = await prepare_active_and_warming(
        activation_engine
    )
    await make_warming_ready(
        activation_engine,
        universe_version_id=new_version_id,
    )
    before = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    function_name = f"fail_task10_{failure_stage}"
    trigger_name = f"trg_task10_{failure_stage}"
    if failure_stage == "old_scopes":
        table_name = "brc_runtime_scopes_current"
        condition = (
            f"OLD.universe_version_id = '{old_version_id}' "
            "AND NEW.lifecycle_state = 'retired'"
        )
    elif failure_stage == "new_scopes":
        table_name = "brc_runtime_scopes_current"
        condition = (
            f"OLD.universe_version_id = '{new_version_id}' "
            "AND NEW.lifecycle_state = 'active'"
        )
    else:
        table_name = "brc_strategy_universe_current"
        condition = "NEW.activation_generation = 2"
    async with activation_engine.begin() as connection:
        await connection.execute(
            sa.text(
                f"""
                CREATE FUNCTION {function_name}()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF {condition} THEN
                        RAISE EXCEPTION
                            'task 10 injected {failure_stage} failure';
                    END IF;
                    RETURN NEW;
                END
                $$
                """
            )
        )
        await connection.execute(
            sa.text(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE UPDATE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION {function_name}()
                """
            )
        )

    with pytest.raises(
        DBAPIError,
        match=f"task 10 injected {failure_stage} failure",
    ):
        async with PostgresKernelUnitOfWork(activation_engine) as uow:
            await advance_strategy_universe(
                uow,
                UniverseActivationRequest(
                    universe_version_id=new_version_id,
                    attempted_at_ms=NOW_MS,
                ),
            )

    after = await activation_snapshot(
        activation_engine,
        event_spec_id=DIRECT_CONTRACT.event_spec_id,
    )
    assert after == before
