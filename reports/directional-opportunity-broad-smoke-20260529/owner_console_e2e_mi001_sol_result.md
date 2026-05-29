# Owner Console E2E MI-001 SOL Result

Generated: 2026-05-29

Scope: Owner Console E2E mainline acceptance for `MI-001 SOL/USDT:USDT long`.

This is not trial start. It does not place orders, cancel orders, create execution intent, grant execution permission, modify leverage, start strategy execution, or modify `exchange_gateway`.

## 1. Summary

Implemented a narrow Owner Console mainline view for MI-001 SOL readiness:

- added read-only backend aggregate endpoint `GET /api/brc/readiness/mi001-sol`;
- added Command Center MI-001 SOL readiness panel;
- exposed the existing guard-only action `POST /api/brc/readiness/startup-guard/preflight-arm` as an Owner-visible readiness action with explicit disabled conditions;
- kept start trial, place order, and execution permission actions disabled/non-exposed.

Current terminal state remains:

`blocked_startup_guard_runtime_coupled`

Reason: the guard-only endpoint exists, but there is no bound runtime listener in this shell for arming the actual runtime-owned startup guard.

## 2. Path Chosen

Path B + Path A frontend slice.

Reason:

- Existing backend had the guard-only startup guard endpoint but no MI-001-specific Owner Console aggregate view.
- Existing Command Center was the correct frontend first screen for Owner acceptance.
- A small read-only aggregate endpoint and Command Center panel can show the full MI-001 chain without touching execution/order/runtime start files.

## 3. E2E Matrix

| step | backend_source | api_available | frontend_available | status | gap | recommended_action |
| --- | --- | --- | --- | --- | --- | --- |
| 1. Strategy family list | `brc_strategy_family_registry`, `brc_strategy_families` | yes: `GET /api/brc/readiness/mi001-sol` summary refs | yes: Command Center panel | pass | dedicated registry browser not required for this flow | keep as read-only summary |
| 2. Candidate detail | MI-001 SOL candidate/admission registration | yes | yes | pass | none for mainline | show candidate id, symbol, side |
| 3. Evidence summary | broad smoke evidence packet | yes | yes | pass | detailed packet viewer remains separate | show signal count and 72h/7d summary |
| 4. Risk disclosure | trial constraint snapshot / risk policy | yes | yes | pass | none for mainline | show max leverage, cap rule, prohibitions |
| 5. Owner acceptance | Owner risk acceptance + trial-start metadata approval | yes | yes | pass | none for mainline | show approval as metadata only |
| 6. PG registration status | PG registration/apply records | yes | yes | pass | full table drilldown not implemented | show source refs |
| 7. Trial policy / risk boundary | trial constraint snapshot + Operation cap | yes | yes | pass | none for mainline | show dedicated subaccount and no-expansion rules |
| 8. Account facts | live read-only account facts result / readiness checklist | yes | yes | pass | endpoint uses readiness view values, not a fresh account refresh | use account facts page for refresh |
| 9. Readiness checklist | generated checklist artifact and runtime guard summary | yes | yes | pass | checklist markdown not rendered verbatim | show verdict/checks/blockers |
| 10. Blocker display | checklist final verdict | yes | yes | pass | none | show `blocked_startup_guard_runtime_coupled` |
| 11. Startup guard preflight action | `POST /api/brc/readiness/startup-guard/preflight-arm` | yes | yes | pass with condition | disabled until runtime context + guard + env gate exist | call only from runtime-bound Owner Console |
| 12. Terminal state | MI-001 aggregate view | yes | yes | pass | no final manual start packet yet | keep terminal state blocked until guard is armed |

## 4. Implemented Changes

Backend:

- `src/interfaces/api_brc_console.py`
  - Added named Pydantic view models for MI-001 SOL Owner Console readiness.
  - Added `GET /api/brc/readiness/mi001-sol`.
  - Endpoint is read-only and returns non-permission flags.

Frontend:

- `gemimi-web-front/src/services/api.ts`
  - Added MI-001 readiness response types.
  - Added `brcApi.mi001SolReadiness()`.
  - Added `brcApi.armStartupGuardPreflight()`.
- `gemimi-web-front/src/pages/brc/CommandCenter.tsx`
  - Added MI-001 SOL readiness panel.
  - Shows candidate, evidence, risk cap, blocker, allowed startup guard preflight action, and non-permissions.
  - Button remains disabled unless backend says the runtime-owned guard can be armed.

Tests:

- `tests/unit/test_brc_console_api_surface.py`
  - Added coverage for MI-001 Owner Console view.
  - Added coverage that startup guard action is enabled only when runtime context, guard, and env gate exist.
  - Confirms no guard arm happens during read-only view.

## 5. Console Acceptance Flow

Owner opens:

`/command-center`

Owner sees:

1. `MI-001-SOL-LONG · SOL/USDT:USDT · long`
2. evidence summary: `8135` signals, `72h mean 1.9531`, `7d mean 4.7372`
3. risk cap summary: max leverage `5`, Operation Layer cap `18262.85481460`
4. current verdict: `blocked_startup_guard_runtime_coupled`
5. current blocker: runtime-owned startup guard is not armed in this console process
6. allowed readiness action: `Arm startup guard preflight`
7. disabled/non-permitted actions:
   - start trial
   - place order
   - grant execution permission
   - runtime start
   - leverage change

If the Owner Console is connected to a runtime-bound process with initialized startup guard and `RUNTIME_CONTROL_API_ENABLED=true`, the panel enables `Arm startup guard preflight`.

Clicking that action calls only:

`POST /api/brc/readiness/startup-guard/preflight-arm`

The action response is required to report:

- `trial_started=false`
- `execution_intent_created=false`
- `order_created=false`
- `execution_permission_granted=false`
- `order_permission_granted=false`
- `exchange_write_methods_called=false`

## 6. Safety Check

| check | answer |
| --- | --- |
| 是否启动 trial？ | no |
| 是否下单？ | no |
| 是否创建 execution intent？ | no |
| 是否授予 execution permission？ | no |
| 是否修改杠杆？ | no |
| 是否触碰 exchange_gateway？ | no |
| 是否暴露 order action？ | no |
| 是否把 readiness 当作 execution permission？ | no |

## 7. Remaining Gaps

| gap | status | impact |
| --- | --- | --- |
| Runtime listener not bound in this shell | open | startup guard preflight action is visible but disabled until a runtime-owned guard exists |
| Checklist still blocked | open | terminal state remains `blocked_startup_guard_runtime_coupled` |
| Final pre-start review packet | not generated | should be generated only after guard preflight succeeds |

## 8. Next Recommended Task

Web acceptance walkthrough.
