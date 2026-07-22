---
title: Tokyo Production Cutover And Runtime Design
status: OWNER_AUTHORIZED_IMPLEMENTATION
date: 2026-07-23
---

# Tokyo Production Cutover And Runtime Design

## Objective

Deploy the rebuilt trading kernel to Tokyo, replace every retired BRC runtime
authority, prove one small real-funds Ticket through terminal Review, then
enable the already approved multi-position operating envelope. The cutover
must not change or interrupt Owner AI, Dingding Bot, nginx infrastructure, or
any other non-quantitative program.

## Evidence And Fixed Decisions

- The exchange account is live Binance USD-M and exposes independent long and
  short sides.
- Current exchange truth is flat with zero regular orders and zero conditional
  or protection orders.
- Legacy PostgreSQL has 187 public tables, 772 MB of data, no active budget,
  no open Incident, no unknown command outcome, and only terminal old Tickets.
- The old approved per-Ticket boundary is 20 USDT notional at 2x leverage.
- The old approved account boundary is at most two concurrent positions.
- The Owner authorized destructive BRC-only cleanup, one small real-funds
  Ticket, full in-boundary write capability after successful closure, and an
  hourly server observation task with engineering repair and redeployment.

No new Owner policy decision is required by this design. It preserves the
existing risk envelope and narrows the acceptance stage below that envelope.

## Alternatives

| Approach | Repeatable | Deletes retired authority | Non-quant isolation | Decision |
| --- | --- | --- | --- | --- |
| Manual shell cutover | No | Partial | Operator-dependent | Rejected |
| Reuse old runtime adapters | Yes | No | Medium | Rejected |
| New kernel runtime factories plus committed cutover adapter | Yes | Yes | Strong | Selected |

## Target Deployment Boundary

```text
/opt/brc/releases/brc-trading-kernel-<commit>
/opt/brc/current -> exact accepted release
/etc/brc/trading-kernel.env
/etc/systemd/system/brc-trading-kernel-*.service
/etc/systemd/system/brc-trading-kernel-*.timer
Docker: brc-trading-kernel-pg
Database: brc_trading_kernel
```

The existing `owner_ai_*` containers, `owner-ai-gateway` nginx site, host
infrastructure services, and non-BRC cron entries are immutable comparison
targets during the cutover.

## Runtime Components

### Production Market Factory

Build one public Binance USD-M CCXT source from the canonical six-instrument
Registry mapping. It has no credentials and only supplies closed candles.

### Production Venue Factory

Build one authenticated Binance USD-M CCXT adapter from masked environment
credentials and exact `venue + account` identity. It owns action-time account
facts, instrument-rule reads, durable command execution, position truth,
unknown-outcome reconciliation, lifecycle facts, and Review Economics.

Every oneshot process closes its exchange client before exit. Credentials are
never printed or persisted outside `/etc/brc/trading-kernel.env`.

### Runtime Authority Seed

One idempotent seed installs:

- the six versioned Event contracts and 22 candidate scopes;
- one live independent-sides runtime profile;
- all 22 runtime scopes;
- one global ENTRY lane and zero account exposure;
- exact commit, schema, and Registry identities;
- acceptance Owner Policy;
- runtime capabilities with new ENTRY disabled initially.

Instrument rules are refreshed from public venue metadata at action time and
persisted as bounded current projections. Ticket issuance fails closed if the
live rule read or persistence is unavailable.

### Tokyo Cutover Adapter

The committed adapter is the only production implementation of the cutover
protocol. It owns exact BRC service names, the dedicated PostgreSQL container,
release symlink, short-lived snapshot, schema bootstrap, authority seed,
readonly certification, and staged capability restoration.

It may never enumerate or mutate targets using broad service, container,
database, directory, or backup wildcards.

## Capability Stages

| Stage | Observation | New ENTRY | Lifecycle writes | Policy envelope |
| --- | --- | --- | --- | --- |
| Post-cutover readonly | Enabled | Disabled | Recovery only | 1 Ticket, 20 USDT, 2x |
| Acceptance armed | Enabled | One serialized Ticket | Enabled for accepted Ticket | 1 Ticket, 20 USDT, 2x |
| Full approved runtime | Enabled | Serialized | Concurrent per Ticket | 2 Tickets, 40 USDT gross, 2x |

New ENTRY capability is distinct from mandatory protection and controlled-exit
continuation. Disabling new ENTRY must never strand an already accepted Ticket
without Initial Stop, reconciliation, or flatten authority.

## Cutover Flow

```text
upload exact committed release
-> create isolated target PostgreSQL container and empty database
-> prove exchange flatness and legacy terminality
-> create write fence
-> stop and disable exact old BRC units
-> repeat exchange and writer verification
-> create short-lived legacy DB snapshot
-> install 0001_initial in target DB
-> seed Registry and acceptance runtime authority
-> switch /opt/brc/current
-> install four Worker units
-> enable Observation only
-> certify schema, seed, account mode, flatness, and signal production
-> arm one acceptance Ticket
-> protect, reconcile, exit, settle, and review it
-> expand only to the prior approved two-Ticket envelope
-> delete old BRC DB container, DB volume, releases, reports, backups, units,
   nginx console, env copies, and short-lived snapshot
-> prove non-quantitative baseline unchanged
```

## Failure Handling

- Any identity, account mode, stale fact, occupied domain, missing rule,
  missing protection, unknown outcome, writer overlap, schema mismatch, or
  non-quantitative drift disables new ENTRY.
- A Ticket already accepted retains protection, reconciliation, and controlled
  exit authority.
- Cutover resumes from the first unverified phase and never restores retired
  BRC runtime authority after the new schema is accepted.
- An hourly observation task classifies the first blocker, keeps new ENTRY
  fail-closed, repairs code/config/schema/service defects locally, commits the
  fix, redeploys the exact commit, and reruns readonly gates before restoration.

## Verification

Tests must prove:

1. production factories reject missing or mismatched identity and never log
   credentials;
2. every exchange client is closed;
3. action-time instrument rules are live, fresh, and persisted;
4. new ENTRY capability can be disabled without blocking an active Ticket's
   protection or exit;
5. the runtime seed is exact and idempotent;
6. the production cutover adapter refuses every failed hard gate and targets
   only the explicit BRC allowlist;
7. the empty target database contains exactly the 33-table kernel baseline;
8. the final Tokyo state has exact commit/schema/seed identity, four healthy
   Workers, one terminal reviewed acceptance Ticket, no residue, and unchanged
   non-quantitative services.

