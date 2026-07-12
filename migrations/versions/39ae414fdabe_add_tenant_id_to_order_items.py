"""add tenant_id to order_items

Revision ID: 39ae414fdabe
Revises: 0005_add_payments
Create Date: 2026-07-12 09:43:12.870427

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39ae414fdabe'
down_revision: Union[str, Sequence[str], None] = '0005_add_payments'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add tenant_id column as nullable
    op.add_column('order_items', sa.Column('tenant_id', sa.String(length=36), nullable=True))
    
    # 2. Backfill existing order items with the parent order's tenant_id
    op.execute("""
        UPDATE order_items 
        INNER JOIN orders ON order_items.order_id = orders.id 
        SET order_items.tenant_id = orders.tenant_id
    """)
    
    # 3. Alter tenant_id column to be NOT NULL
    op.alter_column('order_items', 'tenant_id', nullable=False, existing_type=sa.String(length=36))
    
    # 4. Add foreign key constraint to tenants(id)
    op.create_foreign_key(
        'fk_order_items_tenant',
        'order_items',
        'tenants',
        ['tenant_id'],
        ['id'],
        ondelete='RESTRICT'
    )
    
    # 5. Add composite index on (tenant_id, order_id)
    op.create_index('idx_order_items_tenant_order', 'order_items', ['tenant_id', 'order_id'])


def downgrade() -> None:
    # 1. Drop composite index
    op.drop_index('idx_order_items_tenant_order', table_name='order_items')
    
    # 2. Drop foreign key constraint
    op.drop_constraint('fk_order_items_tenant', 'order_items', type_='foreignkey')
    
    # 3. Drop tenant_id column
    op.drop_column('order_items', 'tenant_id')
