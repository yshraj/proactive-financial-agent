#!/usr/bin/env bash
#
# Post-deploy smoke test for a LIVE KritiFin instance (run against the public
# HTTPS URL, not localhost). Verifies the hardening actually holds in production.
#
# Usage:
#   BASE_URL=https://demo.example.com ACCESS_CODE=your-code ./deploy/smoke-test.sh
# or:
#   ./deploy/smoke-test.sh https://demo.example.com your-code
#
# Opt-in (consumes the day's ingestion budget for this IP):
#   SMOKE_RATE_LIMIT=1 BASE_URL=... ACCESS_CODE=... ./deploy/smoke-test.sh
#
# Some checks (job survives restart, chat thread persists) need a shell on the
# VM and are listed as a MANUAL CHECKLIST at the bottom of this file.

set -u

BASE_URL="${BASE_URL:-${1:-}}"
ACCESS_CODE="${ACCESS_CODE:-${2:-}}"

if [ -z "$BASE_URL" ] || [ -z "$ACCESS_CODE" ]; then
  echo "usage: BASE_URL=https://host ACCESS_CODE=code $0" >&2
  exit 2
fi
BASE_URL="${BASE_URL%/}"   # strip trailing slash

pass=0
fail=0

# ok <description> <actual> <expected>
ok() {
  if [ "$2" = "$3" ]; then
    printf "  PASS  %s (%s)\n" "$1" "$2"
    pass=$((pass + 1))
  else
    printf "  FAIL  %s (got %s, want %s)\n" "$1" "$2" "$3"
    fail=$((fail + 1))
  fi
}

# contains <description> <haystack> <needle>
contains() {
  case "$2" in
    *"$3"*) printf "  PASS  %s\n" "$1"; pass=$((pass + 1)) ;;
    *)      printf "  FAIL  %s (missing '%s' in: %s)\n" "$1" "$3" "$2"; fail=$((fail + 1)) ;;
  esac
}

code() { curl -sk -o /dev/null -w "%{http_code}" "$@"; }
body() { curl -sk "$@"; }

echo "== KritiFin smoke test against $BASE_URL =="

# 1. Liveness (public, ungated)
ok "health is public" "$(code "$BASE_URL/health")" "200"
contains "health payload" "$(body "$BASE_URL/health")" '"status":"ok"'

# 2. Front-door gate
ok "gate blocks with no code"    "$(code "$BASE_URL/api/access/check")" "401"
ok "gate blocks with wrong code" "$(code -H 'X-Access-Code: definitely-wrong' "$BASE_URL/api/access/check")" "401"
ok "gate allows correct code"    "$(code -H "X-Access-Code: $ACCESS_CODE" "$BASE_URL/api/access/check")" "200"

# 3. A gated API route requires the code
ok "clients route blocked without code" "$(code "$BASE_URL/api/monitor/clients")" "401"
ok "clients route allowed with code"    "$(code -H "X-Access-Code: $ACCESS_CODE" "$BASE_URL/api/monitor/clients")" "200"

# 4. Pagination is clamped, not rejected, even for an absurd limit
ok "clients accepts huge limit (clamped)" \
  "$(code -H "X-Access-Code: $ACCESS_CODE" "$BASE_URL/api/monitor/clients?limit=100000")" "200"
contains "clients response is paginated (has total)" \
  "$(body -H "X-Access-Code: $ACCESS_CODE" "$BASE_URL/api/monitor/clients?limit=100000")" '"total"'
ok "alerts accepts huge limit (clamped)" \
  "$(code -H "X-Access-Code: $ACCESS_CODE" "$BASE_URL/api/monitor/alerts?limit=100000")" "200"

# 5. Rate limit -> structured 429 (opt-in; consumes this IP's daily ingestion budget)
if [ "${SMOKE_RATE_LIMIT:-0}" = "1" ]; then
  echo "  .. hammering /api/ingest/transcript to trip the daily budget"
  last=""
  for _ in 1 2 3 4 5 6 7 8; do
    last="$(code -H "X-Access-Code: $ACCESS_CODE" -H 'Content-Type: application/json' \
      -X POST --data '{"text":"hi"}' "$BASE_URL/api/ingest/transcript")"
  done
  ok "ingestion budget returns 429" "$last" "429"
  contains "429 body is structured" \
    "$(body -H "X-Access-Code: $ACCESS_CODE" -H 'Content-Type: application/json' \
        -X POST --data '{"text":"hi"}' "$BASE_URL/api/ingest/transcript")" '"error":"rate_limit"'
else
  echo "  SKIP  rate-limit check (set SMOKE_RATE_LIMIT=1 to run; consumes daily budget)"
fi

echo
echo "== $pass passed, $fail failed =="
[ "$fail" -eq 0 ] || exit 1

cat <<'MANUAL'

-- MANUAL CHECKS (need a shell on the VM) --------------------------------------

A) Ingestion job survives a restart:
   1. In the UI (Ingestion page) start a document upload (async job), OR:
      curl -sk -H "X-Access-Code: $ACCESS_CODE" -F file=@somedoc.pdf \
        "$BASE_URL/api/ingest/upload-async"      # note the returned job_id
   2. Immediately: docker compose restart backend
   3. Poll: curl -sk -H "X-Access-Code: $ACCESS_CODE" \
        "$BASE_URL/api/ingest/jobs/<job_id>"
      PASS = job shows "DONE", or "ERROR" with a clear reason — never vanished.

B) Chat thread persists across a restart:
   1. In the UI (AI Copilot) ask a question and get an answer.
   2. docker compose restart backend
   3. Reload the Copilot page. PASS = the previous thread is still shown.

C) docker compose ps shows backend/frontend "healthy" (not just "running").
MANUAL
