# Missing Fields Registry

## Purpose

This registry records fields needed by the **Trading Console Frontend** that are
not directly available from current backend models, APIs, runtime artifacts, or
control snapshots.

## Source Classes

| Class | Meaning |
| --- | --- |
| **direct** | Existing backend field directly supports the UI field |
| **composed** | UI field is assembled from multiple existing sources |
| **derived** | UI field is calculated from existing fields |
| **artifact-backed** | UI field comes from runtime artifacts or generated projections |
| **mock-required** | No existing supported source has been found |
| **ui-only** | Pure visual metadata, not business data |

## Registry

| UI Page | UI Field | Source Class | Candidate Source | Mock Value Policy | Replacement Target | Status |
| --- | --- | --- | --- | --- | --- | --- |
| **仪表盘** | Equity sparkline history | mock-required | `/api/runtime/portfolio` provides current equity, not guaranteed history | Use deterministic sample series | Runtime equity history read model or existing artifact | Open |
| **仪表盘** | Market sentiment index | mock-required | No confirmed current endpoint | Use fixed neutral score | Existing market facts source if present | Open |
| **账户风险** | Drawdown trend history | mock-required | Current portfolio gives point-in-time risk fields | Use deterministic sample series | Risk stats history or artifact-backed projection | Open |
| **订单台账** | Selected order timeline | composed | `/api/trading-console/audit-chain`, `/api/runtime/events` | Mock only if audit-chain lacks lifecycle rows | Audit-chain adapter | Pending verification |
| **策略组** | StrategyGroup card sparkline | ui-only | Visual decoration from status trend | Use deterministic small series | None; stays UI-only unless real trend exists | Accepted |
| **策略组** | Candidate strength bar | derived | Signal score or watcher evidence | Normalize known score if available; mock otherwise | Signal-marker adapter | Pending verification |
| **异常信息** | Recovery stepper stage labels | composed | Recovery state plus event timeline | Mock labels only, not status facts | Recovery adapter | Pending verification |

## Rules

1. Every **mock-required** field must remain visually plausible but clearly
   tagged in development data.
2. Mock values must be deterministic to keep screenshots stable.
3. Mock values must not be posted back to backend APIs.
4. A field may move from **mock-required** to **direct**, **composed**,
   **derived**, or **artifact-backed** only after code inspection or integration
   evidence proves the source.

