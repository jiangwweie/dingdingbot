---
title: RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP
status: CURRENT_CONSTRAINT
authority: docs/current/RUNTIME_CONTROL_STATE_MAINLINE_FILE_IO_MAP.md
last_verified: 2026-07-07
---

# Runtime Control State Mainline File I/O Map

## Purpose

This document no longer lists concrete runtime JSON/Markdown paths. The old
path-level map was useful during migration, but keeping concrete `latest` file
names in current docs now reintroduces the exact behavior the project is
removing.

The current rule is:

```text
production runtime decisions read PG/current services;
production cadence does not write recurring JSON/MD report state;
generated files are explicit diagnostic exports only;
historical file material belongs in archive-only provenance.
```

## Mainline Authority

| Domain | Current source | Forbidden source |
| --- | --- | --- |
| **Strategy registry** | `brc_strategy_groups`, `brc_strategy_group_versions`, RequiredFacts/version tables | Strategy handoff JSON as runtime source |
| **Owner policy and scope** | `brc_owner_policy_events`, `brc_owner_policy_current`, runtime scope bindings | Repo policy JSON or chat-derived packet files |
| **Candidate universe** | PG candidate scope, runtime scope, event bindings | Code fallback constants or generated Candidate Pool exports |
| **Watcher coverage** | `brc_watcher_runtime_coverage` | Watcher latest-status files as authority |
| **Market/account facts** | `brc_runtime_fact_snapshots` with freshness metadata | Public/account latest JSON exports |
| **Live signals** | `brc_live_signal_events` | Replay files or detector JSON exports as live signal |
| **Promotion** | `brc_promotion_candidates` | Candidate Pool JSON as promotion authority |
| **Action-time lane** | `brc_action_time_lane_inputs` | Resume-pack JSON as lane identity |
| **Action-Time Ticket** | `brc_action_time_tickets`, ticket events | Dispatch artifact JSON as ticket identity |
| **Runtime safety** | `brc_runtime_safety_state_snapshots` | Runtime Safety latest JSON exports |
| **Goal status** | `brc_goal_status_current` | Report-dir goal-status JSON as current source |
| **Server monitor** | `brc_server_monitor_runs`, notification rows, readonly systemd facts | Monitor latest JSON or file dedupe state |
| **Owner explanation** | Backend read models over PG/current state | Frontend or readmodel parsing historical files |

## Production Cadence Rules

Production systemd/timer paths must not add:

| Forbidden behavior | Required replacement |
| --- | --- |
| **Read repo MD/JSON for runtime state** | Read PG repositories or typed current services |
| **Read generated latest JSON/MD as current state** | Read the PG row that generated the export |
| **Write recurring JSON/MD reports on every no-signal tick** | Write PG rows only when state changes, otherwise emit low-noise stdout summary |
| **Use local cache as production monitor input** | Server-side monitor reads PG/current state directly |
| **Use file dedupe state for Owner notification** | PG notification dedupe rows |
| **Use file artifacts as trade identity** | PG `ticket_id`, lane id, promotion id, candidate id |

## Explicit Export Rules

Export files are allowed only when all conditions are true:

1. The command is explicitly invoked with an output path.
2. The export path is outside routine commits or under an archive-only target.
3. No production runtime, monitor, FinalGate, Operation Layer, or Owner-facing
   decision reads the export as authority.
4. The export can be regenerated from PG/current state or is marked historical
   provenance.

Default CLI behavior for PG-backed control builders must be stdout-only.

## Review Rule

Any new file read/write in `scripts`, `src`, or production systemd must answer:

| Question | Required answer |
| --- | --- |
| **Is this a runtime/trading decision input?** | Must be PG/current service, not file |
| **Is this recurring?** | Must not write JSON/MD report state on no-signal cadence |
| **Is this historical evidence?** | Archive-only, not current docs or runtime input |
| **Is this a test fixture?** | Small deterministic fixture under tests only |
| **Is this an export?** | Explicit path only, never default latest path |

Closure is verified by:

```text
python3 scripts/audit_production_runtime_file_io.py \
  --max-owner-explanation-file-source 0 \
  --max-frequent-report-write 0 \
  --max-blocking-cleanup-required 0
```
