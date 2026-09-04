import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNER_ROOTS = (
    REPO_ROOT / "src/trading_kernel/application/owner_console",
    REPO_ROOT / "src/trading_kernel/interfaces/owner_console_http",
)
OWNER_MARKET_DATA = REPO_ROOT / "src/trading_kernel/infrastructure/owner_market_data.py"
OWNER_CONSOLE_RUNNER = REPO_ROOT / "scripts/owner_console/run_api.py"

FORBIDDEN = (
    "application.controlled_exit",
    "application.dispatch_exchange_command",
    "build_binance_usdm_venue_adapter",
    "TRADING_KERNEL_API_KEY",
    "TRADING_KERNEL_API_SECRET",
)


def test_owner_console_packages_exist_and_have_no_exchange_write_authority() -> None:
    for root in OWNER_ROOTS:
        assert root.is_dir()
        for path in root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN:
                assert marker not in source, f"{path}: {marker}"


def test_owner_market_data_has_only_credential_free_public_market_authority() -> None:
    source = OWNER_MARKET_DATA.read_text(encoding="utf-8")

    for marker in (
        "ProductionRuntimeSettings",
        "build_binance_usdm_venue_adapter",
        "TRADING_KERNEL_API_KEY",
        "TRADING_KERNEL_API_SECRET",
    ):
        assert marker not in source, f"{OWNER_MARKET_DATA}: {marker}"


def test_owner_console_runner_accepts_only_its_declared_environment_authority() -> None:
    source = OWNER_CONSOLE_RUNNER.read_text(encoding="utf-8")
    environment_names = {
        call.args[0].value
        for call in ast.walk(ast.parse(source))
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "get"
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
        and call.args[0].value.isupper()
    }

    assert environment_names == {
        "CREDENTIALS_DIRECTORY",
        "OWNER_CONSOLE_MARKET_TIMEOUT_SECONDS",
    }
    for marker in (
        "TRADING_KERNEL_API_KEY",
        "TRADING_KERNEL_API_SECRET",
        "BINANCE_API_KEY",
        "BINANCE_API_SECRET",
        "dotenv",
        "config.json",
    ):
        assert marker not in source, f"{OWNER_CONSOLE_RUNNER}: {marker}"


def test_kernel_systemd_directory_remains_four_workers_plus_slice() -> None:
    expected = {
        "brc-trading-kernel.slice",
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    }
    assert {path.name for path in (REPO_ROOT / "deploy/systemd").iterdir()} == expected


def test_dynamic_activation_rejects_stale_version_before_consuming_totp() -> None:
    source = (
        REPO_ROOT
        / "src/trading_kernel/interfaces/owner_console_http/routes/controls.py"
    ).read_text(encoding="utf-8")
    route = source.split("async def activate_dynamic_selection(", 1)[1].split(
        "\n\n@router", 1
    )[0]

    assert route.index("current.control_version != body.expected_version") < route.index(
        "await _require_step_up(body, request)"
    )
