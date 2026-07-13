"""tenant_soft_delete
Revision ID: fa78e12fd45b
Revises: e9da907f59d5
Create Date: 2026-07-12 18:40:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'fa78e12fd45b'
down_revision: Union[str, Sequence[str], None] = 'e9da907f59d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add deleted_at to tenants table
    op.add_column('tenants', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    # Add legal_business_name to tenants table
    op.add_column('tenants', sa.Column('legal_business_name', sa.String(length=255), nullable=True))
    # Backfill legal_business_name from current name
    op.execute("UPDATE tenants SET legal_business_name = name WHERE legal_business_name IS NULL")


def downgrade() -> None:
    op.drop_column('tenants', 'legal_business_name')
    op.drop_column('tenants', 'deleted_at')
