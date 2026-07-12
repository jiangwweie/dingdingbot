---
title: P0_OWNER_NOTIFICATION_LANGUAGE_AND_RUNTIME_FORENSICS_IMPLEMENTATION_PLAN
status: APPROVED_FOR_IMPLEMENTATION
authority: docs/current/P0_OWNER_NOTIFICATION_LANGUAGE_AND_RUNTIME_FORENSICS_IMPLEMENTATION_PLAN.md
last_verified: 2026-07-12
---

# P0 Owner Notification Language And Runtime Forensics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace jargon-heavy monitor text with deduped, static Owner cards for
material trading/runtime transitions and add one bounded PG/systemd forensics
command consumed by the existing runtime-signal-forensics Skill.

**Architecture:** A pure typed `OwnerNotificationIntent` projector translates
PG/runtime facts. The existing PG notification table owns delivery/dedupe
state. A card renderer is presentation-only. A separate read-only forensics
repository and stdout CLI reconstruct a requested time window without becoming
runtime authority.

**Tech Stack:** Python 3.10+, Pydantic v2, SQLAlchemy 2, PostgreSQL, Alembic,
pytest, Feishu custom-robot Webhook.

## Global Constraints

- PG/current and audit lineage are the only production truth.
- No Feishu callback, button, URL action, policy mutation, exchange write,
  FinalGate, Operation Layer, profile, sizing, strategy, scope, credential,
  withdrawal, or transfer authority.
- Static cards use the current custom-robot Webhook only.
- No runtime JSON/MD/YAML/JSONL files or report directories.
- One notification row per correlation + notification kind; maximum five cards
  per monitor run and three delivery attempts per row.
- Forensics is explicit invocation, stdout-only, bounded to at most 1000 rows,
  and all subprocess/network work is timeout-bounded.
- Every behavior change follows RED -> GREEN -> REFACTOR.

---

### Task 1: Notification Ledger Schema And Typed Intent

**Files:**
- Create: `migrations/versions/2026-07-12-117_extend_owner_notification_ledger.py`
- Create: `src/application/owner_notification.py`
- Create: `tests/unit/test_owner_notification.py`
- Create: `tests/unit/test_owner_notification_migration.py`
- Modify migration-head defaults/tests located by
  `rg "116_add_opportunity_feedback|DEFAULT_EXPECTED_MIGRATION_COUNT"`.

**Interfaces:**
- Produces `OwnerNotificationKind`, `OwnerNotificationSeverity`,
  `OwnerNotificationIntent`, `owner_notification_dedupe_key(...)`, and
  `render_owner_notification_card(...)`.
- Extends `brc_server_monitor_notifications` with `notification_kind`,
  `severity`, `correlation_id`, `template_version`,
  `owner_action_required`, `occurred_at_ms`, and `resolved_at_ms`.

- [ ] Write a failing model test that constructs an opportunity intent and
  rejects missing correlation identity.
- [ ] Write a failing renderer test asserting `msg_type=interactive`, mapped
  header color, Owner fields, no callback/action elements, and absence of
  forbidden internal vocabulary.
- [ ] Write a failing migration round-trip test proving new columns, defaults,
  downgrade/upgrade, and no new table.
- [ ] Run the focused tests and verify RED because the module/migration is
  missing.
- [ ] Implement frozen Pydantic enums/models, deterministic dedupe identity,
  template version `owner-notification-v1`, and static card JSON renderer.
- [ ] Implement migration `117` with backward-compatible defaults and indexes
  on `correlation_id + notification_kind` and `notification_state`.
- [ ] Update migration-head constants and exact migration tests from 116 to
  117 without changing prior migration contents.
- [ ] Run focused tests and verify GREEN.

### Task 2: Material Scenario Projector

**Files:**
- Modify: `src/application/owner_notification.py`
- Create: `tests/unit/test_owner_notification_scenarios.py`
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Modify: `tests/unit/test_tokyo_runtime_server_monitor.py`

