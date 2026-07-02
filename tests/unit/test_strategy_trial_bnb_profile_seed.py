from __future__ import annotations

import pytest

from scripts.seed_strategy_trial_bnb_profile import (
    BNB_STRATEGY_TRIAL_PROFILE,
    PROFILE_NAME,
)
from scripts.seed_prelive_bnb_readonly_profile import (
    PROFILE_NAME as PRELIVE_PROFILE_NAME,
    build_candidate_payload,
    build_resolved_summary,
    build_seed_evidence,
    guard_apply_environment,
    validate_candidate_payload,
)
from scripts.inspect_runtime_profiles_readonly import safe_profile_row
from scripts.probe_runtime_bound_readonly import build_probe_plan, guard_probe_environment
from src.application.runtime_config import RuntimeConfigResolver
from src.infrastructure.runtime_profile_repository import RuntimeProfile


class InMemoryRuntimeProfileRepository:
    def __init__(
        self,
        profile: RuntimeProfile | None = None,
        *,
        profiles: list[RuntimeProfile] | None = None,
        active_name: str | None = None,
    ) -> None:
        profile_list = profiles or ([profile] if profile is not None else [])
        self.profiles = {item.name: item for item in profile_list}
        self.active_name = active_name

    async def get_profile(self, name: str):
        return self.profiles.get(name)

    async def get_active_profile(self):
        if self.active_name is None:
            return None
        return self.profiles.get(self.active_name)


@pytest.mark.asyncio
async def test_bnb_strategy_trial_profile_resolves_to_testnet_bnb_only_scope():
    repo = InMemoryRuntimeProfileRepository(
        RuntimeProfile(
            name=PROFILE_NAME,
            profile_payload=BNB_STRATEGY_TRIAL_PROFILE,
            description="test",
            is_active=False,
            is_readonly=True,
            version=1,
        )
    )
    env = {
        "PG_DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "testnet",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_TESTNET": "true",
        "BRC_EXECUTION_PERMISSION_MAX": "intent_recording",
        "EXCHANGE_API_KEY": "x" * 64,
        "EXCHANGE_API_SECRET": "y" * 64,
        "FEISHU_WEBHOOK_URL": "https://example.invalid/webhook",
        "BACKEND_PORT": "8000",
    }

    resolved = await RuntimeConfigResolver(repo, env=env).resolve(PROFILE_NAME)

    assert resolved.profile_name == "strategy_trial_bnb_testnet_runtime"
    assert resolved.environment.trading_env == "testnet"
    assert resolved.environment.exchange_testnet is True
    assert resolved.market.primary_symbol == "BNB/USDT:USDT"
    assert resolved.market.symbols == ["BNB/USDT:USDT"]
    assert resolved.risk.max_leverage == 1
    assert resolved.risk.max_total_exposure == 10
    assert resolved.risk.daily_max_trades == 1


def test_bnb_strategy_trial_profile_has_no_order_permission_metadata():
    non_permissions = BNB_STRATEGY_TRIAL_PROFILE["brc"]["non_permissions"]

    assert BNB_STRATEGY_TRIAL_PROFILE["brc"]["carrier_id"] == "MI-001-BNB-LONG"
    assert BNB_STRATEGY_TRIAL_PROFILE["brc"]["symbol_sequence"] == ["BNB/USDT:USDT"]
    assert non_permissions["live_ready"] is False
    assert non_permissions["auto_execution_ready"] is False
    assert non_permissions["no_arbitrary_symbol"] is True
    assert non_permissions["no_arbitrary_side"] is True
    assert non_permissions["no_arbitrary_leverage"] is True


def test_prelive_bnb_readonly_profile_payload_keeps_bnb_only_scope():
    payload = build_candidate_payload()
    non_permissions = payload["brc"]["non_permissions"]

    assert payload["market"]["primary_symbol"] == "BNB/USDT:USDT"
    assert payload["market"]["symbols"] == ["BNB/USDT:USDT"]
    assert payload["strategy"]["allowed_directions"] == ["LONG"]
    assert payload["risk"]["max_leverage"] == 1
    assert payload["risk"]["max_total_exposure"] == "10"
    assert payload["risk"]["daily_max_trades"] == 1
    assert payload["brc"]["carrier_id"] == "MI-001-BNB-LONG"
    assert payload["brc"]["fixed_caps"]["BNB/USDT:USDT"]["amount"] == "0.01"
    assert payload["brc"]["fixed_caps"]["BNB/USDT:USDT"]["max_notional"] == "20"
    assert non_permissions["live_ready"] is False
    assert non_permissions["auto_execution_ready"] is False


def test_prelive_bnb_readonly_profile_validation_rejects_scope_drift():
    payload = build_candidate_payload()
    payload["strategy"]["allowed_directions"] = ["SHORT"]

    with pytest.raises(ValueError, match="directions"):
        validate_candidate_payload(payload)


