Please continue from the existing frontend scaffold in `gemimi-web-front/`.

Do not regenerate a different project from scratch.

Use the uploaded planning and handoff documents as the source of truth.

Your task is to add the missing high-value operator pages from a low-frequency quant
user perspective, while keeping the console read-only and mock-data-driven.

## Core constraints

- Read-only only
- Manual refresh only
- No config editing
- No runtime hot reload
- No websocket
- No real backend calls
- No review write-back
- No auth pages
- No landing page

## Existing domains

Runtime:
- Overview
- Signals
- Execution
- Health

Research:
- Candidates
- Candidate Detail
- Replay
- Backtests
- Compare

## Add these pages now

1. `Runtime / Portfolio`
2. `Runtime / Events`
3. `Config / Snapshot`

## Product semantics

### Runtime / Portfolio

This page should help a quant operator understand current risk and account state.

Please include realistic mock sections for:

- total equity
- available balance
- unrealized PnL
- total exposure
- daily loss used / limit
- leverage usage
- open positions table

### Runtime / Events

This page should be a read-only operator journal / timeline.

Please include realistic mock event categories:

- startup
- reconciliation
- breaker
- recovery
- warnings / errors
- signal decisions
- execution lifecycle

### Config / Snapshot

This must be a read-only preview page, not an editor.

Please include:

- runtime profile identity
- profile version / hash
- market snapshot
- strategy snapshot
- risk snapshot
- execution snapshot
- backend summary
- source-of-truth hints
- frozen indicators

Make it visually obvious that this page is a frozen snapshot and not editable.

## Engineering guidance

- Keep the existing layout if it is workable
- Preserve the current visual style unless it is clearly weak
- Keep data mock-based
- Add suitable TypeScript types and mock services
- Add loading / empty / error states
- Add manual refresh behavior consistently

## Output requirement

Please update the existing project and provide:

1. updated file tree
2. new routes
3. new page files
4. new mock service functions and fixtures
5. any shared UI components added
6. README updates if needed

## Important reminder

Do not turn Config into a management console.

It must remain:

- read-only
- preview-oriented
- snapshot-based
