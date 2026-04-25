# Backend Readonly API and API Module Roadmap

> Date: 2026-04-25
> Status: Planning
> Current decision: **Backend-first, read-only API surface next**
> Scope: give the new console stable data, then gradually reduce `src/interfaces/api.py` coupling

---

## 1. Why this is the next main line

The frontend scaffold is now sufficient to continue iterating.

The next bottleneck is no longer page structure; it is the lack of stable backend
read-only data contracts behind the console.

The system needs:

1. runtime observation data
2. portfolio / position visibility
3. event and alert timelines
4. research candidate / replay / backtest read models
5. frozen config snapshot preview

That makes backend read-only API the most valuable next step.

---

## 2. Big direction summary

### Direction A - Build read-only console APIs first

Purpose:

- replace mock-first frontend data with real read-only backend data
- keep the first integration low risk
- avoid write endpoints and control paths

Decision:

- do it first
- keep it read-only
- make it page-oriented, not table-oriented

### Direction B - Keep `api.py` alive for now, but start shrinking it

Purpose:

- current `src/interfaces/api.py` still participates in startup
- it should not be rewritten in one shot
- it should be gradually decomposed into clearer router/service boundaries

Decision:

- do not remove it immediately
- do not break the embedded startup path yet
- start moving console-specific read models into smaller units

### Direction C - Keep Sim-1 runtime as the source of truth

Purpose:

- runtime pages should reflect actual running state
- console should observe the same runtime snapshot / repositories
- no separate “UI truth”

Decision:

- backend read models must be derived from the runtime main process and its repositories
- no UI-side state should become authoritative

---

## 3. Key decisions by big item

### 3.1 Runtime read-only APIs

Decision:

1. Add page-oriented read models.
2. Keep them read-only.
3. No new write endpoints.
4. Prefer aggregated payloads over raw repository dumps.

Required surfaces:

- overview
- portfolio
- positions
- signals
- attempts
- execution intents
- orders
- events
- health

### 3.2 Research read-only APIs

Decision:

1. Candidate and replay data should come from artifact/read-model APIs.
2. Candidate review remains display-only.
3. Backtests and compare are read-only at this stage.

Required surfaces:

- candidates list
- candidate detail
- candidate review summary
- replay context
- backtests list/detail
- compare read model

### 3.3 Config snapshot API

Decision:

1. Config snapshot is read-only.
2. It must reflect frozen runtime state.
3. It is a preview surface, not a config editor.

Required surfaces:

- runtime profile identity
- market snapshot
- strategy snapshot
- risk snapshot
- execution snapshot
- backend summary
- source-of-truth hints
- frozen flags

### 3.4 `api.py` refactor posture

Decision:

1. Keep startup dependency injection working.
2. Avoid a one-shot rewrite.
3. Move toward smaller console-facing routers/services.
4. Split read models by domain when safe.

Practical boundary:

- embedded startup stays for now
- console read APIs can be extracted behind clearer modules
- standalone runtime API and future control-plane API should not be mixed further

---

## 4. Current planning items

### Item 1 - Freeze frontend contract

Goal:

- stabilize mock payload shape and page expectations

What must be frozen:

- page tree
- route names
- field names
- freshness semantics
- review status semantics
- replay context semantics

### Item 2 - Build backend read-only API v1

Goal:

- replace mock data with real backend data for the console

What must be delivered:

- runtime overview
- runtime portfolio
- runtime positions
- runtime events
- runtime health
- research candidates
- candidate detail
- candidate review summary
- replay context
- config snapshot

### Item 3 - Add backend read-model adapters

Goal:

- keep API handlers thin
- isolate aggregation logic

What must be delivered:

- runtime state adapter
- portfolio adapter
- position adapter
- event timeline adapter
- candidate artifact adapter
- backtest artifact adapter
- config snapshot adapter

### Item 4 - Decompose `src/interfaces/api.py`

Goal:

- reduce coupling without breaking startup

What must be delivered:

- route grouping by domain
- move console read endpoints into clearer modules
- keep old path as compatibility layer if needed

### Item 5 - Sim-1 verify against real data

Goal:

- validate the read-only API against live Sim-1 data

What must be delivered:

- freshness / heartbeat correctness
- portfolio / positions correctness
- health / breaker / recovery correctness
- candidate / replay correctness

---

## 5. API priority order

### P0 - Runtime observation

