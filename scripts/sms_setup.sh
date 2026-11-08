#!/usr/bin/env bash
# ============================================================================
#  sms_setup.sh - turn the SMS gateway on, safely, and prove it with a real send
#
#  WHY THIS EXISTS
#  ---------------
#  Diagnosis on the live host (manage.py sms_doctor) reported:
#
#      OTP_PROVIDER             = email     <- phone users get NOTHING
#      OTP_SMS_PROVIDER         = console   <- development backend, never sends
#      NOTIFICATIONS_SMS_ENABLED= False
#      API key                  = NOT SET
#      pattern[login/signup/...]= all unset
#      readiness                = ready=False mode=console
#
#  So "the SMS panel does not work" was never a code bug: the gateway was simply
#  never configured after the server move. This script writes exactly the keys
#  the backend reads (via scripts/env_set.py), restarts the app, and then makes
#  the gateway answer with a REAL message - so the result is proven, not assumed.
#
#  USAGE
#      bash scripts/sms_setup.sh --check
#      bash scripts/sms_setup.sh --apply --key 'APIKEY' --login 'PATTERN_CODE'
#      bash scripts/sms_setup.sh --apply --key '...' --login '...' --signup '...' \
#           --reset '...' --identifier '...' --notification '...' --channel sms
#      bash scripts/sms_setup.sh --test --to 09121234567
#
#  NOTES
#      - the API key and pattern codes come from the IranPayamak panel
#      - values are written with scripts/env_set.py (atomic, backed up, no dupes)
#      - nothing secret is printed: only key names and lengths
#      - --channel sms switches OTP_PROVIDER to sms (phone users get the code);
#        --channel both keeps email and only enables SMS for notifications
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
SETTINGS="${SETTINGS:-config.settings.production}"
DEFAULT_LINE="${DEFAULT_LINE:-50002178584000}"

MODE="check"
APPLY=0
API_KEY=""
PAT_LOGIN=""
PAT_SIGNUP=""
PAT_RESET=""
PAT_IDENTIFIER=""
PAT_NOTIFICATION=""
LINE_NUMBER="$DEFAULT_LINE"
CHANNEL="sms"
TO=""

while [ $# -gt 0 ]; do
  case "$1" in
    --check) MODE="check" ;;
    --apply) APPLY=1; MODE="apply" ;;
    --test) MODE="test" ;;
    --key) API_KEY="${2:-}"; shift ;;
    --login) PAT_LOGIN="${2:-}"; shift ;;
    --signup) PAT_SIGNUP="${2:-}"; shift ;;
    --reset) PAT_RESET="${2:-}"; shift ;;
    --identifier) PAT_IDENTIFIER="${2:-}"; shift ;;
    --notification) PAT_NOTIFICATION="${2:-}"; shift ;;
    --line) LINE_NUMBER="${2:-}"; shift ;;
    --channel) CHANNEL="${2:-}"; shift ;;
    --to) TO="${2:-}"; shift ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
  shift
done

step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
warn() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }

cd "$APP_DIR" || { echo "app dir not found: $APP_DIR"; exit 1; }
[ -x "$VENV_PY" ] || { echo "venv python not found: $VENV_PY"; exit 1; }
[ -f scripts/env_set.py ] || { echo "scripts/env_set.py missing (git pull)"; exit 1; }

