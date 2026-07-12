# Master Production-Ready SaaS Implementation Plan

This implementation plan outlines the steps required to transition HoloMenu from its current prototype state into a production-grade, secure, multi-tenant, offline-resilient SaaS platform. 

---

## 1. Strict Scorecard (0–10)

This scorecard evaluates the current repository state and describes what is needed to reach a production-ready score of 9–10.

| # | Scorecard Category | Current Score | Current Evidence | Required to Reach 9–10 |
| :--- | :--- | :---: | :--- | :--- |
| **1** | **Data Integrity / DB Correctness** | **6/10** | Alembic migrations 0001–0005 exist. Unique constraints on `order_items` implemented. Enum validation active in `order_rules.py`. | Sync the initial `holomenu_db.sql` bootstrap script with migrations. Implement transaction scope management at the database connection layer for multi-table updates. |
| **2** | **Multi-Tenant Isolation** | **5/10** | Tenant column added to major tables. Middleware resolves tenant from path, subdomain, and header context. | **Gap**: Add direct `tenant_id` column to `order_items` table. Validate tenant contexts in repository layer queries. Write automated tenant leakage tests. |
| **3** | **Authentication** | **6/10** | JWT endpoints exist for login, refresh, logout. Hashing uses `bcrypt`. | **Gap**: Migrate JWT secret key to runtime configuration, pull from environment variables, and rewrite Git history to scrub exposed secret files. |
| **4** | **Authorization / RBAC** | **6/10** | Server-side role validation using `require_role` in `dependencies.py` restricts cashier, chef, and admin routers. | Implement test cases verifying that invalid JWT roles and cross-tenant context mismatches generate immediate 403 errors. |
| **5** | **API Security** | **5/10** | CORSMiddleware uses settings file lists. slowapi Rate Limiting is instantiated. | Expose input validation controls by enforcing strict Pydantic parsing. Prevent parameter pollution. Harden CORS to reject wildcards in staging and production. |
| **6** | **Secrets / Least Privilege** | **2/10** | DB connection falls back to `root` with no password. `.env` containing keys is tracked in git. | Configure dedicated MySQL credentials `holomenu_app` with restricted privileges. Use a secure secrets manager for cloud hosting and add `.env` to `.gitignore`. |
| **7** | **Reliability** | **5/10** | SSE and database connection pools are defined. Cashier payment crash fixed in migration 0005. | Implement idempotency key checking at the order creation endpoint to prevent duplicate submissions from unstable kiosk networks. |
| **8** | **Observability** | **8/10** | JSON formatted request logger, Sentry logging middleware, Prometheus `/api/metrics` endpoint, and audit logs are fully implemented. | Add trace context parsing to the gesture WebSocket connection. Pipe Sentry alerts to an active developer monitoring workspace. |
| **9** | **Testing** | **0/10** | No automated tests exist in the codebase. | **BLOCKER**: Configure `pytest`. Write unit, integration, and E2E integration tests (specifically targeting multi-tenant data leaks and state transitions). |
| **10** | **Frontend API Client** | **8/10** | Centralized `HoloApi` client implemented in `api-client.js`. All operator HTML pages migrated. Dedicated login page handles auth redirects. | Add client-side session timeout alerts. Standardize dynamic token refreshing on client network requests. |
| **11** | **API Design Quality** | **7/10** | REST routers separated by domains. Proper HTTP status codes used in routers. | Standardize JSON API error structures. Implement pagination parameters on order lists for cashier and admin endpoints. |
| **12** | **Performance** | **6/10** | Database pool size configured between 2 and 10. | Set up indexes on foreign key lookups. Add instrumentation logging for end-to-end gesture-to-UI action latency. |
| **13** | **Scalability** | **5/10** | Stateless backend routing designed. | Add a Redis cache wrapper layer for tenant configuration reads. Implement database replica routing. |
| **14** | **Maintainability** | **7/10** | Monolith split into Clean Architecture layout. Gesture engine separated into modular packages. | Clean up unused imports, obsolete helper functions, and dead debug logs inside backend files. |
| **15** | **Migrations** | **8/10** | Versioned Alembic migrations present in `migrations/versions/`. | Verify migration compatibility inside the CI build using automated rollback tests against local DB environments. |
| **16** | **Deployment** | **0/10** | Missing Dockerfiles and docker-compose deployment environment descriptions. | Create staging and production deployment configurations using multi-stage Docker builds. |
| **17** | **CI / CD** | **0/10** | No CI workflow configurations exist. | Add GitHub Actions checking linters, migrations, and executing pytest suites on PR merges. |
| **18** | **Backup / DR** | **0/10** | No backup scripting or recovery verification targets exist. | Configure automated daily DB snapshot backups with binlog replication to achieve <15m RPO and <2h RTO. |
| **19** | **Dependency Security** | **2/10** | requirements.txt lists outdated packages. No dependency vulnerability scanners. | Run a package security scanner. Upgrade core dependencies to patched versions. |
| **20** | **SaaS Billing Mechanics** | **0/10** | No billing integrations or Stripe webhook handlers exist. | Implement Stripe subscription lifecycle hook processors. Enforce server-side limit checks on active kiosks and products. |
| **21** | **Self-Service Onboarding** | **0/10** | No onboarding routes or default restaurant seed automation script. | Add a signup pipeline resolving tenant details, creating the database workspace, and creating the default admin user. |
| **22** | **Tenant Offboarding** | **0/10** | No data purge pipeline exists. | Create a pipeline enforcing a 30-day soft-delete grace period followed by a permanent, tenant-safe data purge. |
| **23** | **Privacy / Compliance** | **4/10** | Local gesture classification engine ensures webcam frames do not leave the client device memory. | Document the data privacy architecture. Add verification tests ensuring no camera frames are written to local logs or disks. |

