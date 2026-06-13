# Runtime Governance P0 Fresh Attempt Readiness - 2026-06-13

## Validation Scope

This document records P0-B fresh strategy-driven attempt readiness. It converts
the post-refactor rule into an auditable packet:

```text
operator live-fact gate
-> fresh strategy signal
-> fresh candidate / signal evaluation
-> fresh readiness evidence
-> fresh authorization
-> action-time FinalGate
```

The packet is not execution authority. It does not authorize an order, close,
exchange submit, withdrawal, transfer, runtime budget mutation, or bypass of
the Operation Layer.

## Source Artifacts

| Source | Role |
|---|---|
| `scripts/build_runtime_operator_live_fact_packet.py` | P0-A live fact gate |
| `scripts/build_runtime_fresh_attempt_readiness_packet.py` | P0-B fresh attempt readiness guard |
| `scripts/runtime_fresh_signal_prepare_loop.py` | Fresh signal observation / prepare loop source |
| `scripts/runtime_fresh_signal_readiness_bridge.py` | Fresh signal to readiness / handoff bridge |
| `scripts/runtime_real_signal_readiness_evidence_resolver.py` | Explicit readiness evidence resolver |
| `scripts/runtime_official_fresh_candidate_final_gate_preflight_proof.py` | Fresh candidate FinalGate proof |

## Required Chain

| Stage | Required evidence | If missing or blocked |
|---|---|---|
| Live fact gate | P0-A operator packet status `ready_for_strategy_signal` | Do not start a fresh attempt |
| Fresh strategy signal | Fresh signal loop status `waiting_for_signal`, `ready_for_prepare`, or `ready_for_final_gate_preflight` | Continue observation |
| Fresh candidate | New signal evaluation or shadow candidate from the fresh signal path | Do not use old candidate |
| Readiness evidence | Fresh FinalGate, trusted facts, idempotency, protection, account, position, deployment evidence | Collect evidence explicitly |
| Fresh authorization | Runtime grant, Owner submit authorization, or fresh submit authorization | Do not replay consumed authorization |
| Action-time FinalGate | Official action-time preflight / handoff preview | No submit without current gate |

## Status Contract

| Packet status | Meaning | Allowed operator action |
|---|---|---|
| `blocked_by_live_fact_gate` | P0-A live fact gate is not ready | Resolve position/protection/gate first |
| `waiting_for_fresh_strategy_signal` | Runtime can observe but no fresh signal is ready | Continue read-only signal observation |
| `ready_for_readiness_evidence` | Fresh signal path is ready enough to collect machine evidence | Collect explicit readiness facts |
| `waiting_for_fresh_authorization` | Evidence path needs fresh runtime grant / submit authorization | Bind or resolve fresh authorization |
| `ready_for_action_time_gate` | Fresh path is ready for official action-time gate review | Run action-time FinalGate before any submit |
| `blocked_legacy_authorization_replay` | A source attempted to treat old authorization as current authority | Discard legacy authority and restart fresh chain |
| `blocked_forbidden_effect` | A source report claims an execution side effect occurred | Stop and review side-effect evidence |

## Current Tokyo Classification

The current P0-A live fact packet for Tokyo classifies the active BNB runtime as
`waiting_for_position_resolution`. Therefore the P0-B packet must classify the
current state as `blocked_by_live_fact_gate`.

Current blocking facts:

| Fact | Value |
|---|---|
| Runtime instance | `strategy-runtime-e6138ad7c88f` |
| Symbol | `BNB/USDT:USDT` |
| Side | `long` |
| Active position present | `true` |
| Open stop order count | `1` |
| Protection status | `hard_stop_only` |
| Next-attempt gate | `waiting_for_position_resolution` |

This means the next attempt cannot start from an old first-real-submit packet,
old prepared authorization, old handoff, or old readiness evidence. The system
must first reach a ready live fact gate, then observe a fresh strategy signal.

## Builder Command

```bash
python3 scripts/build_runtime_fresh_attempt_readiness_packet.py \
  --operator-live-fact-packet-json /tmp/brc-p0a-operator-live-fact-packet.json \
  --output-json /tmp/brc-p0b-fresh-attempt-readiness-packet.json
```

Expected current status:

```text
blocked_by_live_fact_gate
```

## Safety Invariants

| Invariant | Required value |
|---|---:|
| `packet_only` | `true` |
| `reads_json_reports_only` | `true` |
| `api_called_by_builder` | `false` |
| `pg_called_by_builder` | `false` |
| `exchange_called_by_builder` | `false` |
| `exchange_write_called_by_builder` | `false` |
| `order_lifecycle_called_by_builder` | `false` |
| `submit_endpoint_called_by_builder` | `false` |
| `runtime_state_mutated_by_builder` | `false` |
| `withdrawal_or_transfer_created_by_builder` | `false` |

## Operator Conclusion

P0-B is now explicit: a fresh strategy-driven attempt is not just "find a
signal." It is a complete current-evidence chain. The first gate in that chain
is the P0-A live fact packet, and the current Tokyo state blocks new attempt
entry until the active BNB position is resolved or separately reviewed.
