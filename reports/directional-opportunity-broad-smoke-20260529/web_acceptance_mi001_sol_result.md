# MI-001 SOL Owner Console Web Acceptance Result

## 1. Summary

This was an Owner Console Web acceptance walkthrough for `MI-001-SOL-LONG` on `/command-center`.

It was not a trial start. No order was created, no execution intent was created, no execution permission was granted, no leverage was changed, and no strategy runtime was started.

## 2. Path Chosen

Path B: low-risk UI/API acceptance fixes.

Reason: the backend aggregate endpoint and `/command-center` panel already existed, but the Owner-facing panel only showed a compact subset of the required MI-001 evidence, risk policy, checklist, actions, and non-permissions. The fix expanded read-only display and clarified API evidence limitations without touching execution/order/runtime files.

## 3. Environment

| item | result |
| --- | --- |
| backend start method | `uvicorn` against `src.interfaces.api:app` with temporary dev/test operator auth env; not `src.main` |
| backend URL | `http://127.0.0.1:8000` |
| frontend start method | `VITE_API_PROXY_TARGET=http://127.0.0.1:8000 npm run dev -- --host 127.0.0.1 --port 3000` |
| opened URL | `http://127.0.0.1:3000/command-center` |
| auth status | BRC operator session authenticated in local dev/test |
| runtime started | no |
| strategy execution started | no |
| order/execution path enabled | no |
| screenshot | Browser text acceptance completed; screenshot capture timed out in the in-app Browser CDP call, so no screenshot artifact was saved |

## 4. Acceptance Checklist

| check | expected | actual | status | notes |
| --- | --- | --- | --- | --- |
| candidate card visible | MI-001-SOL-LONG, MI-001 / Momentum Impulse, SOL/USDT:USDT, long, terminal state | All visible | pass | Candidate panel now separates id, family, symbol, side, terminal state |
| evidence visible | signal_count 8135; 72h mean 1.9531; 72h positive 0.5175; 7d mean 4.7372; 7d positive 0.5398 | All visible | pass | Evidence limitations are separate bullets |
| risk policy visible | dedicated subaccount, equity, available margin, max leverage 5x, Operation cap | All visible | pass | API returned Operation cap `18262.85481460` |
| account facts visible | account equity and available margin | Visible | pass | `4663.39779623` equity and `3652.57096292` available margin from current API response |
| readiness checklist visible | PG registration, account facts, Operation cap, GKS, startup guard, active position/orders, Owner approval | All visible | pass | GKS is `not_checked` in standalone web process; startup guard is blocking |
| blocker visible | `blocked_startup_guard_runtime_coupled` | Visible | pass | Current blocker text explains runtime-owned startup guard is not armed |
| startup guard preflight action visible | present but disabled/guarded when runtime guard is unavailable | Visible and disabled | pass | Requires bound runtime context, runtime-owned guard, `RUNTIME_CONTROL_API_ENABLED=true`, and operator session |
| prohibited actions absent/disabled | no actionable Start Trading / Execute / Place Order / Run Strategy | disabled only where listed | pass | Place order and trial/execution actions are displayed as disabled with safety explanation |
| non-permissions visible | no execution permission, no order permission, no runtime start, no leverage change, no automatic trial start | All visible | pass | Also shows no order capability |
| terminal state correct | startup guard runtime-coupled blocked | `BLOCKED_UNTIL_STARTUP_GUARD_PREFLIGHT` with `blocked_startup_guard_runtime_coupled` verdict | pass | No readiness state was promoted |

## 5. Issues Found / Fixed

| issue | fix |
| --- | --- |
| Evidence limitations were collapsed into one broad-smoke sentence | Split into `no cost`, `no slippage`, `no funding`, `no random baseline`, `no campaign replay`, and execution-permission warning |
| MI-001 panel did not show all required evidence/risk fields | Added full candidate, evidence, risk policy, account facts, Operation cap, and terminal state display |
| Readiness checklist only showed blocking checks | Added full checklist list with status and blocking marker |
| Non-permissions only showed three fields | Added no leverage change, no order capability, and no automatic trial start |
| GKS in standalone web process could appear as blocked even when no runtime GKS service was bound | API now reports `not_checked` with explicit evidence when runtime GKS service is not bound |

## 6. Safety Check

| question | answer |
| --- | --- |
| 是否启动 trial？ | no |
| 是否下单？ | no |
| 是否创建 execution intent？ | no |
| 是否授予 execution permission？ | no |
| 是否修改杠杆？ | no |
| 是否触碰 exchange_gateway？ | no |
| 是否启动 strategy runtime？ | no |
| 是否暴露 order action？ | no order-capable action; disabled order text is shown only as non-permission evidence |

## 7. Final Acceptance Verdict

`accepted_for_owner_console_review`

The `/command-center` page is suitable for Owner manual Web review of the MI-001 SOL mainline. The terminal state remains blocked until an actual runtime-owned startup guard is available and the guarded preflight endpoint is called.

## 8. Next Recommended Task

Owner manual Web review.
