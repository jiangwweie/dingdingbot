# Task 13 Replacement Full-chain Checkpoint

Date: 2026-07-29
Scope: local disposable PostgreSQL only

## RED

The dedicated replacement chain activated atomically, but readonly
certification exposed no bounded lifecycle counts, so it could not prove the
absence of a dual-active pool or an unavailable window.

## GREEN

The new full-chain test proves:

- before replacement: two old active scopes and two new warming scopes;
- after replacement: two new active scopes and two old retired scopes;
- exactly one current pointer;
- zero Ticket, command, position, and Incident side effects;
- readonly Universe structural certification passes before and after the
  replacement.

Readonly certification now returns active/warming/retired scope counts from the
same bounded aggregate query used for Universe integrity.

## Evidence

- replacement plus activation/scripts/cutover regression:
  `53 passed in 30.17s`;
- focused post-format regression: `2 passed in 2.49s`;
- focused Ruff and `git diff --check`: passed.

Failure recovery, query-bound/EXPLAIN, architecture audit, and final complete
suite remain.
