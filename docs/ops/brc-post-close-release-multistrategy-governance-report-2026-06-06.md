# BRC Post-Close Release And Multi-Strategy Governance Report

Date: 2026-06-06

## Verdict

PASS_WITH_CONSTRAINT

BNB and Trend/SOL live-action chains are closed to flat exchange state. Local
version state is classified and push-ready, but not pushed. Production service
is healthy, but release governance still has process/source drift: `app/current`
points at the repaired release directory while the active process remains the
older long-lived PID and the server disk tree is dirty. No restart or deploy was
performed in this sprint.

## Local Version Inventory

This inventory was captured before committing this governance report. The
session final output records the post-report commit and tag state.

- branch: `dev`
- HEAD: `4a2819ce docs(brc): record trend sol full chain closure`
- branch status: `dev...origin/dev [ahead 18]`
- worktree before this report file: clean
- latest local closure tag:
  `brc-trend-sol-full-closure-20260606-r0 -> 4a2819ce`

### Commits Ahead Of Origin

| Commit | Area | Subject |
| --- | --- | --- |
| `56801d4a` | Trading Console | `feat(trading-console): add strategy family admission state` |
| `c1e25331` | Trading Console | `docs(trading-console): add gate2 frontend handoff package` |
| `973f4110` | Trading Console | `docs(trading-console): add runtime-bound acceptance evidence` |
| `fc1036b0` | Repo hygiene | `chore(repo): ignore local readonly env files` |
| `09d56a80` | Trend bridge | `feat(brc): add scoped trend action carrier bridge` |
| `e10a2eec` | Trend bridge | `test(brc): prove trend exact-scope bridge fail-closed` |
| `54b264d1` | Trend bridge | `fix(brc): resolve trend scoped clearance bridge` |
| `2ff7a748` | StrategyFamily standard | `feat(brc): add strategy family action candidate standard` |
| `93a09b82` | GenericActionSpec | `feat(brc): add generic action spec entry readiness` |
| `6493a94c` | Generic final gate | `feat(brc): add generic final gate live action chain` |
| `7adfef9d` | Generic final gate | `fix(brc): structure generic probe guard blockers` |
| `07f6793e` | Server readiness | `fix(brc): preserve structured execute blockers` |
| `b9cf59ce` | Server readiness | `fix(brc): separate final gate execute permission mode` |
| `a067ce95` | Server readiness | `fix(brc): expose owner gateway init blockers` |
| `bda6c1fa` | Server readiness | `fix(brc): add server credential preflight readiness` |
| `8c6ddb9a` | Server readiness | `fix(brc): support scoped gks safety clearance` |
| `210353b3` | Trend/SOL governance | `docs(brc): record trend sol live action governance` |
| `4a2819ce` | Trend/SOL closure | `docs(brc): record trend sol full chain closure` |

### Local Tags

Remote already has:

- `brc-trading-console-bnb-close-20260604-r0`
- `brc-trading-console-bnb-close-20260604-r1`

Local-only tags that should be pushed with the post-close baseline:

- `brc-trend-action-bridge-20260604-r0 -> 09d56a80`
- `brc-trend-sol-live-governance-20260606-r0 -> 210353b3`
- `brc-trend-sol-full-closure-20260606-r0 -> 4a2819ce`

## Push Decision Package

Recommended push batch after this governance report commit:

1. Push `dev` including the post-close governance report commit.
2. Push local-only Trend/SOL tags:
   - `brc-trend-action-bridge-20260604-r0`
   - `brc-trend-sol-live-governance-20260606-r0`
   - `brc-trend-sol-full-closure-20260606-r0`
   - `brc-post-close-release-governance-20260606-r0`

Do not include:

- `.env*` or credential files
- `reports/` evidence files
- server-only dirty overlay files
- screenshots, dist, node modules, or local temporary scripts

Evidence files remain local/server artifacts, not tracked git content.

Push was not performed.

## Production Release State

Tokyo service state:

- service: `brc-owner-console-backend.service`
- health: `{"status":"ok","service":"brc_operator_console","runtime_bound":true,"live_ready":false}`
- active port: `127.0.0.1:18080`
- `18081`: not listening
- `app/current`:
  `/home/ubuntu/brc-deploy/releases/trend-sol-governance-8c6ddb9a-202606061415`
- active process: PID `1123809`, started 2026-06-04, command
  `/home/ubuntu/brc-deploy/venvs/brc-bnb-prelive-20260601/bin/python -m src.main`

Server disk source status:

- current release git HEAD: `0a94553`
- disk tree is dirty and contains tracked modifications plus untracked overlay
  files used during readiness/live-action work.
- active process is healthy but not proven to be running exactly from the
  repaired current symlink target.

No service restart was performed because a restart from a dirty release tree is
not a clean release operation.

## Closure Evidence Consolidation

Fresh read-only Tokyo evidence:

- evidence file:
  `/home/ubuntu/brc-deploy/reports/brc-post-close-governance-20260606/current-bnb-sol-state.json`
- local copy:
  `reports/brc-post-close-governance-20260606/current-bnb-sol-state.json`

Current exchange state:

| Symbol | Position Count | Open Orders | Stop Orders |
| --- | ---: | ---: | ---: |
| `BNB/USDT:USDT` | 0 | 0 | 0 |
| `SOL/USDT:USDT` | 0 | 0 | 0 |

Current PG state:

