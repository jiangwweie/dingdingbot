from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "preview_strategy_group_readonly_observation.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "preview_strategy_group_readonly_observation",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_preview_packet_uses_sample_source_without_side_effects():
    module = _load_module()

    packet = module.build_preview_packet(source_name="sample")

    assert packet["status"] == "preview_built"
    assert packet["source_requested"] == "sample"
    assert packet["checks"]["candidate_count"] >= 8
    assert packet["checks"]["current_signal_count"] >= 8
    assert packet["checks"]["forbidden_effects"] == []
    assert packet["safety_invariants"]["database_connected"] is False
    assert packet["safety_invariants"]["pg_observation_written"] is False
    assert packet["safety_invariants"]["shadow_candidate_created"] is False
    assert packet["safety_invariants"]["execution_intent_created"] is False
    assert packet["safety_invariants"]["order_created"] is False
    assert packet["safety_invariants"]["order_lifecycle_called"] is False
    assert packet["safety_invariants"]["exchange_write_called"] is False
    assert packet["operator_command_plan"]["records_observation"] is False
    assert packet["operator_command_plan"]["places_order"] is False
    for row in packet["would_enter_signals"]:
        assert row["not_order"] is True
        assert row["not_execution_intent"] is True
        assert row["no_execution_permission"] is True
        assert row["no_order_permission"] is True


def test_preview_script_writes_json_output(tmp_path, capsys):
    module = _load_module()
    output_path = tmp_path / "preview.json"

    code = module.main(["--source", "sample", "--output-json", str(output_path)])

    assert code == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output_path.read_text())
    assert stdout_payload == file_payload
    assert file_payload["scope"] == "strategy_group_readonly_observation_preview"
    assert file_payload["safety_invariants"]["runtime_started"] is False
