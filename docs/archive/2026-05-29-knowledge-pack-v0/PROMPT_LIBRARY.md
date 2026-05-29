# PROMPT_LIBRARY.md

Last updated: 2026-05-29
Status: research-only snapshot

---

## 1. Research-only 通用检查提示词

```text
你是一个 bounded execution worker。当前任务是 research-only。

规则：
- 只读代码和报告
- 不修改任何文件
- 不连接交易所
- 不使用 API key
- 不下单
- 不修改运行时状态
- 不修改 PG migration
- 不修改 credentials

输出格式：
- 事实：有证据支持
- 待确认：证据不足
- 已否定：有反面证据
- 编造：绝对禁止
```

---

## 2. PG fact check 提示词

```text
## Task
Verify the following PG chain for completeness:
- Migration file exists and is named correctly
- PG model exists in pg_models.py
- Repository exists and implements required methods
- Domain contract exists and is referenced by the service
- Service exists and wires repository correctly

## Target
[填入具体模块名，例如: Strategy Family Registry]

## Files to check
- migrations/versions/[migration_file].py
- src/infrastructure/pg_models.py (search for table/model)
- src/infrastructure/pg_[module]_repository.py
- src/domain/[module].py
- src/application/[module]_service.py

## Safety
- read-only
- no code changes
- no PG mutation
- no Alembic upgrade/downgrade
- only verify file existence and content structure

## Output format
For each component: EXISTS / NOT_FOUND / NEEDS_VERIFICATION
Plus: overall chain completeness: COMPLETE / PARTIAL / BROKEN
```

---

## 3. Account facts 检查提示词

```text
## Task
Verify the Account Facts read path completeness.

## What to check
1. Does `src/application/account_service.py` exist and have methods for reading account equity/balance?
2. Does it call exchange_gateway for exchange-side facts?
3. Does it read PG for persisted facts?
4. Is there a reconciliation path between exchange and PG?
5. Does `/api/brc/account/facts` endpoint exist?
6. Does the endpoint expose evidence metadata (sources, reconciliation status, timestamp)?

## Safety
- read-only
- no exchange API calls
- no PG mutation
- no credential access
- only verify code structure and endpoint existence

## Output
- [Component]: EXISTS / NOT_FOUND / NEEDS_VERIFICATION
- Overall: COMPLETE / PARTIAL / BROKEN
- Risk items: [list any safety concerns]
```

---

## 4. Strategy family research 提示词

```text
## Task
Research a strategy family direction. This is research-only, not execution.

## Rules
- Use only OHLCV data
- No exchange API calls
- No PG runtime table mutation
- No strategy promotion
- No parameter optimization (unless explicitly approved)
- Label all results as: research-only / exploratory / backtest-only

## Required outputs
1. Signal definition (frozen)
2. Entry/exit/stop rules (frozen)
3. Historical window and data source
4. Signal count, trade count, win rate, PF
5. Top-3/top-5 removal test
6. Direction A/B/C overlap check
7. Classification per SRR-002 or MTC-001
8. Failure modes and known risks

## Safety boundary
- no execution
- no trading
- no live
- no API key usage
- no strategy promotion conclusion
- all numbers labeled with time window and cost assumptions
```

---

## 5. Backtest / evaluation 检查提示词

```text
## Task
Run or verify a backtest. This is research-only.

## Required metadata
Every backtest output must include:
- engine_name
- engine_version
- matching_model
- account_model
- cost_model (slippage, funding, exchange fee)
- risk_model
- data_window (start, end, exchange)
- same_bar_policy
- funding_model
- proxy_or_official

## Required checks
1. Data completeness: no gaps, no duplicates
2. Slippage calculation: verify non-zero when MARKET orders used
3. Cost composition: total = slippage + funding + exchange fee
4. Trade count floor: per SRR-002
5. Winner count floor: per SRR-002
6. Top-3/top-5 removal
7. Year/regime breakdown

## Safety
- research-only
- no PG runtime mutation
- no exchange calls
- results stored in reports/ (local only, .gitignored)
```

---

## 6. No-execution 安全边界提示词

```text
## Safety Envelope — Read This First

The following actions are PROHIBITED unless Owner explicitly authorizes:

### Absolute Prohibitions
- Real live trading
- Using real funds to place orders
- Automated strategy execution
- Modifying execution permissions
- Withdrawal / transfer
- Modifying API keys / credentials
- Strategy self-elevation
- Bypassing the Operation Layer
- Infinite add-to-position
- Automatic symbol/side/leverage expansion

### Allowed (with Owner authorization)
- Binance testnet controlled operations
- Local runtime startup and verification
- Read-only exchange sync
- Research report generation

### Default Safety Posture
- TRADING_ENV=simulation
- EXCHANGE_TESTNET=true
- GKS fail-closed
- startup guard blocked by default
- campaign state observe by default

### Before Any Action, Verify
1. Is this real live? → STOP unless Owner explicitly authorized
2. Does this touch exchange? → Verify testnet mode
3. Does this place/cancel orders? → Verify controlled endpoint + testnet
4. Does this modify PG runtime tables? → Verify authorization
5. Does this use API keys? → Verify testnet keys only
```

---

## 7. 报告生成提示词

```text
## Task
Generate a research report for [topic].

## Format
1. **Summary** (1 paragraph)
2. **Methodology** (frozen rules, data source, window)
3. **Results** (tables with signal count, PF, win rate, DD)
4. **Fragility Checks** (top-3 removal, year breakdown, overlap)
5. **Classification** (per SRR-002 / MTC-001 / project classification framework)
6. **Known Limitations** (cost assumptions, data gaps, survivorship bias)
7. **Conclusion** (classification label + recommendation)
8. **Next Steps** (what would be needed to advance)

## Rules
- All numbers labeled with time window and cost assumptions
- Distinguish "research-only" from "production-ready"
- Don't overstate conclusions
- Separate facts from interpretation
- Include confidence level (HIGH/MEDIUM/LOW)
```

---

## 8. 项目交接提示词

```text
## Context
You are inheriting a crypto derivatives research & governance project.

## Read Order
1. docs/ops/knowledge-pack/PROJECT_OVERVIEW.md — global overview
2. docs/ops/knowledge-pack/CURRENT_STATE_AND_NEXT_ACTIONS.md — current state
3. docs/ops/knowledge-pack/FACT_REGISTRY.md — facts vs assumptions
4. docs/ops/knowledge-pack/MODULE_MAP.md — module structure
5. docs/ops/knowledge-pack/STRATEGY_RESEARCH_HISTORY.md — strategy history
6. docs/ops/knowledge-pack/PROMPT_LIBRARY.md — reusable prompts

## Then read for deeper context
- CLAUDE.md — project operating rules
- docs/ops/project-roadmap-v2.md — long-term direction
- docs/ops/live-safe-v1-task-board.md — task status
- docs/adr/ — architecture decision records

## Safety Rules
- Default: research-only, read-only
- Real live trading: PROHIBITED unless Owner explicitly authorizes
- Execution components are Codex-owned (do not modify)
- LLM is advisory only
- Research-runtime isolation is permanent

## What You'll Find
- A well-structured BRC governance framework (testnet-verified)
- No production-ready strategy
- Rich research history with clear failure/rejection records
- A broad OHLCV smoke screen with 3 unvalidated candidates
- A clear safety boundary model

## What You Won't Find
- Production deployment capability
- Real trading history
- Automated strategy execution
- Multi-asset runtime
- Cloud infrastructure
```
