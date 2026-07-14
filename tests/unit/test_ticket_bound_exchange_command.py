from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from src.domain.ticket_bound_exchange_command import (
    ExchangeCommandOutcomeClass,
    ExchangeCommandState,
    TicketBoundExchangeCommand,
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
TYPED_SCOPE_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-11-113_create_exchange_account_mode_and_domain_holds.py"
)
LIFECYCLE_COMMAND_PATH = (
    REPO_ROOT
    / "migrations/versions/2026-07-11-114_extend_exchange_commands_for_lifecycle.py"
)


def test_tp1_command_requires_explicit_limit_gtc_contract():
    command = TicketBoundExchangeCommand.model_validate(_tp1_command())

    assert command.execution_style == "limit_gtc"
    assert command.time_in_force == "GTC"
    assert command.post_only is False
    assert command.market_fallback_allowed is False


def test_tp1_command_rejects_market_or_missing_limit_contract():
    market = _tp1_command(order_type="market", price=None)
    with pytest.raises(ValueError, match="tp1_requires_limit_price"):
        TicketBoundExchangeCommand.model_validate(market)

    invalid_gtc = _tp1_command(post_only=True)
    with pytest.raises(ValueError, match="tp1_gtc_contract_invalid"):
        TicketBoundExchangeCommand.model_validate(invalid_gtc)


def test_tp1_command_accepts_typed_passive_limit_gtx_only():
    command = TicketBoundExchangeCommand.model_validate(
        _tp1_command(
            execution_style="passive_limit_gtx",
            time_in_force="GTX",
            post_only=True,
        )
    )
    assert command.execution_style == "passive_limit_gtx"

    with pytest.raises(ValueError):
        TicketBoundExchangeCommand.model_validate(
            _tp1_command(market_fallback_allowed=True)
        )


@pytest.mark.parametrize("source", ["exit_policy_runner", "exit_policy_close"])
def test_exit_policy_sources_use_the_existing_typed_command_authority(source):
    command = TicketBoundExchangeCommand.model_validate(
        _tp1_command(
            order_role="RUNNER_SL",
            order_type="stop_market" if source == "exit_policy_runner" else "market",
            execution_style=None,
            time_in_force=None,
            amount="0.125",
            price=None,
            stop_price="1990" if source == "exit_policy_runner" else None,
            command_source=source,
            source_command_id=f"{source}-1",
        )
    )

    assert command.command_source == source
    assert command.reduce_intent == "reduce_position"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _tp1_command(**overrides):
    payload = {
        "exchange_command_id": "command-1",
        "protected_submit_attempt_id": "attempt-1",
        "ticket_id": "ticket-1",
        "operation_submit_command_id": "submit-1",
        "account_id": "account-1",
        "strategy_group_id": "SOR-001",
        "runtime_profile_id": "profile-1",
        "exchange_instrument_id": "binance_usdm:ETH/USDT:USDT",
        "exchange_id": "binance_usdm",
        "gateway_symbol": "ETH/USDT:USDT",
        "symbol": "ETHUSDT",
        "order_role": "TP1",
        "side": "long",
        "gateway_side": "sell",
        "local_order_id": "tp1-1",
        "parent_order_id": "entry-1",
        "client_order_id": "brc-client-tp1-1",
        "command_generation": 1,
        "request_fingerprint": "sha256:command-1",
        "order_type": "limit",
        "execution_style": "limit_gtc",
        "time_in_force": "GTC",
        "post_only": False,
        "market_fallback_allowed": False,
        "amount": "0.25",
        "price": "2100",
        "stop_price": None,
        "reduce_only": True,
        "reduce_intent": "reduce_position",
        "position_mode": "one_way",
        "position_side": None,
        "position_bucket": "BOTH",
        "netting_domain_key": "account-1|binance_usdm|ETHUSDT|BOTH",
        "command_kind": "place_order",
        "command_source": "protected_submit",
        "source_command_id": "attempt-1",
        "authority_source_ref": "operation-layer:submit-1",
        "command_state": "prepared",
        "outcome_class": "pending",
        "prepared_at_ms": 1,
        "updated_at_ms": 1,
    }
    payload.update(overrides)
    return payload


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
            "gateway_symbol",
            "symbol",
            "command_state",
            "request_fingerprint",
            "command_generation",
            "account_id",
            "strategy_group_id",
            "side",
        } <= columns

    engine.dispose()


def test_migration_114_extends_existing_command_authority_for_lifecycle():
    foundation = _load_module(FOUNDATION_PATH, "migration_086_exchange_lifecycle")
    eligibility = _load_module(ELIGIBILITY_PATH, "migration_104_exchange_lifecycle")
    command_migration = _load_module(COMMAND_PATH, "migration_105_exchange_lifecycle")
    typed_scope = _load_module(TYPED_SCOPE_PATH, "migration_113_exchange_lifecycle")
    lifecycle = _load_module(LIFECYCLE_COMMAND_PATH, "migration_114_exchange_lifecycle")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        operations = Operations(MigrationContext.configure(conn))
        for module in (
            foundation,
            eligibility,
            command_migration,
            typed_scope,
            lifecycle,
        ):
            previous = module.op
            module.op = operations
            try:
                module.upgrade()
            finally:
                module.op = previous
        columns = {
            item["name"]
            for item in sa.inspect(conn).get_columns(
                "brc_ticket_bound_exchange_commands"
            )
        }
        assert {
            "exchange_id",
            "position_mode",
            "position_side",
            "position_bucket",
            "netting_domain_key",
            "reduce_intent",
            "command_kind",
            "command_source",
            "source_command_id",
            "target_exchange_order_id",
            "claim_owner",
            "claim_token",
            "claim_expires_at_ms",
            "execution_attempt_count",
            "exchange_result",
        } <= columns
    engine.dispose()
