# Staging Commit Manifest

## Status

| Field | Value |
| --- | --- |
| manifest_status | `post_owner_acceptance_only` |
| worktree | `/Users/jiangwei/Documents/final-system-refactor-20260623` |
| branch | `codex/system-refactor-20260623` |
| head | current local `HEAD`; verify with `git rev-parse --short HEAD` |
| upstream_sync | no behind commits after fetch; verify with `git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1` |
| commit_status | `local_commit_series_created_not_pushed` |
| staging_status | `selected_path_staging_used_for_latest_commits`; optional evidence not default-staged |
| push_status | `not_pushed` |

## Purpose

This manifest prevents the large system-refactor diff from being staged as an
undifferentiated blob after Owner validation.

It is guidance only. It does not stage, commit, push, deploy, clean, or mutate
the main worktree.

## Current Diff Inventory

| Inventory | Value |
| --- | --- |
| tracked_diff | `722 files changed, 78503 insertions(+), 38518 deletions(-)` against upstream; evidence/generated-artifact heavy |
| core_slimming_gate | tracked-core rehearsal `561 files changed, 32709 insertions(+), 63363 deletions(-)` |
| porcelain_status_groups | `417 M`, `92 D`, `166 ??`, `68 MM`, `17 RM`, `15 MD` |
| top_changed_roots | `tests=271`, `scripts=245`, `output=102`, `src=102`, `docs=48`, `migrations=5`, `deploy=1`, `AGENTS.md=1` |
| output_runtime_monitor_top_level_files | `88` |
| output_token_burn_system_refactor_files | `1126` |
| current_index_diff | empty after latest local commit |
| current_index_roots | none |
| current_index_commit_safety | `clean_after_selected_path_commit` |
| current_index_reason | latest commits were created from selected path staging; do not recreate or commit obsolete broad index state |

## Recommended Commit Split

| Commit | Include | Exclude | Validation |
| --- | --- | --- | --- |
| `system-refactor-core-chain` | `src/`, production `scripts/`, `migrations/`, `deploy/`, `AGENTS.md` changes that implement chain compression and old authority removal. | generated runtime output, large token-burn evidence, unrelated local artifacts. | `python3 -m compileall src scripts tests migrations -q`; focused tests relevant to touched chain. |
| `system-refactor-tests` | `tests/unit/` changes proving renamed/demoted authority, Tradeability/Runtime Safety/Strategy Asset/Review Outcome behavior, and negative legacy assertions. | generated output and runtime monitor artifacts. | focused tests and optional full unit. |
| `system-refactor-docs-contracts` | `docs/current/` contract and authority-model changes, including frontend/UI projection removal and Tradeability Decision contract replacement. | runtime-generated evidence outputs unless explicitly accepted. | doc scan / targeted grep checks. |
| `system-refactor-generated-current-artifacts` | selected `output/runtime-monitor/latest-*` artifacts only if Owner wants generated current artifacts committed with the code change. | transient runtime directories, deploy logs, cache-only outputs, unrelated old Tokyo artifacts. | residual policy scan and artifact contract tests. |
| `system-refactor-evidence` | selected `output/token-burn-system-refactor/*` closeout artifacts through `BATCH_1086_EVIDENCE.md`, plus current coverage, staging, validation, merge-readiness, handoff, resume, final evidence, and queue files. | all other historical batch evidence unless Owner explicitly wants the full evidence corpus committed. | `git diff --check`; review evidence links. |

## Stage Include Candidates

| Path Family | Default | Reason |
| --- | --- | --- |
| `src/` | include after Owner acceptance | Core/domain/readmodel boundary changes are part of the architecture refactor. |
| `scripts/` | include after Owner acceptance | Production/current artifact builders and lifecycle projections were renamed/demoted. |
| `tests/unit/` | include after Owner acceptance | Characterization and negative legacy tests protect the migration. |
| `docs/current/` | include after Owner acceptance | Current contracts must match the new state model and removed frontend/UI projection authority. |
| `migrations/` | include after review | Migration/schema compatibility changes need careful diff review, but are part of current branch evidence. |
| `deploy/` | include after review | Systemd/runtime monitor wording changes must be reviewed for operational safety. |
| `AGENTS.md` | include after review | Operating guide changed; verify it reflects accepted Owner decisions. |
| `output/token-burn-system-refactor/` | include selected closeout files | Evidence is useful, but the directory is large and should not be blindly staged. |
| `output/runtime-monitor/latest-*` | include selected artifacts only | Some generated artifacts document current state, but runtime outputs are not all source of truth. |

