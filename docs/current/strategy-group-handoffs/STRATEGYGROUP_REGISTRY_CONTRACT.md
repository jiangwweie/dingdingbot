---
title: STRATEGYGROUP_REGISTRY_CONTRACT
status: CURRENT
last_verified: 2026-07-22
---

# StrategyGroup Registry Contract

## Purpose

The registry owns versioned strategy and event semantics. PostgreSQL rows are
runtime authority; this document defines their meaning and seed boundary.

## Required Fields

| Field | Meaning |
| --- | --- |
| `strategy_group_id` | Stable strategy identity |
| `strategy_version_id` | Immutable strategy semantics version |
| `event_spec_id` | Typed live event contract |
| `supported_sides` | Explicit long/short scope |
| `candidate_instruments` | Canonical supported instruments |
| `required_facts` | Typed facts and freshness rules |
| `protection_semantics` | Initial Stop and exit meaning |
| `status` | Enabled, paused, parked, or retired |

## Active Event Semantics

| StrategyGroup | Event | Side |
| --- | --- | --- |
| `CPM-RO-001` | `CPM-LONG` | long |
| `MPG-001` | `MPG-LONG` | long |
| `MI-001` | `MI-LONG` | long |
| `SOR-001` | `SOR-LONG` | long |
| `SOR-001` | `SOR-SHORT` | short |
| `BRF2-001` | `BRF2-SHORT` | short |

Unsupported opposite sides are rejected. A new side or changed signal meaning
requires a new versioned event contract and tests; it is never inferred from a
name or enabled by mirroring.

## Boundary

The registry does not create current signals, Tickets, commands, orders, or
positions. It never upgrades Owner policy or runtime safety authority.
