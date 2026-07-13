---
title: P1_TEST_FEEDBACK_STRATIFICATION_AND_RELEASE_CERTIFICATION_OPTIMIZATION_DESIGN
status: CURRENT_DESIGN
authority: docs/current/P1_TEST_FEEDBACK_STRATIFICATION_AND_RELEASE_CERTIFICATION_OPTIMIZATION_DESIGN.md
last_verified: 2026-07-13
---

# P1 Test Feedback Stratification And Release Certification Optimization Design

## Decision

The next bounded engineering task is:

```text
P1 Test Feedback Stratification And Release Certification Optimization
```

It shortens developer feedback without changing strategy semantics, risk,
runtime authority, exchange-write authority, lifecycle state, or the complete
release certification boundary. A different-identity natural signal remains a
P0 interrupt for R1B live lifecycle calibration.

## Measured Baseline

The baseline was measured from deployed head `d92a542b` on the isolated branch
`codex/p1-test-feedback-stratification`.

| Measurement | Result | Interpretation |
| --- | --- | --- |
| Existing plain full run | `3021 passed`, `1 skipped`, `13 errors`, `621.28s` wall | The current Python executable lacked declared dependency `psycopg`; pytest continued for ten minutes after the prerequisite failure |
| P0-RCI with declared dependency available | `13 passed` in `42.28s` | PostgreSQL/process certification itself remains healthy |
| Eight-worker unit profile | `3018 passed`, `1 skipped` in `390.48s` | Broad xdist parallelism improves wall time only partially and amplifies database-fixture contention |
| Candidate Mainline base | `2427 passed`, `1 skipped` in `143.22s` wall | Removing complete matrices and other release-only files creates room for representative chain sentinels inside the five-minute budget |
| Candidate Fast contract set | `311 passed` in `9.66s` wall | A deterministic pure/typed contract layer can give sub-minute feedback |

The main source of time is not test count alone. Production-shaped SQLite and
PostgreSQL setup, migration replay, subprocess CLI checks, and full active-scope
matrices dominate wall time.

## Considered Approaches

| Approach | Benefit | Cost or risk | Decision |
| --- | --- | --- | --- |
| Run the complete suite with xdist | Minimal classification work | Eight workers still require `390.48s`; shared database-heavy fixtures contend and deterministic release proof is weaker | Rejected as the default |
| Add manual markers to every test file | Explicit membership | Hundreds of edits, constant marker drift, and new tests can silently miss Mainline | Rejected |
| Central policy with conservative defaults | One reviewable authority, no mass edits, new unit tests default Mainline, new integration tests default Release | Requires a small pytest plugin and an explicit heavy-file/sentinel manifest | Selected |

## Tier Semantics

| Tier | Selection rule | Target | Authority |
| --- | --- | --- | --- |
| `fast` | Explicit stable contract files only | Under `90s`; current candidate is about `10s` | Developer feedback only |
| `mainline` | All unit tests by default, excluding explicit release-only heavy files, plus one or more explicit sentinels from every excluded critical surface | Under `300s` | Commit/mainline regression feedback; not deploy certification |
| `release` | Every collected test, including PostgreSQL/process certification and complete production-shaped matrices | Preserve full `10-12m` boundary | Required before release claims when production behavior changes |

Tier selection is cumulative:

```text
fast subset
-> mainline includes fast and default unit coverage
-> release includes every test
```

No test is deleted. Release uses the same complete collection as plain pytest.

## Central Policy

`tests/feedback_tier_policy.py` owns:

1. The explicit Fast file set.
2. The explicit Release-only heavy file set.
3. Mainline sentinel node IDs that recover representative coverage from every
   excluded critical file.
4. Conservative default rules:
   - new `tests/unit/test_*.py` files enter Mainline;
   - new `tests/integration/test_*.py` files enter Release;
   - Release always includes all collected tests.
5. PostgreSQL release-preflight behavior and masked error messages.

`tests/conftest.py` exposes one stable option:

```text
--test-tier=fast|mainline|release
```

It adds descriptive markers for diagnostics, deselects tests outside the
requested tier before execution, and runs PostgreSQL preflight before a
selected release collection can spend minutes on unit tests.

## PostgreSQL Release Preflight

If the selected collection contains P0-RCI PostgreSQL tests, collection must
fail immediately when either condition is false:

1. The declared `psycopg` dependency can be imported.
2. `BRC_TEST_POSTGRES_ADMIN_URL`, or the existing bounded local default, accepts
   a short `SELECT 1` connection.

The diagnostic may name host, port, database, and dependency installation
command. It must never print a password or complete credential URL.

Fast and Mainline do not require PostgreSQL merely because Release does.

## Stable Commands

```bash
python3 -m pytest -q --test-tier=fast
python3 -m pytest -q --test-tier=mainline
python3 -m pytest -q --test-tier=release
```

Plain `python3 -m pytest -q` remains equivalent to Release selection for
backward compatibility.

## Drift And Coverage Rules

1. Every Release-only critical file must have at least one Mainline sentinel.
2. Every sentinel must belong to its declared Release-only file.
3. Every Fast file must exist and must not be under `tests/integration/`.
4. Unknown test paths fail closed into Release rather than Fast.
5. Tier-policy tests verify the complete manifest and selection matrix.
6. Full release collection count must remain equal to plain pytest collection.
7. Mainline and Fast report deselected counts so their reduced authority is
   visible.

## Cadence And Performance Boundary

| Surface | Required behavior |
| --- | --- |
| Fast edit loop | No PostgreSQL connection, no xdist, no generated JSON/MD, no network/exchange work |
| Mainline loop | Serial deterministic pytest; representative Ticket, FinalGate, Operation Layer, lifecycle, protection, reconciliation, and projection sentinels remain |
| Release loop | Complete serial collection; P0-RCI PostgreSQL/process tests and full scope/failure matrices retained |
| Output | Console only; no benchmark, result, transcript, JSON, Markdown, or report artifacts written by cadence |
| Natural event | Stop at the next committed boundary and switch to R1B natural-event acceptance |

## Authority Boundary

This task must not modify:

```text
strategy parameters
risk or sizing policy
live profile or capital scope
FinalGate or Operation Layer behavior
exchange gateway behavior
ticket or lifecycle state transitions
PG schema or runtime projections
Tokyo runtime cadence
```

It changes developer test selection only. Passing Fast or Mainline never grants
deploy completion, live-submit readiness, exchange-write authority, or R1B live
calibration.

## Acceptance

The task is complete when:

1. Tier policy and plugin tests pass through a RED-GREEN cycle.
2. Fast completes below `90s` and covers the typed/contract core.
3. Mainline completes below `300s` and includes every declared critical
   sentinel.
4. Release selects the exact complete test collection and passes with declared
   dependencies and PostgreSQL available.
5. Missing `psycopg` or unavailable PostgreSQL fails before test execution with
   a masked actionable message.
6. Production runtime file-I/O and output-scope audits remain clear.
7. No production/runtime source file changes.

