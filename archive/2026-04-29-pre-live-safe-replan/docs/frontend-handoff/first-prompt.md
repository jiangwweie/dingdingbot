Please generate a runnable frontend project scaffold based on the uploaded documents.

This is a read-only trading console for Sim-1 observation and research review.

Important constraints:

- Read-only only
- Manual refresh only
- No config editing
- No runtime hot reload
- No websocket
- No candidate review write-back
- Replay is Replay Context, not kline playback
- Local / intranet only
- Use mock data only
- Do not call any real backend

Please implement the frontend using:

- React
- TypeScript
- TailwindCSS

Please build these pages:

Runtime:

- Overview
- Signals
- Execution
- Health

Research:

- Candidates
- Candidate Detail
- Replay

Please include:

- app shell and navigation
- routing
- page components
- shared UI components
- mock API layer
- mock fixture data
- TypeScript types
- loading / empty / error states
- manual refresh button on each page
- README for local run

Do not output only design explanation.
Please generate actual project code structure.

If too long, output by files in this order:

1. `package.json`
2. app shell / routes
3. shared layout and components
4. page files
5. mock services and fixtures
6. types
7. README

Additional UI guidance:

- Use a restrained, professional monitoring-console style
- Prefer dense, scannable layouts over decorative hero sections
- First screen must be the real console, not a landing page
- Make status colors and warnings highly legible
- Distinguish breaker summary and recovery summary
- Highlight freshness status clearly
- Replay page should present replay context, not a chart playback tool
