-- HoloMenu Database Schema
-- Synchronized with Alembic migrations at head (SaaS Readiness Baseline)
-- Run: mysql -u holomenu_app -p < holomenu_db.sql

CREATE DATABASE IF NOT EXISTS holomenu_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE holomenu_db;

-- ─── TENANTS ───
CREATE TABLE `tenants` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `subdomain` varchar(63) COLLATE utf8mb4_unicode_ci NOT NULL,
  `plan` enum('trial','starter','pro','enterprise') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'trial',
  `status` enum('active','suspended','cancelled') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `plan_tier` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'starter',
  `max_kiosks` int(11) NOT NULL DEFAULT 1,
  `grace_period_ends_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `subdomain` (`subdomain`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── DEPARTMENTS ───
CREATE TABLE `departments` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `name_en` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_ar` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `icon_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `display_order` int(11) NOT NULL DEFAULT 0,
  `active` tinyint(1) NOT NULL DEFAULT 1,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_departments_tenant_active_order` (`tenant_id`,`active`,`display_order`),
  CONSTRAINT `fk_departments_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── PRODUCTS ───
CREATE TABLE `products` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `department_id` int(11) NOT NULL,
  `name_en` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name_ar` varchar(150) COLLATE utf8mb4_unicode_ci NOT NULL,
  `description_en` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `description_ar` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `price` decimal(10,2) NOT NULL,
  `currency` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'EGP',
  `ingredients` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`ingredients`)),
  `calories` int(11) DEFAULT 0,
  `allergens` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`allergens`)),
  `media_type` enum('image','video','3d_model') COLLATE utf8mb4_unicode_ci DEFAULT 'image',
  `media_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `thumbnail_path` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `available` tinyint(1) NOT NULL DEFAULT 1,
  `featured` tinyint(1) NOT NULL DEFAULT 0,
  `qr_order_url` varchar(512) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `department_id` (`department_id`),
  KEY `idx_products_tenant_available` (`tenant_id`,`available`),
  CONSTRAINT `fk_products_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `products_ibfk_1` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ORDERS ───
CREATE TABLE `orders` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `order_uid` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` enum('pending','confirmed','cooking','ready','completed','cancelled','expired') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'pending',
  `total_price` decimal(10,2) NOT NULL DEFAULT 0.00,
  `started_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `completed_at` timestamp NULL DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `order_uid` (`order_uid`),
  KEY `idx_orders_tenant_status` (`tenant_id`,`status`),
  CONSTRAINT `fk_orders_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── KIOSKS ───
CREATE TABLE `kiosks` (
  `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `secret` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'active',
  `device_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `tenant_id` (`tenant_id`),
  CONSTRAINT `kiosks_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ORDER_ITEMS ───
