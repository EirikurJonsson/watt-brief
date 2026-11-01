#!/usr/bin/env bash
# Post-deploy checks. Usage: scripts/smoke.sh https://your-hostname
# Makes one real brief request (a fraction of a cent).
set -u
base="${1:?usage: smoke.sh <base-url>}"
fail=0
check() { # name, expected, actual
  if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1 (expected $2, got $3)"; fail=1; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 90 "$@"; }

check "healthz"                200 "$(code "$base/healthz")"
check "index page"             200 "$(code "$base/")"
check "price chart data"       200 "$(code "$base/api/prices")"
check "font served locally"    200 "$(code "$base/static/fonts/bricolage-grotesque-latin-opsz-normal.woff2")"
check "docs hidden"            404 "$(code "$base/docs")"
check "metrics hidden"         404 "$(code "$base/metrics")"
check "non-JSON rejected"      415 "$(code -X POST -H 'Content-Type: text/plain' -d '{"question":"power price?"}' "$base/api/brief")"
check "off-topic rejected"     422 "$(code -X POST -H 'Content-Type: application/json' -d '{"question":"write a poem about cats"}' "$base/api/brief")"
check "real brief"             200 "$(code -X POST -H 'Content-Type: application/json' -d '{"question":"When is power cheapest tomorrow in Germany?"}' "$base/api/brief")"

headers="$(curl -s -D - -o /dev/null "$base/")"
echo "$headers" | grep -qi "content-security-policy: default-src 'self'" \
  && echo "ok   CSP header present" || { echo "FAIL CSP header missing"; fail=1; }
echo "$headers" | grep -qi "x-content-type-options: nosniff" \
  && echo "ok   nosniff header present" || { echo "FAIL nosniff header missing"; fail=1; }

[ "$fail" = 0 ] && echo "SMOKE PASSED" || { echo "SMOKE FAILED"; exit 1; }
