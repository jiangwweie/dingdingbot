from __future__ import annotations

import importlib


ARCHIVED_MODULES = (
    "build_runtime_first_real_submit_owner_packet",
    "build_runtime_first_real_submit_action_authorization_packet",
    "runtime_first_real_submit_api_flow",
    "runtime_executable_submit_readiness_api_flow",
    "build_runtime_first_real_submit_exchange_arm_authorization_packet",
    "build_runtime_first_real_submit_final_review_packet",
    "build_runtime_first_real_submit_local_registration_authorization_packet",
)

CURRENT_FIRST_REAL_SUBMIT_WRAPPERS = {
    "build_runtime_first_real_submit_owner_evidence": (
        "build_runtime_first_real_submit_owner_packet",
        "build_first_real_submit_owner_packet",
        "build_first_real_submit_owner_evidence",
    ),
    "build_runtime_first_real_submit_action_authorization_evidence": (
        "build_runtime_first_real_submit_action_authorization_packet",
        "build_first_real_submit_action_authorization_packet",
        "build_first_real_submit_action_authorization_evidence",
    ),
    "build_runtime_first_real_submit_local_registration_authorization_evidence": (
        "build_runtime_first_real_submit_local_registration_authorization_packet",
        "build_local_registration_authorization_packet",
        "build_local_registration_authorization_evidence",
    ),
    "build_runtime_first_real_submit_exchange_arm_authorization_evidence": (
        "build_runtime_first_real_submit_exchange_arm_authorization_packet",
        "build_exchange_arm_authorization_packet",
        "build_exchange_arm_authorization_evidence",
    ),
    "build_runtime_first_real_submit_final_review_artifact": (
        "build_runtime_first_real_submit_final_review_packet",
        "build_first_real_submit_final_review_packet",
        "build_first_real_submit_final_review_artifact",
    ),
}

CURRENT_EVIDENCE_WRAPPERS = {
    "verify_runtime_submit_rehearsal_pre_live_evidence": (
        "verify_runtime_submit_rehearsal_pre_live_packet",
        "build_pre_live_packet",
    ),
    "runtime_legacy_compatibility_isolation_evidence": (
        "runtime_legacy_compatibility_isolation_packet",
        "build_isolation_packet",
    ),
}


def test_first_real_submit_history_modules_remain_in_archive_namespace() -> None:
    for module_name in ARCHIVED_MODULES:
        archived = importlib.import_module(
            f"scripts.replay_recovery_history.first_real_submit.{module_name}"
        )

        assert archived.__doc__


def test_current_first_real_submit_wrappers_use_evidence_or_artifact_names() -> None:
    for wrapper_name, (archived_name, old_builder, new_builder) in (
        CURRENT_FIRST_REAL_SUBMIT_WRAPPERS.items()
    ):
        wrapper = importlib.import_module(f"scripts.{wrapper_name}")
        archived = importlib.import_module(
            f"scripts.replay_recovery_history.first_real_submit.{archived_name}"
        )

        assert wrapper._archived_module is archived
        assert callable(wrapper.main)
        assert not hasattr(wrapper, old_builder)
        assert callable(getattr(wrapper, new_builder))


def test_current_evidence_wrappers_forward_to_archive_namespace_without_old_builders() -> None:
    for wrapper_name, (archived_name, old_builder) in CURRENT_EVIDENCE_WRAPPERS.items():
        wrapper = importlib.import_module(f"scripts.{wrapper_name}")
        archived = importlib.import_module(
            f"scripts.replay_recovery_history.first_real_submit.{archived_name}"
        )

        assert wrapper._archived_module is archived
        assert callable(wrapper.main)
        assert not hasattr(wrapper, old_builder)


def test_archive_namespace_keeps_first_real_submit_helpers_importable() -> None:
    archived = importlib.import_module(
        "scripts.replay_recovery_history.first_real_submit."
        "runtime_first_real_submit_api_flow"
    )

    assert archived.DEFAULT_API_BASE == "http://127.0.0.1:18080"
    assert (archived.ROOT_DIR / "AGENTS.md").exists()
    assert (archived.ROOT_DIR / "scripts").is_dir()
