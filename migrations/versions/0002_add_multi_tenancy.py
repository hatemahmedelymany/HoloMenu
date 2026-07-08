"""add multi tenancy

Revision ID: 0002_multi_tenancy
Revises: 0001_initial
Create Date: 2026-07-06

Phase 1 changes:
  - Create tenants table
  - Add tenant_id column to departments, products, orders, admins, analytics_events
  - Seed a default 'demo' tenant
  - Assign all existing seed data to the 'demo' tenant
  - Add composite indexes on hot tables
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_multi_tenancy"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

DEMO_TENANT_ID = "d4444444-4444-4444-4444-444444444444"


def upgrade() -> None:
    # 1. Create tenants table
    op.execute("""
        CREATE TABLE tenants (
            id CHAR(36) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            subdomain VARCHAR(63) UNIQUE NOT NULL,
            plan ENUM('trial','starter','pro','enterprise') NOT NULL DEFAULT 'trial',
            status ENUM('active','suspended','cancelled') NOT NULL DEFAULT 'active',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # 2. Seed default demo tenant
    op.execute(f"""
        INSERT INTO tenants (id, name, subdomain, plan, status)
        VALUES ('{DEMO_TENANT_ID}', 'Demo Restaurant', 'demo', 'starter', 'active')
    """)

    # 3. Add tenant_id to departments, products, orders, admins, analytics_events
    # We will make them NOT NULL but set default to DEMO_TENANT_ID so existing rows are automatically migrated.
    
    # ── departments
    op.execute(f"ALTER TABLE departments ADD COLUMN tenant_id CHAR(36) NOT NULL DEFAULT '{DEMO_TENANT_ID}'")
    op.execute("ALTER TABLE departments ADD CONSTRAINT fk_departments_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE departments ALTER COLUMN tenant_id DROP DEFAULT")

    # ── products
    op.execute(f"ALTER TABLE products ADD COLUMN tenant_id CHAR(36) NOT NULL DEFAULT '{DEMO_TENANT_ID}'")
    op.execute("ALTER TABLE products ADD CONSTRAINT fk_products_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE products ALTER COLUMN tenant_id DROP DEFAULT")

    # ── orders
    op.execute(f"ALTER TABLE orders ADD COLUMN tenant_id CHAR(36) NOT NULL DEFAULT '{DEMO_TENANT_ID}'")
    op.execute("ALTER TABLE orders ADD CONSTRAINT fk_orders_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE orders ALTER COLUMN tenant_id DROP DEFAULT")

    # ── admins
    op.execute(f"ALTER TABLE admins ADD COLUMN tenant_id CHAR(36) NOT NULL DEFAULT '{DEMO_TENANT_ID}'")
    op.execute("ALTER TABLE admins ADD CONSTRAINT fk_admins_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE admins ALTER COLUMN tenant_id DROP DEFAULT")

    # ── analytics_events
    op.execute(f"ALTER TABLE analytics_events ADD COLUMN tenant_id CHAR(36) NOT NULL DEFAULT '{DEMO_TENANT_ID}'")
    op.execute("ALTER TABLE analytics_events ADD CONSTRAINT fk_analytics_events_tenant FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT")
    op.execute("ALTER TABLE analytics_events ALTER COLUMN tenant_id DROP DEFAULT")

    # 4. Add composite indexes on hot tables
    op.execute("CREATE INDEX idx_orders_tenant_status ON orders (tenant_id, status)")
    op.execute("CREATE INDEX idx_products_tenant_available ON products (tenant_id, available)")
    op.execute("CREATE INDEX idx_departments_tenant_active_order ON departments (tenant_id, active, display_order)")


def downgrade() -> None:
    # Remove indexes
    op.execute("DROP INDEX idx_departments_tenant_active_order ON departments")
    op.execute("DROP INDEX idx_products_tenant_available ON products")
    op.execute("DROP INDEX idx_orders_tenant_status ON orders")

    # Drop foreign keys and columns
    op.execute("ALTER TABLE analytics_events DROP FOREIGN KEY fk_analytics_events_tenant")
    op.execute("ALTER TABLE analytics_events DROP COLUMN tenant_id")

    op.execute("ALTER TABLE admins DROP FOREIGN KEY fk_admins_tenant")
    op.execute("ALTER TABLE admins DROP COLUMN tenant_id")

    op.execute("ALTER TABLE orders DROP FOREIGN KEY fk_orders_tenant")
    op.execute("ALTER TABLE orders DROP COLUMN tenant_id")

    op.execute("ALTER TABLE products DROP FOREIGN KEY fk_products_tenant")
    op.execute("ALTER TABLE products DROP COLUMN tenant_id")

    op.execute("ALTER TABLE departments DROP FOREIGN KEY fk_departments_tenant")
    op.execute("ALTER TABLE departments DROP COLUMN tenant_id")

    # Drop tenants table
    op.execute("DROP TABLE tenants")
