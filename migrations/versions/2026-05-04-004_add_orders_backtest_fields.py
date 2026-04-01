"""添加 orders 表回测相关字段

Revision ID: 004
Revises: 003
Create Date: 2026-05-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """添加 orders 表回测相关字段"""

    # 检查是否为 SQLite，使用 batch mode
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == 'sqlite'

    if is_sqlite:
        # SQLite 需要使用 batch mode 来添加外键约束
        with op.batch_alter_table('orders', schema=None) as batch_op:
            # 添加 filled_at 字段 (成交时间戳)
            batch_op.add_column(
                sa.Column('filled_at', sa.Integer(), nullable=True)
            )

            # 添加 parent_order_id 字段 (父订单 ID，用于 DCA 分批建仓)
            batch_op.add_column(
                sa.Column('parent_order_id', sa.String(64), nullable=True)
            )

            # 创建外键约束 (自引用)
            batch_op.create_foreign_key(
                'fk_orders_parent_order',
                'orders',
                ['parent_order_id'], ['id'],
                ondelete='SET NULL'
            )

            # 创建索引
            batch_op.create_index(
                'idx_orders_parent_order_id',
                ['parent_order_id'],
                unique=False
            )
    else:
        # 非 SQLite 数据库使用标准方式
        # 添加 filled_at 字段 (成交时间戳)
        op.add_column(
            'orders',
            sa.Column('filled_at', sa.Integer(), nullable=True)
        )

        # 添加 parent_order_id 字段 (父订单 ID，用于 DCA 分批建仓)
        op.add_column(
            'orders',
            sa.Column('parent_order_id', sa.String(64), nullable=True)
        )

        # 创建外键约束 (自引用)
        op.create_foreign_key(
            'fk_orders_parent_order',
            'orders', 'orders',
            ['parent_order_id'], ['id'],
            ondelete='SET NULL'
        )

        # 创建索引
        op.create_index(
            'idx_orders_parent_order_id',
            'orders',
            ['parent_order_id'],
            unique=False
        )


def downgrade() -> None:
    """删除 orders 表回测相关字段"""
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == 'sqlite'

    if is_sqlite:
        # SQLite 需要使用 batch mode
        with op.batch_alter_table('orders', schema=None) as batch_op:
            # 删除索引
            batch_op.drop_index('idx_orders_parent_order_id')

            # 删除外键约束
            batch_op.drop_constraint('fk_orders_parent_order', type_='foreignkey')

            # 删除字段
            batch_op.drop_column('parent_order_id')
            batch_op.drop_column('filled_at')
    else:
        # 非 SQLite 数据库使用标准方式
        # 删除索引
        op.drop_index('idx_orders_parent_order_id', table_name='orders')

        # 删除外键约束
        op.drop_constraint('fk_orders_parent_order', 'orders', type_='foreignkey')

        # 删除字段
        op.drop_column('orders', 'parent_order_id')
        op.drop_column('orders', 'filled_at')