## Stage Exclude By Default

| Path Family | Reason |
| --- | --- |
| transient `output/runtime-monitor/` directories | Runtime evidence/provenance; do not destructively clean or blindly commit. |
| broad historical `output/token-burn-system-refactor/BATCH_*` corpus | Huge evidence history; include only selected closeout packets unless Owner requests full corpus. |
| `output/unit-active-monitor/` | Test/runtime output, not source code. |
| deploy/session logs outside selected current artifacts | Runtime provenance; not necessary for architecture merge. |
| untracked local config, secrets, environment files | Must not be staged. |

## Required Pre-Commit Checks

Run from `/Users/jiangwei/Documents/final-system-refactor-20260623`:

```bash
git fetch origin
git rev-list --left-right --count HEAD...origin/codex/owner-runtime-console-v1
git diff --check
python3 -m compileall src scripts tests migrations -q
rg -n 'next_action|current_action|owner_decision|frontend|bridge|packet' \
  src scripts \
  --glob '!scripts/replay_recovery_history/**'
```

Expected:

- upstream sync remains `0 0`;
- diff check passes;
- compileall passes;
- residual scan remains `19`, classified as Tradeability Decision protected fields and PG historical schema names.

## Optional Pre-Commit Full Unit

```bash
python3 -m pytest tests/unit -q
```

Latest recorded result:

```text
3124 passed, 1 skipped, 1 warning in 72.38s
```

## Staging Guardrails

