"""
Backtest Report Repository - SQLite persistence for backtest reports.

实现回测报告的持久化存储，支持：
- 保存回测报告
- 获取报告详情
- 获取策略历史报告列表
- 获取相同参数组合的历史报告（用于自动调参分析）
- 删除报告
"""
import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

import aiosqlite

from src.domain.models import PMSBacktestReport, PositionSummary, Direction, PositionCloseEvent
from src.domain.models import StrategyDefinition
from src.infrastructure.logger import setup_logger

logger = setup_logger(__name__)


class BacktestReportRepository:
    """
    SQLite repository for persisting backtest reports.

    设计目标:
    - 支持回测报告的历史追踪
    - 支持基于参数哈希的聚类分析（自动调参）
    - 策略快照序列化存储
    """

    def __init__(
        self,
        db_path: str = "data/v3_dev.db",
        connection: Optional[aiosqlite.Connection] = None,
    ):
        """
        Initialize BacktestReportRepository.

        Args:
            db_path: Path to SQLite database file
            connection: Optional injected connection (if None, creates own connection)
        """
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = connection
        self._owns_connection = connection is None
        logger.info(f"回测报告仓库初始化完成：{db_path}")

    async def initialize(self) -> None:
        """
        Initialize database connection and create tables.
        Also creates the data/ directory if it doesn't exist.
        """
        # Create connection if not injected
        if self._owns_connection and self._db is None:
            # Create data directory if not exists
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # Open database connection via connection pool (shared across repos)
            from src.infrastructure.connection_pool import get_connection as pool_get_connection
            self._db = await pool_get_connection(self.db_path)
            # PRAGMAs are set centrally in connection_pool, no need to repeat here

        # Create backtest_reports table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_reports (
                id                  TEXT PRIMARY KEY,
                strategy_id         TEXT NOT NULL,
                strategy_name       TEXT NOT NULL,
                strategy_version    TEXT NOT NULL DEFAULT '1.0.0',
                strategy_snapshot   TEXT NOT NULL,
                parameters_hash     TEXT NOT NULL,
                symbol              TEXT NOT NULL,
                timeframe           TEXT NOT NULL,
                backtest_start      INTEGER NOT NULL,
                backtest_end        INTEGER NOT NULL,
                created_at          INTEGER NOT NULL,
                initial_balance     TEXT NOT NULL,
                final_balance       TEXT NOT NULL,
                total_return        TEXT NOT NULL,
                total_trades        INTEGER NOT NULL DEFAULT 0,
                winning_trades      INTEGER NOT NULL DEFAULT 0,
                losing_trades       INTEGER NOT NULL DEFAULT 0,
                win_rate            TEXT NOT NULL DEFAULT '0',
                total_pnl           TEXT NOT NULL DEFAULT '0',
                total_fees_paid     TEXT NOT NULL DEFAULT '0',
                total_slippage_cost TEXT NOT NULL DEFAULT '0',
                total_funding_cost  TEXT NOT NULL DEFAULT '0',
                max_drawdown        TEXT NOT NULL DEFAULT '0',
                sharpe_ratio        TEXT,
                positions_summary   TEXT,
                monthly_returns     TEXT
            )
        """)

        # Create indexes
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_strategy_id
            ON backtest_reports(strategy_id)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_symbol
            ON backtest_reports(symbol)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_timeframe
            ON backtest_reports(timeframe)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_created_at
            ON backtest_reports(created_at)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_backtest_reports_parameters_hash
            ON backtest_reports(parameters_hash)
        """)

        # Create position_close_events table (任务 1.4)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS position_close_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id       TEXT NOT NULL,
                position_id     TEXT NOT NULL,
                order_id        TEXT,
                event_type      TEXT NOT NULL,
                event_category  TEXT NOT NULL,
                close_price     TEXT,                         -- NULL 允许（sl_modified 时无成交价）
                close_qty       TEXT,                         -- NULL 允许（sl_modified 时无成交量）
                close_pnl       TEXT,                         -- NULL 允许（sl_modified 时无盈亏）
                close_fee       TEXT,                         -- NULL 允许（sl_modified 时无手续费）
                close_time      INTEGER NOT NULL,
                exit_reason     TEXT,                         -- NULL 允许
                FOREIGN KEY (report_id) REFERENCES backtest_reports(id) ON DELETE CASCADE,
                FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE,
                CHECK (event_category != 'exit' OR (
                    close_price IS NOT NULL AND
                    close_qty IS NOT NULL AND
                    close_pnl IS NOT NULL AND
                    close_fee IS NOT NULL
                ))
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_close_events_report_id
            ON position_close_events(report_id)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_close_events_position_id
            ON position_close_events(position_id)
        """)

        # Create backtest_attributions table (归因分析独立表)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS backtest_attributions (
                report_id           TEXT PRIMARY KEY,
                signal_attributions TEXT,
                aggregate_attribution TEXT,
                analysis_dimensions TEXT,
                created_at          INTEGER NOT NULL,
                FOREIGN KEY (report_id) REFERENCES backtest_reports(id) ON DELETE CASCADE
            )
        """)

        await self._db.commit()
        logger.info("回测报告表初始化完成")

        # Migrate existing table if old CHECK constraints are present
        await self._migrate_existing_table()

        # 确保旧表有 total_funding_cost 列（CREATE TABLE IF NOT EXISTS 不会加列）
        await self._ensure_total_funding_cost_column()

    async def close(self) -> None:
        """Clear local connection reference (pool-managed connections are never closed by repos)."""
        if self._db:
            self._db = None

    # ============================================================
    # 工具方法
    # ============================================================

    def _serialize_strategy_snapshot(self, strategy_def: StrategyDefinition) -> str:
        """
        将策略配置序列化为 JSON 字符串。

        Args:
            strategy_def: 策略定义

        Returns:
            JSON 字符串
        """
        snapshot = {
            "id": strategy_def.id,
            "name": strategy_def.name,
            "logic_tree": None,
            "triggers": [],
            "filters": [],
        }

        # 序列化 logic_tree（如果存在）
        if strategy_def.logic_tree:
            snapshot["logic_tree"] = self._serialize_logic_tree(strategy_def.logic_tree)

        # 向后兼容：提取 triggers 和 filters
        triggers = strategy_def.get_triggers_from_logic_tree()
        filters = strategy_def.get_filters_from_logic_tree()

        snapshot["triggers"] = [t.model_dump(mode="json") for t in triggers]
        snapshot["filters"] = [f.model_dump(mode="json") for f in filters]

        return json.dumps(snapshot, ensure_ascii=False)

    def _serialize_logic_tree(self, node) -> Dict[str, Any]:
        """
        递归序列化逻辑树节点。

        Args:
            node: LogicNode 或 LeafNode

        Returns:
            Dict 表示
        """
        from src.domain.logic_tree import LogicNode, TriggerLeaf, FilterLeaf

        if isinstance(node, LogicNode):
            return {
                "type": "node",
                "gate": node.gate,
                "children": [self._serialize_logic_tree(child) for child in node.children]
            }
        elif isinstance(node, TriggerLeaf):
            return {
                "type": "trigger",
                "id": node.id,
                "config": node.config.model_dump(mode="json")
            }
        elif isinstance(node, FilterLeaf):
            return {
                "type": "filter",
                "id": node.id,
                "config": node.config.model_dump(mode="json")
            }
        else:
            return {}

    def _calculate_parameters_hash(self, strategy_snapshot: str, symbol: str, timeframe: str) -> str:
        """
        计算参数组合的 SHA256 哈希。

        用于聚类分析：相同参数组合的不同回测结果可以通过哈希值快速查找。

        Args:
            strategy_snapshot: 策略快照 JSON 字符串
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            SHA256 哈希字符串（64 字符）
        """
        content = f"{strategy_snapshot}:{symbol}:{timeframe}"
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _decimal_to_str(self, value: Decimal) -> str:
        """将 Decimal 转换为字符串用于存储

        使用 normalize() 确保 0 显示为 '0.0' 而不是 '0'，
        以避免 SQLite CHECK 约束比较问题。
        """
        normalized = value.normalize()
        # 确保小数点存在，避免 SQLite 字符串比较问题
        result = str(normalized)
        if '.' not in result and 'E' not in result.upper():
            result += '.0'
        return result

    def _str_to_decimal(self, value: Optional[str]) -> Optional[Decimal]:
        """将字符串转换为 Decimal。非法数值字符串返回 None，不抛异常。"""
        if value is None:
            return None
        try:
            return Decimal(value)
        except Exception:
            return None

    def _serialize_positions_summary(self, positions: List[PositionSummary]) -> str:
        """
        将仓位摘要列表序列化为 JSON 字符串。

        Args:
            positions: 仓位摘要列表

        Returns:
            JSON 字符串
        """
        data = []
        for pos in positions:
            data.append({
                "position_id": pos.position_id,
                "signal_id": pos.signal_id,
                "symbol": pos.symbol,
                "direction": pos.direction.value,
                "entry_price": self._decimal_to_str(pos.entry_price),
                "exit_price": self._decimal_to_str(pos.exit_price) if pos.exit_price else None,
                "entry_time": pos.entry_time,
                "exit_time": pos.exit_time,
                "realized_pnl": self._decimal_to_str(pos.realized_pnl),
                "exit_reason": pos.exit_reason,
            })
        return json.dumps(data, ensure_ascii=False)

    def _deserialize_positions_summary(self, json_str: Optional[str]) -> List[PositionSummary]:
        """
        将 JSON 字符串反序列化为仓位摘要列表。

        Args:
            json_str: JSON 字符串

        Returns:
            仓位摘要列表
        """
        if not json_str:
            return []

        data = json.loads(json_str)
        positions = []
        for item in data:
            positions.append(PositionSummary(
                position_id=item["position_id"],
                signal_id=item["signal_id"],
                symbol=item["symbol"],
                direction=Direction(item["direction"]),
                entry_price=self._str_to_decimal(item["entry_price"]),
                exit_price=self._str_to_decimal(item.get("exit_price")),
                entry_time=item["entry_time"],
                exit_time=item.get("exit_time"),
                realized_pnl=self._str_to_decimal(item["realized_pnl"]),
                exit_reason=item.get("exit_reason"),
            ))
        return positions

    # ============================================================
    # CRUD 接口
    # ============================================================

    async def save_report(
        self,
        report: PMSBacktestReport,
        strategy_snapshot: str,
        symbol: str,
        timeframe: str
    ) -> None:
        """
        保存回测报告。

        Args:
            report: PMSBacktestReport 实例
            strategy_snapshot: 策略快照 JSON 字符串
            symbol: 交易对
            timeframe: 时间周期

        Raises:
            ValueError: 如果报告数据无效
        """
        if not report.strategy_id:
            raise ValueError("strategy_id 不能为空")

        # 计算参数哈希
        parameters_hash = self._calculate_parameters_hash(
            strategy_snapshot,
            symbol,
            timeframe
        )

        # 生成报告 ID。
        # parameters_hash 只表达“同一参数组合”，不能作为运行唯一性的一部分；
        # 同一套参数允许被 Research job 反复复跑，所以 report_id 必须每次保存唯一。
        report_id = f"rpt_{report.strategy_id}_{report.backtest_start}_{parameters_hash[:8]}_{uuid.uuid4().hex[:8]}"

        # 序列化 positions_summary
        positions_summary = self._serialize_positions_summary(report.positions) if report.positions else None

        # 插入数据库
        await self._db.execute("""
            INSERT INTO backtest_reports (
                id, strategy_id, strategy_name, strategy_version,
                strategy_snapshot, parameters_hash, symbol, timeframe,
                backtest_start, backtest_end, created_at,
                initial_balance, final_balance, total_return,
                total_trades, winning_trades, losing_trades, win_rate,
                total_pnl, total_fees_paid, total_slippage_cost,
                total_funding_cost, max_drawdown,
                sharpe_ratio, positions_summary, monthly_returns
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            report.strategy_id,
            report.strategy_name,
            "1.0.0",  # strategy_version
            strategy_snapshot,
            parameters_hash,
            symbol,
            timeframe,
            report.backtest_start,
            report.backtest_end,
            int(datetime.now(timezone.utc).timestamp() * 1000),
            self._decimal_to_str(report.initial_balance),
            self._decimal_to_str(report.final_balance),
            self._decimal_to_str(report.total_return),
            report.total_trades,
            report.winning_trades,
            report.losing_trades,
            self._decimal_to_str(report.win_rate),
            self._decimal_to_str(report.total_pnl),
            self._decimal_to_str(report.total_fees_paid),
            self._decimal_to_str(report.total_slippage_cost),
            self._decimal_to_str(report.total_funding_cost),
            self._decimal_to_str(report.max_drawdown),
            self._decimal_to_str(report.sharpe_ratio) if report.sharpe_ratio else None,
            positions_summary,
            None,  # monthly_returns (暂不使用)
        ))

        # 保存 close_events (任务 1.4)
        if report.close_events:
            for event in report.close_events:
                await self._db.execute("""
                    INSERT INTO position_close_events (
                        report_id, position_id, order_id,
                        event_type, event_category,
                        close_price, close_qty, close_pnl, close_fee,
                        close_time, exit_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    report_id,
                    event.position_id,
                    event.order_id,
                    event.event_type,
                    event.event_category,
                    self._decimal_to_str(event.close_price) if event.close_price is not None else None,
                    self._decimal_to_str(event.close_qty) if event.close_qty is not None else None,
                    self._decimal_to_str(event.close_pnl) if event.close_pnl is not None else None,
                    self._decimal_to_str(event.close_fee) if event.close_fee is not None else None,
                    event.close_time,
                    event.exit_reason,
                ))

        # 保存归因分析数据到 backtest_attributions 表
        attribution_data = {
            "signal_attributions": json.dumps(report.signal_attributions, ensure_ascii=False) if report.signal_attributions else None,
            "aggregate_attribution": json.dumps(report.aggregate_attribution, ensure_ascii=False) if report.aggregate_attribution else None,
            "analysis_dimensions": json.dumps(report.analysis_dimensions, ensure_ascii=False) if report.analysis_dimensions else None,
        }
        if any(v is not None for v in attribution_data.values()):
            await self._db.execute("""
                INSERT OR REPLACE INTO backtest_attributions (
                    report_id, signal_attributions, aggregate_attribution,
                    analysis_dimensions, created_at
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                report_id,
                attribution_data["signal_attributions"],
                attribution_data["aggregate_attribution"],
                attribution_data["analysis_dimensions"],
                int(datetime.now(timezone.utc).timestamp() * 1000),
            ))

        await self._db.commit()
        logger.info(f"已保存回测报告：{report_id}")

    async def get_report(self, report_id: str) -> Optional[PMSBacktestReport]:
        """
        获取报告详情。

        Args:
            report_id: 报告 ID

        Returns:
            PMSBacktestReport 实例，如果不存在则返回 None
        """
        cursor = await self._db.execute("""
            SELECT * FROM backtest_reports WHERE id = ?
        """, (report_id,))
        row = await cursor.fetchone()

        if not row:
            return None

        # 加载 close_events (任务 1.4)
        close_events = []
        close_cursor = await self._db.execute("""
            SELECT * FROM position_close_events WHERE report_id = ?
            ORDER BY close_time ASC
        """, (report_id,))
        for close_row in await close_cursor.fetchall():
            close_events.append(PositionCloseEvent(
                position_id=close_row["position_id"],
                order_id=close_row["order_id"],
                event_type=close_row["event_type"],
                event_category=close_row["event_category"],
                close_price=self._str_to_decimal(close_row["close_price"]),
                close_qty=self._str_to_decimal(close_row["close_qty"]),
                close_pnl=self._str_to_decimal(close_row["close_pnl"]),
                close_fee=self._str_to_decimal(close_row["close_fee"]),
                close_time=close_row["close_time"],
                exit_reason=close_row["exit_reason"],
            ))

        # 读取归因分析数据
        signal_attributions = None
        aggregate_attribution = None
        analysis_dimensions = None
        attr_cursor = await self._db.execute("""
            SELECT signal_attributions, aggregate_attribution, analysis_dimensions
            FROM backtest_attributions
            WHERE report_id = ?
        """, (report_id,))
        attr_row = await attr_cursor.fetchone()
        if attr_row:
            for col_name, attr_val in [
                ("signal_attributions", attr_row["signal_attributions"]),
                ("aggregate_attribution", attr_row["aggregate_attribution"]),
                ("analysis_dimensions", attr_row["analysis_dimensions"]),
            ]:
                if attr_val:
                    try:
                        parsed = json.loads(attr_val)
                        if col_name == "signal_attributions":
                            signal_attributions = parsed
                        elif col_name == "aggregate_attribution":
                            aggregate_attribution = parsed
                        else:
                            analysis_dimensions = parsed
                    except json.JSONDecodeError as e:
                        logger.warning(f"归因数据 {col_name} JSON 解析失败，已忽略: {e}")

        return PMSBacktestReport(
            strategy_id=row["strategy_id"],
            strategy_name=row["strategy_name"],
            backtest_start=row["backtest_start"],
            backtest_end=row["backtest_end"],
            initial_balance=self._str_to_decimal(row["initial_balance"]),
            final_balance=self._str_to_decimal(row["final_balance"]),
            total_return=self._str_to_decimal(row["total_return"]),
            total_trades=row["total_trades"],
            winning_trades=row["winning_trades"],
            losing_trades=row["losing_trades"],
            win_rate=self._str_to_decimal(row["win_rate"]),
            total_pnl=self._str_to_decimal(row["total_pnl"]),
            total_fees_paid=self._str_to_decimal(row["total_fees_paid"]),
            total_slippage_cost=self._str_to_decimal(row["total_slippage_cost"]),
            total_funding_cost=self._str_to_decimal(row["total_funding_cost"]) if "total_funding_cost" in row.keys() else Decimal('0'),
            max_drawdown=self._str_to_decimal(row["max_drawdown"]),
            sharpe_ratio=self._str_to_decimal(row["sharpe_ratio"]) if row["sharpe_ratio"] else None,
            positions=self._deserialize_positions_summary(row["positions_summary"]),
            close_events=close_events,
            signal_attributions=signal_attributions,
            aggregate_attribution=aggregate_attribution,
            analysis_dimensions=analysis_dimensions,
        )

    async def get_reports_by_strategy(
        self,
        strategy_id: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取策略的历史报告列表（仅返回摘要信息）。

        Args:
            strategy_id: 策略 ID
            limit: 返回数量限制

        Returns:
            报告摘要列表，每项包含：
            - id: 报告 ID
            - strategy_name: 策略名称
            - backtest_start: 回测开始时间
            - backtest_end: 回测结束时间
            - total_return: 总收益率
            - win_rate: 胜率
            - total_pnl: 总盈亏
            - max_drawdown: 最大回撤
        """
        cursor = await self._db.execute("""
            SELECT id, strategy_name, backtest_start, backtest_end,
                   total_return, win_rate, total_pnl, max_drawdown,
                   total_trades, winning_trades, losing_trades
            FROM backtest_reports
            WHERE strategy_id = ?
            ORDER BY backtest_start DESC
            LIMIT ?
        """, (strategy_id, limit))

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "strategy_name": row["strategy_name"],
                "backtest_start": row["backtest_start"],
                "backtest_end": row["backtest_end"],
                "total_return": self._str_to_decimal(row["total_return"]),
                "win_rate": self._str_to_decimal(row["win_rate"]),
                "total_pnl": self._str_to_decimal(row["total_pnl"]),
                "max_drawdown": self._str_to_decimal(row["max_drawdown"]),
                "total_trades": row["total_trades"],
                "winning_trades": row["winning_trades"],
                "losing_trades": row["losing_trades"],
            }
            for row in rows
        ]

    async def get_reports_by_parameters_hash(
        self,
        parameters_hash: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取相同参数组合的历史报告（用于自动调参分析）。

        Args:
            parameters_hash: 参数组合 SHA256 哈希
            limit: 返回数量限制

        Returns:
            报告摘要列表
        """
        cursor = await self._db.execute("""
            SELECT id, strategy_name, backtest_start, backtest_end,
                   total_return, win_rate, total_pnl, max_drawdown,
                   total_trades, winning_trades, losing_trades
            FROM backtest_reports
            WHERE parameters_hash = ?
            ORDER BY backtest_start DESC
            LIMIT ?
        """, (parameters_hash, limit))

        rows = await cursor.fetchall()
        return [
            {
                "id": row["id"],
                "strategy_name": row["strategy_name"],
                "backtest_start": row["backtest_start"],
                "backtest_end": row["backtest_end"],
                "total_return": self._str_to_decimal(row["total_return"]),
                "win_rate": self._str_to_decimal(row["win_rate"]),
                "total_pnl": self._str_to_decimal(row["total_pnl"]),
                "max_drawdown": self._str_to_decimal(row["max_drawdown"]),
                "total_trades": row["total_trades"],
                "winning_trades": row["winning_trades"],
                "losing_trades": row["losing_trades"],
            }
            for row in rows
        ]

    async def delete_report(self, report_id: str) -> None:
        """
        删除报告。

        Args:
            report_id: 报告 ID
        """
        await self._db.execute("""
            DELETE FROM backtest_reports WHERE id = ?
        """, (report_id,))
        await self._db.commit()
        logger.info(f"已删除回测报告：{report_id}")

    async def get_report_snapshot(self, report_id: str) -> Optional[str]:
        """
        获取报告关联的策略快照。

        Args:
            report_id: 报告 ID

        Returns:
            策略快照 JSON 字符串，如果报告不存在则返回 None
        """
        cursor = await self._db.execute("""
            SELECT strategy_snapshot FROM backtest_reports WHERE id = ?
        """, (report_id,))
        row = await cursor.fetchone()

        if not row:
            return None

        return row["strategy_snapshot"]

    async def list_reports(
        self,
        strategy_id: Optional[str] = None,
        symbol: Optional[str] = None,
        start_date: Optional[int] = None,
        end_date: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = 'created_at',
        sort_order: str = 'desc'
    ) -> Dict[str, Any]:
        """
        获取回测报告列表（支持筛选、排序、分页）。

        Args:
            strategy_id: 策略 ID 筛选
            symbol: 交易对筛选
            start_date: 开始时间戳（毫秒）
            end_date: 结束时间戳（毫秒）
            page: 页码（从 1 开始）
            page_size: 每页数量
            sort_by: 排序字段 ('total_return' | 'win_rate' | 'created_at')
            sort_order: 排序方向 ('asc' | 'desc')

        Returns:
            {
                "reports": List[BacktestReportSummary],
                "total": int,
                "page": int,
                "pageSize": int
            }
        """
        # 构建 WHERE 子句
        conditions = []
        params = []

        if strategy_id:
            conditions.append("strategy_id = ?")
            params.append(strategy_id)

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)

        if start_date:
            conditions.append("backtest_start >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("backtest_start <= ?")
            params.append(end_date)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 排序字段映射
        sort_column_map = {
            'total_return': 'CAST(REPLACE(total_return, ",", ".") AS REAL)',
            'win_rate': 'CAST(REPLACE(win_rate, ",", ".") AS REAL)',
            'created_at': 'created_at'
        }
        sort_column = sort_column_map.get(sort_by, 'created_at')
        sort_direction = 'ASC' if sort_order.lower() == 'asc' else 'DESC'

        # 计算总数
        count_query = f"""
            SELECT COUNT(*) FROM backtest_reports {where_clause}
        """
        cursor = await self._db.execute(count_query, params)
        total_row = await cursor.fetchone()
        total = total_row[0] if total_row else 0

        # 计算分页
        offset = (page - 1) * page_size

        # 获取数据 - 使用 COALESCE 确保 sharpe_ratio 列不存在时返回 NULL
        query = f"""
            SELECT id, strategy_id, strategy_name, strategy_version,
                   symbol, timeframe, backtest_start, backtest_end,
                   created_at, total_return, total_trades, win_rate,
                   total_pnl, max_drawdown,
                   COALESCE(sharpe_ratio, NULL) as sharpe_ratio
            FROM backtest_reports
            {where_clause}
            ORDER BY {sort_column} {sort_direction}
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])

        cursor = await self._db.execute(query, params)
        rows = await cursor.fetchall()

        reports = [
            {
                "id": row["id"],
                "strategy_id": row["strategy_id"],
                "strategy_name": row["strategy_name"],
                "strategy_version": row["strategy_version"],
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "backtest_start": row["backtest_start"],
                "backtest_end": row["backtest_end"],
                "created_at": row["created_at"],
                "total_return": str(self._str_to_decimal(row["total_return"])),
                "total_trades": row["total_trades"],
                "win_rate": str(self._str_to_decimal(row["win_rate"])),
                "total_pnl": str(self._str_to_decimal(row["total_pnl"])),
                "max_drawdown": str(self._str_to_decimal(row["max_drawdown"])),
                "sharpe_ratio": str(self._str_to_decimal(row["sharpe_ratio"])),
            }
            for row in rows
        ]

        return {
            "reports": reports,
            "total": total,
            "page": page,
            "pageSize": page_size
        }

    async def _ensure_total_funding_cost_column(self) -> None:
        """确保 backtest_reports 表有 total_funding_cost 列（旧表升级兼容）。"""
        try:
            cursor = await self._db.execute("PRAGMA table_info(backtest_reports)")
            columns = {row["name"] for row in await cursor.fetchall()}
            if "total_funding_cost" not in columns:
                await self._db.execute(
                    "ALTER TABLE backtest_reports ADD COLUMN total_funding_cost TEXT NOT NULL DEFAULT '0'"
                )
                await self._db.commit()
                logger.info("[MIGRATE] backtest_reports 表已添加 total_funding_cost 列")
        except Exception as e:
            logger.warning(f"[MIGRATE] 添加 total_funding_cost 列失败（可能已存在）: {e}")

    async def _migrate_existing_table(self) -> None:
        """
        迁移 backtest_reports 表，移除旧 CHECK 约束。

        旧表有 win_rate CHECK 约束（0~1），但代码传入百分比（0~100）导致 INSERT 失败。
        此方法为幂等操作：无旧约束时跳过。
        """
        try:
            # 1. Check if table exists
            cursor = await self._db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='backtest_reports'"
            )
            row = await cursor.fetchone()
            if not row:
                logger.info("[MIGRATE] backtest_reports 表不存在，跳过迁移")
                return

            table_sql = row["sql"]

            # 2. Check for old CHECK constraints
            has_old_constraint = "CHECK" in table_sql.upper() and (
                "win_rate" in table_sql or "max_drawdown" in table_sql
            )

            if not has_old_constraint:
                logger.info("[MIGRATE] backtest_reports 表无旧 CHECK 约束，跳过迁移")
                return

            logger.info("[MIGRATE] 检测到旧 CHECK 约束，开始迁移...")

            # 3. Rename old table to _old
            await self._db.execute("ALTER TABLE backtest_reports RENAME TO backtest_reports_old")

            # 4. Create new table (without CHECK constraints - CREATE TABLE IF NOT EXISTS will create fresh)
            await self._db.execute("""
                CREATE TABLE backtest_reports (
                    id                  TEXT PRIMARY KEY,
                    strategy_id         TEXT NOT NULL,
                    strategy_name       TEXT NOT NULL,
                    strategy_version    TEXT NOT NULL DEFAULT '1.0.0',
                    strategy_snapshot   TEXT NOT NULL,
                    parameters_hash     TEXT NOT NULL,
                    symbol              TEXT NOT NULL,
                    timeframe           TEXT NOT NULL,
                    backtest_start      INTEGER NOT NULL,
                    backtest_end        INTEGER NOT NULL,
                    created_at          INTEGER NOT NULL,
                    initial_balance     TEXT NOT NULL,
                    final_balance       TEXT NOT NULL,
                    total_return        TEXT NOT NULL DEFAULT '0',
                    total_trades        INTEGER NOT NULL DEFAULT 0,
                    winning_trades      INTEGER NOT NULL DEFAULT 0,
                    losing_trades       INTEGER NOT NULL DEFAULT 0,
                    win_rate            TEXT NOT NULL DEFAULT '0',
                    total_pnl           TEXT NOT NULL DEFAULT '0',
                    total_fees_paid     TEXT NOT NULL DEFAULT '0',
                    total_slippage_cost TEXT NOT NULL DEFAULT '0',
                    total_funding_cost  TEXT NOT NULL DEFAULT '0',
                    max_drawdown        TEXT NOT NULL DEFAULT '0',
                    sharpe_ratio        TEXT,
                    positions_summary   TEXT,
                    monthly_returns     TEXT
                )
            """)

            # 5. Copy data from old table (handle column count mismatch)
            # 旧表可能没有 total_funding_cost 列，需要逐列映射
            try:
                await self._db.execute("""
                    INSERT INTO backtest_reports (
                        id, strategy_id, strategy_name, strategy_version,
                        strategy_snapshot, parameters_hash, symbol, timeframe,
                        backtest_start, backtest_end, created_at,
                        initial_balance, final_balance, total_return,
                        total_trades, winning_trades, losing_trades, win_rate,
                        total_pnl, total_fees_paid, total_slippage_cost,
                        total_funding_cost, max_drawdown,
                        sharpe_ratio, positions_summary, monthly_returns
                    )
                    SELECT
                        id, strategy_id, strategy_name, strategy_version,
                        strategy_snapshot, parameters_hash, symbol, timeframe,
                        backtest_start, backtest_end, created_at,
                        initial_balance, final_balance, total_return,
                        total_trades, winning_trades, losing_trades, win_rate,
                        total_pnl, total_fees_paid, total_slippage_cost,
                        '0', max_drawdown,
                        sharpe_ratio, positions_summary, monthly_returns
                    FROM backtest_reports_old
                """)
            except Exception:
                # 旧表已有 total_funding_cost 列时，直接 SELECT *
                await self._db.execute("""
                    INSERT INTO backtest_reports
                    SELECT * FROM backtest_reports_old
                """)

            # 6. Drop old table
            await self._db.execute("DROP TABLE backtest_reports_old")

            # 7. Recreate indexes
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_reports_strategy_id
                ON backtest_reports(strategy_id)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_reports_symbol
                ON backtest_reports(symbol)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_reports_timeframe
                ON backtest_reports(timeframe)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_reports_created_at
                ON backtest_reports(created_at)
            """)
            await self._db.execute("""
                CREATE INDEX IF NOT EXISTS idx_backtest_reports_parameters_hash
                ON backtest_reports(parameters_hash)
            """)

            await self._db.commit()
            logger.info("[MIGRATE] backtest_reports 表迁移完成（旧 CHECK 约束已移除）")

        except Exception as e:
            logger.error(f"[MIGRATE] backtest_reports 表迁移失败: {e}")
            # 不重新抛出异常，允许系统继续运行（降级为无迁移模式）
