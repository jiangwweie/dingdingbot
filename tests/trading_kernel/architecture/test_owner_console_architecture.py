from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNER_ROOTS = (
    REPO_ROOT / "src/trading_kernel/application/owner_console",
    REPO_ROOT / "src/trading_kernel/interfaces/owner_console_http",
)

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


def test_kernel_systemd_directory_remains_four_workers_plus_slice() -> None:
    expected = {
        "brc-trading-kernel.slice",
        "brc-trading-kernel-observation-worker.service",
        "brc-trading-kernel-entry-worker.service",
        "brc-trading-kernel-lifecycle-worker.service",
        "brc-trading-kernel-reconciliation-worker.service",
    }
    assert {path.name for path in (REPO_ROOT / "deploy/systemd").iterdir()} == expected