@pytest.mark.asyncio
async def test_prelive_bnb_readonly_profile_summary_resolves_live_readonly_scope():
    summary = await build_resolved_summary()

    assert summary["profile_name"] == PRELIVE_PROFILE_NAME
    assert summary["is_active"] is True
    assert summary["is_readonly"] is True
    assert summary["trading_env"] == "live"
    assert summary["exchange_testnet"] is False
    assert summary["permission_max"] == "read_only"
    assert summary["primary_symbol"] == "BNB/USDT:USDT"
    assert summary["symbols"] == ["BNB/USDT:USDT"]
    assert summary["allowed_directions"] == ["LONG"]
    assert summary["max_leverage"] == 1
    assert summary["max_total_exposure"] == "10"
    assert summary["daily_max_trades"] == 1
    assert len(summary["config_hash"]) == 16


def _safe_prelive_seed_env(**overrides: str) -> dict[str, str]:
    env = {
        "OWNER_APPROVED_RUNTIME_PROFILE_SEED": PRELIVE_PROFILE_NAME,
        "PG_DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "live",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "RUNTIME_CONTROL_API_ENABLED": "false",
        "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "false",
    }
    env.update(overrides)
    return env


def test_prelive_bnb_readonly_profile_apply_guard_accepts_safe_metadata_env():
    guard_apply_environment(_safe_prelive_seed_env())


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"OWNER_APPROVED_RUNTIME_PROFILE_SEED": ""}, "OWNER_APPROVED_RUNTIME_PROFILE_SEED"),
        ({"BRC_EXECUTION_PERMISSION_MAX": "order_allowed"}, "BRC_EXECUTION_PERMISSION_MAX"),
        ({"RUNTIME_PROFILE": "prelive_bnb_readonly_runtime"}, "RUNTIME_PROFILE"),
        ({"RUNTIME_CONTROL_API_ENABLED": "true"}, "RUNTIME_CONTROL_API_ENABLED"),
        ({"RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "true"}, "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"),
    ],
)
def test_prelive_bnb_readonly_profile_apply_guard_rejects_unsafe_env(
    override: dict[str, str],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        guard_apply_environment(_safe_prelive_seed_env(**override))


def test_runtime_profile_readonly_inspection_omits_full_payload():
    payload = build_candidate_payload()
    row = {
        "name": PRELIVE_PROFILE_NAME,
        "description": "test",
        "profile_payload": payload,
        "is_active": True,
        "is_readonly": True,
        "created_at": 1,
        "updated_at": 2,
        "version": 3,
    }

    summary = safe_profile_row(row)

    assert "profile_payload" not in summary
    assert summary["name"] == PRELIVE_PROFILE_NAME
    assert summary["is_active"] is True
    assert summary["is_readonly"] is True
    assert summary["payload_summary"]["market"]["primary_symbol"] == "BNB/USDT:USDT"
    assert summary["payload_summary"]["strategy"]["allowed_directions"] == ["LONG"]
    assert summary["payload_summary"]["risk"]["max_leverage"] == 1
    assert summary["payload_summary"]["brc"]["carrier_id"] == "MI-001-BNB-LONG"
    assert "payload_hash" in summary["payload_summary"]


def test_runtime_bound_readonly_probe_plan_is_dry_run_by_default():
    plan = build_probe_plan(_safe_prelive_seed_env())

    assert plan["mode"] == "dry_run"
    assert plan["entrypoint"] == "python -m src.main"
    assert plan["port"] == 18082
    assert plan["health_url"] == "http://127.0.0.1:18082/api/health"
    assert plan["safety"]["runtime_control_api"] == "disabled"
    assert plan["safety"]["requires_single_active_pg_profile"] is True


def test_runtime_bound_readonly_probe_plan_can_be_explicit_run_mode():
    plan = build_probe_plan(
        _safe_prelive_seed_env(
            RUN_RUNTIME_PROBE="true",
            RUNTIME_PROBE_PORT="19082",
            RUNTIME_PROBE_TIMEOUT_SECONDS="9",
        )
    )

    assert plan["mode"] == "run"
    assert plan["port"] == 19082
    assert plan["timeout_seconds"] == 9
    assert plan["health_url"] == "http://127.0.0.1:19082/api/health"


def test_runtime_bound_readonly_probe_guard_accepts_safe_env():
    guard_probe_environment(_safe_prelive_seed_env())


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"BRC_EXECUTION_PERMISSION_MAX": "order_allowed"}, "BRC_EXECUTION_PERMISSION_MAX"),
        ({"RUNTIME_PROFILE": "prelive_bnb_readonly_runtime"}, "RUNTIME_PROFILE"),
        ({"RUNTIME_CONTROL_API_ENABLED": "true"}, "RUNTIME_CONTROL_API_ENABLED"),
        ({"RUNTIME_TEST_SIGNAL_INJECTION_ENABLED": "true"}, "RUNTIME_TEST_SIGNAL_INJECTION_ENABLED"),
        ({"PG_DATABASE_URL": ""}, "PG_DATABASE_URL"),
    ],
)
def test_runtime_bound_readonly_probe_guard_rejects_unsafe_env(
    override: dict[str, str],
    message: str,
):
    with pytest.raises(ValueError, match=message):
        guard_probe_environment(_safe_prelive_seed_env(**override))


