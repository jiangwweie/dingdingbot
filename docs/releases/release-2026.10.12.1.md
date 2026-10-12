# Project Release — release-2026.10.12.1

## Scope

This immutable repository milestone consolidates the reviewed Trading Kernel
baseline and documentation on synchronized dev/main. It is a project release,
not a new Tokyo deployment, strategy activation or economic-performance claim.
Exact live identity and posture remain owned only by
[Main Control Roadmap](../current/MAIN_CONTROL_ROADMAP.md).

## Included capabilities

| Area | Published baseline | Boundary |
| --- | --- | --- |
| Generic Selection | CPM/MPG/MI/BRF2 frozen Specs, Candidate24, DB Snapshot handoff | Not proven alpha or automatic activation |
| Runtime materialization | Independent leases, Warming, Vacuum/drain, authority and fallback/recovery | Normal latest-unconsumed close differs from failure future-close-only/rebase |
| Comparison | Separate MPG/MI ComparisonUniverse and versioned rebase | No invented rising edge after cohort replacement |
| Capacity B | Same strategy/side2, continuation2; global3, gross6%, direction4%, per-Ticket2% unchanged | Distinct Instrument/Episode/Signal; same Netting Domain1; no rank scheduling |
| ExitProfile Authority | Immutable typed profiles/bindings, CAS and frozen Ticket lifecycle | No YAML authority or profile switch implied by publication |
| Entry restoration | Current-Universe readiness, exact Owner Resume/TOTP proof and paused preparation | No automatic Policy arming or bypass of order-time facts |
| Operations | Low-impact cleanup/retention procedure and release versus runtime tag distinction | No database deletion or server redeployment in this task |
| Documentation | Forward chain through Generic and Capacity revisions; active versus retired strategy scope | Crypto SOR remains permanently retired; TradFi separately paused |

## Evidence and deferred work

Existing exact production R3/R4/R2/R1 evidence remains bound to its original
candidate and command set; this project node does not re-label it as a new
full release certification. This consolidation changes docs and document tests
only, with zero production execution/schema/frontend/service-code delta from
the latest reviewed repository baseline. New document invariants were RED
before the correction; focused/architecture/static verification results are
recorded here:84 Architecture tests PASS (including26 current-document tests),
Ruff PASS and diff-check PASS. No new full Kernel Integration, server load test
or exchange certification was run for this docs/test-only publication.

Full long-run soak, offline MAE/MFE projector, complete GS-13 task acceptance
and first Generic live takeover/economic evidence are not claimed PASS.
Owner Dynamic intent is not successful activation. Existing Tickets continue
their frozen protection/exit/reconciliation/settlement/review lifecycle.

## Version management

- `dev`: integrated development baseline.
- `main`: reviewed published baseline; this Owner-authorized consolidation uses
  fast-forward history when possible, without force-push or redundant merges.
- `release-YYYY.MM.DD.N`: immutable project publication node.
- `tokyo-runtime-YYYY.MM.DD.N`: immutable exact deployed software node.
- GitHub Release/source archives contain tracked files only; no generated
  output, local environment, credentials or disposable research cache.

Historical production snapshots are preserved in
[the archived roadmap](../archive/2026-10-12-main-control-roadmap-history.md).
They are evidence, not current instructions or restore authority.
