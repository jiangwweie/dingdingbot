"""
Signal Repository - SQLite persistence for trading signals.
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any

import aiosqlite

from src.domain.models import (
    SignalResult, SignalQuery, SignalDeleteRequest, AttemptQuery, AttemptDeleteRequest,
    SignalAttempt, PatternResult, FilterResult
)
from src.domain.logic_tree import LogicNode, LeafNode, TriggerLeaf, FilterLeaf
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class SignalRepository:
    """
    SQLite repository for persisting trading signals.
    """

    def __init__(self, db_path: str = "data/signals.db"):
        """
        Initialize SignalRepository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None
        logger.info(f"数据库初始化完成：{db_path}")

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        # Create data directory if not exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        # Open database connection
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row

        # Create signals table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT NOT NULL,
                symbol        TEXT NOT NULL,
                timeframe     TEXT NOT NULL,
                direction     TEXT NOT NULL,
                entry_price   TEXT NOT NULL,
                stop_loss     TEXT NOT NULL,
                position_size TEXT NOT NULL,
                leverage      INTEGER NOT NULL,
                tags_json     TEXT NOT NULL DEFAULT '[]',
                risk_info     TEXT NOT NULL
            )
        """)

        # Create indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_created_at ON signals(created_at)
        """)

        # Create signal_attempts table for observability
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS signal_attempts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT NOT NULL,
                symbol        TEXT NOT NULL,
                timeframe     TEXT NOT NULL,
                strategy_name TEXT NOT NULL,
                direction     TEXT,
                pattern_score REAL,
                final_result  TEXT NOT NULL,
                filter_stage  TEXT,
                filter_reason TEXT,
                details       TEXT NOT NULL
            )
        """)

        # Add performance tracking columns to signals table
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN status TEXT DEFAULT 'PENDING'
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN take_profit_1 TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN closed_at TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN pnl_ratio TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add kline_timestamp to signals table
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN kline_timestamp INTEGER
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add kline_timestamp column to signal_attempts table
        try:
            await self._db.execute("""
                ALTER TABLE signal_attempts ADD COLUMN kline_timestamp INTEGER
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add evaluation_summary column to signal_attempts table for semantic reports
        try:
            await self._db.execute("""
                ALTER TABLE signal_attempts ADD COLUMN evaluation_summary TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add trace_tree column to signal_attempts table for trace visualization
        try:
            await self._db.execute("""
                ALTER TABLE signal_attempts ADD COLUMN trace_tree JSON
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add signal_id column to signals table (S5-2)
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN signal_id TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Create index for signal_id
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_signal_id ON signals(signal_id)
        """)

        # Create index for status
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status)
        """)

        # Create custom_strategies table for strategy templates
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS custom_strategies (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                description   TEXT,
                strategy_json TEXT NOT NULL,
                is_active     INTEGER DEFAULT 0,
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL
            )
        """)

        # Create index for custom_strategies
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_custom_strategies_name ON custom_strategies(name)
        """)

        # Create config_snapshots table for configuration version control
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS config_snapshots (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                version       TEXT NOT NULL,
                config_json   TEXT NOT NULL,
                description   TEXT DEFAULT '',
                created_at    TEXT NOT NULL,
                created_by    TEXT DEFAULT 'user',
                is_active     INTEGER DEFAULT 0
            )
        """)

        # Create index for version lookup
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_version ON config_snapshots(version)
        """)

        # Create index for active snapshot
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_active ON config_snapshots(is_active)
        """)

        # Add strategy_name and score columns to signals table (for multi-strategy support)
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN strategy_name TEXT DEFAULT 'unknown'
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN score REAL DEFAULT 0.0
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add source column to distinguish live vs backtest signals (S6-2)
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN source TEXT DEFAULT 'live'
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add tags_json column for dynamic signal tags (backtest support)
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN tags_json TEXT DEFAULT '[]'
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add risk_info column for signal risk description
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN risk_info TEXT DEFAULT ''
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add pattern_score column for signal pattern quality score (0~1)
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN pattern_score REAL
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Add legacy columns for backward compatibility (ema_trend, mtf_status)
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN ema_trend TEXT DEFAULT ''
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN mtf_status TEXT DEFAULT ''
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # S6-2-3: Add columns for signal covering mechanism
        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN superseded_by TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN opposing_signal_id TEXT
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        try:
            await self._db.execute("""
                ALTER TABLE signals ADD COLUMN opposing_signal_score REAL
            """)
        except aiosqlite.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise

        # Create index for source
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source)
        """)

        # Create index for signal_attempts
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_attempts_symbol ON signal_attempts(symbol)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_attempts_created_at ON signal_attempts(created_at)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_attempts_final_result ON signal_attempts(final_result)
        """)

        # S6-3: Create signal_take_profits table for multi-level take-profit tracking
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS signal_take_profits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                tp_id TEXT NOT NULL,              -- "TP1", "TP2"
                position_ratio TEXT NOT NULL,     -- 仓位比例
                risk_reward TEXT NOT NULL,        -- 盈亏比
                price_level TEXT NOT NULL,        -- 止盈价格
                status TEXT DEFAULT 'PENDING',    -- PENDING/WON/CANCELLED
                filled_at TEXT,
                pnl_ratio TEXT,
                FOREIGN KEY (signal_id) REFERENCES signals(id) ON DELETE CASCADE
            )
        """)

        # Create indexes for signal_take_profits
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_tp_signal_id ON signal_take_profits(signal_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_signal_tp_status ON signal_take_profits(status)
        """)

        await self._db.commit()

    def _generate_evaluation_summary(self, attempt: SignalAttempt, symbol: str, timeframe: str) -> str:
        """
        Generate a semantic evaluation summary report for a signal attempt.

        Args:
            attempt: SignalAttempt object
            symbol: Trading pair symbol
            timeframe: Timeframe string

        Returns:
            Chinese evaluation summary report string
        """
        lines = []

        # Header
        lines.append(f"=== 信号评估报告 ===")
        lines.append(f"币种：{symbol}")
        lines.append(f"周期：{timeframe}")
        lines.append(f"策略：{attempt.strategy_name}")
        lines.append("")

        # Final result
        lines.append("【评估结果】")
        if attempt.final_result == "SIGNAL_FIRED":
            direction_str = "看涨" if attempt.direction == "long" else "看跌" if attempt.direction == "short" else "未知"
            lines.append(f"最终结果：信号触发 ({direction_str})")
        elif attempt.final_result == "NO_PATTERN":
            lines.append("最终结果：未检测到有效形态")
        elif attempt.final_result == "FILTERED":
            lines.append("最终结果：信号被过滤器拦截")
        else:
            lines.append(f"最终结果：{attempt.final_result}")
        lines.append("")

        # Pattern detection
        lines.append("【形态检测】")
        if attempt.pattern:
            direction_str = "看涨" if attempt.pattern.direction == "long" else "看跌" if attempt.pattern.direction == "short" else "未知"
            lines.append(f"检测到形态：{attempt.pattern.strategy_name} ({direction_str})")
            lines.append(f"形态评分：{attempt.pattern.score:.2f}")
            # Add pattern details if available
            if attempt.pattern.details:
                details = attempt.pattern.details
                if "wick_ratio" in details:
                    lines.append(f"影线占比：{details['wick_ratio']:.2f}")
                if "body_ratio" in details:
                    lines.append(f"实体占比：{details['body_ratio']:.2f}")
        else:
            lines.append("未检测到形态")
        lines.append("")

        # Filter results
        lines.append("【过滤器结果】")
        if attempt.filter_results:
            for f_name, f_result in attempt.filter_results:
                status = "通过" if f_result.passed else "失败"
                lines.append(f"  - {f_name}: {status} ({f_result.reason})")
        else:
            lines.append("无过滤器")
        lines.append("")

        # Final summary
        lines.append("【最终结果】")
        if attempt.final_result == "SIGNAL_FIRED":
            lines.append("所有条件满足，信号已触发")
        elif attempt.final_result == "NO_PATTERN":
            lines.append("未检测到有效 K 线形态，不生成信号")
        elif attempt.final_result == "FILTERED":
            # Find the first failed filter
            for f_name, f_result in attempt.filter_results:
                if not f_result.passed:
                    lines.append(f"被过滤器 '{f_name}' 拦截：{f_result.reason}")
                    break

        return "\n".join(lines)

    def _build_trace_tree(self, attempt: SignalAttempt) -> dict:
        """
        Build a TraceTree structure representing the signal evaluation path.

        Args:
            attempt: SignalAttempt object

        Returns:
            dict representing the trace tree structure:
            {
                "node_id": str,
                "node_type": "and_gate" | "trigger" | "filter",
                "passed": bool,
                "reason": str,
                "metadata": dict,
                "children": list
            }
        """
        import uuid

        # Determine overall pass status
        overall_passed = attempt.final_result == "SIGNAL_FIRED"

        # Build root node (AND gate)
        root = {
            "node_id": str(uuid.uuid4()),
            "node_type": "and_gate",
            "passed": overall_passed,
            "reason": "all_conditions_met" if overall_passed else "condition_failed",
            "metadata": {
                "strategy_name": attempt.strategy_name,
                "final_result": attempt.final_result
            },
            "children": []
        }

        # Add trigger node if pattern exists
        if attempt.pattern:
            trigger_passed = True  # If we have a pattern, the trigger passed
            trigger_node = {
                "node_id": str(uuid.uuid4()),
                "node_type": "trigger",
                "passed": trigger_passed,
                "reason": "pattern_detected" if trigger_passed else "no_pattern",
                "metadata": {
                    "trigger_type": attempt.pattern.strategy_name,
                    "direction": attempt.pattern.direction.value if attempt.pattern.direction else None,
                    "score": attempt.pattern.score,
                    "details": attempt.pattern.details
                },
                "children": []
            }
            root["children"].append(trigger_node)
        else:
            # No pattern detected
            trigger_node = {
                "node_id": str(uuid.uuid4()),
                "node_type": "trigger",
                "passed": False,
                "reason": "no_pattern_detected",
                "metadata": {
                    "trigger_type": attempt.strategy_name,
                    "direction": None,
                    "score": None,
                    "details": None
                },
                "children": []
            }
            root["children"].append(trigger_node)

        # Add filter nodes - Scheme D: merge f_result.metadata
        for f_name, f_result in attempt.filter_results:
            filter_node = {
                "node_id": str(uuid.uuid4()),
                "node_type": "filter",
                "passed": f_result.passed,
                "reason": f_result.reason,
                "metadata": {
                    "filter_name": f_name,
                    "filter_type": f_name,
                    **f_result.metadata  # ✅ Scheme D: merge metadata
                },
                "children": []
            }
            root["children"].append(filter_node)

        return root

    async def save_attempt(self, attempt, symbol: str, timeframe: str) -> None:
        """
        Save a SignalAttempt to the signal_attempts table.

        Args:
            attempt: SignalAttempt object from strategy engine
            symbol: Trading pair symbol
            timeframe: Timeframe string
        """
        created_at = datetime.now(timezone.utc).isoformat()

        # Extract fields from attempt
        direction = attempt.pattern.direction.value if attempt.pattern else None
        pattern_score = attempt.pattern.score if attempt.pattern else None
        final_result = attempt.final_result
        kline_timestamp = attempt.kline_timestamp

        # Find first failed filter
        filter_stage = None
        filter_reason = None
        for f_name, f_result in attempt.filter_results:
            if not f_result.passed:
                filter_stage = f_name
                filter_reason = f_result.reason
                break

        # Build details JSON (for backward compatibility) - Scheme D: include metadata
        details_dict = {
            "pattern": attempt.pattern.details if attempt.pattern else None,
            "filters": [
                {
                    "name": f_name,
                    "passed": f_result.passed,
                    "reason": f_result.reason,
                    "metadata": f_result.metadata  # ✅ Scheme D: include metadata
                }
                for f_name, f_result in attempt.filter_results
            ]
        }
        details_json = json.dumps(details_dict)

        # Generate evaluation summary report
        evaluation_summary = self._generate_evaluation_summary(attempt, symbol, timeframe)

        # Build trace tree structure
        trace_tree = self._build_trace_tree(attempt)
        trace_tree_json = json.dumps(trace_tree)

        await self._db.execute(
            """
            INSERT INTO signal_attempts (
                created_at, symbol, timeframe, strategy_name,
                direction, pattern_score, final_result,
                filter_stage, filter_reason, details, kline_timestamp,
                evaluation_summary, trace_tree
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                symbol,
                timeframe,
                attempt.strategy_name,
                direction,
                pattern_score,
                final_result,
                filter_stage,
                filter_reason,
                details_json,
                kline_timestamp,
                evaluation_summary,
                trace_tree_json,
            ),
        )
        await self._db.commit()

        logger.debug(f"Attempt 已记录：{symbol}:{timeframe} {final_result}")

    async def get_diagnostics(
        self,
        symbol: str = None,
        hours: int = 24,
    ) -> dict:
        """
        Get signal attempt diagnostics for the past N hours.

        Args:
            symbol: Optional symbol filter
            hours: Lookback window in hours (default 24)

        Returns:
            {
                "summary": {
                    "total_klines": int,
                    "no_pattern": int,
                    "signal_fired": int,
                    "filtered": int,
                    "filter_breakdown": {"ema_trend": int, "mtf": int, ...}
                },
                "recent_attempts": List[dict]  # 最近 20 条，按时间倒序
            }
        """
        # Calculate since time
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # Build WHERE clause
        where_clauses = ["created_at >= ?"]
        params = [since]

        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)

        where_sql = " AND ".join(where_clauses)

        # Get total klines
        async with self._db.execute(
            f"SELECT COUNT(*) as count FROM signal_attempts WHERE {where_sql}", params
        ) as cursor:
            row = await cursor.fetchone()
            total_klines = row["count"]

        # Get no_pattern count
        async with self._db.execute(
            f"SELECT COUNT(*) as count FROM signal_attempts WHERE {where_sql} AND final_result = ?",
            params + ["NO_PATTERN"]
        ) as cursor:
            row = await cursor.fetchone()
            no_pattern = row["count"]

        # Get signal_fired count
        async with self._db.execute(
            f"SELECT COUNT(*) as count FROM signal_attempts WHERE {where_sql} AND final_result = ?",
            params + ["SIGNAL_FIRED"]
        ) as cursor:
            row = await cursor.fetchone()
            signal_fired = row["count"]

        # Get filtered count
        async with self._db.execute(
            f"SELECT COUNT(*) as count FROM signal_attempts WHERE {where_sql} AND final_result = ?",
            params + ["FILTERED"]
        ) as cursor:
            row = await cursor.fetchone()
            filtered = row["count"]

        # Get filter breakdown (only for FILTERED rows)
        filter_breakdown = {}
        async with self._db.execute(
            f"""
            SELECT filter_stage, COUNT(*) as count
            FROM signal_attempts
            WHERE {where_sql} AND final_result = 'FILTERED'
            GROUP BY filter_stage
            """,
            params
        ) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                if row["filter_stage"]:
                    filter_breakdown[row["filter_stage"]] = row["count"]

        # Get recent 20 attempts
        async with self._db.execute(
            f"""
            SELECT * FROM signal_attempts
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT 20
            """,
            params
        ) as cursor:
            rows = await cursor.fetchall()
            recent_attempts = [dict(row) for row in rows]

        return {
            "summary": {
                "total_klines": total_klines,
                "no_pattern": no_pattern,
                "signal_fired": signal_fired,
                "filtered": filtered,
                "filter_breakdown": filter_breakdown,
            },
            "recent_attempts": recent_attempts,
        }

    async def save_signal(self, signal: SignalResult, signal_id: str = None, status: str = "PENDING", source: str = "live") -> str:
        """
        Save a signal to the database.

        Args:
            signal: SignalResult to save
            signal_id: Optional signal ID from tracker (for external tracking)
            status: Initial signal status
            source: Signal source - 'live' for real-time signals, 'backtest' for historical backtest

        Returns:
            signal_id: The database signal ID or provided tracker ID
        """
        created_at = datetime.now(timezone.utc).isoformat()
        tags_json = json.dumps(signal.tags)

        # Use signal_id if provided, otherwise use created_at as signal_id
        signal_id_value = signal_id or created_at

        await self._db.execute(
            """
            INSERT INTO signals (
                created_at, symbol, timeframe, direction,
                entry_price, stop_loss, position_size, leverage,
                tags_json, risk_info, status, pnl_ratio,
                kline_timestamp, strategy_name, score, signal_id, source,
                ema_trend, mtf_status, pattern_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                signal.symbol,
                signal.timeframe,
                signal.direction.value,
                str(signal.entry_price),
                str(signal.suggested_stop_loss),
                str(signal.suggested_position_size),
                signal.current_leverage,
                tags_json,
                signal.risk_reward_info,
                status,
                signal.pnl_ratio,
                signal.kline_timestamp,
                signal.strategy_name,
                signal.score,
                signal_id_value,
                source,
                '',  # ema_trend (legacy field, empty for new signals)
                '',  # mtf_status (legacy field, empty for new signals)
                signal.score,  # pattern_score (same as score, for sorting compatibility)
            ),
        )
        await self._db.commit()

        signal_id_result = signal_id_value
        logger.info(f"信号已保存：id={signal_id_result}, {signal.symbol}:{signal.timeframe}")

        # S6-3: Save take profit levels if present
        if signal.take_profit_levels:
            await self.store_take_profit_levels(signal_id_result, signal.take_profit_levels)

        return signal_id_result

    # ============================================================
    # S6-2-3: Signal Covering Mechanism Methods
    # ============================================================

    async def update_signal_status_by_tracker_id(self, signal_id: str, status: str) -> None:
        """
        Update signal status (supports SUPERSEDED).

        Args:
            signal_id: Signal ID (signal_id field from tracker)
            status: New status (e.g., 'ACTIVE', 'SUPERSEDED')
        """
        await self._db.execute(
            "UPDATE signals SET status = ? WHERE signal_id = ?",
            (status, signal_id)
        )
        await self._db.commit()
        logger.debug(f"Signal status updated: signal_id={signal_id}, status={status}")

    async def update_superseded_by(self, signal_id: str, superseded_by: str) -> None:
        """
        Mark signal as superseded by another signal.

        Args:
            signal_id: Signal ID to mark as superseded
            superseded_by: Signal ID that superseded this one
        """
        await self._db.execute(
            """
            UPDATE signals
            SET superseded_by = ?, status = 'superseded'
            WHERE signal_id = ?
            """,
            (superseded_by, signal_id)
        )
        await self._db.commit()
        logger.debug(f"Signal marked as superseded: signal_id={signal_id}, superseded_by={superseded_by}")

    async def get_active_signal(self, dedup_key: str) -> Optional[dict]:
        """
        Get the ACTIVE signal for a given dedup key.

        Args:
            dedup_key: Deduplication key (format: symbol:timeframe:direction:strategy_name)
                       Note: symbol may contain colons (e.g., "BTC/USDT:USDT")

        Returns:
            Signal dict if found, None otherwise
        """
        # Parse dedup_key - symbol may contain colons, so we split from the end
        # Format: symbol:timeframe:direction:strategy_name
        # Example: BTC/USDT:USDT:15m:long:pinbar
        parts = dedup_key.split(":")
        if len(parts) < 4:
            logger.warning(f"Invalid dedup_key format: {dedup_key}")
            return None

        # Extract from the end: strategy_name, direction, timeframe, and the rest is symbol
        strategy_name = parts[-1]
        direction = parts[-2]
        timeframe = parts[-3]
        symbol = ":".join(parts[:-3])  # Join remaining parts as symbol

        # Build WHERE clause
        # Support both uppercase ACTIVE and lowercase active for backward compatibility
        where_clauses = [
            "symbol = ?",
            "timeframe = ?",
            "direction = ?",
            "(status = 'ACTIVE' OR status = 'active')"
        ]
        params = [symbol, timeframe, direction]

        if strategy_name:
            where_clauses.append("strategy_name = ?")
            params.append(strategy_name)

        where_sql = " AND ".join(where_clauses)

        async with self._db.execute(
            f"SELECT * FROM signals WHERE {where_sql} ORDER BY created_at DESC LIMIT 1",
            params
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def get_opposing_signal(
        self,
        symbol: str,
        timeframe: str,
        direction: str
    ) -> Optional[dict]:
        """
        Get the opposing direction ACTIVE signal.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe
            direction: Current signal direction ("long" or "short")

        Returns:
            Signal dict if found, None otherwise
        """
        # Determine opposing direction
        opposing_direction = "short" if direction == "long" else "long"

        async with self._db.execute(
            """
            SELECT * FROM signals
            WHERE symbol = ? AND timeframe = ? AND direction = ? AND (status = 'ACTIVE' OR status = 'active')
            ORDER BY created_at DESC LIMIT 1
            """,
            (symbol, timeframe, opposing_direction)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def get_signals(
        self,
        query: SignalQuery = None,
        limit: int = 50,
        offset: int = 0,
        symbol: str = None,
        timeframe: str = None,
        direction: str = None,
        strategy_name: str = None,
        status: str = None,
        start_time: str = None,
        end_time: str = None,
        sort_by: str = "created_at",
        order: str = "desc",
        source: str = None,  # Filter by source: 'live' or 'backtest'
    ) -> dict:
        """
        Query signals with pagination and optional filtering.

        Args:
            query: SignalQuery object (optional, overrides individual params)
            limit: Maximum number of results to return
            offset: Number of results to skip
            symbol: Optional symbol filter (e.g., "BTC/USDT:USDT")
            timeframe: Optional timeframe filter (e.g., "15m", "1h", "4h", "1d")
            direction: Optional direction filter ("long" or "short")
            strategy_name: Optional strategy name filter ("pinbar", "engulfing")
            status: Optional status filter ("PENDING", "WON", "LOST")
            start_time: Optional start time filter (ISO 8601 or timestamp)
            end_time: Optional end time filter (ISO 8601 or timestamp)
            sort_by: Sort field ("created_at" or "pattern_score"), default "created_at"
            order: Sort order ("asc" or "desc"), default "desc"
            source: Optional source filter ('live' or 'backtest')

        Returns:
            {"total": int (filtered total), "data": list[dict]}
        """
        # Use query object if provided, otherwise use individual params
        if query:
            limit = query.limit
            offset = query.offset
            symbol = query.symbol
            direction = query.direction
            strategy_name = query.strategy_name
            status = query.status
            start_time = query.start_time
            end_time = query.end_time

        # Build WHERE clause dynamically
        where_clauses = ["1=1"]
        params = []

        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)

        if timeframe:
            where_clauses.append("timeframe = ?")
            params.append(timeframe)

        if direction:
            where_clauses.append("direction = ?")
            params.append(direction)

        if strategy_name:
            where_clauses.append("strategy_name = ?")
            params.append(strategy_name)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if start_time:
            where_clauses.append("created_at >= ?")
            params.append(start_time)

        if end_time:
            where_clauses.append("created_at <= ?")
            params.append(end_time)

        if source:
            where_clauses.append("source = ?")
            params.append(source)

        where_sql = " AND ".join(where_clauses)

        # Get filtered total count
        async with self._db.execute(
            f"SELECT COUNT(*) as count FROM signals WHERE {where_sql}", params
        ) as cursor:
            row = await cursor.fetchone()
            filtered_total = row["count"]

        # Validate sort_by and order to prevent SQL injection
        valid_sort_fields = {"created_at", "pattern_score"}
        valid_orders = {"asc", "desc"}

        if sort_by not in valid_sort_fields:
            sort_by = "created_at"
        if order.lower() not in valid_orders:
            order = "desc"

        # Get paginated data with dynamic sorting
        query_sql = f"SELECT * FROM signals WHERE {where_sql} ORDER BY {sort_by} {order.upper()} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self._db.execute(query_sql, params) as cursor:
            rows = await cursor.fetchall()
            # Normalize status to lowercase for frontend SignalStatus enum compatibility
            data = []
            for row in rows:
                row_dict = dict(row)
                if row_dict.get("status"):
                    row_dict["status"] = row_dict["status"].lower()

                # S6-3: Load take profit levels for each signal
                signal_id_str = row_dict.get("signal_id")
                if signal_id_str:
                    tp_levels = await self.get_take_profit_levels(signal_id_str)
                    row_dict["take_profit_levels"] = tp_levels
                else:
                    row_dict["take_profit_levels"] = []

                data.append(row_dict)
            return {"total": filtered_total, "data": data}

    async def delete_signals(
        self,
        request: SignalDeleteRequest = None,
        ids: list = None,
        delete_all: bool = False,
        symbol: str = None,
        direction: str = None,
        strategy_name: str = None,
        status: str = None,
        start_time: str = None,
        end_time: str = None,
        source: str = None,
    ) -> int:
        """
        Delete signals by ids or by filter conditions.

        Args:
            request: SignalDeleteRequest object (optional, overrides individual params)
            ids: List of signal IDs to delete
            delete_all: If True, delete by filter conditions
            symbol: Optional symbol filter
            direction: Optional direction filter
            strategy_name: Optional strategy name filter
            status: Optional status filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            source: Optional source filter ('live' or 'backtest')

        Returns:
            Number of deleted records
        """
        # Use request object if provided
        if request:
            ids = request.ids
            delete_all = request.delete_all
            symbol = request.symbol
            direction = request.direction
            strategy_name = request.strategy_name
            status = request.status
            start_time = request.start_time
            end_time = request.end_time
            source = request.source

        # If ids provided, delete by IDs
        if ids and len(ids) > 0:
            placeholders = ",".join("?" * len(ids))
            cursor = await self._db.execute(
                f"DELETE FROM signals WHERE id IN ({placeholders})", ids
            )
            await self._db.commit()
            return cursor.rowcount

        # If delete_all is False and no ids, do nothing
        if not delete_all:
            return 0

        # Build WHERE clause for conditional delete
        where_clauses = ["1=1"]
        params = []

        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)

        if direction:
            where_clauses.append("direction = ?")
            params.append(direction)

        if strategy_name:
            where_clauses.append("strategy_name = ?")
            params.append(strategy_name)

        if status:
            where_clauses.append("status = ?")
            params.append(status)

        if start_time:
            where_clauses.append("created_at >= ?")
            params.append(start_time)

        if end_time:
            where_clauses.append("created_at <= ?")
            params.append(end_time)

        if source:
            where_clauses.append("source = ?")
            params.append(source)

        where_sql = " AND ".join(where_clauses)

        # Execute delete
        cursor = await self._db.execute(f"DELETE FROM signals WHERE {where_sql}", params)
        await self._db.commit()
        return cursor.rowcount

    async def get_signal_by_id(self, signal_id: int) -> Optional[dict]:
        """
        Get a single signal by ID.

        Args:
            signal_id: Signal record ID

        Returns:
            Signal dict with all fields, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            signal = dict(row)

            # S6-3: Load take profit levels
            signal_id_str = signal.get("signal_id")
            if signal_id_str:
                tp_levels = await self.get_take_profit_levels(signal_id_str)
                signal["take_profit_levels"] = tp_levels
            else:
                signal["take_profit_levels"] = []

            return signal

    async def get_stats(self) -> dict:
        """
        Get signal statistics.

        Returns:
            Dictionary with total, today, long_count, short_count,
            win_rate, won_count, lost_count
        """
        # Get total count
        async with self._db.execute("SELECT COUNT(*) as count FROM signals") as cursor:
            row = await cursor.fetchone()
            total = row["count"]

        # Get today's count (UTC)
        today = datetime.now(timezone.utc).date().isoformat()
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM signals WHERE created_at LIKE ?",
            (f"{today}%",)
        ) as cursor:
            row = await cursor.fetchone()
            today_count = row["count"]

        # Get long count
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM signals WHERE direction = ?",
            ("long",)
        ) as cursor:
            row = await cursor.fetchone()
            long_count = row["count"]

        # Get short count
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM signals WHERE direction = ?",
            ("short",)
        ) as cursor:
            row = await cursor.fetchone()
            short_count = row["count"]

        # Get won count
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM signals WHERE status = 'WON'",
        ) as cursor:
            row = await cursor.fetchone()
            won_count = row["count"]

        # Get lost count
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM signals WHERE status = 'LOST'",
        ) as cursor:
            row = await cursor.fetchone()
            lost_count = row["count"]

        # Calculate win rate
        closed_count = won_count + lost_count
        win_rate = won_count / closed_count if closed_count > 0 else 0.0

        return {
            "total": total,
            "today": today_count,
            "long_count": long_count,
            "short_count": short_count,
            "win_rate": win_rate,
            "won_count": won_count,
            "lost_count": lost_count,
        }

    async def close(self) -> None:
        """Close database connection."""
        if self._db:
            await self._db.close()

    async def get_pending_signals(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Get all PENDING signals for a symbol.

        Args:
            symbol: Trading pair symbol

        Returns:
            List of pending signals with fields: id, symbol, timeframe, direction,
            entry_price, stop_loss, take_profit_1, status
        """
        async with self._db.execute(
            """
            SELECT id, symbol, timeframe, direction, entry_price, stop_loss, take_profit_1
            FROM signals
            WHERE symbol = ? AND status = 'PENDING'
            ORDER BY created_at DESC
            """,
            (symbol,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "symbol": row["symbol"],
                    "timeframe": row["timeframe"],
                    "direction": row["direction"],
                    "entry_price": Decimal(row["entry_price"]),
                    "stop_loss": Decimal(row["stop_loss"]),
                    "take_profit_1": Decimal(row["take_profit_1"]) if row["take_profit_1"] else None,
                }
                for row in rows
            ]

    async def update_signal_status(
        self,
        signal_id: int,
        status: str,
        pnl_ratio: Optional[Decimal] = None,
    ) -> None:
        """
        Update signal status when price hits take-profit or stop-loss.

        Args:
            signal_id: Signal record ID
            status: New status ("WON" or "LOST")
            pnl_ratio: PnL ratio for WON signals (take_profit - entry) / (entry - stop_loss)
        """
        closed_at = datetime.now(timezone.utc).isoformat()
        pnl_ratio_str = str(pnl_ratio) if pnl_ratio is not None else None

        await self._db.execute(
            """
            UPDATE signals
            SET status = ?, closed_at = ?, pnl_ratio = ?
            WHERE id = ?
            """,
            (status, closed_at, pnl_ratio_str, signal_id)
        )
        await self._db.commit()

    async def get_attempts(
        self,
        query: AttemptQuery = None,
        limit: int = 50,
        offset: int = 0,
        symbol: str = None,
        timeframe: str = None,
        strategy_name: str = None,
        final_result: str = None,
        filter_stage: str = None,
        start_time: str = None,
        end_time: str = None,
    ) -> dict:
        """
        Query signal attempts with pagination and optional filtering.

        Args:
            query: AttemptQuery object (optional, overrides individual params)
            limit: Maximum number of results to return
            offset: Number of results to skip
            symbol: Optional symbol filter
            timeframe: Optional timeframe filter
            strategy_name: Optional strategy name filter
            final_result: Optional result filter ("SIGNAL_FIRED", "NO_PATTERN", "FILTERED")
            filter_stage: Optional filter stage ("ema_trend", "mtf")
            start_time: Optional start time filter (ISO 8601 or timestamp)
            end_time: Optional end time filter (ISO 8601 or timestamp)

        Returns:
            {"total": int (filtered total), "data": list[dict]}
        """
        # Use query object if provided
        if query:
            limit = query.limit
            offset = query.offset
            symbol = query.symbol
            timeframe = query.timeframe
            strategy_name = query.strategy_name
            final_result = query.final_result
            filter_stage = query.filter_stage
            start_time = query.start_time
            end_time = query.end_time

        # Build WHERE clause dynamically
        where_clauses = ["1=1"]
        params = []

        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)

        if timeframe:
            where_clauses.append("timeframe = ?")
            params.append(timeframe)

        if strategy_name:
            where_clauses.append("strategy_name = ?")
            params.append(strategy_name)

        if final_result:
            where_clauses.append("final_result = ?")
            params.append(final_result)

        if filter_stage:
            where_clauses.append("filter_stage = ?")
            params.append(filter_stage)

        if start_time:
            where_clauses.append("created_at >= ?")
            params.append(start_time)

        if end_time:
            where_clauses.append("created_at <= ?")
            params.append(end_time)

        where_sql = " AND ".join(where_clauses)

        # Get filtered total count
        async with self._db.execute(
            f"SELECT COUNT(*) as count FROM signal_attempts WHERE {where_sql}", params
        ) as cursor:
            row = await cursor.fetchone()
            filtered_total = row["count"]

        # Get paginated data
        query_sql = f"SELECT * FROM signal_attempts WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        async with self._db.execute(query_sql, params) as cursor:
            rows = await cursor.fetchall()
            return {"total": filtered_total, "data": [dict(row) for row in rows]}

    async def delete_attempts(
        self,
        request: AttemptDeleteRequest = None,
        ids: list = None,
        delete_all: bool = False,
        symbol: str = None,
        timeframe: str = None,
        strategy_name: str = None,
        final_result: str = None,
        filter_stage: str = None,
        start_time: str = None,
        end_time: str = None,
    ) -> int:
        """
        Delete signal attempts by ids or by filter conditions.

        Args:
            request: AttemptDeleteRequest object (optional, overrides individual params)
            ids: List of attempt IDs to delete
            delete_all: If True, delete by filter conditions
            symbol: Optional symbol filter
            timeframe: Optional timeframe filter
            strategy_name: Optional strategy name filter
            final_result: Optional result filter
            filter_stage: Optional filter stage filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Number of deleted records
        """
        # Use request object if provided
        if request:
            ids = request.ids
            delete_all = request.delete_all
            symbol = request.symbol
            timeframe = request.timeframe
            strategy_name = request.strategy_name
            final_result = request.final_result
            filter_stage = request.filter_stage
            start_time = request.start_time
            end_time = request.end_time

        # If ids provided, delete by IDs
        if ids and len(ids) > 0:
            placeholders = ",".join("?" * len(ids))
            cursor = await self._db.execute(
                f"DELETE FROM signal_attempts WHERE id IN ({placeholders})", ids
            )
            await self._db.commit()
            return cursor.rowcount

        # If delete_all is False and no ids, do nothing
        if not delete_all:
            return 0

        # Build WHERE clause for conditional delete
        where_clauses = ["1=1"]
        params = []

        if symbol:
            where_clauses.append("symbol = ?")
            params.append(symbol)

        if timeframe:
            where_clauses.append("timeframe = ?")
            params.append(timeframe)

        if strategy_name:
            where_clauses.append("strategy_name = ?")
            params.append(strategy_name)

        if final_result:
            where_clauses.append("final_result = ?")
            params.append(final_result)

        if filter_stage:
            where_clauses.append("filter_stage = ?")
            params.append(filter_stage)

        if start_time:
            where_clauses.append("created_at >= ?")
            params.append(start_time)

        if end_time:
            where_clauses.append("created_at <= ?")
            params.append(end_time)

        where_sql = " AND ".join(where_clauses)

        # Execute delete
        cursor = await self._db.execute(f"DELETE FROM signal_attempts WHERE {where_sql}", params)
        await self._db.commit()
        return cursor.rowcount

    async def clear_all_signals(self) -> int:
        """
        Clear all signals from the database.

        Returns:
            Number of deleted records
        """
        cursor = await self._db.execute("DELETE FROM signals")
        await self._db.commit()
        return cursor.rowcount

    async def clear_all_attempts(self) -> int:
        """
        Clear all signal attempts from the database.

        Returns:
            Number of deleted records
        """
        cursor = await self._db.execute("DELETE FROM signal_attempts")
        await self._db.commit()
        return cursor.rowcount

    # ========================================================================
    # Custom Strategies CRUD Methods
    # ========================================================================

    async def get_all_custom_strategies(self) -> List[Dict[str, Any]]:
        """
        Get all custom strategy templates (list view with basic info only).

        Returns:
            List of strategies with id, name, description, is_active, created_at, updated_at
        """
        async with self._db.execute(
            """
            SELECT id, name, description, is_active, created_at, updated_at
            FROM custom_strategies
            ORDER BY created_at DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_custom_strategy_by_id(self, strategy_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a single custom strategy by ID with full strategy_json data.

        Args:
            strategy_id: Strategy record ID

        Returns:
            Strategy dict with all fields, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM custom_strategies WHERE id = ?", (strategy_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    async def create_custom_strategy(
        self,
        name: str,
        strategy_json: str,
        description: str = None,
    ) -> int:
        """
        Create a new custom strategy template.

        Args:
            name: Strategy name
            strategy_json: Serialized StrategyDefinition JSON
            description: Optional description

        Returns:
            ID of the newly created strategy
        """
        created_at = datetime.now(timezone.utc).isoformat()
        updated_at = created_at

        cursor = await self._db.execute(
            """
            INSERT INTO custom_strategies (name, description, strategy_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, description, strategy_json, created_at, updated_at),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def update_custom_strategy(
        self,
        strategy_id: int,
        name: str = None,
        strategy_json: str = None,
        description: str = None,
    ) -> bool:
        """
        Update an existing custom strategy template.

        Args:
            strategy_id: Strategy record ID
            name: New name (optional)
            strategy_json: New strategy JSON (optional)
            description: New description (optional)

        Returns:
            True if updated successfully, False if strategy not found
        """
        updated_at = datetime.now(timezone.utc).isoformat()

        # Build dynamic UPDATE clause
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if strategy_json is not None:
            updates.append("strategy_json = ?")
            params.append(strategy_json)
        if description is not None:
            updates.append("description = ?")
            params.append(description)

        if not updates:
            return False

        updates.append("updated_at = ?")
        params.append(updated_at)
        params.append(strategy_id)

        update_sql = "UPDATE custom_strategies SET " + ", ".join(updates) + " WHERE id = ?"

        cursor = await self._db.execute(update_sql, params)
        await self._db.commit()
        return cursor.rowcount > 0

    async def delete_custom_strategy(self, strategy_id: int) -> bool:
        """
        Delete a custom strategy template by ID.

        Args:
            strategy_id: Strategy record ID

        Returns:
            True if deleted successfully, False if strategy not found
        """
        cursor = await self._db.execute(
            "DELETE FROM custom_strategies WHERE id = ?", (strategy_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def activate_custom_strategy(self, strategy_id: int) -> bool:
        """
        Activate a custom strategy template by ID.
        Deactivates all other strategies first to ensure only one active strategy.

        Args:
            strategy_id: Strategy record ID

        Returns:
            True if activated successfully, False if strategy not found
        """
        # Deactivate all strategies first
        await self._db.execute(
            "UPDATE custom_strategies SET is_active = 0, updated_at = ? WHERE is_active = 1",
            (datetime.now(timezone.utc).isoformat(),)
        )

        # Activate the specified strategy
        cursor = await self._db.execute(
            "UPDATE custom_strategies SET is_active = 1, updated_at = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), strategy_id)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    # ========================================================================
    # Config Snapshot CRUD Methods
    # ========================================================================

    async def create_config_snapshot(
        self,
        version: str,
        config_json: str,
        description: str = "",
        created_by: str = "user",
    ) -> int:
        """
        Create a new config snapshot.

        Args:
            version: Version tag, e.g., 'v1.0.0'
            config_json: Serialized UserConfig JSON
            description: Snapshot description
            created_by: Creator identifier

        Returns:
            ID of the newly created snapshot
        """
        created_at = datetime.now(timezone.utc).isoformat()

        # Deactivate all existing snapshots
        await self._db.execute(
            "UPDATE config_snapshots SET is_active = 0 WHERE is_active = 1"
        )

        cursor = await self._db.execute(
            """
            INSERT INTO config_snapshots (version, config_json, description, created_at, created_by, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (version, config_json, description, created_at, created_by),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def get_config_snapshots(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """
        Get all config snapshots with pagination.

        Args:
            limit: Maximum number of results to return
            offset: Number of results to skip

        Returns:
            {"total": int, "data": list[dict]}
        """
        # Get total count
        async with self._db.execute(
            "SELECT COUNT(*) as count FROM config_snapshots"
        ) as cursor:
            row = await cursor.fetchone()
            total = row["count"]

        # Get paginated data
        async with self._db.execute(
            """
            SELECT * FROM config_snapshots
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ) as cursor:
            rows = await cursor.fetchall()
            return {"total": total, "data": [dict(row) for row in rows]}

    async def get_config_snapshot_by_id(self, snapshot_id: int) -> Optional[dict]:
        """
        Get a single snapshot by ID.

        Args:
            snapshot_id: Snapshot record ID

        Returns:
            Snapshot dict with all fields, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE id = ?", (snapshot_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_active_config_snapshot(self) -> Optional[dict]:
        """
        Get the currently active snapshot.

        Returns:
            Active snapshot dict with all fields, or None if not found
        """
        async with self._db.execute(
            "SELECT * FROM config_snapshots WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def activate_config_snapshot(self, snapshot_id: int) -> bool:
        """
        Activate a snapshot (deactivate all others first).

        Args:
            snapshot_id: Snapshot record ID

        Returns:
            True if activated successfully, False if not found
        """
        # Deactivate all
        await self._db.execute("UPDATE config_snapshots SET is_active = 0")

        # Activate target
        cursor = await self._db.execute(
            "UPDATE config_snapshots SET is_active = 1 WHERE id = ?", (snapshot_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def delete_config_snapshot(self, snapshot_id: int) -> bool:
        """
        Delete a config snapshot by ID.

        Args:
            snapshot_id: Snapshot record ID

        Returns:
            True if deleted successfully, False if not found
        """
        cursor = await self._db.execute(
            "DELETE FROM config_snapshots WHERE id = ?", (snapshot_id,)
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_all_attempts(self) -> List[dict]:
        """
        Get all signal attempts from database.

        Returns:
            List of all attempt records
        """
        async with self._db.execute("SELECT * FROM signal_attempts") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ============================================================
    # S6-3: Multi-Level Take Profit CRUD Methods
    # ============================================================

    async def store_take_profit_levels(
        self,
        signal_id: str,
        take_profit_levels: List[Dict[str, str]],
    ) -> None:
        """
        保存止盈级别到数据库

        Args:
            signal_id: 信号 ID
            take_profit_levels: 止盈级别列表，结构:
                [
                    {"id": "TP1", "position_ratio": "0.5", "risk_reward": "1.5", "price": "43000"},
                    ...
                ]
        """
        # Get numeric signal_id for foreign key
        cursor = await self._db.execute("SELECT id FROM signals WHERE signal_id = ?", (signal_id,))
        row = await cursor.fetchone()
        if row is None:
            logger.warning(f"Signal not found for take profit storage: signal_id={signal_id}")
            return

        numeric_signal_id = row[0]

        for tp in take_profit_levels:
            await self._db.execute(
                """
                INSERT INTO signal_take_profits
                (signal_id, tp_id, position_ratio, risk_reward, price_level, status)
                VALUES (?, ?, ?, ?, ?, 'PENDING')
                """,
                (
                    numeric_signal_id,
                    tp["id"],
                    tp["position_ratio"],
                    tp["risk_reward"],
                    tp["price"],
                ),
            )
        await self._db.commit()
        logger.debug(f"Stored {len(take_profit_levels)} take-profit levels for signal {signal_id}")

    async def get_take_profit_levels(
        self,
        signal_id: str,
    ) -> List[Dict[str, Any]]:
        """
        获取信号的止盈级别

        Args:
            signal_id: 信号 ID

        Returns:
            止盈级别列表:
                [
                    {
                        "id": 1,
                        "tp_id": "TP1",
                        "position_ratio": "0.5",
                        "risk_reward": "1.5",
                        "price_level": "43000.00",
                        "status": "PENDING"
                    },
                    ...
                ]
        """
        # Get numeric signal_id for foreign key
        cursor = await self._db.execute("SELECT id FROM signals WHERE signal_id = ?", (signal_id,))
        row = await cursor.fetchone()
        if row is None:
            return []

        numeric_signal_id = row[0]

        async with self._db.execute(
            """
            SELECT id, tp_id, position_ratio, risk_reward, price_level, status, filled_at, pnl_ratio
            FROM signal_take_profits
            WHERE signal_id = ?
            ORDER BY tp_id
            """,
            (numeric_signal_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_take_profit_status(
        self,
        signal_id: str,
        tp_id: str,
        status: str,
        pnl_ratio: Optional[Decimal] = None,
        filled_at: Optional[str] = None,
    ) -> None:
        """
        更新止盈级别状态

        Args:
            signal_id: 信号 ID
            tp_id: 止盈级别 ID (如 "TP1")
            status: 新状态 ("WON" / "CANCELLED")
            pnl_ratio: 盈亏比（可选）
            filled_at: 成交时间（可选）
        """
        # Get numeric signal_id for foreign key
        cursor = await self._db.execute("SELECT id FROM signals WHERE signal_id = ?", (signal_id,))
        row = await cursor.fetchone()
        if row is None:
            logger.warning(f"Signal not found for take profit status update: signal_id={signal_id}")
            return

        numeric_signal_id = row[0]

        await self._db.execute(
            """
            UPDATE signal_take_profits
            SET status = ?, pnl_ratio = ?, filled_at = ?
            WHERE signal_id = ? AND tp_id = ?
            """,
            (
                status,
                str(pnl_ratio) if pnl_ratio else None,
                filled_at,
                numeric_signal_id,
                tp_id,
            ),
        )
        await self._db.commit()
        logger.debug(f"Updated take-profit status: signal_id={signal_id}, tp_id={tp_id}, status={status}")
