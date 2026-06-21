from __future__ import annotations

import importlib


ARCHIVED_MODULES = (
    "build_runtime_first_real_submit_owner_packet",
    "runtime_legacy_compatibility_isolation_packet",
    "build_runtime_first_real_submit_action_authorization_packet",
    "runtime_first_real_submit_api_flow",
    "runtime_executable_submit_readiness_api_flow",
    "build_runtime_first_real_submit_exchange_arm_authorization_packet",
    "build_runtime_first_real_submit_final_review_packet",
    "verify_runtime_submit_rehearsal_pre_live_packet",
    "build_runtime_first_real_submit_local_registration_authorization_packet",
)


def test_legacy_first_real_submit_modules_forward_to_archive_namespace() -> None:
    for module_name in ARCHIVED_MODULES:
        legacy = importlib.import_module(f"scripts.{module_name}")
        archived = importlib.import_module(
            f"scripts.replay_recovery_history.first_real_submit.{module_name}"
        )

        assert legacy._archived_module is archived
        assert callable(legacy.main)
        assert callable(legacy._main)
        assert legacy.__doc__
        assert archived.__doc__


def test_archive_namespace_keeps_first_real_submit_helpers_importable() -> None:
    archived = importlib.import_module(
        "scripts.replay_recovery_history.first_real_submit."
        "runtime_first_real_submit_api_flow"
    )

    assert archived.DEFAULT_API_BASE == "http://127.0.0.1:18080"
    assert archived.ROOT_DIR.name == "final"
