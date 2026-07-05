from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_runtime_file_authority_boundary.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "validate_runtime_file_authority_boundary",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _manifest(*, matches: list[str], occurrence_count: int = 1) -> dict:
    return {
        "schema": "brc.runtime_file_authority_boundary.v1",
        "status": "current",
        "authority_boundary": {
            "production_runtime_file_authority_allowed": False,
            "finalgate_called": False,
            "operation_layer_called": False,
            "exchange_write_called": False,
            "order_created": False,
            "live_profile_changed": False,
            "order_sizing_changed": False,
        },
        "monitored_occurrences": [
            {
                "path": "monitored.py",
                "pattern_id": "output_runtime_latest_literal",
                "occurrence_count": occurrence_count,
                "matches": matches,
                "disposition": "pre_pg_cutover_debt",
                "replacement": "brc_control_read_model_snapshots",
                "sunset_condition": "JSON becomes export-only",
            }
        ],
    }


def test_runtime_file_authority_validator_accepts_exact_baseline(tmp_path: Path):
    module = _load_module()
    (tmp_path / "monitored.py").write_text(
        'PATH = "output/runtime-monitor/latest-strategy-live-candidate-pool.json"\n',
        encoding="utf-8",
    )
    manifest = _manifest(
        matches=["output/runtime-monitor/latest-strategy-live-candidate-pool.json"]
    )

    assert module.validate_manifest(manifest) == []
    assert module.validate_occurrences(manifest, repo_root=tmp_path) == []


def test_runtime_file_authority_validator_rejects_added_occurrence(tmp_path: Path):
    module = _load_module()
    (tmp_path / "monitored.py").write_text(
        "\n".join(
            [
                'A = "output/runtime-monitor/latest-strategy-live-candidate-pool.json"',
                'B = "output/runtime-monitor/latest-strategy-live-candidate-pool.json"',
            ]
        ),
        encoding="utf-8",
    )
    manifest = _manifest(
        matches=["output/runtime-monitor/latest-strategy-live-candidate-pool.json"],
        occurrence_count=1,
    )

    errors = module.validate_occurrences(manifest, repo_root=tmp_path)

    assert any("occurrence_count changed" in error for error in errors)


def test_runtime_file_authority_validator_rejects_new_source_literal(tmp_path: Path):
    module = _load_module()
    (tmp_path / "monitored.py").write_text(
        'PATH = "output/runtime-monitor/latest-new-authority-source.json"\n',
        encoding="utf-8",
    )
    manifest = _manifest(
        matches=["output/runtime-monitor/latest-strategy-live-candidate-pool.json"]
    )

    errors = module.validate_occurrences(manifest, repo_root=tmp_path)

    assert any("matches changed" in error for error in errors)


def test_runtime_file_authority_manifest_requires_replacement_and_no_authority():
    module = _load_module()
    manifest = _manifest(
        matches=["output/runtime-monitor/latest-strategy-live-candidate-pool.json"]
    )
    manifest["authority_boundary"]["production_runtime_file_authority_allowed"] = True
    manifest["monitored_occurrences"][0]["replacement"] = ""
    manifest["monitored_occurrences"][0]["sunset_condition"] = ""

    errors = module.validate_manifest(manifest)

    assert "authority_boundary.production_runtime_file_authority_allowed must be false" in errors
    assert "monitored_occurrences[0].replacement is required" in errors
    assert "monitored_occurrences[0].sunset_condition is required" in errors


def test_runtime_file_authority_validator_rejects_retired_production_live_facts_flags(
    tmp_path: Path,
):
    module = _load_module()
    source = tmp_path / "production.py"
    source.write_text('parser.add_argument("--collect-live-facts-before-refresh")\n')

    errors = module.validate_forbidden_production_text(
        repo_root=tmp_path,
        forbidden_by_path={
            "production.py": (
                "--collect-live-facts-before-refresh",
            )
        },
    )

    assert errors == [
        (
            "production.py contains retired production file-authority text: "
            "--collect-live-facts-before-refresh"
        )
    ]


def test_runtime_file_authority_validator_accepts_clean_production_file(
    tmp_path: Path,
):
    module = _load_module()
    source = tmp_path / "production.py"
    source.write_text('parser.add_argument("--output-json")\n')

    assert (
        module.validate_forbidden_production_text(
            repo_root=tmp_path,
            forbidden_by_path={
                "production.py": (
                    "--collect-live-facts-before-refresh",
                )
            },
        )
        == []
    )


def test_runtime_file_authority_validator_rejects_ticket_bound_loose_inputs(
    tmp_path: Path,
):
    module = _load_module()
    source = tmp_path / "ticket_bound.py"
    source.write_text('parser.add_argument("--authorization-id")\n')

    errors = module.validate_forbidden_production_text(
        repo_root=tmp_path,
        forbidden_by_path={
            "ticket_bound.py": (
                "--authorization-id",
                "--candidate-json",
            )
        },
    )

    assert errors == [
        (
            "ticket_bound.py contains retired production file-authority text: "
            "--authorization-id"
        )
    ]


def test_runtime_file_authority_validator_accepts_ticket_only_inputs(
    tmp_path: Path,
):
    module = _load_module()
    source = tmp_path / "ticket_bound.py"
    source.write_text(
        "\n".join(
            [
                'parser.add_argument("--ticket-id")',
                'parser.add_argument("--finalgate-pass-id")',
                'parser.add_argument("--operation-submit-command-id")',
            ]
        )
    )

    assert (
        module.validate_forbidden_production_text(
            repo_root=tmp_path,
            forbidden_by_path={
                "ticket_bound.py": (
                    "--authorization-id",
                    "--candidate-json",
                    "--strategy-group-id",
                    "--symbol",
                    "--side",
                )
            },
        )
        == []
    )
