"""迁移旧 custom_strategies 表到新 strategies 表

Revision ID: 006
Revises: 005
Create Date: 2026-04-13

方案 B: 彻底统一策略表。将旧表 custom_strategies 中的数据迁移到新表 strategies，
然后删除旧表。新部署（旧表不存在）时跳过迁移。
"""
from typing import Sequence, Union
import json
import uuid

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    升级：迁移 custom_strategies -> strategies，然后删除旧表。

    步骤:
    1. 检查旧表 custom_strategies 是否存在，不存在则跳过
    2. 检查新表 strategies 是否存在，不存在则报错
    3. 读取旧表所有行，解析 strategy_json
    4. 将解析后的数据映射到新表字段
    5. 生成新 UUID 作为 ID
    6. 插入新表
    7. 删除旧表
    """
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. 旧表不存在 -> 全新部署，跳过迁移
    if 'custom_strategies' not in tables:
        print("[MIGRATION 006] custom_strategies table not found, skipping migration (fresh deployment)")
        return

    # 2. 新表必须存在
    if 'strategies' not in tables:
        raise RuntimeError(
            "[MIGRATION 006] FATAL: 'strategies' table does not exist! "
            "Please ensure migration 005 (or equivalent) has been run first."
        )

    # 3. 读取旧表数据
    result = conn.execute(sa.text(
        "SELECT id, name, description, strategy_json, created_at, updated_at "
        "FROM custom_strategies ORDER BY created_at"
    ))
    old_rows = result.fetchall()

    print(f"[MIGRATION 006] Found {len(old_rows)} rows in custom_strategies")

    for old_row in old_rows:
        old_id, name, description, strategy_json_str, created_at, updated_at = old_row

        # 4. 解析 strategy_json 并映射到新表字段
        strategy_def = json.loads(strategy_json_str)

        # Extract trigger_config (first trigger from triggers list)
        triggers = strategy_def.get('triggers', [])
        trigger_config = json.dumps(triggers[0] if triggers else {})

        # Extract filter_configs
        filters = strategy_def.get('filters', [])
        filter_configs = json.dumps(filters)

        # Extract filter_logic
        filter_logic = strategy_def.get('filter_logic', 'AND')

        # Extract symbols and timeframes from apply_to
        apply_to = strategy_def.get('apply_to', [])
        symbols = []
        timeframes = []
        for scope in apply_to:
            # Format: "BTC/USDT:USDT:15m" -> symbol="BTC/USDT:USDT", timeframe="15m"
            parts = scope.rsplit(':', 1)
            if len(parts) == 2:
                symbols.append(parts[0])
                timeframes.append(parts[1])
            else:
                symbols.append(scope)
                timeframes.append('15m')  # default

        # Generate new UUID
        new_id = str(uuid.uuid4())

        # 5. 插入新表
        conn.execute(sa.text(
            """
            INSERT INTO strategies (
                id, name, description, is_active,
                trigger_config, filter_configs, filter_logic,
                symbols, timeframes,
                created_at, updated_at, version
            ) VALUES (
                :id, :name, :description, 1,
                :trigger_config, :filter_configs, :filter_logic,
                :symbols, :timeframes,
                :created_at, :updated_at, 1
            )
            """
            ,
            {
                'id': new_id,
                'name': name,
                'description': description,
                'trigger_config': trigger_config,
                'filter_configs': filter_configs,
                'filter_logic': filter_logic,
                'symbols': json.dumps(symbols),
                'timeframes': json.dumps(timeframes),
                'created_at': created_at,
                'updated_at': updated_at,
            }
        ))
        print(f"[MIGRATION 006] Migrated strategy '{name}' (old_id={old_id} -> new_id={new_id})")

    conn.commit()

    # 6. 删除旧表
    op.drop_table('custom_strategies')
    print("[MIGRATION 006] Dropped custom_strategies table")


def downgrade() -> None:
    """
    降级：重建空的 custom_strategies 表（数据不可恢复，因为旧表已被删除）。

    注意：由于 upgrade() 删除了旧表，downgrade 只能重建空表结构。
    已迁移到新表的数据不会回写。
    """
    op.create_table(
        'custom_strategies',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('strategy_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.Text(), nullable=False),
    )

    op.create_index(
        'idx_custom_strategies_name',
        'custom_strategies',
        ['name'],
        unique=False
    )

    print("[MIGRATION 006 DOWNGRADE] Rebuilt empty custom_strategies table (data not recoverable)")