---

## 2. Approved SaaS Architecture Decisions

The following structural decisions are established as the technical constraints for this project:

```
[Tenant Subdomain] (mario.holomenu.app) 
        │
        ▼ (Subdomain Resolver Middleware)
[Tenant Slug] (mario) ──► Server Resolves ──► [tenant_id] (42)
                                                 │
                                                 ▼ (Trusted Context)
                                         Scoped Database Queries
```

1.  **Tenant Resolution**: Hybrid model. Dedicated subdomains represent tenant identities (e.g. `mario.holomenu.app` maps to tenant slug `mario`, resolved server-side to a unique `tenant_id`). The trusted `tenant_id` for operator functions must be derived from validated JWT scopes, not untrusted request parameters. Path-based resolution (`/api/t/{slug}/`) remains available for dev environments.
2.  **Gesture Engine Topology**: Local device daemon. Camera frames are processed strictly in-memory on the kiosk hardware via OpenCV/MediaPipe and immediately discarded. Abstract commands (e.g., `swipe_left`, `thumbs_up`) are broadcast over loopback WebSockets (`127.0.0.1:8766`). Tauri is the preferred production framework for wrapping the kiosk interface.
3.  **WebSocket Security**: WebSocket control channels must authenticate using a One-Time Pairing code combined with a Short-Lived Signed Session Token containing tenant, kiosk, device, and session bindings. Command payloads must be validated against strict JSON schemas.
4.  **SaaS Billing Gating**: Gating operates on Starter, Pro, and Enterprise subscription tiers. Limits enforce active kiosk counts, product catalogue sizes, and staff seat allocations. Gating is checked server-side, driven by Stripe webhook events. Grace periods default to 7 days before suspending services.
5.  **Tenant Offboarding**: Enforce a 30-day soft-delete grace period. Upon expiration, a tenant-safe deletion pipeline purges operational data (products, layouts, audits, orders) while preserving minimal anonymized financial history for compliance.
6.  **3D Model Assets**: Objects are uploaded as `.glb` files, stored in Amazon S3 or Cloudflare R2, and delivered via CDN. Pure black rendering backgrounds are controlled at the canvas layer. Asset validation enforces limits on polygon count, texture size (<5MB targets, 15MB hard limit), and Draco/Meshopt compression standards.
7.  **Performance Budgets**: Target end-to-end gesture-to-UI visual latency of <100ms. Database queries must average <50ms (p95), normal REST APIs <150ms, and cached kiosk startups <2s. Idempotency keys are mandatory for all order creation requests.
8.  **Offline Resiliency**: Kiosks function offline using browser Cache Storage, IndexedDB, and a durable client-side database queue. Orders are created with unique tracking codes. Upon reconnection, offline queues synchronize automatically and are validated against server-side idempotency keys.
9.  **Backup & DR Policy**: Database recovery targets are set to **RPO <= 15 minutes** and **RTO <= 2 hours** using daily full snapshots and continuous binlog backups. Restore integrity is tested monthly using an automated sandbox environment.
10. **Geographic & Privacy Compliance**: Raw frames are never written to disk, sent to the cloud, or stored. Only abstract interaction coordinates and events are logged.