run_manage() { DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" manage.py "$@"; }

echo "============================================================"
echo " besat sms setup | $(date '+%Y-%m-%d %H:%M') | mode=$MODE"
echo "============================================================"

# ------------------------------------------------------------------ current state
step "1/5 current state"
CUR=$(run_manage sms_doctor 2>&1)
printf '%s\n' "$CUR" | grep -E 'OTP_|NOTIFICATIONS_SMS|readiness|API key|line_number|pattern\[' | sed 's/^/       /'
if printf '%s' "$CUR" | grep -q 'ready=True'; then ok "gateway already ready"; else warn "gateway NOT ready (see the lines above)"; fi

if [ "$MODE" = "check" ]; then
  echo
  info "to configure, run:"
  info "  bash scripts/sms_setup.sh --apply --key 'YOUR-API-KEY' --login 'LOGIN-PATTERN' \\"
  info "       --signup 'SIGNUP-PATTERN' --reset 'RESET-PATTERN' --identifier 'IDENTIFIER-PATTERN'"
  info "then prove it with a real send:"
  info "  bash scripts/sms_setup.sh --test --to 09xxxxxxxxx"
  exit 0
fi

# ------------------------------------------------------------------------ apply
if [ "$MODE" = "apply" ]; then
  step "2/5 validating the values you passed"
  FAIL=0
  if [ -z "$API_KEY" ]; then bad "--key is required (IranPayamak API key)"; FAIL=1; else ok "api key provided (${#API_KEY} chars)"; fi
  if [ -z "$PAT_LOGIN" ]; then bad "--login is required (approved pattern code for login OTP)"; FAIL=1; else ok "login pattern: $PAT_LOGIN"; fi
  [ -n "$PAT_SIGNUP" ] && ok "signup pattern: $PAT_SIGNUP" || warn "no --signup pattern (signup OTP would fail)"
  [ -n "$PAT_RESET" ] && ok "reset pattern: $PAT_RESET" || warn "no --reset pattern (password reset OTP would fail)"
  [ -n "$PAT_IDENTIFIER" ] && ok "identifier pattern: $PAT_IDENTIFIER" || info "no --identifier pattern (optional)"
  [ -n "$LINE_NUMBER" ] && ok "line number: $LINE_NUMBER" || warn "empty --line (the panel default is $DEFAULT_LINE)"
  case "$CHANNEL" in
    sms)  ok "channel: sms (OTP_PROVIDER=sms -> phone users receive the code)" ;;
    both) ok "channel: both (OTP_PROVIDER stays email, SMS enabled for notifications)" ;;
    *) bad "--channel must be sms or both"; FAIL=1 ;;
  esac
  if [ "$FAIL" -eq 1 ]; then echo; bad "nothing was written"; exit 1; fi

  step "3/5 writing .env (atomic, backed up, no duplicate keys)"
  ARGS=(
    "OTP_SMS_PROVIDER=iranpayamak"
    "SMS_IRANPAYAMAK_API_KEY=$API_KEY"
    "SMS_IRANPAYAMAK_LINE_NUMBER=$LINE_NUMBER"
    "SMS_IRANPAYAMAK_PATTERN_LOGIN=$PAT_LOGIN"
    "NOTIFICATIONS_SMS_ENABLED=True"
  )
  [ -n "$PAT_SIGNUP" ] && ARGS+=("SMS_IRANPAYAMAK_PATTERN_SIGNUP=$PAT_SIGNUP")
  [ -n "$PAT_RESET" ] && ARGS+=("SMS_IRANPAYAMAK_PATTERN_PASSWORD_RESET=$PAT_RESET")
  [ -n "$PAT_IDENTIFIER" ] && ARGS+=("SMS_IRANPAYAMAK_PATTERN_IDENTIFIER_ADD=$PAT_IDENTIFIER")
  [ -n "$PAT_NOTIFICATION" ] && ARGS+=("SMS_IRANPAYAMAK_PATTERN_NOTIFICATION=$PAT_NOTIFICATION")
  [ "$CHANNEL" = "sms" ] && ARGS+=("OTP_PROVIDER=sms")
  if ! "$VENV_PY" scripts/env_set.py --section "sms gateway" "${ARGS[@]}"; then
    bad "writing .env failed"; exit 1
  fi
  ok ".env written"

  step "4/5 restarting the application (so the new settings load)"
  if [ -x scripts/serve_gunicorn.sh ]; then
    bash scripts/serve_gunicorn.sh restart 2>&1 | sed 's/^/       /'
  fi
  mkdir -p tmp && touch tmp/restart.txt && ok "tmp/restart.txt touched"
  sleep 2

  step "5/5 re-checking readiness"
  CUR=$(run_manage sms_doctor 2>&1)
  printf '%s\n' "$CUR" | grep -E 'OTP_|readiness|API key|pattern\[' | sed 's/^/       /'
  if printf '%s' "$CUR" | grep -q 'ready=True'; then
    ok "gateway is READY"
    echo
    info "final proof (a real SMS): bash scripts/sms_setup.sh --test --to 09xxxxxxxxx"
    exit 0
  fi
  bad "still not ready - the lines above say which key is missing"
  exit 1
fi

# ------------------------------------------------------------------------- test
if [ "$MODE" = "test" ]; then
  step "2/5 readiness"
  CUR=$(run_manage sms_doctor 2>&1)
  if ! printf '%s' "$CUR" | grep -q 'ready=True'; then
    bad "gateway is not ready yet - run --apply first, then --test"
    printf '%s\n' "$CUR" | grep -E 'readiness|API key|pattern\[' | sed 's/^/       /'
    exit 1
  fi
  ok "ready"

  if [ -z "$TO" ]; then
    bad "--to 09xxxxxxxxx is required for a real send"
    exit 2
  fi
  case "$TO" in
    09[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
    *) warn "phone does not look like 09xxxxxxxxx - continuing anyway" ;;
  esac

  step "3/5 real send through the gateway (raw response is printed below)"
  run_manage sms_doctor --to "$TO" --purpose login 2>&1 | tail -25 | sed 's/^/       /'

  step "4/5 what the backend recorded"
  DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - 2>&1 <<'PY' | sed 's/^/       /'
import django, os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.production"))
django.setup()
try:
    from apps.notifications.models import Notification
    qs = Notification.objects.order_by("-id")[:5]
    print("recent notifications:")
    for n in qs:
        print(f"  #{n.pk} {getattr(n, 'channel', '?')} {getattr(n, 'status', '?')} {getattr(n, 'created_at', '')}")
except Exception as exc:
    print(f"(no notification rows to show: {exc})")
PY

  step "5/5 verdict"
  info "if the number received the code, the gateway is done end to end."
  info "if the panel returned an error above, that message is the gateway's own"
  info "reason (unapproved pattern / line mismatch / low credit) - send it as is."
  exit 0
fi
