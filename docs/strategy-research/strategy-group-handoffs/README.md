# Strategy Group Handoff Contract

Status: ACTIVE_V3_HANDOFF_CONTRACT
Last updated: 2026-06-14

## Purpose

This directory converts strategy-research evidence into Strategy Group Handoff
Packs that the main-control window can review and consume.

A handoff pack is not runtime registration. It is not an order, execution
intent, FinalGate input, Operation Layer input, live-profile change,
credential change, exchange write, deployment request, or order-sizing default.

## Required Files

Each strategy group should publish two files:

| File | Reader | Purpose |
| --- | --- | --- |
| `handoff.md` | Owner and main-control review | Human-readable strategy semantics, evidence, scope, risks, and handoff notes. |
| `handoff.json` | Runtime-admission adapter or validator | Stable field contract, supported observation scope, RequiredFacts, risk proposal, hard stops, and sample packets. |

## Required Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `strategy_group_id` | Yes | Stable strategy-group identifier. |
| `version` | Yes | Handoff version for traceability. |
| `supported_symbols` | Yes | Research-supported observation symbols, pending main-control exchange and rule validation. |
| `supported_sides` | Yes | `long`, `short`, or both. |
| `signal_ready_rule` | Yes | Fresh-signal definition, including freshness, confidence, fields, and stale/conflict behavior. |
| `required_facts` | Yes | Facts needed before observation, signal evaluation, candidate preparation, or promotion review. |
| `risk_defaults` | Yes | Research risk proposal only; it must not be interpreted as live order-sizing defaults. |
| `hard_stops` | Yes | Strategy-level reasons to block observation, candidate preparation, or execution review. |
| `sample_signal_packet` | Yes | Example fresh signal output. |
| `sample_no_signal_packet` | Yes | Example no-signal output. |

## Packet Semantics

The strategy-research window owns:

1. Strategy-group semantics.
2. Activation and disable boundaries.
3. RequiredFacts proposals.
4. Research risk proposals.
5. Sample signal/no-signal/stale/conflict packets.
6. Reproducible evidence references.

The main-control window owns:

1. Strategy group admission.
2. Runtime binding.
3. Watcher and notification scope.
4. FinalGate and Operation Layer integration.
5. Real execution boundary.
6. Budget, order sizing, post-submit settlement, reconciliation, and review.

## Handoff Statuses

| Status | Meaning |
| --- | --- |
| `draft` | Human-readable shape exists but JSON contract is not stable. |
| `handoff_ready_for_main_control_review` | Markdown, JSON, RequiredFacts, hard stops, and sample packets exist. |
| `needs_research_revision` | Main-control review found missing fields or unclear strategy semantics. |
| `parked` | The group is preserved for future revival, but should not enter observation now. |

## Boundary

All handoff packs in this directory are research artifacts. They carry no order,
execution intent, exchange-write authority, deploy authority, credential
authority, live-profile authority, FinalGate authority, Operation Layer
authority, OrderLifecycle authority, exchange gateway authority, or order-sizing
authority.
