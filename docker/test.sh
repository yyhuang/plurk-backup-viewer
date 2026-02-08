#!/bin/sh
# Docker smoke tests for plurk-viewer container
# Usage: ./docker/test.sh
#
# Expects container running on localhost:8000

BASE_URL="http://localhost:8000"
PASS=0
FAIL=0

check() {
    desc="$1"
    shift
    if "$@" > /dev/null 2>&1; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc"
        FAIL=$((FAIL + 1))
    fi
}

check_output() {
    desc="$1"
    expected="$2"
    shift 2
    output=$("$@" 2>/dev/null)
    if echo "$output" | grep -q "$expected"; then
        echo "  PASS: $desc"
        PASS=$((PASS + 1))
    else
        echo "  FAIL: $desc (expected '$expected', got '$output')"
        FAIL=$((FAIL + 1))
    fi
}

echo "=== Docker Smoke Tests ==="
echo ""

# 1. Container health
echo "[Container]"
check "container is running" docker ps --filter name=plurk --format '{{.Status}}' | grep -q "Up"

# 2. API endpoints
echo "[API]"
check_output "/api/stats returns plurk_count" "plurk_count" \
    curl -sf "$BASE_URL/api/stats"

check_output "/api/stats returns response_count" "response_count" \
    curl -sf "$BASE_URL/api/stats"

check_output "/api/stats returns link_count" "link_count" \
    curl -sf "$BASE_URL/api/stats"

# 3. Search - LIKE mode (no ICU needed)
echo "[Search - LIKE]"
check_output "LIKE search returns results" '"total"' \
    curl -sf "$BASE_URL/api/search?q=test&type=plurks&mode=like&page=0"

# 4. Search - FTS mode (needs ICU)
echo "[Search - FTS]"
check_output "FTS search works" '"total"' \
    curl -sf "$BASE_URL/api/search?q=test&type=plurks&mode=fts&page=0"

check_output "FTS Chinese search works" '"total"' \
    curl -sf "$BASE_URL/api/search?q=%E4%BD%A0%E5%A5%BD&type=plurks&mode=fts&page=0"

# 5. HTML pages
echo "[Pages]"
check_output "root redirects to landing" "302" \
    curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/"

check_output "landing.html loads" "200" \
    curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/landing.html"

check_output "search.html loads" "200" \
    curl -s -o /dev/null -w '%{http_code}' "$BASE_URL/search.html"

# 6. Plurk lookup
echo "[Lookup]"
check_output "/api/plurk returns base_id or not found" 'base_id\|error' \
    curl -s "$BASE_URL/api/plurk/1"

# Summary
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
