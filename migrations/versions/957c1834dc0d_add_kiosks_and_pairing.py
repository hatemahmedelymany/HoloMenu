"""add_kiosks_and_pairing

Revision ID: 957c1834dc0d
Revises: 39ae414fdabe
Create Date: 2026-07-12 10:36:45.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '957c1834dc0d'
down_revision: Union[str, Sequence[str], None] = '39ae414fdabe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add plan_tier and max_kiosks columns to tenants table
    op.add_column('tenants', sa.Column('plan_tier', sa.String(length=20), nullable=False, server_default='starter'))
    op.add_column('tenants', sa.Column('max_kiosks', sa.Integer(), nullable=False, server_default='1'))

    # 2. Update demo tenant metadata to plan 'pro' and 5 max kiosks
    op.execute("UPDATE tenants SET plan_tier = 'pro', max_kiosks = 5 WHERE id = 'd4444444-4444-4444-4444-444444444444'")

    # 3. Create kiosks table using sa.CHAR(36) and strict collation arguments
    op.create_table(
        'kiosks',
        sa.Column('id', sa.CHAR(36), primary_key=True),
        sa.Column('tenant_id', sa.CHAR(36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('secret', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )

    # 4. Create websocket_sessions table using sa.CHAR(36) and strict collation arguments
    op.create_table(
        'websocket_sessions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('token', sa.String(length=512), nullable=False, unique=True),
        sa.Column('tenant_id', sa.CHAR(36), nullable=False),
        sa.Column('kiosk_id', sa.CHAR(36), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['kiosk_id'], ['kiosks.id'], ondelete='CASCADE'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        mysql_collate='utf8mb4_unicode_ci'
    )


def downgrade() -> None:
    # 1. Drop websocket_sessions table
    op.drop_table('websocket_sessions')

    # 2. Drop kiosks table
    op.drop_table('kiosks')

    # 3. Remove columns from tenants table
    op.drop_column('tenants', 'max_kiosks')
    op.drop_column('tenants', 'plan_tier')
