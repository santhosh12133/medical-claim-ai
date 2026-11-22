#!/usr/bin/env bash
# Checks a deployment made by setup-server.sh from the outside, through the web server only.
#   sudo deploy/verify-deployment.sh http://localhost admin@example.com 'admin-password'
set -euo pipefail
BASE="${1:?base URL}"; ADMIN_EMAIL="${2:?admin email}"; ADMIN_PASSWORD="${3:?admin password}"
cd "$(dirname "$0")/.."
COMPOSE=(docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml)
FAILED=0
check() {  # check NAME COMMAND...
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "[PASS] $name"; else echo "[FAIL] $name"; FAILED=1; fi
}
json() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

check "Website served at /" bash -c "curl -fsS '$BASE/' | grep -qi '<div id=\"root\"'"
check "Deep link served by the SPA" bash -c "curl -fsS '$BASE/admin/login' | grep -qi '<div id=\"root\"'"
BUNDLE=$(curl -fsS "$BASE/" | grep -o '/assets/[^"]*\.js' | head -1)
check "Bundle calls the API at $BASE/api" bash -c "curl -fsS '$BASE$BUNDLE' | grep -qF '$BASE/api'"
check "Bundle has no demo passwords" bash -c "! curl -fsS '$BASE$BUNDLE' | grep -qE 'admin123|employee123'"
check "API health through /api" bash -c "curl -fsS '$BASE/api/health/ready' | grep -q ready"
check "Swagger UI loads /api/openapi.json" bash -c "curl -fsS '$BASE/api/docs' | grep -q '/api/openapi.json'"
check "OpenAPI schema served" bash -c "curl -fsS '$BASE/api/openapi.json' | grep -q '\"openapi\"'"
check "Security headers set" bash -c "curl -fsSI '$BASE/' | grep -qi '^x-content-type-options: nosniff'"
check "API port 8000 not exposed on the host" bash -c "! ss -ltnH | awk '{print \$4}' | grep -qE ':(8000|8080|5432)$'"

TOKEN=$(curl -fsS -X POST "$BASE/api/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\": \"$ADMIN_EMAIL\", \"password\": \"$ADMIN_PASSWORD\"}" | json "['access_token']" || true)
check "Admin can log in" test -n "$TOKEN"
check "Admin role confirmed by /auth/me" bash -c "curl -fsS -H 'Authorization: Bearer $TOKEN' '$BASE/api/auth/me' | grep -q '\"role\":\"admin\"'"
check "Admin endpoint works" bash -c "curl -fsS -H 'Authorization: Bearer $TOKEN' '$BASE/api/claims/summary' | grep -q total"
check "Policies loaded and searchable" bash -c "curl -fsS -H 'Authorization: Bearer $TOKEN' '$BASE/api/rag/policies' | python3 -c 'import json,sys; assert len(json.load(sys.stdin)) >= 25'"
check "Demo accounts with public passwords do not exist" bash -c "[ \"\$(curl -s -o /dev/null -w '%{http_code}' -X POST '$BASE/api/auth/login' -H 'Content-Type: application/json' -d '{\"email\":\"admin@demo.com\",\"password\":\"admin123\"}')\" = 401 ]"

# The API must see the visitor's address (from X-Forwarded-For), not the proxy's, or one attacker could
# trigger the login rate limit for everybody.
CADDY_IP=$("${COMPOSE[@]}" exec -T caddy hostname -i | awk '{print $1}')
curl -fsS "$BASE/api/health?probe=client-ip" >/dev/null
SEEN=$("${COMPOSE[@]}" logs --no-color --tail 200 api | grep 'probe=client-ip' | tail -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+' | head -1 | cut -d: -f1 || true)
check "API sees the client address ($SEEN), not the proxy ($CADDY_IP)" bash -c "[ -n '$SEEN' ] && [ '$SEEN' != '$CADDY_IP' ]"

[ "$FAILED" -eq 0 ] && echo "All deployment checks passed" || { echo "Deployment checks FAILED"; exit 1; }
