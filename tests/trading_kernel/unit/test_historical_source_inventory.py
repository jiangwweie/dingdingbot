"""Later schema additions cannot enter an older stopped-upgrade proof."""

import importlib

import pytest
import sqlalchemy as sa

from scripts.trading_kernel import verify_schema


@pytest.mark.parametrize(
    "inventory",
    [
        verify_schema._source_0010_table_columns,
        verify_schema._source_0011_table_columns,
        verify_schema._source_0012_table_columns,
        verify_schema._source_0013_table_columns,
    ],
)
def test_pre_manual_source_inventory_excludes_frozen_0024_additions(inventory):
    migration = importlib.import_module(
        "migrations.trading_kernel.versions.0024_owner_cooperation"
    )
    added = migration._define_frozen_tables(sa.MetaData())
    columns = inventory()
    assert not ({table.name for table in added} & columns.keys())
    assert not (
        {
            "owner_reduction_context",
            "active_stop_close_position",
            "pending_stop_close_position",
            "protection_return_status",
            "protection_operation_id",
            "manual_profit_plan",
        }
        & set(columns["brc_trade_aggregates"])
    )
    assert {"ticket_id", "position_qty", "tp1_filled_qty"} <= set(
        columns["brc_trade_aggregates"]
    )
