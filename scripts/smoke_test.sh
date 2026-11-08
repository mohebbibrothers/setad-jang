#!/usr/bin/env bash
# ============================================================================
#  smoke_test.sh - check the public site end-to-end from anywhere
#
#  USAGE
#      bash scripts/smoke_test.sh                 # https://besat.me
#      bash scripts/smoke_test.sh https://api.besat.me
#
#  Exit code is 1 if any critical endpoint is not healthy, so it can be used in
#  cron ("mail me if the site breaks") or CI.
# ============================================================================

set -uo pipefail

BASE="${1:-https://besat.me}"
BASE="${BASE%/}"
FAIL=0

ok()   { printf '  [OK] %-44s %s\n' "$1" "$2"; }
bad()  { FAIL=$((FAIL+1)); printf '  [!!] %-44s %s\n' "$1" "$2"; }

echo "============================================================"
echo " smoke test: $BASE | $(date '+%Y-%m-%d %H:%M')"
echo "============================================================"

# --- critical API endpoints (must be 200) ----------------------------------
for path in \
  /api/v1/health/ \
  /api/v1/geo/provinces/ \
  /api/v1/kindness-wall/listings/ \
  /api/v1/kindness-wall/categories/ \
  /api/v1/kindness-wall/stats/ \
  /api/v1/madadkar/campaigns/
do
  CODE=$(curl -sL -o /dev/null -w '%{http_code}' --max-time 25 "$BASE$path" 2>/dev/null)
  if [ "$CODE" = "200" ]; then ok "$path" "$CODE"; else bad "$path" "$CODE"; fi
done

# --- credential passthrough: a bogus Bearer must be rejected AS A TOKEN ------
# If Django instead says "no credentials were provided", the Authorization
# header is being dropped by the proxy - and then every logged-in user is
# silently anonymous (the "welcome then instantly logged out" incident).
BODY=$(curl -sL --max-time 25 -H "Authorization: Bearer smoke.invalid.token" \
  "$BASE/api/v1/auth/me/" 2>/dev/null)
if printf '%s' "$BODY" | grep -qiE 'token_not_valid|نامعتبر|not valid|invalid'; then
  ok "Authorization passthrough" "rejected as token"
elif printf '%s' "$BODY" | grep -qiE 'ارسال نشده|not provided|credentials'; then
  bad "Authorization passthrough" "header DROPPED - users are anonymous"
else
  bad "Authorization passthrough" "inconclusive"
fi

# --- admin login page (200 or 302 are both fine) ---------------------------
CODE=$(curl -sL -o /dev/null -w '%{http_code}' --max-time 25 "$BASE/admin/login/" 2>/dev/null)
case "$CODE" in 200|302) ok "/admin/login/" "$CODE" ;; *) bad "/admin/login/" "$CODE" ;; esac

# --- front pages ----------------------------------------------------------
for path in / /kindness-wall; do
  CODE=$(curl -sL -o /dev/null -w '%{http_code}' --max-time 25 "$BASE$path" 2>/dev/null)
  if [ "$CODE" = "200" ]; then ok "$path" "$CODE"; else bad "$path" "$CODE"; fi
done

# --- a real listing page (slug from the API) ------------------------------
SLUG=$(curl -sL --max-time 25 "$BASE/api/v1/kindness-wall/listings/?page_size=1" 2>/dev/null \
  | tr ',' '\n' | grep -m1 '"slug"' | sed 's/.*"slug":"//; s/".*//')
if [ -n "${SLUG:-}" ]; then
  ENC=$(printf '%s' "$SLUG" | python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.stdin.read()))' 2>/dev/null || printf '%s' "$SLUG")
  CODE=$(curl -sL -o /dev/null -w '%{http_code}' --max-time 25 "$BASE/kindness-wall/$ENC" 2>/dev/null)
  if [ "$CODE" = "200" ]; then ok "/kindness-wall/<slug>" "$CODE"; else bad "/kindness-wall/<slug>" "$CODE"; fi
else
  printf '  [--] %-44s %s\n' "/kindness-wall/<slug>" "skipped (no listing)"
fi

# --- the contact gate must not leak a full phone number -------------------
DET=$(curl -sL --max-time 25 "$BASE/api/v1/kindness-wall/listings/${ENC:-}/" 2>/dev/null)
if printf '%s' "$DET" | grep -qE '"link":"tel:\+98[0-9]{9}"'; then
  bad "contact gate" "LEAK: full tel link exposed"
else
  ok "contact gate" "no full tel link"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo " RESULT: healthy"
else
  echo " RESULT: $FAIL problem(s)"
fi
echo "============================================================"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
