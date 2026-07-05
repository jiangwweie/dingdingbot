# Trading Console Product Design

## Design Intent

### Product Role

The **Trading Console Frontend** is an operational supervision surface for a
bounded real-profit experiment. It should help the Owner see system state,
strategy-group readiness, account risk, orders, protection health, and recovery
exceptions without turning the Owner into a manual execution operator.

### Visual Direction

The supplied screenshots define a dense, audit-friendly control console:

1. **Left navigation** with five primary modules.
2. **Top status bar** showing system, account, execution permission, clock, and
   notification state.
3. **Card-grid cockpit layout** for dashboard and risk summaries.
4. **High-density tables** for order ledger and exception lists.
5. **Right-side detail panels** for strategy detail and order timelines.
6. **Dark mode as primary**, with a complete light mode using the same semantic
   tokens.

## Information Architecture

| Navigation Item | Route | Screenshot Basis | Primary User Outcome |
| --- | --- | --- | --- |
| **仪表盘** | `/dashboard` | Image 2 | Understand global runtime, PnL, market, risk, and recent actions |
| **账户风险** | `/account-risk` | Image 5 | Inspect capital, margin, leverage, protection coverage, and alerts |
| **订单台账** | `/order-ledger` | Image 3 | Audit orders, execution quality, and selected order lifecycle |
| **策略组** | `/strategy-groups` | Image 1 | Track StrategyGroup state, candidates, fresh signals, and readiness |
| **异常信息** | `/exceptions` | Image 4 | Triage recovery items, protection gaps, reconciliation issues, and audit notes |
| **登录** | `/login` | New required page | Authenticate with username, password, and Google Authenticator style code |

## Page Design

### 登录

The **login page** must include:

1. Username input.
2. Password input.
3. Six-digit authenticator code input.
4. Submit button with loading and failure states.
5. Session check redirect behavior.
6. No display of **TOTP secret**, password hash, or environment variable values.

### 仪表盘

The **dashboard page** contains:

1. KPI cards for active strategies, open orders, unrealized PnL, and market
   fundamentals.
2. Runtime overview band for uptime, exchange readiness, strategy-group count,
   and signal freshness.
3. Equity trend chart.
4. Operation cockpit summary.
5. Risk boundary gauges.
6. Right-side lists for recent action, alert summary, and market watch.

### 账户风险

The **account-risk page** contains:

1. Account equity, available margin, risk rate, and protection coverage cards.
2. Equity trend and drawdown/exposure trend charts.
3. Position risk distribution table.
4. Budget and boundary block.
5. Protection health checklist.
6. Risk alert feed.

### 订单台账

The **order-ledger page** contains:

1. Daily order, fill rate, hanging order, and abnormal order KPI cards.
2. Filter toolbar for StrategyGroup, pair, direction, exchange, time range, and
   status.
3. Order table with selected-row highlighting.
4. Right-side order detail timeline.
5. Execution quality charts and status distribution.

### 策略组

The **strategy-groups page** contains:

1. StrategyGroup count cards for total, running, watching, and paused.
2. StrategyGroup cards with purpose, direction, supported symbols, fresh event,
   health, and daily action count.
3. Candidate pool table.
4. Event status summary.
5. Right-side selected StrategyGroup detail panel.
6. StrategyGroup health distribution chart.

### 异常信息

The **exceptions page** contains:

1. Current exception, high-priority, recovery item, and 24h event KPI cards.
2. Exception list with priority, target, detection time, and state.
3. Recovery workbench stepper.
4. Impact assessment.
5. Reconciliation/protection health card.
6. Audit and notes timeline.

## Theme System

### Required Tokens

| Token Class | Examples | Purpose |
| --- | --- | --- |
| **Surface** | `background`, `panel`, `panel-strong` | Page shell and cards |
| **Text** | `text-primary`, `text-muted`, `text-subtle` | Scan-friendly hierarchy |
| **Border** | `border-soft`, `border-strong`, `focus-ring` | Dense layout separation |
| **Status** | `success`, `warning`, `danger`, `info`, `paused` | Product state recognition |
| **Charts** | `chart-green`, `chart-blue`, `chart-purple`, `chart-orange`, `chart-red` | Consistent chart language |

### Mode Behavior

1. **Dark mode** is the default visual match for the screenshots.
2. **Light mode** must be fully readable and not a color-inversion afterthought.
3. **Theme switching** must be instant and persist in local storage.
4. **Charts and badges** must use semantic tokens rather than hard-coded dark
   colors.

## UX States

| State | Required UI Behavior |
| --- | --- |
| **Loading** | Skeleton panels preserve layout dimensions |
| **Empty** | Empty state explains no current data without suggesting Owner action |
| **API unavailable** | Page remains navigable and marks affected cards as unavailable |
| **Mock-backed field** | Internal development indicator or data-source registry entry |
| **Unauthorized** | Redirect to `/login` |
| **Session expired** | Return to `/login` and preserve intended route |

