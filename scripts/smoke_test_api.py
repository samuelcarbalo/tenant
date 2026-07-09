"""Smoke test contra servidor en vivo. Ejecutar con backend en :8000"""
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000/api/v1"
TENANT = "conectando-empleo"
results = []


def req(method, path, data=None, token=None):
    url = f"{BASE}{path}"
    headers = {"Content-Type": "application/json", "X-Tenant": TENANT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=15) as res:
            raw = res.read().decode()
            return res.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"raw": raw[:200]}
        return e.code, payload


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    sym = "OK" if ok else "FAIL"
    print(f"  [{sym}] {name}" + (f" — {detail}" if detail else ""))


print("\n=== Smoke Test API (live) ===\n")

# Public endpoints
code, data = req("GET", "/payments/packages/")
check("GET /payments/packages/", code == 200 and len(data) == 4, f"status={code} count={len(data) if isinstance(data, list) else '?'}")

code, data = req("GET", "/payments/config/")
check("GET /payments/config/", code == 200 and data.get("public_key", "").startswith("APP_USR"), f"status={code}")

code, data = req("GET", "/jobs/offers/")
check("GET /jobs/offers/", code == 200, f"status={code}")

code, data = req("GET", "/real-estate/offers/")
check("GET /real-estate/offers/", code == 200, f"status={code}")

code, data = req("GET", "/sports/tournaments/")
check("GET /sports/tournaments/", code == 200, f"status={code}")

# Login (needs existing user - may fail if no user in DB)
code, data = req("POST", "/auth/login/", {
    "email": "manager@test.com",
    "password": "TestPass123!",
    "organization_slug": TENANT,
})
token = data.get("access") if code == 200 else None
check("POST /auth/login/", code in (200, 401), f"status={code} (401 si no hay usuario en BD local)")

if token:
    code, data = req("GET", "/auth/me/", token=token)
    check("GET /auth/me/", code == 200 and "credits" in data, f"credits={data.get('credits')}")

    code, data = req("GET", "/notifications/unread-count/", token=token)
    check("GET /notifications/unread-count/", code == 200, f"status={code}")

    code, data = req("GET", "/messaging/conversations/unread-count/", token=token)
    check("GET /messaging/conversations/unread-count/", code == 200, f"status={code}")

    # Real MP preference (sandbox)
    code, data = req("POST", "/payments/create-preference/", {"package_id": "basico"}, token=token)
    pref_ok = code == 200 and bool(data.get("preference_id"))
    check("POST /payments/create-preference/ (Mercado Pago real)", pref_ok, f"status={code} pref={data.get('preference_id', data)[:50] if isinstance(data, dict) else data}")
else:
    check("Auth-dependent tests", False, "skipped — crear usuario manager@test.com o usar credenciales existentes")

passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"\n=== Resultado: {passed}/{total} ===\n")
sys.exit(0 if passed == total else 1)