1. `GET /api/runtime/overview`
2. `GET /api/runtime/portfolio`
3. `GET /api/runtime/positions`
4. `GET /api/runtime/events`
5. `GET /api/runtime/health`

### P1 - Runtime details and research entry

1. `GET /api/runtime/signals`
2. `GET /api/runtime/attempts`
3. `GET /api/runtime/execution/intents`
4. `GET /api/runtime/execution/orders`
5. `GET /api/research/candidates`
6. `GET /api/research/candidates/{candidate_name}`
7. `GET /api/research/candidates/{candidate_name}/review-summary`
8. `GET /api/research/replay/{candidate_name}`

### P2 - Research depth and snapshot

1. `GET /api/research/backtests`
2. `GET /api/research/backtests/{report_id}`
3. `GET /api/research/compare/candidates`
4. `GET /api/research/compare/backtests`
5. `GET /api/config/snapshot`

### P3 - Optional later surfaces

1. runtime alerts
2. research runs
3. artifact explorer

---

## 6. Implementation steps

### Phase 1 - Contract lock

1. Freeze frontend page tree and field names.
2. Define each page's backend read model.
3. Decide the payload for `overview`, `portfolio`, `positions`, `events`, `health`.
4. Decide artifact payloads for candidates and replay.
5. Mark config snapshot as read-only.

### Phase 2 - Backend read models

1. Implement runtime overview adapter.
2. Implement portfolio adapter.
3. Implement positions adapter.
4. Implement events adapter.
5. Implement health adapter.
6. Implement candidate list/detail adapter.
7. Implement replay context adapter.
8. Implement config snapshot adapter.

### Phase 3 - API wiring

1. Add or extend console-facing routers.
2. Keep handlers thin.
3. Reuse current repositories and runtime providers where possible.
4. Preserve embedded startup behavior.

### Phase 4 - API module shrinkage

1. Group routes by domain.
2. Move read-only console endpoints to smaller modules.
3. Keep old behavior working during the transition.
4. Avoid a one-shot `api.py` rewrite.

### Phase 5 - Sim-1 verification

1. Point frontend from mock to backend for one page at a time.
2. Verify data freshness and correctness.
3. Confirm read-only surfaces do not mutate runtime state.
4. Review any mismatch against Sim-1 observations.

---

## 7. To-do steps for the current planning items

### To-do A - Frontend contract freeze

1. Lock the current page tree from `gemimi-web-front`.
2. Freeze `Runtime / Portfolio`, `Runtime / Positions`, `Runtime / Events`, `Config / Snapshot`, `Research / Candidate Review` as official pages.
3. Freeze the field naming in mock payloads.
4. Freeze read-only semantics in the docs.

### To-do B - Runtime API v1

1. Define `overview` payload fields.
2. Define `portfolio` payload fields.
3. Define `positions` payload fields.
4. Define `events` payload fields.
5. Define `health` payload fields.
6. Decide where each payload is sourced from in the current main process.

### To-do C - Research API v1

1. Define candidate list payload.
2. Define candidate detail payload.
3. Define review summary payload.
4. Define replay context payload.
5. Define backtests and compare payloads.

### To-do D - Config snapshot v1

1. Define frozen snapshot fields.
2. Decide what comes from runtime profile vs code defaults.
3. Keep the page read-only.

### To-do E - `api.py` decoupling

1. Identify the console-facing endpoints currently living in `src/interfaces/api.py`.
2. Separate them into domain groups.
3. Extract the read-only console endpoints first.
4. Keep embedded startup compatibility.

### To-do F - Sim-1 validation

1. Reconcile frontend mock values with real Sim-1 data.
2. Confirm freshness / heartbeat behavior.
3. Confirm portfolio and position values.
4. Confirm events and health summaries.
5. Confirm candidate and replay payloads.

---

## 8. Success criteria

This phase is successful when:

1. The frontend can switch from mock to backend with minimal churn.
2. Runtime observation pages are backed by stable read-only APIs.
3. Research pages are backed by artifact/read-model APIs.
4. Config snapshot remains read-only.
5. `api.py` is no longer growing as a monolith.

---

## 9. Non-goals

1. No config editor.
2. No runtime hot reload.
3. No write-back from the console.
4. No websocket UI in the first pass.
5. No one-shot `api.py` rewrite.
6. No public internet exposure by default.