CREATE TABLE `order_items` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `order_id` int(11) NOT NULL,
  `product_id` int(11) NOT NULL,
  `quantity` int(11) NOT NULL DEFAULT 1 CHECK (`quantity` > 0),
  `unit_price` decimal(10,2) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `tenant_id` varchar(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_order_product` (`order_id`,`product_id`),
  KEY `product_id` (`product_id`),
  KEY `idx_order_items_tenant_order` (`tenant_id`,`order_id`),
  CONSTRAINT `fk_order_items_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `order_items_ibfk_1` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`),
  CONSTRAINT `order_items_ibfk_2` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ANALYTICS_EVENTS ───
CREATE TABLE `analytics_events` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `event_type` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `product_id` int(11) DEFAULT NULL,
  `department_id` int(11) DEFAULT NULL,
  `session_uid` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `meta` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`meta`)),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  KEY `product_id` (`product_id`),
  KEY `department_id` (`department_id`),
  KEY `fk_analytics_events_tenant` (`tenant_id`),
  CONSTRAINT `analytics_events_ibfk_1` FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE SET NULL,
  CONSTRAINT `analytics_events_ibfk_2` FOREIGN KEY (`department_id`) REFERENCES `departments` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_analytics_events_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── ADMINS ───
CREATE TABLE `admins` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  `password_hash` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` enum('owner','admin','chef','cashier') COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'chef',
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  KEY `fk_admins_tenant` (`tenant_id`),
  CONSTRAINT `fk_admins_tenant` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── REFRESH_TOKENS ───
CREATE TABLE `refresh_tokens` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `admin_id` int(11) NOT NULL,
  `token` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`),
  KEY `tenant_id` (`tenant_id`),
  KEY `admin_id` (`admin_id`),
  KEY `idx_refresh_tokens_lookup` (`token`(191)),
  CONSTRAINT `refresh_tokens_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `refresh_tokens_ibfk_2` FOREIGN KEY (`admin_id`) REFERENCES `admins` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── AUDIT_LOGS ───
CREATE TABLE `audit_logs` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `user_id` int(11) DEFAULT NULL,
  `action` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_type` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `target_id` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `before_state` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`before_state`)),
  `after_state` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`after_state`)),
  `ip_address` varchar(45) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `user_agent` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `idx_audit_tenant_time` (`tenant_id`,`created_at`),
  CONSTRAINT `audit_logs_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `audit_logs_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `admins` (`id`) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── PAYMENTS ───
CREATE TABLE `payments` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `order_id` int(11) NOT NULL,
  `payment_method` varchar(32) COLLATE utf8mb4_unicode_ci NOT NULL,
  `amount_tendered` decimal(10,2) DEFAULT NULL,
  `amount_paid` decimal(10,2) NOT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  KEY `idx_payments_tenant` (`tenant_id`),
  KEY `idx_payments_order` (`order_id`),
  CONSTRAINT `payments_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`),
  CONSTRAINT `payments_ibfk_2` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── WEBSOCKET_SESSIONS ───
CREATE TABLE `websocket_sessions` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `token` varchar(512) COLLATE utf8mb4_unicode_ci NOT NULL,
  `tenant_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `kiosk_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL,
  `device_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `expires_at` datetime NOT NULL,
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`id`),
  UNIQUE KEY `token` (`token`),
  KEY `tenant_id` (`tenant_id`),
  KEY `kiosk_id` (`kiosk_id`),
  CONSTRAINT `websocket_sessions_ibfk_1` FOREIGN KEY (`tenant_id`) REFERENCES `tenants` (`id`) ON DELETE CASCADE,
  CONSTRAINT `websocket_sessions_ibfk_2` FOREIGN KEY (`kiosk_id`) REFERENCES `kiosks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── STRIPE_PROCESSED_EVENTS ───
CREATE TABLE `stripe_processed_events` (
  `event_id` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL,
  `processed_at` timestamp NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`event_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── SEED DATA ───────────────────────────────────────────────────────────────

-- 1. Seed default demo tenant
INSERT INTO tenants (id, name, subdomain, plan, status) VALUES
  ('d4444444-4444-4444-4444-444444444444', 'Demo Restaurant', 'demo', 'starter', 'active');

-- 2. Seed departments (demo tenant)
INSERT INTO departments (tenant_id, name_en, name_ar, icon_path, display_order, active) VALUES
  ('d4444444-4444-4444-4444-444444444444', 'Burgers',  'برجر',    'assets/icons/burgers.svg',  1, TRUE),
  ('d4444444-4444-4444-4444-444444444444', 'Sides',    'مقبلات',  'assets/icons/sides.svg',    2, TRUE),
  ('d4444444-4444-4444-4444-444444444444', 'Drinks',   'مشروبات', 'assets/icons/drinks.svg',   3, TRUE),
  ('d4444444-4444-4444-4444-444444444444', 'Desserts', 'حلويات',  'assets/icons/desserts.svg', 4, TRUE);

-- 3. Seed products (demo tenant)
INSERT INTO products
  (tenant_id, department_id, name_en, name_ar, description_en, description_ar,
   price, ingredients, calories, allergens,
   media_type, media_path, thumbnail_path, available, featured, qr_order_url)
VALUES
-- Burgers (dept 1)
('d4444444-4444-4444-4444-444444444444', 1, 'Holo Classic Burger', 'هولو برجر كلاسيك',
 'Premium double beef patty, aged cheddar, secret smoky sauce, fresh lettuce on a toasted brioche bun.',
 'شريحتين لحم بقري فاخر، جبن شيدر معتق، صلصة مدخنة سرية، خس طازج في خبز بريوش محمص.',
 180.00,
 '["100% Beef Patty","Cheddar Cheese","Secret Sauce","Lettuce","Brioche Bun"]',
 720,
 '["Gluten","Dairy"]',
 'image', 'assets/images/burger.png', 'assets/images/burger_thumb.png',
 TRUE, TRUE, 'https://example.com/order/prod_burger'),

