# HoloMenu → 10/10 SaaS Readiness Plan

**Goal:** take HoloMenu from a 4.2–4.9/10 functional prototype to a genuinely production-grade, multi-tenant, secure, commercially deployable SaaS product.

**How to use this document:** each phase is ordered by dependency — later phases assume earlier ones are done. Do not skip Phase 0. A schema you can't trust makes every later investment (auth, tests, billing) worthless, because it's all built on top of a data model that can silently misrepresent reality.

**Scoring logic:** each phase lists which scorecard category it moves and roughly how much. By the end of Phase 6, every category in the original report should be justifiably at 9–10/10.

---

## Phase 0 — Fix the Data Model (Foundation, do this first)

**Fixes: Database Correctness 3→9, Reliability 3→7, Backend Quality 5→7**

This is the single highest-leverage fix in the entire plan. Nothing else matters until the backend and schema agree on what an order *is*.

### 0.1 Reconcile the order status lifecycle

Pick ONE canonical lifecycle. Recommended (covers both what the SQL had and what the backend actually uses):

```sql
CREATE TABLE orders (
  ...
  status ENUM(
    'pending',       -- order created, not yet confirmed
    'confirmed',     -- customer confirmed, sent to kitchen
    'cooking',       -- chef accepted, in progress
    'ready',         -- food ready, awaiting pickup/payment
    'completed',     -- paid and handed over
    'cancelled',     -- cancelled before completion
    'expired'        -- abandoned/timed out at kiosk
  ) NOT NULL DEFAULT 'pending',
  ...
);
```

Action items:
- [ ] Audit every place in `backend/main.py` that reads or writes `orders.status`. Build a table: endpoint → status values used.
- [ ] Rewrite the enum above as a single migration (see Phase 0.3 for migration tooling).
- [ ] Add a status transition table in code (not just a raw string field) so illegal transitions are rejected at the application layer, e.g. `cancelled → cooking` should be impossible:

```python
VALID_TRANSITIONS = {
    "pending":   {"confirmed", "cancelled", "expired"},
    "confirmed": {"cooking", "cancelled"},
    "cooking":   {"ready", "cancelled"},
    "ready":     {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "expired":   set(),
}

def assert_valid_transition(current: str, new: str):
    if new not in VALID_TRANSITIONS.get(current, set()):
        raise HTTPException(409, f"Cannot move order from {current} to {new}")
```

### 0.2 Fix the `order_items` upsert bug

- [ ] Add the missing unique constraint the code assumes exists:

```sql
ALTER TABLE order_items
  ADD CONSTRAINT uq_order_product UNIQUE (order_id, product_id);
```

- [ ] Re-test the `ON DUPLICATE KEY UPDATE` path after this — confirm quantity increments correctly instead of creating duplicate rows.
- [ ] Add a DB-level `CHECK` (or app-level validation) that `quantity > 0`.

### 0.3 Introduce real migration tooling

Stop hand-editing a single `.sql` file. Use **Alembic** (you already used it in the VFR backend — reuse that pattern here).

- [ ] `pip install alembic`
- [ ] `alembic init migrations`
- [ ] Convert `holomenu_db.sql` into an initial migration (`alembic revision --autogenerate -m "initial schema"`)
- [ ] Every future schema change = a new migration file, committed to git, reviewed like code.
- [ ] Add a `alembic upgrade head` step to your deployment pipeline (Phase 5).

### 0.4 Add referential integrity everywhere it's implied but not enforced