**Interfaces:**
- Produces `project_owner_notification_intents(control_state, now_ms) -> list[OwnerNotificationIntent]`.
- Consumes Live signals, promotions, lanes, Tickets, exchange commands,
  lifecycle runs, Live Outcome rows, process outcomes, notification ledger,
  and current system health.

- [ ] Write failing tests for `opportunity_detected` using a fresh Live signal
  and proving promotion/lane/Ticket rows do not create duplicate cards for the
  same signal.
- [ ] Write failing tests for `opportunity_not_executed` when a previously sent
  signal becomes stale/rejected/superseded without a submitted Ticket.
- [ ] Write failing tests for submitted trade, protected position, TP1 runner,
  and closed trade; when several stages are visible, assert only the newest
  material stage for the Ticket is emitted.
- [ ] Write failing tests for unprotected position, unknown exchange outcome,
  hard-stopped command, persistent process/system failure, and recovery of a
  previously sent incident.
- [ ] Verify RED against the current single `_recent_pg_chain_event` path.
- [ ] Implement pure per-correlation stage reduction and priority ordering.
- [ ] Preserve the existing top-level monitor decision for health while adding
  `notification_intents`; do not let notification presentation become runtime
  truth.
- [ ] Limit output to five intents, ordered by severity then occurrence time.
- [ ] Run scenario and monitor tests and verify GREEN.

### Task 3: Card Delivery, Dedupe, Retry, And Recovery

**Files:**
- Modify: `scripts/run_tokyo_runtime_server_monitor.py`
- Modify: `tests/unit/test_tokyo_runtime_server_monitor.py`
- Modify: `src/application/owner_notification.py`

**Interfaces:**
- Replaces direct `_notification_text(...)` delivery with typed card payloads.
- Persists template/correlation fields in the existing notification table.

- [ ] Write a failing delivery test asserting the custom Webhook request body
  contains `msg_type=interactive` and a static `card`, not `msg_type=text`.
- [ ] Write a failing dedupe test asserting signal/promotion/lane observations
  with one signal identity send one `opportunity_detected` card.
- [ ] Write a failing retry-cap test: attempts 1-3 may send; attempt 4 remains
  failed without invoking the notifier.
- [ ] Write a failing recovery test: only a previously sent material incident
  creates one `incident_recovered` card; ordinary healthy wait remains silent.
- [ ] Verify RED.
- [ ] Generalize the Feishu sender to accept a complete card payload while
  preserving secret signing and timeout behavior.
- [ ] Replace the single notification application path with a bounded loop over
  projected intents and transaction-safe PG ledger updates.
- [ ] Remove primary rendering of `blocker_class`, `checkpoint`, raw reasons,
  and evidence paths; retain them only in technical refs/PG audit.
- [ ] Verify GREEN, including webhook absent, dry-run, failure, retry, dedupe,
  and quiet paths.

### Task 4: Read-Only Runtime Signal Forensics

**Files:**
- Create: `src/infrastructure/runtime_signal_forensics_repository.py`
- Create: `src/application/runtime_signal_forensics.py`
- Create: `scripts/ops/query_runtime_signal_forensics.py`
- Create: `tests/unit/test_runtime_signal_forensics.py`
- Create: `tests/unit/test_query_runtime_signal_forensics.py`

**Interfaces:**
- Produces `RuntimeSignalForensicsQuery`, `RuntimeSignalForensicsResult`,
  `PgRuntimeSignalForensicsRepository.query(...)`, and a stdout-only CLI.
- Consumes absolute ISO-8601 window, optional StrategyGroup/symbol/side, bounded
  limit, and optional local systemd snapshot.

- [ ] Write failing reducer tests for no-signal covered window, fresh signal
  without Ticket, Ticket without exchange command, submitted/protected/closed
  Ticket, and notification configured/attempted/sent/suppressed/failed.
