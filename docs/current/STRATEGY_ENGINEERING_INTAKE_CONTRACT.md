---
title: STRATEGY_ENGINEERING_INTAKE_CONTRACT
status: CURRENT
last_verified: 2026-07-22
---

# Strategy Engineering Intake Contract

## Purpose

Convert an accepted StrategyGroup into typed inputs that the trading kernel can
validate without importing research files or strategy-specific execution code.

## Required Intake

- stable `strategy_group_id` and immutable strategy version;
- versioned `event_spec_id`;
- supported instrument and side scope;
- typed fact definitions and freshness rules;
- a typed live-signal producer contract;
- entry, Initial Stop, take-profit, and invalidation semantics;
- current Owner policy and runtime profile binding;
- negative tests for unsupported side, stale signal, wrong scope, missing facts,
  and malformed protection.

## Kernel Boundary

The strategy layer emits one typed live signal. The kernel validates current
registry, policy, profile, instrument, account mode, fact digest, deadline,
capacity, and Netting Domain before freezing a Ticket.

Research Markdown, replay files, generated JSON, and handoff directories are
not runtime inputs. Strategy-specific code must not dispatch venue commands or
mutate Ticket lifecycle state.