('d4444444-4444-4444-4444-444444444444', 1, 'Neon Smash Burger', 'برجر سماش النيون',
 'Two smashed patties, American cheese, pickles, mustard, crispy onions on a sesame bun.',
 'شريحتان مسحوقتان، جبن أمريكي، مخلل، خردل، بصل مقرمش في خبز سمسم.',
 160.00,
 '["Smash Patties","American Cheese","Pickles","Mustard","Crispy Onions","Sesame Bun"]',
 680,
 '["Gluten","Dairy"]',
 'image', 'assets/images/burger.png', 'assets/images/burger_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_smash'),

-- Sides (dept 2)
('d4444444-4444-4444-4444-444444444444', 2, 'Neon Loaded Fries', 'بطاطس نيون لودد',
 'Crispy golden hand-cut fries loaded with warm cheese sauce, jalapeno slices, and chopped chives.',
 'بطاطس مقرمشة ذهبية مغطاة بصلصة الجبن الدافئة وشرائح الهالبينو والثوم المعمر.',
 95.00,
 '["Hand-cut Fries","Cheese Sauce","Jalapenos","Chives"]',
 480,
 '["Dairy"]',
 'image', 'assets/images/fries.png', 'assets/images/fries_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_fries'),

('d4444444-4444-4444-4444-444444444444', 2, 'Onion Rings', 'حلقات البصل',
 'Golden battered onion rings with smoky dipping sauce.',
 'حلقات بصل مغطاة بالعجينة الذهبية مع صلصة مدخنة للغمس.',
 65.00,
 '["Onion Rings","Batter","Smoky Sauce"]',
 320,
 '["Gluten","Dairy"]',
 'image', 'assets/images/fries.png', 'assets/images/fries_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_rings'),

-- Drinks (dept 3)
('d4444444-4444-4444-4444-444444444444', 3, 'Holographic Blue Mojito', 'موهيتو أزرق هولوغرافي',
 'Refreshing mocktail with blue curaçao, fresh lime juice, crushed mint leaves, and sparkling soda.',
 'موكتيل منعش مع بلو كوراساو وعصير ليمون طازج وأوراق نعناع مهروسة وصودا فوارة.',
 75.00,
 '["Blue Curaçao","Fresh Lime","Mint Leaves","Sparkling Soda"]',
 150, '[]',
 'image', 'assets/images/mojito.png', 'assets/images/mojito_thumb.png',
 TRUE, TRUE, 'https://example.com/order/prod_mojito'),

('d4444444-4444-4444-4444-444444444444', 3, 'Cyber Lemonade', 'عصير الليمون السيبراني',
 'Electric yellow lemonade with a hint of ginger and soda.',
 'عصير ليمون كهربائي أصفر مع لمسة من الزنجبيل والصودا.',
 55.00,
 '["Lemon","Ginger","Soda","Sugar Syrup"]',
 90, '[]',
 'image', 'assets/images/mojito.png', 'assets/images/mojito_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_lemonade'),

-- Desserts (dept 4)
('d4444444-4444-4444-4444-444444444444', 4, 'Cyber Lava Cake', 'كيكة الحمم السيبرانية',
 'Warm chocolate cake with a molten dark chocolate center, dusted with neon pink raspberry powder.',
 'كيكة شوكولاتة دافئة بقلب شوكولاتة داكنة ذائبة مرشوشة ببودرة التوت.',
 110.00,
 '["Belgian Cocoa","Dark Chocolate","Raspberry Dust"]',
 540,
 '["Gluten","Dairy","Eggs"]',
 'image', 'assets/images/cake.png', 'assets/images/cake_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_cake'),

('d4444444-4444-4444-4444-444444444444', 4, 'Galaxy Cheesecake', 'تشيز كيك المجرة',
 'No-bake cheesecake with a galaxy swirl topping of blueberry and blackcurrant.',
 'تشيز كيك بدون خبز مع طبقة علوية بنمط المجرة من التوت الأزرق والكشمش الأسود.',
 95.00,
 '["Cream Cheese","Biscuit Base","Blueberry","Blackcurrant"]',
 420,
 '["Dairy","Gluten"]',
 'image', 'assets/images/cake.png', 'assets/images/cake_thumb.png',
 TRUE, FALSE, 'https://example.com/order/prod_cheesecake');
