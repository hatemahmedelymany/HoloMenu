-- HoloMenu Database Schema
-- Run in phpMyAdmin or: mysql -u root -p < holomenu_db.sql

CREATE DATABASE IF NOT EXISTS holomenu_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE holomenu_db;

-- ─── DEPARTMENTS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS departments (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  name_en       VARCHAR(100) NOT NULL,
  name_ar       VARCHAR(100) NOT NULL,
  icon_path     VARCHAR(255) DEFAULT NULL,
  display_order INT          NOT NULL DEFAULT 0,
  active        BOOLEAN      NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── PRODUCTS ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
  id              INT PRIMARY KEY AUTO_INCREMENT,
  department_id   INT          NOT NULL,
  name_en         VARCHAR(150) NOT NULL,
  name_ar         VARCHAR(150) NOT NULL,
  description_en  TEXT,
  description_ar  TEXT,
  price           DECIMAL(10,2) NOT NULL,
  currency        VARCHAR(10)  NOT NULL DEFAULT 'EGP',
  ingredients     JSON,
  calories        INT          DEFAULT 0,
  allergens       JSON,
  media_type      ENUM('image','video','3d_model') DEFAULT 'image',
  media_path      VARCHAR(255),
  thumbnail_path  VARCHAR(255),
  available       BOOLEAN      NOT NULL DEFAULT TRUE,
  featured        BOOLEAN      NOT NULL DEFAULT FALSE,
  qr_order_url    VARCHAR(512),
  created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ORDERS ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
  id           INT PRIMARY KEY AUTO_INCREMENT,
  order_uid    VARCHAR(64) UNIQUE NOT NULL,
  status       ENUM('in_progress','confirmed','cancelled','expired') NOT NULL DEFAULT 'in_progress',
  total_price  DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  started_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ORDER ITEMS ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
  id          INT PRIMARY KEY AUTO_INCREMENT,
  order_id    INT          NOT NULL,
  product_id  INT          NOT NULL,
  quantity    INT          NOT NULL DEFAULT 1,
  unit_price  DECIMAL(10,2) NOT NULL,
  FOREIGN KEY (order_id)   REFERENCES orders(id)   ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ANALYTICS EVENTS ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_events (
  id            BIGINT PRIMARY KEY AUTO_INCREMENT,
  event_type    VARCHAR(50) NOT NULL,
  product_id    INT NULL,
  department_id INT NULL,
  session_uid   VARCHAR(64) NOT NULL,
  meta          JSON NULL,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ADMINS (Phase 4) ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS admins (
  id            INT PRIMARY KEY AUTO_INCREMENT,
  username      VARCHAR(50) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role          ENUM('admin','employee') NOT NULL DEFAULT 'employee'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── SEED: DEPARTMENTS ──────────────────────────────────────────────────────
INSERT INTO departments (name_en, name_ar, icon_path, display_order, active) VALUES
  ('Burgers',  'برجر',    'assets/icons/burgers.svg',  1, TRUE),
  ('Sides',    'مقبلات',  'assets/icons/sides.svg',    2, TRUE),
  ('Drinks',   'مشروبات', 'assets/icons/drinks.svg',   3, TRUE),
  ('Desserts', 'حلويات',  'assets/icons/desserts.svg', 4, TRUE);

-- ─── SEED: PRODUCTS ─────────────────────────────────────────────────────────
INSERT INTO products
  (department_id, name_en, name_ar, description_en, description_ar,
   price, ingredients, calories, allergens,
   media_type, media_path, thumbnail_path, available, featured, qr_order_url)
VALUES
-- Burgers (dept 1)
(1, 'Holo Classic Burger', 'هولو برجر كلاسيك',
 'Premium double beef patty, aged cheddar, secret smoky sauce, fresh lettuce on a toasted brioche bun.',
 'شريحتين لحم بقري فاخر، جبن شيدر معتق، صلصة مدخنة سرية، خس طازج في خبز بريوش محمص.',
 180.00,
 '["100% Beef Patty","Cheddar Cheese","Secret Sauce","Lettuce","Brioche Bun"]',
 720,
 '["Gluten","Dairy"]',
 'image', 'assets/images/burger.png', 'assets/images/burger_thumb.png',
 TRUE, TRUE, 'https://example.com/order/prod_burger'),

(1, 'Neon Smash Burger', 'برجر سماش النيون',
 'Two smashed patties, American cheese, pickles, mustard, crispy onions on a sesame bun.',
 'شريحتان مسحوقتان، جبن أمريكي، مخلل، خردل، بصل مقرمش في خبز سمسم.',
 160.00,
 '["Smash Patties","American Cheese","Pickles","Mustard","Crispy Onions","Sesame Bun"]',
 680,
 '["Gluten","Dairy"]',
 'image', 'assets/images/burger.png', 'assets/images/burger_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_smash'),

-- Sides (dept 2)
(2, 'Neon Loaded Fries', 'بطاطس نيون لودد',
 'Crispy golden hand-cut fries loaded with warm cheese sauce, jalapeno slices, and chopped chives.',
 'بطاطس مقرمشة ذهبية مغطاة بصلصة الجبن الدافئة وشرائح الهالبينو والثوم المعمر.',
 95.00,
 '["Hand-cut Fries","Cheese Sauce","Jalapenos","Chives"]',
 480,
 '["Dairy"]',
 'image', 'assets/images/fries.png', 'assets/images/fries_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_fries'),

(2, 'Onion Rings', 'حلقات البصل',
 'Golden battered onion rings with smoky dipping sauce.',
 'حلقات بصل مغطاة بالعجينة الذهبية مع صلصة مدخنة للغمس.',
 65.00,
 '["Onion Rings","Batter","Smoky Sauce"]',
 320,
 '["Gluten","Dairy"]',
 'image', 'assets/images/fries.png', 'assets/images/fries_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_rings'),

-- Drinks (dept 3)
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

-- Desserts (dept 4)
(4, 'Cyber Lava Cake', 'كيكة الحمم السيبرانية',
 'Warm chocolate cake with a molten dark chocolate center, dusted with neon pink raspberry powder.',
 'كيكة شوكولاتة دافئة بقلب شوكولاتة داكنة ذائبة مرشوشة ببودرة التوت.',
 110.00,
 '["Belgian Cocoa","Dark Chocolate","Raspberry Dust"]',
 540,
 '["Gluten","Dairy","Eggs"]',
 'image', 'assets/images/cake.png', 'assets/images/cake_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_cake'),

(4, 'Galaxy Cheesecake', 'تشيز كيك المجرة',
 'No-bake cheesecake with a galaxy swirl topping of blueberry and blackcurrant.',
 'تشيز كيك بدون خبز مع طبقة علوية بنمط المجرة من التوت الأزرق والكشمش الأسود.',
 95.00,
 '["Cream Cheese","Biscuit Base","Blueberry","Blackcurrant"]',
 420,
 '["Dairy","Gluten"]',
 'image', 'assets/images/cake.png', 'assets/images/cake_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_cheesecake');

-- ─── CREATE APP USER (run as root) ──────────────────────────────────────────
-- CREATE USER IF NOT EXISTS 'holomenu_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
-- GRANT SELECT, INSERT, UPDATE ON holomenu_db.* TO 'holomenu_app'@'localhost';
-- FLUSH PRIVILEGES;
