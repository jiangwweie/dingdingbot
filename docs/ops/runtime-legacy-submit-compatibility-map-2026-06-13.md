# Runtime Legacy Submit Compatibility Map

Last updated: 2026-06-13

## Purpose

This document records the post-RTF-103 legacy cleanup boundary and the P2
archive-hygiene migration completed on 2026-06-13.

The runtime-level mainline is now:

```text
RTF-100 bridge readiness
-> RTF-101 official prepare / FinalGate preflight
-> RTF-102 local runtime cycle
-> RTF-103 Tokyo integration proof
```

Historical pre-attempt rehearsal and first-real-submit packet implementations
now live under `scripts/replay_recovery_history/first_real_submit/`.
The old `scripts/*.py` paths remain thin compatibility wrappers for existing
tests, commands, and audit evidence.

## Current Mainline Entry

| Surface | Status | Mainline Role |
|---|---|---|
| `scripts/runtime_official_prepare_api_flow.py` | active wrapper | Neutral official prepare API flow import surface |
| `scripts/runtime_official_flat_next_attempt_end_to_end_proof.py` | active proof | Strategy-driven next-attempt to official prepare / FinalGate / preflight |
| `scripts/runtime_controlled_tiny_live_bridge_to_preflight_proof.py` | active proof | Bridge-ready to official preflight proof |
| `scripts/runtime_controlled_tiny_live_bridge_to_local_cycle_proof.py` | active proof | Bridge-ready local runtime cycle proof |

## Legacy Compatibility Surfaces

| Legacy wrapper path | Archived implementation path | Classification | Allowed Uses | Forbidden Uses |
|---|---|---|---|---|
| `scripts/verify_runtime_submit_rehearsal_pre_live_packet.py` | `scripts/replay_recovery_history/first_real_submit/verify_runtime_submit_rehearsal_pre_live_packet.py` | replay-only pre-attempt rehearsal | Audit replay, recovery investigation, historical report reproduction, compatibility tests | Runtime grant, bounded auto-attempt primary gate, new-attempt authority |
| `scripts/build_runtime_first_real_submit_owner_packet.py` | `scripts/replay_recovery_history/first_real_submit/build_runtime_first_real_submit_owner_packet.py` | legacy Owner review packet | Audit replay, recovery investigation, historical report reproduction, compatibility tests | Runtime grant, bounded auto-attempt primary gate, new-attempt authority |
| `scripts/build_runtime_first_real_submit_final_review_packet.py` | `scripts/replay_recovery_history/first_real_submit/build_runtime_first_real_submit_final_review_packet.py` | legacy final review packet | Audit replay, recovery investigation, historical report reproduction, compatibility tests | Runtime grant, bounded auto-attempt primary gate, new-attempt authority |
| `scripts/build_runtime_first_real_submit_action_authorization_packet.py` | `scripts/replay_recovery_history/first_real_submit/build_runtime_first_real_submit_action_authorization_packet.py` | legacy action packet | Audit replay, recovery investigation, historical report reproduction, compatibility tests | Runtime grant, bounded auto-attempt primary gate, automatic live submit authority |
| `scripts/build_runtime_first_real_submit_local_registration_authorization_packet.py` | `scripts/replay_recovery_history/first_real_submit/build_runtime_first_real_submit_local_registration_authorization_packet.py` | legacy local-registration packet | Audit replay, recovery investigation, historical report reproduction, compatibility tests | Runtime grant, bounded auto-attempt primary gate, automatic live submit authority |
| `scripts/build_runtime_first_real_submit_exchange_arm_authorization_packet.py` | `scripts/replay_recovery_history/first_real_submit/build_runtime_first_real_submit_exchange_arm_authorization_packet.py` | legacy exchange-arm packet | Audit replay, recovery investigation, historical report reproduction, compatibility tests | Runtime grant, bounded auto-attempt primary gate, automatic live submit authority |
| `scripts/runtime_first_real_submit_api_flow.py` | `scripts/replay_recovery_history/first_real_submit/runtime_first_real_submit_api_flow.py` | historically named implementation | Backward-compatible implementation behind `runtime_official_prepare_api_flow.py` | Direct runtime mainline import |

## Required Guard

`scripts/runtime_legacy_compatibility_isolation_packet.py` is the guard for
this boundary.

Current expected result:

```text
status=legacy_compatibility_isolated_from_runtime_mainline
blockers=[]
mainline_has_no_legacy_primary_gate_terms=true
historically_named_prepare_helper_wrapped=true
legacy_artifacts_classified=true
legacy_artifacts_archived_to_replay_recovery_history=true
legacy_wrapper_paths_preserved=true
mainline_exit_cleanup_complete=true
future_cleanup_required=false
archive_hygiene_completed=true
```

## Notes

- Do not delete `OwnerBoundedExecutionService` as part of this cleanup.
- Do not use the legacy first-real-submit packet family as the runtime-level
  bounded auto-attempt grant.
- Do not use pre-attempt rehearsal as the primary gate after an execution result
  exists.
- Owner manual withdrawals remain outside this execution chain.
- The legacy wrappers are compatibility entry points only. New references should
  prefer the archived implementation namespace when replay/recovery/history
  behavior is intentional.
