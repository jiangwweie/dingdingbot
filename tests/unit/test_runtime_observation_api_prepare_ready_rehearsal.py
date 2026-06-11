from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "verify_runtime_observation_api_prepare_ready_rehearsal.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "verify_runtime_observation_api_prepare_ready_rehearsal",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ready_rehearsal_reaches_prepare_without_execution():
    module = _load_module()

    report = module.build_rehearsal_report()

    assert report["status"] == "rehearsal_passed"
    assert report["checks"]["ready_without_allow_stops_before_prepare"] is True
    assert report["checks"]["allow_prepare_reaches_final_gate_preflight"] is True
    assert report["checks"]["prepared_authorization_id_present"] is True
    assert report["checks"]["forbidden_execution_flags"] == []
    assert report["dry_run_payload"]["status"] == "ready_for_prepare"
    assert report["dry_run_payload"]["prepare_packet"] is None
    assert report["allow_prepare_payload"]["status"] == "ready_for_final_gate_preflight"
    assert (
        report["allow_prepare_payload"]["prepare_packet"]["created_records"][
            "attempt_mutation_created"
        ]
        is False
    )
    assert all(value is False for key, value in report["safety_invariants"].items() if key != "local_in_memory_only")