- [ ] Write failing repository tests proving every query is read-only,
  time-window bounded, filter-aware, and limited to 1000 rows.
- [ ] Write failing CLI tests for required PG, invalid/reversed windows,
  stdout-only JSON, no output path, no apply/live-submit flags, and masked
  configuration facts.
- [ ] Verify RED.
- [ ] Implement typed window/result models and one recursive first-missing-object
  explanation over signal -> promotion -> lane -> Ticket -> exchange command ->
  lifecycle -> outcome.
- [ ] Implement SQLAlchemy read queries for the required PG tables; do not reuse
  current-state filters that remove stale/terminal window evidence.
- [ ] Implement optional local systemd snapshot using a bounded subprocess and
  correct oneshot interpretation.
- [ ] Implement CLI with default limit 200, maximum 1000, stdout only, and
  forbidden-effect flags all false.
- [ ] Verify GREEN.

### Task 5: Skill And Program Integration

**Files:**
- Modify: `.agents/skills/runtime-signal-forensics/SKILL.md`
- Modify: `AGENTS.md`
- Modify: `docs/current/MAIN_CONTROL_ROADMAP.md`
- Modify: `docs/current/MAINLINE_ENGINEERING_PROGRAM_PLAN.md`
- Modify: `docs/current/PROJECT_INFORMATION_ARCHITECTURE.md` if the new current
  contract is registered there.
- Modify: this design and plan with final evidence.

**Interfaces:**
- Skill invokes the deployed command through approved Tokyo SSH and translates
  structured stdout into the existing Chinese report format.

- [ ] Add the exact SSH command pattern, timezone conversion, filter mapping,
  timeout, and failure classification to the Skill.
- [ ] Require the Skill to use the command before ad hoc PG/systemd queries;
  retain direct read-only commands only as a diagnostic fallback when the
  command itself fails.
- [ ] Add card/forensics contract docs to current authority indexes.
- [ ] Mark P0-0 integration complete and P0-1 as the final proactive medium
  package before natural Live calibration.
- [ ] Run placeholder/contradiction scans and current-doc validation.

### Task 6: Regression, Deploy, And Production Acceptance

**Files:**
- Modify deploy expectations/tests for migration 117 only where required.
- No output/report files may be committed.

**Interfaces:**
- Deploys the exact focused branch through the bounded Tokyo git-export path.

- [ ] Run owner-notification, server-monitor, migration, forensics, runtime
  repository, deploy, and production-shaped 22-scope focused suites.
- [ ] Run the full suite after focused tests pass.
- [ ] Run `validate_current_docs_authority.py`,
  `validate_output_artifact_scope.py --git-status --git-tracked`,
  `validate_no_runtime_file_authority.py`,
  `audit_production_runtime_file_io.py --json`, `git diff --check`, and Python
  compilation for new modules/scripts.
- [ ] Commit and push the exact focused branch.
- [ ] Deploy migration 117 and code through the bounded Tokyo deploy path with
  zero exchange write.
- [ ] Run notification dry-run fixtures on Tokyo for every card kind without
  sending cards to the real Webhook.
- [ ] Run the forensics command against a recent production window and verify
  PG lineage, notification delivery facts, masked configuration, bounded rows,
  stdout-only behavior, and no mutations.
- [ ] Verify backend, watcher, monitor, and lifecycle timers; verify production
  file-I/O performance risk remains clear.
- [ ] Do not synthesize a fresh production signal or real order for acceptance.

## Done When

P0-0 is integrated into `dev`; the deployed monitor uses typed static Owner
cards for all material opportunity/trade/incident/recovery scenarios; duplicate
stage jargon is eliminated; delivery retries are bounded; one stdout-only
forensics command powers the existing Skill; migration, focused/full tests,
production constraints, deployment, and Tokyo read-only acceptance pass; and
the project enters feature freeze pending a natural signal or safety incident.