---

## 3. Dependency-Aware Roadmap Phases

### Phase 0: Security & Testing Infrastructure (Blockers)

```
                       ┌───────────────────────────┐
                       │   Phase 0: Base Security  │
                       │   - pytest Isolation Tests│
                       │   - Environment Hardening │
                       └─────────────┬─────────────┘
                                     │
                                     ▼
                       ┌───────────────────────────┐
                       │ Phase 1: DB & Model Fixes │
                       │   - order_items tenant_id │
                       │   - Reconcile SQL Bootstrap│
                       └─────────────┬─────────────┘
                                     │
                                     ▼
                       ┌───────────────────────────┐
                       │ Phase 2: WebSocket & Auth │
                       │   - OTP WebSocket Pairing │
                       │   - Tauri App Skeleton    │
                       └───────────────────────────┘
```

*   **Goal**: Close critical security holes, establish verification testing, and resolve database bootstrap inconsistencies.
*   **Exact Problem Solved**:
    1.  Lack of test suites makes it impossible to guarantee that new multi-tenancy changes do not leak data across boundaries.
    2.  Secrets committed to Git history compromise key validation.
    3.  `root` access on MySQL violates the principle of least privilege.
    4.  Initial `holomenu_db.sql` database scripts define different structures than those generated by Alembic migrations.
*   **Files/Modules Affected**:
    *   [backend/.env](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/backend/.env), [backend/.env.example](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/backend/.env.example)
    *   [holomenu_db.sql](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/holomenu_db.sql)
    *   `backend/infrastructure/database/pool.py`
    *   New test suite directories.
*   **New Files to Create**:
    *   `backend/tests/conftest.py` — Configures mock databases, tenant setups, and client fixtures.
    *   `backend/tests/test_tenant_isolation.py` — Verifies that Tenant A cannot read/mutate Tenant B data.
    *   `backend/tests/test_auth_rbac.py` — Asserts permissions based on user JWT roles.
    *   `backend/tests/test_order_lifecycle.py` — Validates order status machine transitions.
*   **Database Migrations**: None in this phase.
*   **API Changes**: None.
*   **Security Changes**:
    *   Scrub Git history of all `.env` credentials using `git-filter-repo` or `BFG Repo-Cleaner`.
    *   Configure `backend/.env` with random `JWT_SECRET_KEY` pulled from environment variables.
    *   Enable MySQL credentials `holomenu_app` with access grants restricted to the `holomenu_db` database.
*   **Tests Required**:
    *   Test setup verifies DB pool instantiation using non-root parameters.
    *   Pytest execution asserting zero cross-tenant leakage.
*   **Acceptance Criteria**:
    *   Pytest runs and executes all isolation tests successfully.
    *   Git tracking for `.env` is removed, and files are ignored.
    *   `holomenu_db.sql` schema structures match the Alembic database state.
*   **Rollback Strategy**: Keep a copy of git history before rewriting. Backup the database using `mysqldump` before changing credentials.
*   **Risks**: Rewriting git history will disrupt local clones. Coordinate development checks.
*   **Dependencies**: MySQL running locally.

---

### Phase 1: Database Tenancy & Correctness Gaps

*   **Goal**: Enforce direct tenant isolation on order items and fix missing parameters.
*   **Exact Problem Solved**:
    1.  The `order_items` table lacks a direct `tenant_id` column. If complex analytics queries are written, developers must join `orders` to filter items by tenant, creating BOLA leakage risk.
    2.  `holomenu_db.sql` bootstrap script is out of sync with Alembic migration histories.
*   **Files/Modules Affected**:
    *   [holomenu_db.sql](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/holomenu_db.sql)
    *   `backend/infrastructure/database/mysql_order_repo.py`
    *   `backend/application/use_cases/orders.py`
*   **New Files to Create**:
    *   `migrations/versions/0006_add_tenant_id_to_order_items.py` — Alembic script to safely add `tenant_id` to `order_items`.
*   **Database Migrations**:
    *   `0006_add_tenant_id_to_order_items.py`: Adds `tenant_id CHAR(36) NOT NULL` column linked to `tenants(id)` on `order_items`. Adds a composite index on `(tenant_id, order_id)`.
