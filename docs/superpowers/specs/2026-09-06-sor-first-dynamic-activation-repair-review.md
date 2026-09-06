# SOR first Dynamic activation: incident analysis and repair verification

This is engineering incident evidence, not runtime authority. Current deployment,
Owner controls and exposure remain owned by `docs/current/MAIN_CONTROL_ROADMAP.md`
and current PostgreSQL/exchange facts.

## Confirmed failure sequence

Source: Tokyo PostgreSQL materialization events and the Observation journal for
2026-09-06 09:00–09:31 Asia/Shanghai, collected read-only.

| Beijing time | Evidence | Interpretation |
| --- | --- | --- |
| 09:00:04 | Snapshot: 24 Candidates, 22 ready, seven selected | Selection computed successfully |
| 09:00:09–11 | Vacuum fenced and drained | Entry cancellation boundary completed |
| 09:18:45 | Generation STAGED, both target Universes present | Serial warming completed within the 30-minute budget |
| 09:18:45 onward | 261 ValidationError ticks | Activation repeatedly rolled back |
| 09:30:10 | FALLBACK_PREVIOUS and completed fallback Gap Audit | Static pair restored; Dynamic never became active |

The confirmed root cause is the mode assigned to the proposed Authority.
`_complete_pending_authority_gap_audit` copied the current Static mode into
`ACTIVE_NEW`. `SelectionSessionAuthority` correctly rejects that combination:
`ACTIVE_NEW requires dynamic_selection mode`. The control must stay Static until
the transaction commits, but the new Authority must describe the resulting
Dynamic mode. Production-shaped local PostgreSQL tests reproduce this exact
exception; correcting this field makes the first activation succeed.

Increasing the materialization timeout would not fix this deterministic error.
Earlier success tests started in Dynamic mode and therefore missed first activation.

## Repairs and related defects

| Finding | Fix | Verification |
| --- | --- | --- |
| First ACTIVE_NEW used Static mode | Freeze Dynamic mode for successful activation; retain Static only for first fallback | First activation and subsequent switching through the real materialization runtime entry point, with two- and seven-member sets |
| Fallback left ACTIVE_NEW audit pending | Fail the displaced activation audit atomically before staging fallback | Timeout in both modes closes the obsolete audit; fallback remains audited and retryable |
| Two audits of one episode violated suppression uniqueness | Insert once per episode, verify matching first-trigger time and detector, preserve original provenance | Matching evidence accepted; changed time or detector rolls back the second audit |
| Retarget rewrote historical fence/drain times | Preserve original timestamps; timeout starts at max(original fence, replacement Desired time) | Recovered Owner-pause retarget progresses into warming with original fence evidence intact |
| Worker errors exposed only exception type | Emit code filename/function/line without exception arguments or locals | Failure-isolation test proves useful location and no secret input leakage |
| Recovered Owner Pause blocked a new VALID_EMPTY Snapshot | Resolve the drained fence and commit non-trading Dynamic authority without creating a zero-member Generation | Empty/nonempty recovery paths and missing exact recovery-event proof; the abandoned Generation remains abandoned |

## Regression boundary

- First Static-to-Dynamic and subsequent Dynamic-to-Dynamic transitions.
- Serial LONG then SHORT staging, followed by atomic pair activation and mode change.
- Fault injection at old/target scopes, both Universe pointers, Authority row and
  current pointer, terminal Generation, Vacuum resolution and first mode switch.
- A failed transaction preserves previous pair, pending mode, staged targets and
  pending audit. No partial pair or uncommitted mode change is visible.
- Existing tests retain coverage for Owner pause, fallback retry, audit windows,
  source failures, stale facts, Session expiry, latest Snapshot supersession,
  valid-empty non-retroactivity, independent leases and entry suppression.
- Tests use disposable PostgreSQL and typed market/audit fixtures; these prove
  software behavior, not future Binance availability or trading profitability.

## Delivery and remaining acceptance

The release candidate must pass the exact-commit R3 manifest after this review.
Production deployment remains stopped-flat; a protected live Ticket is not flat.
The failed Session must not be revived, the 30-minute parameter remains unchanged,
and a future first activation still uses the official Owner control boundary.

After deployment, acceptance requires actual `ACTIVE_NEW`, Dynamic mode with no
pending transition, the exact selected LONG/SHORT pair, completed Gap Audit,
resolved Vacuum and no unexpected command/position mutation during the switch.
Local certification alone cannot establish that this production acceptance passed.

## Other operational limitation found during review

The release/Entry promotion tooling still has Static membership assumptions:
`certify_readonly.py` compares the active profile against
`APPROVED_UNIVERSE_BATCHES`, `bootstrap_strategy_universes.py` validates the same
Static manifest, and `deploy_tokyo_release.py` has fixed 15-instrument/58-scope
checks. A successfully activated Dynamic set with additional instruments, or
fewer than seven selected members, can fail those later maintenance gates.
This was not the cause of the incident: the Materialization runtime does not use
those CLI gates to activate the pair. It is a separate fail-closed maintenance
limitation, not repaired by the Authority-mode fix. It must be adapted to the
DB-authorized current set before a later deployment/Entry re-promotion in Dynamic
mode; no operator should bypass it by hand-editing members or a Fence.
