from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "runtime_interaction_levels.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "runtime_interaction_levels",
        SCRIPT_PATH,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_runtime_interaction_levels_cover_l0_to_l5_boundaries():
    module = _load_module()

    assert set(module.INTERACTION_LEVELS) == {"L0", "L1", "L2", "L3", "L4", "L5"}
    assert module.interaction_rank("L0_local_cache_read") == 0
    assert module.interaction_rank("L1_readonly_snapshot") == 1
    assert module.interaction_rank("L3_bounded_deploy_apply") == 3
    assert module.interaction_rank("L5_official_operation_layer_order") == 5

    assert module.interaction_policy("L0_local_cache_read")["remote_interaction_allowed"] is False
    assert module.interaction_policy("L1_readonly_snapshot")["remote_mutation_allowed"] is False
    assert module.interaction_policy("L2_dry_run_audit")["exchange_write_allowed"] is False
    assert module.interaction_policy("L3_bounded_deploy_apply")["remote_mutation_allowed"] is True
    assert module.interaction_policy("L3_bounded_deploy_apply")["exchange_write_allowed"] is False
    assert module.interaction_policy("L4_action_time_gate")["approaches_real_order"] is True
    assert module.interaction_policy("L4_action_time_gate")["exchange_write_allowed"] is False
    assert module.interaction_policy("L5_official_operation_layer_order")["exchange_write_allowed"] is True


def test_runtime_interaction_annotation_adds_owner_policy():
    module = _load_module()

    annotated = module.annotate_interaction(
        {
            "level": "L1_daily_check_from_snapshot",
            "remote_interaction_count": 1,
        }
    )

    assert annotated["policy"]["level_prefix"] == "L1"
    assert annotated["policy"]["owner_label"] == "只读低交互"
    assert annotated["policy"]["exchange_write_allowed"] is False