*   **API Changes**: None.
*   **Security Changes**:
    *   All raw SQL execution statements inside the order repository query scope are verified to filter by `tenant_id`.
*   **Tests Required**:
    *   Integration test in `backend/tests/test_tenant_isolation.py` asserting that adding items directly to an order returns a tenant mismatch error if the item tenant does not match the order's parent tenant context.
*   **Acceptance Criteria**:
    *   `alembic upgrade head` runs without failure.
    *   Direct queries against `order_items` must include the `tenant_id` column check.
*   **Rollback Strategy**:
    *   `alembic downgrade 0005_add_payments` drops the column safely.
*   **Risks**: Schema updates on existing database records require populating parent `tenant_id` fields first. The migration script must fetch the parent order's `tenant_id` to update existing items before altering the column to `NOT NULL`.
*   **Dependencies**: Phase 0.

---

### Phase 2: WebSocket Transport Security & Kiosk App Skeleton

*   **Goal**: Secure the local gesture WebSocket interface and define the Tauri kiosk container framework.
*   **Exact Problem Solved**:
    1.  The current WebSocket channel allows unauthenticated clients to trigger gestures and command actions.
    2.  Browsers block raw WS connections under standard HTTPS configuration guidelines.
*   **Files/Modules Affected**:
    *   [gesture_engine/transport/websocket_server.py](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/gesture_engine/transport/websocket_server.py)
    *   [gesture_engine/transport/commands.py](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/gesture_engine/transport/commands.py)
    *   [assets/js/websocket-client.js](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/assets/js/websocket-client.js)
*   **New Files to Create**:
    *   `src-tauri/` — Tauri configuration folder to package the kiosk interface locally.
    *   `backend/interface/routers/pairing.py` — API routes to coordinate one-time pairing codes.
*   **Database Migrations**:
    *   `migrations/versions/0007_add_kiosks_and_pairing.py` — Adds `kiosks` (id, tenant_id, name, secret) and `websocket_sessions` (token, tenant_id, kiosk_id, expires_at) tables.
*   **API Changes**:
    *   `POST /api/pairing/request` — Generates a 6-digit short-lived pairing PIN.
    *   `POST /api/pairing/verify` — Validates PIN and returns a WebSocket access token.
*   **Security Changes**:
    *   The local WebSocket handler rejects connections unless an active, signed token is validated.
    *   WebSocket inputs are validated against strict JSON payload schemas to prevent command injection.
*   **Tests Required**:
    *   WebSocket client connection simulation sending invalid/expired tokens, verifying immediate closure.
    *   Malicious command injection tests (e.g. sending commands containing SQL syntax).
*   **Acceptance Criteria**:
    *   Unauthenticated WebSocket connections are rejected.
    *   Kiosk pairing succeeds using the pairing PIN.
*   **Rollback Strategy**: Provide toggles in `config.json` to temporarily disable WebSocket auth for local testing.
*   **Dependencies**: Phase 1.

---

### Phase 3: SaaS Billing, Gating, and Offboarding

```
                       ┌───────────────────────────┐
                       │ Phase 3: SaaS Operations  │
                       │   - Stripe Webhook Process│
                       │   - Limit Gating Logic    │
                       │   - Soft Delete Retention │
                       └─────────────┬─────────────┘
                                     │
                                     ▼
                       ┌───────────────────────────┐
                       │  Phase 4: Resiliency &    │
                       │  Offline Queueing         │
                       │   - IndexedDB Offline Sync│
                       │   - Multi-Stage Docker    │
                       └───────────────────────────┘
```

*   **Goal**: Implement commercial subscription mechanics, gate plans, and automate tenant offboarding data deletion.
*   **Exact Problem Solved**:
    1.  Subscription lifecycles and limits (Starter/Pro/Enterprise) are not checked in the backend.
    2.  Cancelling a tenant leaves orphaned data in the database with no automated purge.
*   **Files/Modules Affected**:
    *   `backend/interface/dependencies.py`
    *   `backend/interface/routers/admin.py`
*   **New Files to Create**:
    *   `backend/interface/routers/billing.py` — Stripe webhook receiver and billing sync endpoints.
    *   `backend/application/use_cases/billing.py` — Subscription status updates and limit checks.
    *   `backend/application/use_cases/offboarding.py` — Deletion scheduler pipeline logic.
    *   `backend/tests/test_billing_gating.py` — Verifies plan limits.