- Do not stage from `/Users/jiangwei/Documents/final`.
- Current index is clean after the latest selected-path commit. Do not recreate or commit the obsolete broad partial index described in Batch 1060.
- Batch 1065 dry-run include candidates are `705` paths, but the default staging path is lean: `673` lean default paths plus `32` optional evidence paths.
- Batch 1086 latest staging plan counts are `727` include candidates and `695` lean default paths after adding selected evidence through `BATCH_1085_EVIDENCE.md`; optional evidence remains `32`.
- Batch 1065 temporary-index rehearsal found line-size risk: full include `624 files changed, 121581 insertions(+), 29187 deletions(-)` and lean default `592 files changed, 61499 insertions(+), 29187 deletions(-)`. Future authorized staging must preserve visible architecture slimming through commit split and staged shortstat gates.
- Batch 1066 commit split gate requires the first authorized staging rehearsal to be tracked core-only: `561 files changed, 32709 insertions(+), 63363 deletions(-)`, proving visible core slimming before replacement additions, generated artifacts, or evidence are staged.
- Batch 1067 sequential delta rehearsal shows commit2 untracked replacements are `112 files changed, 42682 insertions(+)`, so they must be split by feature family instead of bulk-staged after commit1.
- Batch 1068 replacement feature-family rehearsal splits those `112` additions and flags the largest families for separate review: `runtime_artifact_evidence_scripts` `43 files changed, 17706 insertions(+)`, `tests_artifact_evidence_projection` `43 files changed, 11757 insertions(+)`, `strategygroup_core_state_builders` `3 files changed, 3880 insertions(+)`, and `tests_core_state` `3 files changed, 3879 insertions(+)`.
- Batch 1069 large-family subfamily rehearsal splits the two largest families into lifecycle groups; `strategygroup_asset_review` `10 files changed, 6941 insertions(+)` and `observation_shadow_projection` `22 files changed, 6419 insertions(+)` must be staged with focused tests or split again.
- Batch 1070 focused-test gate runs the two largest subfamily suites: `strategygroup_asset_review` `31 passed in 0.15s` and `observation_shadow_projection` `73 passed in 1.39s`; all remaining lifecycle subfamilies have required commands in `STAGING_REBUILD_PLAN.json`.
- Batch 1071 runs all remaining lifecycle subfamily focused gates; all `7` lifecycle subfamilies now have executed test evidence totaling `265 passed`.
- Batch 1072 refreshes full-unit validation after the complete subfamily gate set: `3123 passed, 1 skipped, 1 warning in 54.73s`.
- Batch 1073 refreshes Owner-validation/current-boundary scans after full unit: frontend/static `0`, active top-level packet/bridge/verdict entrypoints `0`, Owner-action legacy `0`, real-order authority true `0`, broad residual `19` retained/protected.
- Batch 1074 rehearses the authorized staging order in a temporary index: tracked core slimming first, then foundation/small replacements, lifecycle subfamilies, generated runtime-monitor review artifacts, and minimal closeout evidence. Real index remains unchanged and not commit-safe as-is.
- Batch 1075 refreshes Owner acceptance checklist, dry-run, handoff index, long-goal completion audit, and merge-management entry points to the current Batch 1074/1075 state.
- Batch 1076 refreshes closeout metadata wording so current-validation evidence is distinguished from historical Batch 1062/1043 transcript evidence.
- Batch 1077 replays the Owner acceptance command set and refreshes full unit to `3123 passed, 1 skipped, 1 warning in 47.90s`.
- Batch 1078 clarifies Owner acceptance baseline authority: Batch 1077 is the latest executed full-unit proof; Batch 1078 is metadata-only closeout evidence.
- Batch 1079 refreshes full-unit authority after Batch 1078 metadata repair: `3123 passed, 1 skipped, 1 warning in 47.82s`.
- Batch 1080 fetches upstream and confirms local HEAD still matches `origin/codex/owner-runtime-console-v1`, with current-boundary scans clean/protected.
- Batch 1081 repairs queue/map completion-gate drift so stale Test Queue and Operation Layer map wording do not reopen same-branch work.
- Batch 1082 adds current file-level objective-root coverage: `1012` non-`.pyc` files classified, unknown count `0`.
- Batch 1063 dry-run review/exclude buckets must remain explicit: generated current artifacts `95`, runtime monitor provenance `25`, other output review `1`, transient runtime output exclude `57`, and broad token-burn historical evidence exclude `1080` unless Owner explicitly accepts the full corpus.
- Batch 1063 old-name path audit found `98` tracked `packet/bridge/verdict` entries: `92` deletions and `6` modifications, so staging rebuild must preserve deletion entries without treating old paths as active authority.
- Do not run destructive cleanup to make staging easier.
- Do not stage secrets, environment files, or credential material.
- Do not stage deploy/apply logs unless explicitly accepted as provenance.
- Do not remove generated evidence only because it is untracked.
- Do not squash away evidence that proves old packet/bridge/frontend authority lost judgment power.
- Do not create compatibility layers during staging just to reduce diff discomfort.

## Commit Message Template

```text
refactor(strategygroup): compress trading lifecycle state chain

- make Tradeability Decision the can-trade readmodel authority
- keep Runtime Safety State as live-submit readiness authority
- demote packet/bridge/report/monitor outputs to lifecycle evidence/projections
- remove frontend/UI projection authority and stale packet builders
- preserve FinalGate, Operation Layer, RequiredFacts, exchange safety, protection, reconciliation, and settlement
- retain 19 protected residuals: Tradeability Decision fields and PG historical schema names
- core slimming gate: tracked-core rehearsal 32709 insertions / 63363 deletions
- latest closeout evidence: BATCH_1086_EVIDENCE.md

Validation:
- python3 -m compileall src scripts tests migrations -q
- git diff --check
- python3 -m pytest tests/unit -q -> 3124 passed, 1 skipped, 1 warning in 72.38s
- owner-validation dry-run -> frontend/static 0; packet/bridge/verdict scripts 0; production Owner-action legacy 0; broad residuals 19 retained/protected
- index audit -> latest selected-path index is clean after commit; do not reuse obsolete broad partial index
- closeout consistency -> post-fetch upstream sync 0 0; current index unchanged at 112 files, +5228/-3549
```

## No-Go

- No push before Owner acceptance.
- No deploy.
- No real order.
- No withdrawal or transfer.
- No secret or credential mutation.
- No live profile expansion.
- No order sizing default expansion.
- No destructive migration.
- No direct mutation of `/Users/jiangwei/Documents/final`.
