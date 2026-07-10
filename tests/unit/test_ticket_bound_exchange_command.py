from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    command_transition_blockers,
    deterministic_client_order_id,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
FOUNDATION_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-04-086_create_pg_runtime_control_state_foundation.py"
)
ELIGIBILITY_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-104_add_execution_eligibility_authority.py"
)
COMMAND_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-10-105_create_ticket_bound_exchange_commands.py"
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_network_timeout_transitions_dispatching_to_outcome_unknown():
    blockers = command_transition_blockers(
        current=ExchangeCommandState.DISPATCHING,
        target=ExchangeCommandState.OUTCOME_UNKNOWN,
        outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
    )

    assert blockers == []


def test_confirmed_rejected_requires_authoritative_rejection():
    blockers = command_transition_blockers(
        current=ExchangeCommandState.DISPATCHING,
        target=ExchangeCommandState.CONFIRMED_REJECTED,
        outcome_class=ExchangeCommandOutcomeClass.NETWORK_AMBIGUOUS,
    )

    assert "confirmed_rejected_requires_authoritative_rejection" in blockers


def test_client_order_id_is_stable_per_ticket_role_generation():
    first = deterministic_client_order_id("ticket-1", "submit-1", "ENTRY", 1)
    second = deterministic_client_order_id("ticket-1", "submit-1", "ENTRY", 1)
    next_generation = deterministic_client_order_id(
        "ticket-1",
        "submit-1",
        "ENTRY",
        2,
    )

    assert first == second
    assert first != next_generation
    assert len(first) <= 36


def test_migration_105_creates_normalized_exchange_command_table():
    foundation = _load_module(FOUNDATION_PATH, "migration_086_exchange_command")
    eligibility = _load_module(ELIGIBILITY_PATH, "migration_104_exchange_command")
    command = _load_module(COMMAND_PATH, "migration_105_exchange_command")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        old_foundation_op = foundation.op
        foundation.op = operations
        try:
            foundation.upgrade()
        finally:
            foundation.op = old_foundation_op

        old_eligibility_op = eligibility.op
        eligibility.op = operations
        try:
            eligibility.upgrade()
        finally:
            eligibility.op = old_eligibility_op

        old_command_op = command.op
        command.op = operations
        try:
            command.upgrade()
        finally:
            command.op = old_command_op

        inspector = sa.inspect(conn)
        columns = {
            column["name"]
            for column in inspector.get_columns(
                "brc_ticket_bound_exchange_commands"
            )
        }
        assert {
            "exchange_command_id",
            "client_order_id",
            "exchange_instrument_id",
            "command_state",
            "request_fingerprint",
            "command_generation",
            "account_id",
            "strategy_group_id",
            "side",
        } <= columns

    engine.dispose()