*   **Database Migrations**:
    *   `migrations/versions/0008_add_billing_and_deletion.py` — Adds subscription state logs to `tenants` and maps deletion scheduling dates.
*   **API Changes**:
    *   `POST /api/billing/webhook` — Listens to Stripe events (`customer.subscription.updated`, etc.).
    *   `POST /api/t/{slug}/admin/offboard` — Schedules soft-deletion grace period.
*   **Security Changes**:
    *   Verify Stripe webhook signature using the configured webhook secret.
    *   Mutations on admin routes (e.g. adding products or kiosks) throw a `403 Forbidden` error if the tenant exceeds active subscription limits.
*   **Tests Required**:
    *   Stripe event simulation testing: verify that payment failures transition a tenant's state to `past_due` and suspend features after 7 days.
    *   Soft-delete tests: verify that a scheduled purge deletes operational records but retains minimal required invoices.
*   **Acceptance Criteria**:
    *   Webhooks update the tenant status in the DB.
    *   Admin requests to add products past plan limits are blocked.
*   **Rollback Strategy**: Backup current tenant records before upgrading the database schema.
*   **Dependencies**: Phase 2.

---

### Phase 4: Resiliency, Offline Mode, & Deployment

*   **Goal**: Make the Customer Kiosk capable of offline browsing and order caching, and containerize the environment.
*   **Exact Problem Solved**:
    1.  Network cuts instantly disable the customer kiosk ordering flow.
    2.  Local development lacks a containerized setup to ensure identical execution environments in staging and production.
