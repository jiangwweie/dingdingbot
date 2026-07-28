from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.trading_kernel.domain.strategy_universe import build_strategy_universe

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts/trading_kernel/configure_strategy_universe.py"
STATUS_SCRIPT = REPO_ROOT / "scripts/trading_kernel/read_strategy_universe_status.py"


@pytest.mark.parametrize(
    ("instruments", "expected_error"),
    [
        ((), "the following arguments are required: --instrument"),
        (("BTCUSDT", "BTCUSDT"), "instruments must be unique"),
        (
            tuple(f"COIN{index}USDT" for index in range(11)),
            "between one and ten instruments",
        ),
        (("BTCBUSD",), "instrument must be an uppercase USDT perpetual symbol"),
    ],
)
def test_configure_cli_rejects_invalid_member_sets_before_database_access(
    tmp_path: Path,
    instruments: tuple[str, ...],
    expected_error: str,
) -> None:
    """Catches truncation, deduplication, quote guessing, or DB-first validation."""

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            "not-a-database-url",
            "--runtime-profile-id",
            "tiny-live-v1",
            "--event-spec-id",
            "SOR-LONG",
            *(
                argument
                for instrument in instruments
                for argument in ("--instrument", instrument)
            ),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert expected_error in completed.stderr
    assert completed.stdout == ""
    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize(
    ("identity_flag", "identity_value"),
    [
        ("--runtime-profile-id", " tiny-live-v1"),
        ("--event-spec-id", "SOR-LONG "),
    ],
)
def test_configure_cli_rejects_non_exact_authority_identity_without_traceback(
    tmp_path: Path,
    identity_flag: str,
    identity_value: str,
) -> None:
    """Catches whitespace normalization or an unsanitized validation traceback."""

    arguments = {
        "--runtime-profile-id": "tiny-live-v1",
        "--event-spec-id": "SOR-LONG",
    }
    arguments[identity_flag] = identity_value
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--database-url",
            "postgresql+asyncpg://user:SECRET@127.0.0.1/not-used",
            "--runtime-profile-id",
            arguments["--runtime-profile-id"],
            "--event-spec-id",
            arguments["--event-spec-id"],
            "--instrument",
            "BTCUSDT",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "configuration identities must be exact" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "SECRET" not in completed.stderr
    assert tuple(tmp_path.iterdir()) == ()


def test_status_cli_rejects_non_exact_identity_without_secret_traceback(
    tmp_path: Path,
) -> None:
    """Catches status validation leaking a database URL or supplied identity."""

    completed = subprocess.run(
        [
            sys.executable,
            str(STATUS_SCRIPT),
            "--database-url",
            "postgresql+asyncpg://user:SECRET@127.0.0.1/not-used",
            "--runtime-profile-id",
            " tiny-live-v1",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "status identities must be exact" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "SECRET" not in completed.stderr
    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.asyncio
async def test_configure_use_case_resolves_authority_then_installs_canonical_members() -> (
    None
):
    """Catches a script-owned SQL/install path or unresolved public Event alias."""

    module = importlib.import_module(
        "src.trading_kernel.application.install_strategy_universe"
    )
    configure = getattr(module, "configure_strategy_universe", None)
    request_type = getattr(module, "UniverseConfigurationRequest", None)
    context_type = getattr(module, "UniverseInstallContext", None)
    assert callable(configure)
    assert request_type is not None
    assert context_type is not None

    request = request_type(
        runtime_profile_id="tiny-live-v1",
        event_id="SOR-LONG",
        exchange_instrument_ids=(
            "binance-usdm:SOLUSDT:perpetual",
            "binance-usdm:BTCUSDT:perpetual",
        ),
        installed_at_ms=1_800_001_000_000,
    )
    expected_universe = build_strategy_universe(
        universe_version_id="universe:event_spec:SOR-001:SOR-LONG:v2:v1",
        strategy_group_id="SOR-001",
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        universe_version=1,
        exchange_instrument_ids=request.exchange_instrument_ids,
        installed_at_ms=request.installed_at_ms,
    )
    expected_result = module.UniverseInstallResult(
        status=module.UniverseInstallStatus.INSTALLED,
        universe=expected_universe,
        lifecycle_state="warming",
        inserted_instrument_count=2,
        inserted_version_count=1,
        inserted_member_count=2,
        inserted_scope_count=2,
    )

    class _Repository:
        def __init__(self) -> None:
            self.installed_request = None

        async def resolve_install_context(
            self,
            *,
            runtime_profile_id: str,
            event_id: str,
        ):
            assert runtime_profile_id == "tiny-live-v1"
            assert event_id == "SOR-LONG"
            return context_type(
                event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
                owner_policy_id="policy-main",
            )

        async def install(self, actual_request):
            self.installed_request = actual_request
            return expected_result

    repository = _Repository()
    actual = await configure(
        SimpleNamespace(strategy_universes=repository),
        request,
    )

    assert actual == expected_result
    assert repository.installed_request == module.UniverseInstallRequest(
        event_spec_id="event_spec:SOR-001:SOR-LONG:v2",
        runtime_profile_id="tiny-live-v1",
        owner_policy_id="policy-main",
        exchange_instrument_ids=(
            "binance-usdm:BTCUSDT:perpetual",
            "binance-usdm:SOLUSDT:perpetual",
        ),
        installed_at_ms=1_800_001_000_000,
    )
