"""
Baseline Capture Script for HoloMenu Clean Architecture Refactor.

Hits every endpoint in main.py (happy + error paths) and saves
response status codes and bodies to baseline/responses.json.

Usage:
    1. Start the server:  uvicorn backend.main:app --host 127.0.0.1 --port 8081
    2. Run this script:   python scripts/capture_baseline.py
    3. To verify after a refactor step:
       python scripts/capture_baseline.py --verify
"""
import argparse
import json
import os
import sys
import time
import httpx

BASE = "http://127.0.0.1:8081"
TENANT = "demo"
HEADERS = {"X-Tenant": TENANT}
BASELINE_DIR = os.path.join(os.path.dirname(__file__), "..", "baseline")
BASELINE_FILE = os.path.join(BASELINE_DIR, "responses.json")


def _serialize_body(resp):
    """Return JSON body if parseable, else raw text."""
    try:
        return resp.json()
    except Exception:
        return resp.text[:500]


def capture_endpoint(client, method, path, **kwargs):
    """Hit one endpoint and return a result dict."""
    url = f"{BASE}{path}"
    headers = {**HEADERS, **kwargs.pop("headers", {})}
    try:
        resp = client.request(method, url, headers=headers, timeout=10, **kwargs)
        return {
            "method": method,
            "path": path,
            "status_code": resp.status_code,
            "body": _serialize_body(resp),
        }
    except Exception as e:
        return {
            "method": method,
            "path": path,
            "status_code": -1,
            "body": f"CONNECTION ERROR: {e}",
        }


def login(client):
    """Login as admin and return access token."""
    resp = client.post(
        f"{BASE}/api/auth/login",
        headers=HEADERS,
        json={"username": "admin", "password": "admin123"},
        timeout=10,
    )
    if resp.status_code == 200:
        data = resp.json()
        return data.get("access_token")
    return None