- [ ] Foreign keys on `order_items.order_id → orders.id` and `order_items.product_id → products.id` with `ON DELETE RESTRICT` (don't let a product deletion silently orphan historical orders).
- [ ] `NOT NULL` constraints audited on every column the backend assumes is always present.
- [ ] Add `created_at` / `updated_at` timestamps (with `ON UPDATE CURRENT_TIMESTAMP`) to every table — you'll need these for auditing (Phase 2) and analytics.

**Exit criteria for Phase 0:** you can run the full order lifecycle (create → cook → ready → pay → complete) end-to-end without a single manual DB fix, and a bad transition throws a clean 409, not a silent write.

---

## Phase 1 — Multi-Tenancy (the actual "SaaS" part)

**Fixes: SaaS Readiness 2→8**

Right now HoloMenu is a single-restaurant app. SaaS means many restaurants, one codebase, isolated data.

### 1.1 Add a tenant model

```sql
CREATE TABLE tenants (
  id CHAR(36) PRIMARY KEY DEFAULT (UUID()),
  name VARCHAR(255) NOT NULL,
  subdomain VARCHAR(63) UNIQUE NOT NULL,   -- e.g. mario-pizza.holomenu.app
  plan ENUM('trial','starter','pro','enterprise') NOT NULL DEFAULT 'trial',
  status ENUM('active','suspended','cancelled') NOT NULL DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- [ ] Add `tenant_id CHAR(36) NOT NULL REFERENCES tenants(id)` to **every** existing table: `departments`, `products`, `orders`, `order_items`, `admins`, `analytics_events`.
- [ ] Add a composite index on `(tenant_id, <primary lookup column>)` for every hot table, e.g. `(tenant_id, status)` on `orders`.

### 1.2 Enforce tenant isolation at the query layer, not just by convention

The most common SaaS security bug is "developer forgot the `WHERE tenant_id = ?`" on one query. Fix this structurally:

- [ ] Build a single `get_db_session(tenant_id)` dependency in FastAPI that every route depends on.
- [ ] Wrap all repository/query functions so `tenant_id` is a **required positional argument**, never optional, never inferred from a header the client controls without verification.
- [ ] Resolve `tenant_id` server-side from the authenticated session/token (Phase 2) — **never** trust a `tenant_id` passed directly in the request body or query string.
- [ ] Add an automated test (Phase 4) that asserts: authenticated as Tenant A, querying Tenant B's order ID returns 404, not the order.

### 1.3 Resolve tenant from subdomain or path

- [ ] Decide the routing strategy: subdomain (`mario-pizza.holomenu.app`) is cleaner for SaaS branding; path prefix (`/t/mario-pizza/...`) is faster to ship. Recommend starting path-based, migrating to subdomain once you have paying customers.
- [ ] Add FastAPI middleware that extracts tenant identity early in the request lifecycle and attaches it to `request.state.tenant_id`.

**Exit criteria for Phase 1:** two different restaurants can use HoloMenu simultaneously with zero data leakage between them, provably (via the isolation test above).

---

## Phase 2 — Authentication & Authorization

**Fixes: Security 1→8, SaaS Readiness (contributes further)**

### 2.1 Real auth system

- [ ] Implement JWT-based auth (you already have this pattern from the VFR FastAPI backend — port it over).
- [ ] Password hashing with `bcrypt` or `argon2` — never plaintext, never reversible encryption.
- [ ] `POST /auth/login` → issues short-lived access token (15 min) + longer-lived refresh token (7 days), refresh token stored `httpOnly` cookie.
- [ ] `POST /auth/refresh`, `POST /auth/logout` (with refresh token revocation list in Redis or DB).

### 2.2 Role-based access control (RBAC)

- [ ] Roles: `owner`, `admin`, `chef`, `cashier`, `kiosk` (kiosk = unauthenticated/public read-only for menu browsing, everything else requires auth).
- [ ] Each JWT carries `tenant_id`, `user_id`, `role`.
- [ ] FastAPI dependency for role enforcement:

```python
def require_role(*allowed_roles):
    def checker(user: AuthedUser = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(403, "Insufficient permissions")
        return user
    return checker

@app.post("/api/orders/{order_id}/status")
def update_status(order_id: str, user=Depends(require_role("chef","admin","owner"))):
    ...
```

- [ ] Apply this to **every** mutating endpoint — admin CRUD, chef status updates, cashier payment completion. No exceptions.

### 2.3 Least-privilege database access

- [ ] Stop using `root` with an empty password (report flagged this — it's the single worst line in the current config).
- [ ] Create a dedicated MySQL user for the app with grants scoped only to the HoloMenu database, no `GRANT OPTION`, no `SUPER`.
- [ ] Separate read replica credentials for analytics queries if/when you scale (not urgent now, but design the `.env` structure to support it later).
- [ ] Move all secrets out of `.env` committed to git — use a `.env.example` with placeholders, real `.env` in `.gitignore`, production secrets in a proper secret manager (AWS Secrets Manager / Doppler / Vault — pick one in Phase 5).

### 2.4 API hardening

- [ ] CORS: explicit allow-list of origins per tenant subdomain, not `*`.
- [ ] Rate limiting: `slowapi` (FastAPI-compatible) — e.g. 100 req/min per IP on public kiosk endpoints, 20 req/min on auth endpoints to blunt brute force.
- [ ] Input validation via Pydantic models on every request body — reject unknown fields (`model_config = ConfigDict(extra="forbid")`).
- [ ] Add security headers middleware (`X-Content-Type-Options`, `X-Frame-Options`, `Content-Security-Policy`).

**Exit criteria for Phase 2:** every non-public endpoint requires a valid, role-checked token; a captured kiosk request cannot mutate admin data; `root`/blank password no longer exists anywhere.

---

## Phase 3 — Auditability & Observability

**Fixes: Reliability 7→9, Security (further), SaaS Readiness (further)**

### 3.1 Audit trail

- [ ] `audit_log` table: `tenant_id, user_id, action, entity_type, entity_id, before_state (JSON), after_state (JSON), created_at`.
- [ ] Write to it on every status change, every admin CRUD mutation, every login.
- [ ] This alone answers "who changed this price / who cancelled this order" — a hard SaaS requirement once real money is involved.

### 3.2 Structured logging

- [ ] Replace any `print()` debugging with structured logging (`structlog` or Python's `logging` with JSON formatter).
- [ ] Log every request with `tenant_id`, `user_id`, `route`, `status_code`, `latency_ms`.
- [ ] Ship logs somewhere queryable in production (see Phase 5 — even a hosted log service like Better Stack or a self-hosted Loki stack is fine to start).

### 3.3 Application monitoring

- [ ] Add a `/health` endpoint that checks DB connectivity, not just "process is alive."
- [ ] Add basic metrics: request count, error rate, p95 latency per endpoint (Prometheus + Grafana, or a hosted alternative like Sentry for errors + a simple uptime monitor to start).
- [ ] Error tracking via Sentry (free tier is enough at this stage) — wire it into FastAPI exception handlers so every unhandled 500 is captured with tenant/user context.

**Exit criteria for Phase 3:** you can answer "what happened to order #4521 and who touched it" from the audit log alone, and you get alerted before a customer has to tell you something is broken.

---

## Phase 4 — Testing

**Fixes: Reliability 9→10, Maintainability 5→8**

### 4.1 Test pyramid

- [ ] **Unit tests** (pytest): status transition validator, price calculations, tenant isolation helper functions. Target: every pure function with business logic.
- [ ] **Integration tests**: spin up a test MySQL (via `testcontainers` or a dockerized test DB), hit real endpoints, assert real DB state changes. Cover the full order lifecycle happy path + every illegal transition.
- [ ] **Tenant isolation tests** (critical, see Phase 1.2): assert cross-tenant data access is always blocked.
- [ ] **Auth tests**: expired token rejected, wrong role rejected, refresh flow works, revoked token rejected.

### 4.2 CI enforcement

- [ ] GitHub Actions workflow: on every PR, run `pytest`, run `alembic upgrade head` against a throwaway DB to catch broken migrations, run a linter (`ruff`).
- [ ] Block merge if tests fail or coverage drops below a threshold (start at something achievable like 60%, raise over time).

### 4.3 Frontend smoke tests

- [ ] Even basic Playwright/Cypress smoke tests for the 4 HTML surfaces: kiosk order flow completes, chef can transition status, cashier can complete payment, admin CRUD works. Doesn't need to be exhaustive — needs to catch "I broke the build" before a customer does.

**Exit criteria for Phase 4:** CI blocks any change that breaks the order lifecycle, auth, or tenant isolation, without you having to manually click through the app every time.

---

## Phase 5 — Deployment & Infrastructure

**Fixes: Deployment Readiness 2→9**

### 5.1 Containerize everything

- [ ] `Dockerfile` for the FastAPI backend (multi-stage build, non-root user inside the container).
- [ ] `docker-compose.yml` for local dev (app + MySQL + Redis).
- [ ] Never run the app as `root` inside the container either.

### 5.2 Environment separation

- [ ] Three real environments: `local`, `staging`, `production` — each with its own DB, its own secrets, no shared credentials.
- [ ] Staging is a mandatory gate: nothing reaches production without passing through staging first.

### 5.3 CI/CD pipeline

- [ ] On merge to `main`: build image → run migrations against staging → deploy to staging → run smoke tests → manual approval gate → deploy to production.
- [ ] Rollback plan: keep the previous image tagged and deployable within one command; migrations should be written to be backward-compatible for at least one release (additive changes first, destructive changes in a follow-up release).

### 5.4 Hosting decision

Pick one path based on your budget/skill, don't over-engineer this early:
- **Simplest**: Railway or Render — managed MySQL + managed app hosting, minimal ops overhead, good for first paying customers.
- **More control**: a single VPS (DigitalOcean/Hetzner) running docker-compose behind Caddy/Nginx with automatic TLS.
- **Scale-later**: AWS (RDS + ECS/Fargate) once you have real multi-tenant load — don't start here, it's overkill for customer #1–10.

### 5.5 Backups & disaster recovery

- [ ] Automated daily DB backups with at least 7-day retention.
- [ ] Documented, *tested* restore procedure — a backup you've never restored from is not a backup.
- [ ] Point-in-time recovery if your hosting supports it (RDS does; a raw VPS needs binlog-based PITR set up manually).

**Exit criteria for Phase 5:** a new schema change goes from your laptop to production through an automated, reviewed, rollback-capable pipeline — no manual SSH-and-pray deploys.

---

## Phase 6 — Commercial SaaS Mechanics

**Fixes: SaaS Readiness 8→10 (the final stretch — this is what makes it *sellable*, not just *safe*)**

### 6.1 Billing & subscription management

- [ ] Integrate Stripe (Billing + Subscriptions): plans tied to the `tenants.plan` field from Phase 1.1.
- [ ] Webhook handler for `invoice.paid`, `invoice.payment_failed`, `customer.subscription.deleted` → update `tenants.status` accordingly (auto-suspend on failed payment after a grace period).
- [ ] Usage-based gating if relevant (e.g. order volume limits per plan tier) enforced at the API layer, not just in the UI.

### 6.2 Onboarding flow

- [ ] Self-serve tenant signup: create tenant → create owner admin account → seed default departments/products → redirect to admin dashboard. This replaces you manually setting up each restaurant.
- [ ] Email verification on signup (prevents throwaway/abuse accounts).

### 6.3 Tenant-facing settings & branding

- [ ] Let each tenant set their own logo, color theme (you already have design-system experience from the VFR project — reuse that instinct here), and business hours.
- [ ] Custom subdomain confirmation step if using subdomain routing (Phase 1.3).

### 6.4 Support & SLA basics

- [ ] A status page (even a simple one — see instatus.com or a self-hosted Cachet) so tenants can check if there's an outage without emailing you.
- [ ] A documented support channel and response-time expectation, even if informal at first (e.g. "support@..., we respond within 24h").
- [ ] Terms of Service + Privacy Policy — required before you can legally take paying customers' data, especially with EU/GCC customers if you expand there.

### 6.5 Data export & tenant offboarding

- [ ] A tenant can export their order history / product catalog (CSV/JSON) — required for trust, and often for legal compliance if a customer leaves.
- [ ] A clean tenant deletion path that actually removes/anonymizes their data, not just flips a `status` flag silently forever.

**Exit criteria for Phase 6:** a stranger can find HoloMenu, sign up, pay, configure their restaurant, and start taking orders — without you personally doing anything — and if their card fails, the system handles it gracefully instead of breaking silently.

---

## Suggested Execution Order (realistic solo-dev timeline)

| Phase | Focus | Rough effort (solo, part-time) |
|---|---|---|
| 0 | Data model fix | 3–5 days |
| 1 | Multi-tenancy | 1–2 weeks |
| 2 | Auth/RBAC/security | 1–2 weeks |
| 3 | Audit/observability | 3–5 days |
| 4 | Testing | 1 week (ongoing after) |
| 5 | Deployment/infra | 1 week |
| 6 | Billing/commercial | 1–2 weeks |

**Total to a genuine 10/10 SaaS product: roughly 6–10 weeks of focused solo work**, assuming Phase 0–2 aren't skipped or rushed — they're the load-bearing walls everything else stands on.

## Final Scorecard After Full Plan

| Area | Before | After |
|---|---|---|
| Product Vision | 7/10 | 8/10 (unchanged by this plan — needs product work, not engineering) |
| UX/UI | 7/10 | 8/10 |
| Backend Quality | 5/10 | 9/10 |
| Database Correctness | 3/10 | 10/10 |
| Security | 1/10 | 9/10 |
| Reliability | 3/10 | 9/10 |
| Maintainability | 5/10 | 9/10 |
| Deployment Readiness | 2/10 | 9/10 |
| SaaS Readiness | 2/10 | 10/10 |

**Overall: 4.2/10 → 9.1/10**, with SaaS Readiness specifically hitting **10/10** — the rest can't perfectly hit 10 without also improving product-level UX polish and vision execution, which is a design/product exercise, not an engineering one.
