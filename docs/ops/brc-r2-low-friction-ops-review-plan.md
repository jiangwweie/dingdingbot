# BRC-R2-001 Low-Friction Campaign Operations And Review Packet

Status: IMPLEMENTING
Date: 2026-05-26

## Purpose

`BRC-R0/R1` proved the bounded campaign loop on Binance testnet with ETH then BTC controlled exposure and mock PnL. `BRC-R2-001` turns that proof into a lower-friction operating layer:

- produce a deterministic campaign review packet;
- expose a read-only next-campaign eligibility gate;
- provide a simple local operator helper for review and eligibility reads;
- draft read-only operator actions from short Owner text;
- build an Owner-confirmed read-only action plan and runner;
- keep real live, withdrawal, transfer, automatic sizing, and LLM trade decisions unauthorized.

This is not a new runtime expansion and does not add a new order path.

## Business Role

The system is now modeled as a `Bounded Risk Campaign System`.

The Owner may run bounded campaigns under an isolated risk bucket, but the system must preserve these hard boundaries:

- campaign PnL continuity across playbook switches;
- no refill of a loss-locked bucket by switching playbooks;
- no third attempt when the risk envelope allows only two attempts;
- no new campaign before final flatness and review;
- no programmatic withdrawal or transfer;
- no real-live action.

## R2 Scope

### Review Packet

The review packet summarizes the latest BRC campaign, including:

- campaign id, status, outcome, current playbook;
- risk bucket and envelope;
- realized mock PnL;
- attempt count and attempt closure state;
- switch decision count;
- mock PnL event count;
- profit-protect and loss-lock trigger flags;
- final inventory flatness when available;
- invariant checks;
- embedded evidence packet.

### Next Eligibility Gate

The gate answers one question:

```text
Can the Owner start another bounded campaign now?
```

Initial policy:

- no prior campaign -> `observe_only`;
- open campaign -> `blocked`;
- non-flat final inventory -> `blocked`;
- ended loss-locked rehearsal -> `owner_review_required` with cooldown required;
- any other ended campaign -> `owner_review_required`.

`next_campaign_allowed=false` is the default until the Owner explicitly authorizes a fresh campaign envelope.

### Operator Medium

The first low-friction medium is a local read-only script:

```bash
python scripts/brc_operator.py review
python scripts/brc_operator.py eligibility
python scripts/brc_operator.py evidence
python scripts/brc_operator.py draft "帮我看下一轮能不能开"
python scripts/brc_operator.py plan "帮我看下一轮能不能开"
python scripts/brc_operator.py --confirm CONFIRM_READ_ONLY_BRC run "帮我看下一轮能不能开"
```

The script calls only local runtime read endpoints. It does not mutate campaign state or exchange state.

The first text-to-machine step is deliberately narrow:

```text
Owner text -> read-only action draft -> endpoint path
```

R2 can draft only:

- `read_review_packet`;
- `read_next_eligibility`;
- `read_evidence`.

Unknown or mutation-like requests are not made executable in R2.

Execution is still not automatic. The read-only runner requires an explicit
confirmation phrase:

```text
CONFIRM_READ_ONLY_BRC
```

The runner re-builds the plan from the Owner text, rejects unknown actions, and
executes only the read-only BRC endpoints modeled by the plan.

## API Additions

Read-only endpoints:

- `GET /api/runtime/test/brc/review-packet`
- `GET /api/runtime/test/brc/next-eligibility`
- `POST /api/runtime/test/brc/operator/draft`
- `POST /api/runtime/test/brc/operator/plan`
- `POST /api/runtime/test/brc/operator/run`

These require local/internal runtime control, Binance testnet mode, and the BRC runtime profile. They do not require test signal injection because they do not mutate state.

## Non-Goals

- no real live trading;
- no mainnet access;
- no withdrawal or transfer endpoint;
- no new testnet order path;
- no strategy implementation;
- no automatic playbook choice;
- no natural-language auto-execution.

Natural-language execution remains a future shell around this sequence:

```text
Owner text -> structured draft -> machine checks -> Owner confirm -> allowed local action
```

R2 implements only the read-only draft/review/check layer.

## BRC-R2-002 Extension

`BRC-R2-002` adds the first Owner confirmation chain:

```text
Owner text -> draft -> read-only execution plan -> confirmation phrase -> read-only run result
```

Hard boundaries:

- `run` accepts only read-only plans;
- `run` requires `CONFIRM_READ_ONLY_BRC`;
- unknown text is blocked;
- mutation-intended plans are blocked;
- result payloads carry `mutation_executed=false`, `withdrawal_executed=false`, and `live_ready=false`.
