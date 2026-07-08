"""extend roles and refresh tokens

Revision ID: 0003_auth_and_rbac
Revises: 0002_multi_tenancy
Create Date: 2026-07-06

Phase 2 Auth & RBAC:
  - Migrate existing 'employee' admins to 'chef'
  - Alter admins.role ENUM to ('owner', 'admin', 'chef', 'cashier')
  - Create refresh_tokens table (fully tenant-isolated)
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_auth_and_rbac"
down_revision = "0002_multi_tenancy"
branch_labels = None
depends_on = None

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"

def upgrade() -> None:
    # 1. Update any existing 'employee' users to 'chef' role so we don't violate the new Enum constraint
    op.execute("UPDATE admins SET role = 'chef' WHERE role = 'employee'")

    # 2. Modify admins.role enum definition
    op.execute("""
        ALTER TABLE admins 
        MODIFY COLUMN role ENUM('owner', 'admin', 'chef', 'cashier') NOT NULL DEFAULT 'chef'
    """)

    # 3. Create refresh_tokens table
    op.execute("""
        CREATE TABLE refresh_tokens (
            id INT PRIMARY KEY AUTO_INCREMENT,
            tenant_id CHAR(36) NOT NULL,
            admin_id INT NOT NULL,
            token VARCHAR(512) UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT,
            FOREIGN KEY (admin_id) REFERENCES admins(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 4. Add index for quick token lookup
    op.execute("CREATE INDEX idx_refresh_tokens_lookup ON refresh_tokens (token(191))")


def downgrade() -> None:
    # 1. Drop index & table
    op.execute("DROP INDEX idx_refresh_tokens_lookup ON refresh_tokens")
    op.execute("DROP TABLE refresh_tokens")

    # 2. Re-map any 'owner', 'chef', 'cashier' roles to 'admin'/'employee' before shrinking the ENUM
    op.execute("UPDATE admins SET role = 'admin' WHERE role = 'owner'")
    op.execute("UPDATE admins SET role = 'employee' WHERE role IN ('chef', 'cashier')")

    # 3. Restore old role ENUM
    op.execute("""
        ALTER TABLE admins 
        MODIFY COLUMN role ENUM('admin', 'employee') NOT NULL DEFAULT 'employee'
    """)
