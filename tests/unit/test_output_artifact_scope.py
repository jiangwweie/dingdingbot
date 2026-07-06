from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_output_artifact_scope.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_output_artifact_scope",
        VALIDATOR_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_output_artifact_scope_rejects_previous_control_snapshot_pair():
    module = _load_module()

    errors = module.validate_changed_output_paths(
        [
            "output/runtime-monitor/latest-daily-live-enablement-table.json",
            "output/runtime-monitor/latest-daily-live-enablement-table.md",
        ]
    )

    assert errors == [
        "output/runtime-monitor/latest-daily-live-enablement-table.json is generated output; do not include output/** in routine commits",
        "output/runtime-monitor/latest-daily-live-enablement-table.md is generated output; do not include output/** in routine commits",
    ]


def test_output_artifact_scope_rejects_volatile_public_facts():
    module = _load_module()

    errors = module.validate_changed_output_paths(
        ["output/runtime-monitor/latest-binance-usdm-public-facts.json"]
    )

    assert errors == [
        "output/runtime-monitor/latest-binance-usdm-public-facts.json is generated output; do not include output/** in routine commits"
    ]


def test_output_artifact_scope_rejects_unknown_output():
    module = _load_module()

    errors = module.validate_changed_output_paths(
        ["output/runtime-monitor/latest-random-summary.json"]
    )

    assert errors == [
        "output/runtime-monitor/latest-random-summary.json is generated output; do not include output/** in routine commits"
    ]


def test_output_artifact_scope_rejects_existing_tracked_output(tmp_path: Path):
    module = _load_module()
    existing = tmp_path / "output" / "runtime-monitor" / "latest-daily-live-enablement-table.json"
    existing.parent.mkdir(parents=True)
    existing.touch()

    errors = module.validate_tracked_output_paths(
        [
            "output/runtime-monitor/latest-daily-live-enablement-table.json",
            "output/runtime-monitor/latest-random-summary.json",
        ],
        repo_root=tmp_path,
    )

    assert errors == [
        "output/runtime-monitor/latest-daily-live-enablement-table.json is tracked generated output; remove it from git",
    ]


def test_output_artifact_scope_allows_deleted_tracked_output_cleanup(tmp_path: Path):
    module = _load_module()

    errors = module.validate_tracked_output_paths(
        ["output/runtime-monitor/latest-daily-live-enablement-table.json"],
        repo_root=tmp_path,
    )

    assert errors == []


def test_output_artifact_scope_cli_path_round_trip():
    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            "--path",
            "output/runtime-monitor/latest-single-lane-task-packet.json",
            "--path",
            "output/runtime-monitor/latest-single-lane-task-packet.md",
            "--path",
            "output/runtime-monitor/latest-strategy-live-candidate-pool.json",
            "--path",
            "output/runtime-monitor/latest-strategy-live-candidate-pool.md",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "do not include output/** in routine commits" in result.stderr


def test_git_status_parser_ignores_output_deletions_for_cleanup():
    module = _load_module()

    paths = module._changed_output_paths_from_porcelain(
        "\n".join(
            [
                "D  output/runtime-monitor/latest-old-report.json",
                " D output/runtime-monitor/latest-local-noise.json",
                " M output/runtime-monitor/latest-daily-live-enablement-table.json",
                "?? output/runtime-monitor/latest-random-summary.json",
            ]
        )
    )

    assert paths == [
        "output/runtime-monitor/latest-daily-live-enablement-table.json",
        "output/runtime-monitor/latest-random-summary.json",
    ]