def run_all(client, token=None):
    """Run every endpoint test case. Returns list of result dicts."""
    results = []
    auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

    # ── Health ──
    results.append(capture_endpoint(client, "GET", "/api/health"))
    results.append(capture_endpoint(client, "GET", "/api/metrics"))

    # ── Auth: happy path ──
    results.append(capture_endpoint(
        client, "POST", "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    ))
    # Auth: wrong password
    results.append(capture_endpoint(
        client, "POST", "/api/auth/login",
        json={"username": "admin", "password": "wrongpass"},
    ))
    # Auth: missing fields
    results.append(capture_endpoint(
        client, "POST", "/api/auth/login",
        json={"username": "admin"},
    ))
    # Auth: extra fields (should be rejected by extra=forbid)
    results.append(capture_endpoint(
        client, "POST", "/api/auth/login",
        json={"username": "admin", "password": "admin123", "extra": "bad"},
    ))

    # ── Departments (public) ──
    results.append(capture_endpoint(client, "GET", "/api/departments"))
    results.append(capture_endpoint(client, "GET", "/api/departments/1/products"))
    results.append(capture_endpoint(client, "GET", "/api/departments/99999/products"))

    # ── Products (public) ──
    results.append(capture_endpoint(client, "GET", "/api/products/1"))
    results.append(capture_endpoint(client, "GET", "/api/products/99999"))  # 404

    # ── Orders: full lifecycle ──
    # Create order
    create_resp = capture_endpoint(client, "POST", "/api/orders")
    results.append(create_resp)

    order_uid = None
    if create_resp["status_code"] == 201 and isinstance(create_resp["body"], dict):
        order_uid = create_resp["body"].get("order_uid")

    if order_uid:
        # Add item (may fail if product 1 doesn't exist, that's fine - captures the error)
        results.append(capture_endpoint(
            client, "POST", f"/api/orders/{order_uid}/items",
            json={"product_id": 1, "quantity": 2},
        ))
        # Update item
        results.append(capture_endpoint(
            client, "PUT", f"/api/orders/{order_uid}/items",
            json={"product_id": 1, "quantity": 3},
        ))
        # Confirm order
        results.append(capture_endpoint(
            client, "POST", f"/api/orders/{order_uid}/confirm",
        ))
        # Cancel a new order (create another to test cancel path)
        create2 = capture_endpoint(client, "POST", "/api/orders")
        results.append(create2)
        if create2["status_code"] == 201 and isinstance(create2["body"], dict):
            uid2 = create2["body"].get("order_uid")
            if uid2:
                results.append(capture_endpoint(
                    client, "POST", f"/api/orders/{uid2}/cancel",
                ))
    else:
        results.append({"method": "SKIP", "path": "/api/orders/*", "status_code": -1, "body": "order_uid not obtained"})

    # Invalid order UID
    results.append(capture_endpoint(client, "POST", "/api/orders/nonexistent-uid/confirm"))
    results.append(capture_endpoint(client, "POST", "/api/orders/nonexistent-uid/cancel"))

    # ── Protected endpoints: no auth (should 401/403) ──
    results.append(capture_endpoint(client, "GET", "/api/admin/orders"))
    results.append(capture_endpoint(client, "GET", "/api/admin/stats"))
    results.append(capture_endpoint(client, "GET", "/api/analytics/summary"))
    results.append(capture_endpoint(client, "GET", "/api/chef/orders"))
    results.append(capture_endpoint(client, "GET", "/api/cashier/orders"))
    results.append(capture_endpoint(client, "POST", "/api/products", json={
        "department_id": 1, "name_en": "Test", "name_ar": "اختبار", "price": 10.0,
    }))

    # ── Protected endpoints: with auth ──
    if token:
        results.append(capture_endpoint(client, "GET", "/api/admin/orders", headers=auth_headers))
        results.append(capture_endpoint(client, "GET", "/api/admin/stats", headers=auth_headers))
        results.append(capture_endpoint(client, "GET", "/api/analytics/summary", headers=auth_headers))
        results.append(capture_endpoint(client, "GET", "/api/chef/orders", headers=auth_headers))
        results.append(capture_endpoint(client, "GET", "/api/cashier/orders", headers=auth_headers))

        # Status update (need a confirmed order)
        if order_uid:
            # Try valid transition: confirmed → cooking
            results.append(capture_endpoint(
                client, "POST", f"/api/orders/1/status",
                headers=auth_headers,
                json={"status": "cooking"},
            ))
            # Invalid transition
            results.append(capture_endpoint(
                client, "POST", f"/api/orders/1/status",
                headers=auth_headers,
                json={"status": "pending"},
            ))
            # Invalid status value
            results.append(capture_endpoint(
                client, "POST", f"/api/orders/1/status",
                headers=auth_headers,
                json={"status": "nonexistent_status"},
            ))

        # Product CRUD
        prod_create = capture_endpoint(
            client, "POST", "/api/products",
            headers=auth_headers,
            json={
                "department_id": 1, "name_en": "Baseline Test",
                "name_ar": "اختبار", "price": 15.50,
            },
        )
        results.append(prod_create)

        test_prod_id = None
        if prod_create["status_code"] == 201 and isinstance(prod_create["body"], dict):
            test_prod_id = prod_create["body"].get("id")

        if test_prod_id:
            results.append(capture_endpoint(
                client, "PUT", f"/api/products/{test_prod_id}",
                headers=auth_headers,
                json={
                    "department_id": 1, "name_en": "Baseline Updated",
                    "name_ar": "محدث", "price": 20.0,
                },
            ))
            results.append(capture_endpoint(
                client, "DELETE", f"/api/products/{test_prod_id}",
                headers=auth_headers,
            ))
        # Product 404
        results.append(capture_endpoint(
            client, "PUT", f"/api/products/99999",
            headers=auth_headers,
            json={
                "department_id": 1, "name_en": "Ghost", "name_ar": "شبح", "price": 1.0,
            },
        ))
        results.append(capture_endpoint(
            client, "DELETE", f"/api/products/99999",
            headers=auth_headers,
        ))

        # Department CRUD
        dept_create = capture_endpoint(
            client, "POST", "/api/departments",
            headers=auth_headers,
            json={"name_en": "Baseline Dept", "name_ar": "قسم", "display_order": 99},
        )
        results.append(dept_create)

        test_dept_id = None
        if dept_create["status_code"] == 201 and isinstance(dept_create["body"], dict):
            test_dept_id = dept_create["body"].get("id")

        if test_dept_id:
            results.append(capture_endpoint(
                client, "PUT", f"/api/departments/{test_dept_id}",
                headers=auth_headers,
                json={"name_en": "Updated Dept", "name_ar": "محدث", "display_order": 100},
            ))
            results.append(capture_endpoint(
                client, "DELETE", f"/api/departments/{test_dept_id}",
                headers=auth_headers,
            ))
        # Department 404
        results.append(capture_endpoint(
            client, "PUT", f"/api/departments/99999",
            headers=auth_headers,
            json={"name_en": "Ghost", "name_ar": "شبح"},
        ))
        results.append(capture_endpoint(
            client, "DELETE", f"/api/departments/99999",
            headers=auth_headers,
        ))

        # Logout
        results.append(capture_endpoint(client, "POST", "/api/auth/logout", headers=auth_headers))
    else:
        results.append({"method": "SKIP", "path": "auth-protected/*", "status_code": -1, "body": "no token obtained"})

    # ── Analytics (public write) ──
    results.append(capture_endpoint(
        client, "POST", "/api/analytics/events",
        json={
            "event_type": "baseline_test",
            "session_uid": "baseline-session-001",
            "product_id": 1,
        },
    ))

    return results


def normalize_for_comparison(results):
    """Strip volatile fields (timestamps, tokens, UIDs) for stable diffing."""
    normalized = []
    for r in results:
        entry = {
            "method": r["method"],
            "path_pattern": _generalize_path(r["path"]),
            "status_code": r["status_code"],
        }
        # Keep body structure but strip volatile values
        body = r.get("body")
        if isinstance(body, dict):
            entry["body_keys"] = sorted(body.keys())
        elif isinstance(body, list):
            entry["body_type"] = "list"
            entry["body_length"] = len(body)
        else:
            entry["body_type"] = type(body).__name__
        normalized.append(entry)
    return normalized


def _generalize_path(path):
    """Replace dynamic IDs in paths for stable matching."""
    import re
    path = re.sub(r'/orders/[a-f0-9-]{36}', '/orders/{uid}', path)
    path = re.sub(r'/orders/\d+', '/orders/{id}', path)
    path = re.sub(r'/products/\d+', '/products/{id}', path)
    path = re.sub(r'/departments/\d+', '/departments/{id}', path)
    return path


def save_baseline(results, normalized):
    os.makedirs(BASELINE_DIR, exist_ok=True)
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_endpoints": len(results),
            "raw_results": results,
            "normalized": normalized,
        }, f, indent=2, default=str, ensure_ascii=False)
    print(f"\n✅ Baseline saved to {BASELINE_FILE}")
    print(f"   Total test cases: {len(results)}")
    successes = sum(1 for r in results if 200 <= r["status_code"] < 300)
    errors = sum(1 for r in results if 400 <= r["status_code"] < 500)
    failures = sum(1 for r in results if r["status_code"] >= 500 or r["status_code"] == -1)
    print(f"   2xx: {successes} | 4xx: {errors} | 5xx/fail: {failures}")


