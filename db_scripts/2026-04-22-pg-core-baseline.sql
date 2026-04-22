-- Core PG baseline schema
-- Date: 2026-04-22
-- Purpose:
--   Define the target PostgreSQL baseline for the first migration wave:
--   orders / execution_intents / positions
--
-- Principles:
--   1. This is not a 1:1 copy of SQLite schemas.
--   2. Migrate while fixing obvious schema issues.
--   3. Keep signal_id as a logical reference for now; signals still live in SQLite.

BEGIN;

-- ============================================================
-- orders
-- ============================================================
CREATE TABLE IF NOT EXISTS orders (
    id                  TEXT PRIMARY KEY,
    signal_id           TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    direction           TEXT NOT NULL
                        CHECK (direction IN ('LONG', 'SHORT')),
    order_type          TEXT NOT NULL
                        CHECK (order_type IN (
                            'MARKET',
                            'LIMIT',
                            'STOP_MARKET',
                            'STOP_LIMIT',
                            'TRAILING_STOP'
                        )),
    order_role          TEXT NOT NULL
                        CHECK (order_role IN (
                            'ENTRY',
                            'SL',
                            'TP1',
                            'TP2',
                            'TP3',
                            'TP4',
                            'TP5'
                        )),
    status              TEXT NOT NULL
                        CHECK (status IN (
                            'CREATED',
                            'PENDING',
                            'SUBMITTED',
                            'OPEN',
                            'PARTIALLY_FILLED',
                            'FILLED',
                            'CANCELED',
                            'REJECTED',
                            'EXPIRED'
                        )),
    price               NUMERIC(30, 8),
    trigger_price       NUMERIC(30, 8),
    requested_qty       NUMERIC(30, 8) NOT NULL
                        CHECK (requested_qty > 0),
    filled_qty          NUMERIC(30, 8) NOT NULL DEFAULT 0
                        CHECK (filled_qty >= 0 AND filled_qty <= requested_qty),
    average_exec_price  NUMERIC(30, 8),
    reduce_only         BOOLEAN NOT NULL DEFAULT FALSE,
    parent_order_id     TEXT,
    oco_group_id        TEXT,
    exit_reason         TEXT,
    exchange_order_id   TEXT,
    filled_at           BIGINT,
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL,
    CONSTRAINT fk_orders_parent
        FOREIGN KEY (parent_order_id)
        REFERENCES orders(id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_orders_signal_id
    ON orders(signal_id);

CREATE INDEX IF NOT EXISTS idx_orders_symbol
    ON orders(symbol);

CREATE INDEX IF NOT EXISTS idx_orders_status
    ON orders(status);

CREATE INDEX IF NOT EXISTS idx_orders_parent_order_id
    ON orders(parent_order_id);

CREATE INDEX IF NOT EXISTS idx_orders_oco_group_id
    ON orders(oco_group_id);

CREATE INDEX IF NOT EXISTS idx_orders_created_at
    ON orders(created_at);

CREATE INDEX IF NOT EXISTS idx_orders_symbol_status
    ON orders(symbol, status);

CREATE INDEX IF NOT EXISTS idx_orders_parent_role
    ON orders(parent_order_id, order_role);

CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_exchange_order_id
    ON orders(exchange_order_id)
    WHERE exchange_order_id IS NOT NULL;

-- ============================================================
-- execution_intents
-- ============================================================
CREATE TABLE IF NOT EXISTS execution_intents (
    id                  TEXT PRIMARY KEY,
    signal_id           TEXT NOT NULL,
    symbol              TEXT NOT NULL,
    status              TEXT NOT NULL
                        CHECK (status IN (
                            'pending',
                            'blocked',
                            'submitted',
                            'failed',
                            'protecting',
                            'partially_protected',
                            'completed'
                        )),
    order_id            TEXT,
    exchange_order_id   TEXT,
    blocked_reason      TEXT,
    blocked_message     TEXT,
    failed_reason       TEXT,
    signal_payload      JSONB NOT NULL,
    strategy_payload    JSONB,
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL,
    CONSTRAINT fk_execution_intents_order
        FOREIGN KEY (order_id)
        REFERENCES orders(id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX IF NOT EXISTS idx_execution_intents_status
    ON execution_intents(status);

CREATE INDEX IF NOT EXISTS idx_execution_intents_symbol
    ON execution_intents(symbol);

CREATE INDEX IF NOT EXISTS idx_execution_intents_created_at
    ON execution_intents(created_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_intents_order_id
    ON execution_intents(order_id)
    WHERE order_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_intents_exchange_order_id
    ON execution_intents(exchange_order_id)
    WHERE exchange_order_id IS NOT NULL;

-- ============================================================
-- positions
-- ============================================================
CREATE TABLE IF NOT EXISTS positions (
    id                  TEXT PRIMARY KEY,
    signal_id           TEXT,
    symbol              TEXT NOT NULL,
    direction           TEXT NOT NULL
                        CHECK (direction IN ('LONG', 'SHORT')),
    quantity            NUMERIC(30, 8) NOT NULL
                        CHECK (quantity >= 0),
    entry_price         NUMERIC(30, 8),
    mark_price          NUMERIC(30, 8),
    leverage            INTEGER
                        CHECK (leverage IS NULL OR leverage > 0),
    unrealized_pnl      NUMERIC(30, 8),
    realized_pnl        NUMERIC(30, 8),
    is_closed           BOOLEAN NOT NULL DEFAULT FALSE,
    opened_at           BIGINT NOT NULL,
    closed_at           BIGINT,
    updated_at          BIGINT NOT NULL,
    position_payload    JSONB
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol
    ON positions(symbol);

CREATE INDEX IF NOT EXISTS idx_positions_is_closed
    ON positions(is_closed);

CREATE INDEX IF NOT EXISTS idx_positions_signal_id
    ON positions(signal_id);

CREATE INDEX IF NOT EXISTS idx_positions_updated_at
    ON positions(updated_at);

COMMIT;
