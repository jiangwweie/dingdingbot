Please continue from the existing frontend scaffold in `gemimi-web-front/`.

Do **not** regenerate a completely different app from scratch.

Use the uploaded planning documents and the existing scaffold as the base.

Your task is to expand the scaffold into a fuller read-only internal console using
mock data only.

## Core constraints

- Read-only only
- Manual refresh only
- No config editing
- No runtime hot reload
- No websocket
- No candidate review write-back
- No real backend calls
- No auth pages
- No landing page

## Stack

- React
- TypeScript
- TailwindCSS

## Keep and improve the current domain split

### Runtime
- Overview
- Signals
- Execution
- Health

### Research
- Candidates
- Candidate Detail
- Replay
- Backtests
- Compare

## Important product semantics

1. `Runtime / Overview`
   - must strongly show freshness / heartbeat status
   - must show runtime profile / version / hash / frozen / health summaries

2. `Runtime / Health`
   - must keep `breaker_summary` and `recovery_summary` clearly separated

3. `Research / Replay`
   - means Replay Context / Reproduce Context
   - do not implement candlestick playback

4. `Research / Candidates`
   - should feel like a candidate review entry point
   - show review status, strict gate result, warnings, and key metadata

5. `Research / Candidate Detail`
   - should feel much richer than the current scaffold
   - include best trial metrics, top trials, rubric evaluation, fixed params,
     runtime overrides, constraints, and resolved request

6. `Research / Backtests`
   - create a read-only page that lists backtest reports / runs
   - use realistic mock data

7. `Research / Compare`
   - create a read-only comparison page for candidates/backtests
   - use comparison tables or compact metric cards

## Mock data requirements

Please improve the current mock data quality:

- make runtime values align with project intent better
- avoid toy-like placeholder content
- include realistic warning / stale / degraded scenarios
- include multiple candidates with different statuses
- include richer candidate detail payloads
- include backtest records and compare records

## Engineering requirements

- preserve or improve the current layout if it is workable
- preserve the read-only/manual-refresh model
- keep code reasonably modular
- create shared UI components where helpful
- avoid unnecessary complexity

## Output requirement

Please output actual code updates for the existing project.

If output is long, provide changes in this order:

1. updated file tree
2. shared layout/components
3. runtime pages
4. research pages
5. mock services / fixtures / types
6. README updates

## Additional guidance

This is an internal console, not a polished marketing surface.

Bias toward:

- dense, scannable, operational layouts
- clear status hierarchy
- minimal decorative noise
- readable tables and summaries