| Symbol | PG Open Orders | PG Active Positions |
| --- | ---: | ---: |
| `BNB/USDT:USDT` | 0 | 0 |
| `SOL/USDT:USDT` | 0 | 0 |

BNB closure summary:

- first BNB live trial closed flat through recovery after protection attach
  failure.
- second BNB live trial closed flat through recovery after hedge-mode
  reduce-only protection rejection.
- later BNB bounded live chain validated entry, TP/SL protection, and closeout
  through Trading Console evidence.
- all listed BNB authorizations in current Tokyo PG evidence are consumed.
- current BNB exchange and PG state are flat with no open or stop orders.

Trend/SOL closure summary:

- authorization:
  `auth-8e591fb066af43578094c27064ede55f`, consumed.
- intent:
  `intent-e6ec405fa0fe4ba1bc82d3b246a6c9ef`, `completed`.
- entry:
  `218766349737`, filled `0.1` at observed price `62.38`.
- TP:
  `218766349863`, filled `0.1` at observed price `63.0`.
- residual SL/algo:
  `4000001500443218`, no longer visible in stop-order reads.
- PG TP local row is `FILLED`.
- PG SL local row is `CANCELED`.
- PG position projection is closed with `current_qty=0`.
- post-live closure result:
  `post-live-closure-auth-8e591fb066af43578094c27064ede55f`.
- order audit logs exist for TP filled and SL canceled transitions.

Known evidence gap:

- the SOL residual SL cleanup response payload was not captured because the
  cleanup script failed after the exchange fallback cancellation and before
  final audit serialization. Later read-only evidence proves the observable
  result: stop-order count moved to zero and remains zero.

## Blocker Records

### BR-POSTCLOSE-RELEASE-DIRTY-RUNTIME-20260606

- stage: release governance
- path: Tokyo `app/current` and active systemd process
- evidence: `app/current` points to the repaired release directory, but the
  active process is the older long-lived PID and the release tree is dirty
- severity: medium
- bridge: leave service running because it is healthy; do not restart from a
  dirty tree
- retry_condition: create a clean release artifact from pushed `dev`, verify
  tags, repoint `current`, then perform a planned restart and post-restart API
  route check

### BR-POSTCLOSE-SOL-CANCEL-RESPONSE-NOT-CAPTURED-20260606

- stage: closure evidence
- path: SOL residual stop cleanup
- evidence: result envelope records `cleanup_response_captured=false` while
  final exchange truth shows stop orders zero
- severity: medium
- bridge: preserve the explicit gap in reports and rely on post-cleanup
  exchange/PG evidence
- retry_condition: future cleanup scripts must persist the exchange response
  before audit-log writes and generate audit IDs within schema limits

### BR-POSTCLOSE-SERVER-OVERLAY-NOT-VERSIONED-20260606

- stage: version governance
- path: Tokyo disk tree
- evidence: server `git status` shows many modified and untracked overlay files
- severity: medium
- bridge: local repo is clean and ahead with committed source; do not classify
  server overlay as canonical source
- retry_condition: push local canonical commits, deploy from clean checkout, and
  archive or remove untracked server overlay files during a maintenance window

## Next Multi-Strategy Candidate Plan

Principles:

- Trend exact-scope action path remains the only non-BNB strategy action bridge
  proven through bounded live execution.
- Volatility Expansion and Mean Reversion remain proposal/non-action until a
  first-class `ActionCandidateSpec -> GenericActionSpec -> FinalGate` path is
  implemented and tested.
- Strategy weakness, incomplete signal markers, fee/funding/slippage gaps, and
  incomplete UI remain risk disclosures, not automatic blockers for tiny
  bounded actions.
- Hard blockers remain Owner authorization, exact scope mismatch, exposure
  unreadability/conflict, invalid mandatory TP/SL plan, PG/review/audit
  recording failure, credential/profile mismatch, and runtime guard conflict.

Next sprint outline:

1. Freeze ActionCandidate inputs for `VB-001-live-readonly-v0` and
   `MR-001-live-readonly-v0` as L2 proposal rows with no action enablement.
2. Add proposal-to-GenericActionSpec preview contracts for Volatility Expansion
   and Mean Reversion with `frontend_action_enabled=false` and
   `may_execute_live=false`.
3. Extend final-gate diagnostics to classify why each proposal is not
   action-capable without creating authorization, intent, order, or PG mutation.
4. Select at most one candidate for action-bridge work after Owner scope is
   explicit; keep symbol/side/qty/notional/leverage/protection exact.
5. Require pre/post read-only exchange and PG evidence, mandatory TP/SL plan,
   review envelope, and retry/duplicate proof before any production attempt.

## Checks

- `git status --short --branch`: pre-report baseline clean,
  `dev...origin/dev [ahead 18]`
- `git diff --check`: passed
- `python3 -m alembic heads`: `042 (head)`
- Tokyo `/api/health`: passed
- read-only BNB/SOL PG and exchange verification: passed
- evidence JSON parse for current BNB/SOL state: passed

No pytest was run because this sprint only adds governance documentation and
read-only evidence. No code was changed.

## Safety Proof

- No new live strategy action was started.
- No order was placed.
- No cancel, replace, flatten, retry protection, or auto-execution was
  performed in this sprint.
- No broad action API was enabled.
- No production service restart was performed.
- No credentials or secret values were printed or committed.
- No push was performed.
