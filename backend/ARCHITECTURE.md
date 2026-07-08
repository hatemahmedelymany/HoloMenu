# HoloMenu Backend Clean Architecture Reference Guide

This document defines the architectural patterns, layout layers, and codebase conventions introduced during the backend restructuring.

---

## Architectural Layers

The HoloMenu backend conforms to a classic 4-layer Clean Architecture structure:

```
┌─────────────────────────────────────────────────────────┐
│                       INTERFACE                         │
│ (FastAPI Router Handlers, Middleware, DI setup/wiring)  │
└───────────┬─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│                      APPLICATION                        │
│ (Use Cases / Service orchestrators & Repo Interfaces)   │
└───────────┬─────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│                        DOMAIN                           │
│ (Core business rules, entities, transitions - NO framework)│
└─────────────────────────────────────────────────────────┘
            ▲
            │
┌───────────┴─────────────────────────────────────────────┐
│                     INFRASTRUCTURE                      │
│ (MySQL Repos, Sentry, Prometheus, Logging, settings.py) │
└─────────────────────────────────────────────────────────┘
```

### 1. `domain/`
* **Purpose**: Core business entities and rules.
* **Rules**: Zero external/framework dependencies (no FastAPI, no Pydantic, no SQL library imports).
* **Key Components**:
  * `domain/order_rules.py`: Hard transitions of status (`assert_valid_transition`).

### 2. `application/`
* **Purpose**: Orchestrates and coordinates use cases. Defines abstract interface boundaries for data access.
* **Rules**: Imports `domain` but is entirely decoupled from MySQL query execution and FastAPI dependencies.
* **Key Components**:
  * `application/interfaces/`: Abstract repository contracts (`OrderRepository`, `ProductRepository`, `AuditRepository`, etc.).
  * `application/use_cases/`: Orchestrator logic coordinating validations, repo writes, and audit logs.

### 3. `infrastructure/`
* **Purpose**: Concrete implementations of input/output boundaries (telemetry, repositories, event emitters).
* **Rules**: Integrates external technologies (aiomysql, Sentry, Prometheus).
* **Key Components**:
  * `infrastructure/database/`: Concrete MySQL classes implementation matching repository protocols.
  * `infrastructure/security/`: Hashing and error logging.
  * `infrastructure/logging/`: Structured JSON logging engine.
  * `infrastructure/monitoring/`: Prometheus instrumentation coordinates.

### 4. `interface/`
* **Purpose**: Handlers capturing network requests, resolving tenants, and dispatching parameters to the Use Cases.
* **Key Components**:
  * `interface/routers/`: Segmented endpoints (orders, cashier, chef, admin, analytics).
  * `interface/dependencies.py`: Role-based security checks and cookie processing context.

---

## Data Access & Dependency Injection (DI)

Repositories receive an active database connection context injected via FastAPI dependencies:

```python
# interface/routers/admin.py example
@router.get("/api/admin/orders")
async def get_admin_orders(
    tenant_id: str = Depends(get_current_tenant_id),
    conn=Depends(get_db_conn),
):
    order_repo = MysqlOrderRepo(conn)
    use_cases = AdminUseCases(order_repo)
    return await use_cases.get_admin_orders(tenant_id)
```

---

## Regression Verification

All code edits must be validated against the captured baseline suite to ensure no behavior changes occur:
```bash
# Start backend server
python -m uvicorn backend.main:app --port 8081

# In another terminal, run baseline check
python scripts/capture_baseline.py --verify
```
