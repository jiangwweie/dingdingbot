"""创建 orders 和 positions 表

Revision ID: 002
Revises: 001
Create Date: 2026-05-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 orders 和 positions 表"""

    # ===== 创建 orders 表 =====
    op.create_table(
        'orders',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('signal_id', sa.String(), nullable=False),
        sa.Column('exchange_order_id', sa.String(), nullable=True),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('order_type', sa.String(), nullable=False),
        sa.Column('order_role', sa.String(), nullable=False),
        sa.Column('price', sa.String(), nullable=True),
        sa.Column('trigger_price', sa.String(), nullable=True),
        sa.Column('requested_qty', sa.String(), nullable=False),
        sa.Column('filled_qty', sa.String(), nullable=False, server_default="'0'"),
        sa.Column('average_exec_price', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default="'PENDING'"),
        sa.Column('exit_reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ondelete='CASCADE'),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name='check_orders_direction'),
    )

    # orders 表索引
    op.create_index('idx_orders_signal_id', 'orders', ['signal_id'], unique=False)
    op.create_index('idx_orders_status', 'orders', ['status'], unique=False)
    op.create_index('idx_orders_symbol', 'orders', ['symbol'], unique=False)

    # ===== 创建 positions 表 =====
    op.create_table(
        'positions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('signal_id', sa.String(), nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('entry_price', sa.String(), nullable=False),
        sa.Column('current_qty', sa.String(), nullable=False),
        sa.Column('highest_price_since_entry', sa.String(), nullable=False),
        sa.Column('realized_pnl', sa.String(), nullable=False, server_default="'0'"),
        sa.Column('total_fees_paid', sa.String(), nullable=False, server_default="'0'"),
        sa.Column('is_closed', sa.Integer(), nullable=False, server_default="0"),
        sa.Column('created_at', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['signal_id'], ['signals.id'], ondelete='CASCADE'),
        sa.CheckConstraint("direction IN ('LONG', 'SHORT')", name='check_positions_direction'),
    )

    # positions 表索引
    op.create_index('idx_positions_signal_id', 'positions', ['signal_id'], unique=False)
    op.create_index('idx_positions_is_closed', 'positions', ['is_closed'], unique=False)
    op.create_index('idx_positions_symbol', 'positions', ['symbol'], unique=False)


def downgrade() -> None:
    """删除 orders 和 positions 表"""
    # 删除 positions 表
    op.drop_index('idx_positions_symbol', table_name='positions')
    op.drop_index('idx_positions_is_closed', table_name='positions')
    op.drop_index('idx_positions_signal_id', table_name='positions')
    op.drop_table('positions')

    # 删除 orders 表
    op.drop_index('idx_orders_symbol', table_name='orders')
    op.drop_index('idx_orders_status', table_name='orders')
    op.drop_index('idx_orders_signal_id', table_name='orders')
    op.drop_table('orders')