*   **Files/Modules Affected**:
    *   [index.html](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/index.html), [app.js](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/app.js)
    *   [assets/js/api-client.js](file:///c:/Users/DELL/.gemini/antigravity/scratch/HoloMenu/assets/js/api-client.js)
*   **New Files to Create**:
    *   `Dockerfile` — Multi-stage non-root Python runner build.
    *   `docker-compose.yml` — Container environment setup (backend, MySQL, Redis).
    *   `assets/js/service-worker.js` — Offline cache manager.
    *   `assets/js/offline-db.js` — IndexedDB client order queue manager.
*   **Database Migrations**: None.
*   **API Changes**:
    *   `POST /api/orders` endpoints updated to require and validate an `Idempotency-Key` header.
*   **Security Changes**:
    *   Verify that API endpoints reject duplicate orders using the idempotency key check.
*   **Tests Required**:
    *   Simulate kiosk network disconnects: verify the menu remains browsable and offline orders are stored.
    *   Simulate reconnection: verify that duplicate order syncs are rejected by the server using the idempotency key.
*   **Acceptance Criteria**:
    *   `docker-compose up` builds and starts all services.
    *   Kiosk orders flow and synchronize without creating duplicates during network changes.
*   **Rollback Strategy**: The offline script fallback disables the local DB queue if IndexedDB is not supported by the browser.
*   **Dependencies**: Phase 3.

---

### Phase 5: Backup Verification & Disaster Recovery

*   **Goal**: Implement transaction logging, point-in-time recovery configurations, and automated recovery tests to hit RPO/RTO targets.
*   **Exact Problem Solved**:
    1.  Lack of automated backup validation risks data loss during database failures.
*   **Files/Modules Affected**:
    *   `backend/infrastructure/database/pool.py`
*   **New Files to Create**:
    *   `scripts/backup_db.ps1` — Automated daily database dump and transaction log sync script.
    *   `scripts/restore_db.ps1` — Restore script validating data integrity.
*   **Database Migrations**: None.
*   **API Changes**: None.
*   **Security Changes**:
    *   Backup archives are encrypted (AES-256) before upload to secondary storage.
*   **Tests Required**:
    *   Automated sandbox recovery testing: spin up a separate database container, restore the backup, and assert that all tables are intact and tenant isolation holds.
*   **Acceptance Criteria**:
    *   The restore script successfully spins up a mock DB and validates database integrity.
    *   RPO/RTO metrics are verified (RPO <= 15 minutes, RTO <= 2 hours).
*   **Rollback Strategy**: Retain backup logs and keep secondary regions active during recoveries.
*   **Dependencies**: Phase 4.

---

## 4. Execution Order & Complexity Matrix

Tasks are ordered strictly by dependency, ensuring security and stability are addressed before commercialization.

```
P0 (Prod Blockers) ──────► P1 (Pre-Customer Required) ──────► P2 (Post-Launch)
  - Security Fixes           - Stripe Billing Integration      - DR / Failovers
  - Pytest Suite             - Offline Resiliency              - Advanced Metrics
  - DB Schema Sync           - Offboarding Pipeline
```

| Task ID | Component / Area | Description | Priority | Complexity | Risk | Dependencies |
| :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| **A.1** | Secrets & Credentials | Remove secrets from git, set up env variables, and configure MySQL `holomenu_app` user. | **P0** | Low | Low | None |
| **A.2** | Schema Integrity | Sync `holomenu_db.sql` bootstrap script with migrations. | **P0** | Low | Medium | None |
| **A.3** | Pytest Framework | Initialize `conftest.py` and write tenant isolation and RBAC test suites. | **P0** | Medium | Low | A.1, A.2 |
| **A.4** | Database Model | Add direct `tenant_id` to `order_items` table and update database queries. | **P0** | Medium | Medium | A.3 |
| **B.1** | WebSocket Security | Implement One-Time Pairing and Session Token authentication for the gesture engine. | **P0** | High | High | A.4 |
| **B.2** | Kiosk Packaging | Initialize Tauri kiosk container framework wrapper. | **P1** | Medium | Low | B.1 |
| **C.1** | Billing webhook | Create Stripe webhook handler and manage subscription status. | **P1** | Medium | Medium | A.4 |
| **C.2** | Plan Gating | Implement backend validation for kiosk and product limits. | **P1** | Low | Low | C.1 |
| **C.3** | Soft-Delete Purge | Implement the 30-day soft-delete grace period and data purge pipeline. | **P1** | Medium | Medium | A.4, C.2 |
| **D.1** | Containerization | Write Dockerfiles and `docker-compose.yml` configurations. | **P1** | Low | Low | B.2 |
| **D.2** | Offline Resiliency | Implement IndexedDB local caching and automatic order synchronization. | **P1** | High | High | D.1 |
| **D.3** | Backup & DR | Write database dump and recovery scripts, and configure binlog backups. | **P2** | Medium | Medium | D.1 |

---

## 5. Unified Test Matrix

This matrix defines the required roles, tenants, credentials, and error conditions to verify before claiming production readiness.

| Test Case ID | Role | Tenant | Authentication State | Failure Mode / Scenario | Expected Outcome |
| :--- | :--- | :---: | :--- | :--- | :--- |
| **T-ISO-01** | Kiosk | Tenant A | Public (Unauthenticated) | Read Tenant B Product catalogue | **404 Not Found** / Access Blocked |
| **T-ISO-02** | Chef | Tenant A | Authenticated (JWT) | Access Tenant B order list | **403 Forbidden** (Tenant context mismatch) |
| **T-ISO-03** | Cashier | Tenant A | Authenticated (JWT) | Cancel Tenant B order | **403 Forbidden** (Tenant context mismatch) |
| **T-ATH-01** | Admin | Tenant A | Expired token | Add new product to catalogue | **401 Unauthorized** (Token has expired) |
| **T-ATH-02** | Chef | Tenant A | Revoked token | Update order status to cooking | **401 Unauthorized** |
| **T-ATH-03** | Cashier | Tenant A | Invalid Role (Chef JWT) | Process order cash payment | **403 Forbidden** |
| **T-WS-01** | Kiosk | Tenant A | Missing socket token | Connect to WebSocket server | Connection rejected (Immediate disconnect) |
| **T-WS-02** | Kiosk | Tenant A | Expired token | Send gesture interaction command | Connection closed (Token expired) |
| **T-WS-03** | Kiosk | Tenant A | Valid Auth | Send malformed JSON command | Payload rejected (Message malformed) |
| **T-RES-01** | Kiosk | Tenant A | Offline | Submit order during network disconnect | Order queued locally, UI stays interactive |
| **T-RES-02** | Kiosk | Tenant A | Reconnected | Sync order (Server duplicate request) | Order created exactly once via idempotency key |
| **T-BIL-01** | Admin | Tenant A | Active subscription | Add product past limit threshold | Request blocked (Upgrade subscription) |
| **T-BIL-02** | Admin | Tenant A | Suspended | Load operator interfaces | Access restricted page displayed |
| **T-BIL-03** | System | Tenant A | Webhook duplicate | Process identical Stripe hook event | Event ignored (Idempotent webhook handler) |

---

## 6. Threat Model

| Threat Description | Likelihood | Impact | Current Protection | Missing Protection | Mitigation | Required Test |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Cross-Tenant Leakage (BOLA/IDOR)** | High | Critical | Tenant queries isolated by route logic checks. | Direct `tenant_id` check is missing on the `order_items` table. | Add `tenant_id` to `order_items` and validate it in all SQL statements. | `test_tenant_isolation.py` (Assert Tenant A query for Tenant B item returns 404). |
| **Exposure of Production Credentials** | High | Critical | None. `.env` containing keys is committed to Git. | Git history is not cleaned. `.env` is tracked. | Rewrite Git history, move secrets to environment variables, and add to `.gitignore`. | Git audit sweep checking for tracked credentials files. |
| **Unauthorized Kiosk Command Injection** | Medium | High | None. WebSocket channel accepts connections globally. | Token validation and local loopback binding checks are missing. | Bind WS server to `127.0.0.1`. Require pairing validation using session tokens. | Simulation script attempting to connect to WebSocket without pairing. |
| **Kiosk Denial of Service / Network Failure** | High | Medium | None. Kiosk crashes if REST API connection fails. | Local storage caching and synchronization logic are missing. | Implement IndexedDB client-side database queue caching. | Disconnect ethernet cable, complete transaction locally, verify auto-sync on reconnect. |
| **Duplicate Payments / Double Order Submissions** | High | High | None. Duplicate requests create multiple orders. | Idempotency keys are missing on order creation endpoints. | Require and validate `Idempotency-Key` headers on backend endpoints. | Send duplicate API requests with the same transaction key concurrently. |

---

## 7. Production Readiness Checklist

This checklist requires verified evidence before production deployment.

*   [ ] **Credentials & Secrets Hardening**
    *   *Required Evidence*: Output of git scan verifying zero tracked `.env` or credential files. Verification that `main.py` connects to MySQL using the restricted `holomenu_app` user.
*   [ ] **Database Schema Synchronized**
    *   *Required Evidence*: Verification that `alembic upgrade head` runs against a blank database and generates a schema identical to `holomenu_db.sql`.
*   [ ] **Multi-Tenant Isolation Verification**
    *   *Required Evidence*: Test run log output of `test_tenant_isolation.py` showing all isolation tests passing.
*   [ ] **WebSocket Control Channel Authenticated**
    *   *Required Evidence*: Test script logs showing connection rejection for unauthenticated WebSocket requests.
*   [ ] **Stripe Hook Processing Operational**
    *   *Required Evidence*: Automated billing test runs simulating Stripe webhooks updating tenant status from `active` to `suspended`.
*   [ ] **Kiosk Offline Resiliency Verified**
    *   *Required Evidence*: Kiosk UI execution log showing offline order creation, database queue caching, and successful synchronization upon network recovery.
*   [ ] **Database Backup Configuration Confirmed**
    *   *Required Evidence*: Daily backup scripts configured, and restore verification test logs demonstrating recovery under the 2-hour RTO limit.

---

## 8. Definition of Done (DoD)

A release is considered done and production-ready only when it meets the following measurable criteria:

1.  **Zero Known Security Blockers**: No active credentials or keys exist in the Git history, wildcard CORS settings are disabled in staging/production, and the database connects using least-privilege credentials.
2.  **Schema Consistency**: Alembic migrations run successfully against new database instances, generating schemas consistent with `holomenu_db.sql`.
3.  **Automated Test Parity**: The pytest suite runs and passes (100% success rate), covering tenant isolation, RBAC role permissions, and order lifecycle status transitions.
4.  **WebSocket Authentication Enforced**: All gesture engine WebSocket sessions require pairing verification and signed token validations.
5.  **Offline Resiliency Verified**: Kiosk menu browsing and local database order queuing function during network cuts, and synchronize without duplicate entries upon reconnection.
6.  **Disaster Recovery Confirmed**: Automated backup restore tests run successfully, confirming database recovery in under 2 hours (RTO) with less than 15 minutes of transactional data loss (RPO).
7.  **CI Build Verification**: Linters, packaging configurations, and migrations run automatically and pass on every pull request merged to the main branch.
