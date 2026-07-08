"""initial_schema

Revision ID: 0001_initial
Revises: 
Create Date: 2026-07-06

Phase 0 fixes applied on top of holomenu_db.sql:
  - orders.status ENUM corrected to the canonical 7-value lifecycle
    (pending, confirmed, cooking, ready, completed, cancelled, expired)
    replacing the old 4-value set that didn't match the backend
  - order_items: added UNIQUE(order_id, product_id) so ON DUPLICATE KEY UPDATE works
  - order_items: changed order_id FK to ON DELETE RESTRICT (was CASCADE — dangerous)
  - order_items: added CHECK quantity > 0
  - All tables: added created_at / updated_at timestamps where missing
  - analytics_events: product_id / department_id made strict FKs (with SET NULL)
  - admins: added created_at timestamp
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Drop existing tables in reverse dependency order if they exist ──────
    # (idempotent — safe to run on a fresh DB or one seeded by holomenu_db.sql)
    op.execute("SET FOREIGN_KEY_CHECKS = 0")
    op.execute("DROP TABLE IF EXISTS analytics_events")
    op.execute("DROP TABLE IF EXISTS order_items")
    op.execute("DROP TABLE IF EXISTS orders")
    op.execute("DROP TABLE IF EXISTS admins")
    op.execute("DROP TABLE IF EXISTS products")
    op.execute("DROP TABLE IF EXISTS departments")
    op.execute("SET FOREIGN_KEY_CHECKS = 1")

    # ── departments ──────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE departments (
            id            INT          PRIMARY KEY AUTO_INCREMENT,
            name_en       VARCHAR(100) NOT NULL,
            name_ar       VARCHAR(100) NOT NULL,
            icon_path     VARCHAR(255) DEFAULT NULL,
            display_order INT          NOT NULL DEFAULT 0,
            active        BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── products ─────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE products (
            id              INT           PRIMARY KEY AUTO_INCREMENT,
            department_id   INT           NOT NULL,
            name_en         VARCHAR(150)  NOT NULL,
            name_ar         VARCHAR(150)  NOT NULL,
            description_en  TEXT,
            description_ar  TEXT,
            price           DECIMAL(10,2) NOT NULL,
            currency        VARCHAR(10)   NOT NULL DEFAULT 'EGP',
            ingredients     JSON,
            calories        INT           DEFAULT 0,
            allergens       JSON,
            media_type      ENUM('image','video','3d_model') DEFAULT 'image',
            media_path      VARCHAR(255),
            thumbnail_path  VARCHAR(255),
            available       BOOLEAN       NOT NULL DEFAULT TRUE,
            featured        BOOLEAN       NOT NULL DEFAULT FALSE,
            qr_order_url    VARCHAR(512),
            created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                   ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (department_id) REFERENCES departments(id)
                ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── orders ───────────────────────────────────────────────────────────────
    # FIX (Phase 0.1): corrected ENUM from 4 values to the canonical 7-value
    # lifecycle that the backend actually uses.
    # Old values: in_progress, confirmed, cancelled, expired
    # New values: pending(≡in_progress), confirmed, cooking, ready,
    #             completed, cancelled, expired
    op.execute("""
        CREATE TABLE orders (
            id           INT           PRIMARY KEY AUTO_INCREMENT,
            order_uid    VARCHAR(64)   UNIQUE NOT NULL,
            status       ENUM(
                'pending',
                'confirmed',
                'cooking',
                'ready',
                'completed',
                'cancelled',
                'expired'
            ) NOT NULL DEFAULT 'pending',
            total_price  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
            started_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP     NULL DEFAULT NULL,
            created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── order_items ──────────────────────────────────────────────────────────
    # FIX (Phase 0.2): added UNIQUE(order_id, product_id) — the backend's
    #   ON DUPLICATE KEY UPDATE assumed this but the schema never defined it.
    # FIX (Phase 0.2): quantity CHECK > 0
    # FIX (Phase 0.4): order_id FK changed from CASCADE to RESTRICT so you
    #   can't silently destroy order history by deleting an order row directly.
    op.execute("""
        CREATE TABLE order_items (
            id          INT           PRIMARY KEY AUTO_INCREMENT,
            order_id    INT           NOT NULL,
            product_id  INT           NOT NULL,
            quantity    INT           NOT NULL DEFAULT 1
                            CHECK (quantity > 0),
            unit_price  DECIMAL(10,2) NOT NULL,
            created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_order_product UNIQUE (order_id, product_id),
            FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE RESTRICT,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── analytics_events ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE analytics_events (
            id            BIGINT       PRIMARY KEY AUTO_INCREMENT,
            event_type    VARCHAR(50)  NOT NULL,
            product_id    INT          NULL,
            department_id INT          NULL,
            session_uid   VARCHAR(64)  NOT NULL,
            meta          JSON         NULL,
            created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id)    REFERENCES products(id)    ON DELETE SET NULL,
            FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── admins ───────────────────────────────────────────────────────────────
    # NOTE: roles will be expanded in Phase 2 (owner, admin, chef, cashier, kiosk)
    # For now keeping existing values and adding timestamps.
    op.execute("""
        CREATE TABLE admins (
            id            INT          PRIMARY KEY AUTO_INCREMENT,
            username      VARCHAR(50)  UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role          ENUM('admin','employee') NOT NULL DEFAULT 'employee',
            created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # ── Seed departments ─────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO departments (name_en, name_ar, icon_path, display_order, active) VALUES
          ('Burgers',  'برجر',    'assets/icons/burgers.svg',  1, TRUE),
          ('Sides',    'مقبلات',  'assets/icons/sides.svg',    2, TRUE),
          ('Drinks',   'مشروبات', 'assets/icons/drinks.svg',   3, TRUE),
          ('Desserts', 'حلويات',  'assets/icons/desserts.svg', 4, TRUE)
    """)

    # ── Seed products ────────────────────────────────────────────────────────
    op.execute("""
        INSERT INTO products
          (department_id, name_en, name_ar, description_en, description_ar,
           price, ingredients, calories, allergens,
           media_type, media_path, thumbnail_path, available, featured, qr_order_url)
        VALUES
        (1, 'Holo Classic Burger', 'هولو برجر كلاسيك',
         'Premium double beef patty, aged cheddar, secret smoky sauce, fresh lettuce on a toasted brioche bun.',
         'شريحتين لحم بقري فاخر، جبن شيدر معتق، صلصة مدخنة سرية، خس طازج في خبز بريوش محمص.',
         180.00,
         '["100% Beef Patty","Cheddar Cheese","Secret Sauce","Lettuce","Brioche Bun"]',
         720, '["Gluten","Dairy"]',
         'image', 'assets/images/burger.png', 'assets/images/burger_thumb.png',
         TRUE, TRUE, 'https://example.com/order/prod_burger'),

        (1, 'Neon Smash Burger', 'برجر سماش النيون',
         'Two smashed patties, American cheese, pickles, mustard, crispy onions on a sesame bun.',
         'شريحتان مسحوقتان، جبن أمريكي، مخلل، خردل، بصل مقرمش في خبز سمسم.',
         160.00,
         '["Smash Patties","American Cheese","Pickles","Mustard","Crispy Onions","Sesame Bun"]',
         680, '["Gluten","Dairy"]',
         'image', 'assets/images/burger.png', 'assets/images/burger_thumb.png',
         TRUE, FALSE, 'https://example.com/order/prod_smash'),

        (2, 'Neon Loaded Fries', 'بطاطس نيون لودد',
         'Crispy golden hand-cut fries loaded with warm cheese sauce, jalapeno slices, and chopped chives.',
         'بطاطس مقرمشة ذهبية مغطاة بصلصة الجبن الدافئة وشرائح الهالبينو والثوم المعمر.',
         95.00,
         '["Hand-cut Fries","Cheese Sauce","Jalapenos","Chives"]',
         480, '["Dairy"]',
         'image', 'assets/images/fries.png', 'assets/images/fries_thumb.png',
         TRUE, FALSE, 'https://example.com/order/prod_fries'),

        (2, 'Onion Rings', 'حلقات البصل',
         'Golden battered onion rings with smoky dipping sauce.',
         'حلقات بصل مغطاة بالعجينة الذهبية مع صلصة مدخنة للغمس.',
         65.00,
         '["Onion Rings","Batter","Smoky Sauce"]',
         320, '["Gluten","Dairy"]',
         'image', 'assets/images/fries.png', 'assets/images/fries_thumb.png',
         TRUE, FALSE, 'https://example.com/order/prod_rings'),

        (3, 'Holographic Blue Mojito', 'موهيتو أزرق هولوغرافي',
         'Refreshing mocktail with blue curaçao, fresh lime juice, crushed mint leaves, and sparkling soda.',
         'موكتيل منعش مع بلو كوراساو وعصير ليمون طازج وأوراق نعناع مهروسة وصودا فوارة.',
         75.00,
         '["Blue Curaçao","Fresh Lime","Mint Leaves","Sparkling Soda"]',
         150, '[]',
         'image', 'assets/images/mojito.png', 'assets/images/mojito_thumb.png',
         TRUE, TRUE, 'https://example.com/order/prod_mojito'),

        (3, 'Cyber Lemonade', 'عصير الليمون السيبراني',
         'Electric yellow lemonade with a hint of ginger and soda.',
         'عصير ليمون كهربائي أصفر مع لمسة من الزنجبيل والصودا.',
         55.00,
         '["Lemon","Ginger","Soda","Sugar Syrup"]',
         90, '[]',
         'image', 'assets/images/mojito.png', 'assets/images/mojito_thumb.png',
         TRUE, FALSE, 'https://example.com/order/prod_lemonade'),

        (4, 'Cyber Lava Cake', 'كيكة الحمم السيبرانية',
         'Warm chocolate cake with a molten dark chocolate center, dusted with neon pink raspberry powder.',
         'كيكة شوكولاتة دافئة بقلب شوكولاتة داكنة ذائبة مرشوشة ببودرة التوت.',
         110.00,
         '["Belgian Cocoa","Dark Chocolate","Raspberry Dust"]',
         540, '["Gluten","Dairy","Eggs"]',
         'image', 'assets/images/cake.png', 'assets/images/cake_thumb.png',
         TRUE, FALSE, 'https://example.com/order/prod_cake'),

        (4, 'Galaxy Cheesecake', 'تشيز كيك المجرة',
         'No-bake cheesecake with a galaxy swirl topping of blueberry and blackcurrant.',
         'تشيز كيك بدون خبز مع طبقة علوية بنمط المجرة من التوت الأزرق والكشمش الأسود.',
         95.00,
         '["Cream Cheese","Biscuit Base","Blueberry","Blackcurrant"]',
         420, '["Dairy","Gluten"]',
         'image', 'assets/images/cake.png', 'assets/images/cake_thumb.png',
         TRUE, FALSE, 'https://example.com/order/prod_cheesecake')
    """)


def downgrade() -> None:
    op.execute("SET FOREIGN_KEY_CHECKS = 0")
    op.execute("DROP TABLE IF EXISTS analytics_events")
    op.execute("DROP TABLE IF EXISTS order_items")
    op.execute("DROP TABLE IF EXISTS orders")
    op.execute("DROP TABLE IF EXISTS admins")
    op.execute("DROP TABLE IF EXISTS products")
    op.execute("DROP TABLE IF EXISTS departments")
    op.execute("SET FOREIGN_KEY_CHECKS = 1")