def _contains_key(value, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def test_prelive_seed_evidence_omits_full_payload():
    profile = RuntimeProfile(
        name=PRELIVE_PROFILE_NAME,
        profile_payload=build_candidate_payload(),
        description="seeded",
        is_active=True,
        is_readonly=True,
        created_at=1,
        updated_at=2,
        version=3,
    )
    before = {"runtime_profiles_exists": True, "count": 0, "active_count": 0, "profiles": []}
    after = {
        "runtime_profiles_exists": True,
        "count": 1,
        "active_count": 1,
        "profiles": [safe_profile_row({"profile_payload": profile.profile_payload, **profile.__dict__})],
    }
    candidate_summary = {
        "profile_name": PRELIVE_PROFILE_NAME,
        "config_hash": "754a0e60dba3cfef",
    }

    evidence = build_seed_evidence(
        candidate_summary=candidate_summary,
        before_report=before,
        after_report=after,
        seeded_profile=profile,
    )

    assert evidence["profile_name"] == PRELIVE_PROFILE_NAME
    assert evidence["before"]["count"] == 0
    assert evidence["after"]["active_count"] == 1
    assert evidence["safety"]["profile_payload_omitted"] is True
    assert evidence["safety"]["runtime_started"] is False
    assert not _contains_key(evidence, "profile_payload")


@pytest.mark.asyncio
async def test_live_startup_requires_active_runtime_profile_when_env_selector_absent():
    repo = InMemoryRuntimeProfileRepository()
    env = {
        "PG_DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "live",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "EXCHANGE_API_KEY": "x" * 64,
        "EXCHANGE_API_SECRET": "y" * 64,
        "FEISHU_WEBHOOK_URL": "https://example.invalid/webhook",
        "BACKEND_PORT": "8000",
    }

    with pytest.raises(ValueError, match="active runtime profile not found"):
        await RuntimeConfigResolver(repo, env=env).resolve_startup()


@pytest.mark.asyncio
async def test_live_startup_uses_active_pg_runtime_profile_without_env_selector():
    profile = RuntimeProfile(
        name="prelive_bnb_readonly_runtime",
        profile_payload=BNB_STRATEGY_TRIAL_PROFILE,
        description="active prelive readonly profile",
        is_active=True,
        is_readonly=True,
        version=7,
    )
    repo = InMemoryRuntimeProfileRepository(profiles=[profile], active_name=profile.name)
    env = {
        "PG_DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "live",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_TESTNET": "false",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "EXCHANGE_API_KEY": "x" * 64,
        "EXCHANGE_API_SECRET": "y" * 64,
        "FEISHU_WEBHOOK_URL": "https://example.invalid/webhook",
        "BACKEND_PORT": "8000",
    }

    resolved = await RuntimeConfigResolver(repo, env=env).resolve_startup()

    assert resolved.profile_name == profile.name
    assert resolved.version == 7
    assert resolved.environment.trading_env == "live"
    assert resolved.environment.exchange_testnet is False
    assert resolved.environment.brc_execution_permission_max.value_name == "read_only"


@pytest.mark.asyncio
async def test_non_live_startup_keeps_legacy_default_profile_fallback():
    profile = RuntimeProfile(
        name="sim1_eth_runtime",
        profile_payload=BNB_STRATEGY_TRIAL_PROFILE,
        description="legacy default",
        is_active=False,
        is_readonly=True,
        version=1,
    )
    repo = InMemoryRuntimeProfileRepository(profiles=[profile])
    env = {
        "PG_DATABASE_URL": "postgresql://user:pass@localhost:5432/test",
        "CORE_EXECUTION_INTENT_BACKEND": "postgres",
        "CORE_ORDER_BACKEND": "postgres",
        "CORE_POSITION_BACKEND": "postgres",
        "TRADING_ENV": "testnet",
        "EXCHANGE_NAME": "binance",
        "EXCHANGE_TESTNET": "true",
        "BRC_EXECUTION_PERMISSION_MAX": "read_only",
        "EXCHANGE_API_KEY": "x" * 64,
        "EXCHANGE_API_SECRET": "y" * 64,
        "FEISHU_WEBHOOK_URL": "https://example.invalid/webhook",
        "BACKEND_PORT": "8000",
    }

    resolved = await RuntimeConfigResolver(repo, env=env).resolve_startup()

    assert resolved.profile_name == "sim1_eth_runtime"