def verify_against_baseline(results, normalized):
    if not os.path.exists(BASELINE_FILE):
        print("❌ No baseline file found! Run without --verify first.")
        sys.exit(1)

    with open(BASELINE_FILE, "r", encoding="utf-8") as f:
        baseline = json.load(f)

    baseline_norm = baseline["normalized"]
    diffs = []

    max_len = max(len(baseline_norm), len(normalized))
    for i in range(max_len):
        if i >= len(baseline_norm):
            diffs.append(f"  [NEW #{i}] {normalized[i]}")
            continue
        if i >= len(normalized):
            diffs.append(f"  [MISSING #{i}] {baseline_norm[i]}")
            continue

        b, n = baseline_norm[i], normalized[i]
        if b["status_code"] != n["status_code"]:
            diffs.append(
                f"  [{i}] {n.get('method','')} {n.get('path_pattern','')}: "
                f"status {b['status_code']} → {n['status_code']}"
            )
        if b.get("body_keys") != n.get("body_keys"):
            diffs.append(
                f"  [{i}] {n.get('method','')} {n.get('path_pattern','')}: "
                f"body keys changed {b.get('body_keys')} → {n.get('body_keys')}"
            )

    if diffs:
        print(f"\n⚠️  DIFFERENCES FOUND ({len(diffs)}):")
        for d in diffs:
            print(d)
        sys.exit(1)
    else:
        print(f"\n✅ Verification passed — {len(normalized)} test cases match baseline.")


def main():
    parser = argparse.ArgumentParser(description="HoloMenu baseline capture & verify")
    parser.add_argument("--verify", action="store_true", help="Verify against saved baseline")
    args = parser.parse_args()

    print("🔄 Connecting to HoloMenu backend...")
    client = httpx.Client()

    try:
        # Quick connectivity check
        try:
            client.get(f"{BASE}/api/health", headers=HEADERS, timeout=5)
        except Exception as e:
            print(f"❌ Cannot reach {BASE}/api/health: {e}")
            print("   Make sure the server is running: uvicorn backend.main:app --host 127.0.0.1 --port 8081")
            sys.exit(1)

        print("🔑 Logging in as admin...")
        token = login(client)
        if token:
            print("   ✓ Login successful")
            # Wait 1.1 seconds to avoid identical JWT refresh token expiration timestamps
            time.sleep(1.1)
        else:
            print("   ⚠ Login failed — protected endpoint tests will be skipped")

        print("🧪 Running endpoint tests...")
        results = run_all(client, token)
        normalized = normalize_for_comparison(results)

        if args.verify:
            verify_against_baseline(results, normalized)
        else:
            save_baseline(results, normalized)
    finally:
        client.close()


if __name__ == "__main__":
    main()

