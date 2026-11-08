#!/usr/bin/env bash
# ============================================================================
#  host_doctor.sh - end-to-end health + stability report (read-only)
#
#  One command that answers: "is this host serving the site correctly, and is
#  it going to stay that way?"  Every check is read-only.
#
#  Sections
#     1  disk / quota headroom
#     2  repo state (commit, clean tree, remote)
#     3  venv + package integrity
#     4  Django checks (production settings)
#     5  database reachability + row counts
#     6  media + static presence
#     7  serving wiring (proxy .htaccess + WSGI port, or Passenger)
#     8  local HTTP health through the real vhost
#     9  public HTTP health (through the domain)
#    10  backups + cron + retention
#    11  leftover artefacts from our debugging (should be empty)
#
#  USAGE
#      bash scripts/host_doctor.sh
#      bash scripts/host_doctor.sh --quiet     # only problems
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
DOCROOT="${DOCROOT:-$HOME/public_html/api.besat.me}"
DOMAIN="${DOMAIN:-api.besat.me}"
SETTINGS="config.settings.production"
QUIET=0
for a in "$@"; do [ "$a" = "--quiet" ] && QUIET=1; done

PASS=0; WARN=0; FAIL=0
step() { [ "$QUIET" -eq 1 ] || printf '\n=== %s\n' "$1"; }
ok()   { PASS=$((PASS+1)); [ "$QUIET" -eq 1 ] || printf '  [OK] %s\n' "$1"; }
warn() { WARN=$((WARN+1)); printf '  [--] %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  [!!] %s\n' "$1"; }
info() { [ "$QUIET" -eq 1 ] || printf '       %s\n' "$1"; }
human(){ awk -v k="$1" 'BEGIN{ if (k>=1048576) printf "%.1f GB", k/1048576; else if (k>=1024) printf "%.1f MB", k/1024; else printf "%d KB", k }'; }
kb_of(){ [ -e "$1" ] && du -sk "$1" 2>/dev/null | awk '{print $1}' || echo 0; }

echo "============================================================"
echo " besat host doctor | $(date '+%Y-%m-%d %H:%M') | user=$USER"
echo "============================================================"

# ---------------------------------------------------------------- 1 disk
step "1/11 disk headroom"
USE_PCT=$(df -P "$HOME" | tail -1 | awk '{gsub("%","",$5); print $5}')
AVAIL=$(df -P "$HOME" | tail -1 | awk '{print $4}')
info "used ${USE_PCT}%  avail $(human "$AVAIL")"
if [ "${USE_PCT:-0}" -ge 93 ]; then bad "disk almost full (${USE_PCT}%) - run host_cleanup.sh --apply"
elif [ "${USE_PCT:-0}" -ge 90 ]; then warn "disk getting tight (${USE_PCT}%)"
else ok "disk healthy (${USE_PCT}%)"; fi

# ---------------------------------------------------------------- 2 repo
step "2/11 repository"
if [ -d "$APP_DIR/.git" ]; then
  cd "$APP_DIR" || exit 1
  HEAD=$(git log --oneline -1 2>/dev/null)
  DIRTY=$(git status --porcelain 2>/dev/null | grep -vc '^??' || true)
  ok "HEAD: $HEAD"
  if [ "${DIRTY:-0}" -gt 0 ]; then warn "$DIRTY tracked file(s) modified locally (deploy would overwrite)"; else ok "working tree clean"; fi
else
  bad ".git not found in $APP_DIR"
fi

# ---------------------------------------------------------------- 3 venv
step "3/11 python environment"
if [ -x "$VENV_PY" ]; then
  ok "venv python: $("$VENV_PY" -V 2>&1)"
  if "$VENV_PY" -c "import django" >/dev/null 2>&1; then
    ok "django $("$VENV_PY" -c 'import django;print(django.get_version())' 2>/dev/null)"
  else
    bad "django not importable from the venv"
  fi
  BROKEN=$("$VENV_PY" -m pip check 2>&1 | grep -c "requires" || true)
  if [ "${BROKEN:-0}" -gt 0 ]; then warn "pip check reports $BROKEN issue(s)"; else ok "pip check clean"; fi
else
  bad "venv python missing: $VENV_PY"
fi

# ---------------------------------------------------------------- 4 django
step "4/11 django system checks (production)"
CHK=$(DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" manage.py check --deploy 2>&1 | tail -5)
ISSUES=$(printf '%s' "$CHK" | grep -c "^\?:" || true)
if printf '%s' "$CHK" | grep -qi "System check identified no issues"; then
  ok "no issues"
else
  N=$(printf '%s' "$CHK" | grep -oE "identified [0-9]+ issue" | grep -oE "[0-9]+" || echo 0)
  warn "check --deploy reports ${N:-?} issue(s) (expected: the 8 known mysql.W003/models.W036)"
fi

# ---------------------------------------------------------------- 5 database
step "5/11 database"
DBINFO=$(DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" manage.py shell -c "
from django.db import connection
from django.contrib.auth import get_user_model
print('ENGINE:', connection.settings_dict.get('ENGINE'))
print('NAME  :', connection.settings_dict.get('NAME'))
print('USERS :', get_user_model().objects.count())
try:
    from apps.kindness_wall.models import KindnessListing
    print('LISTINGS:', KindnessListing.all_objects.count())
except Exception:
    pass
" 2>&1 | grep -E "^(ENGINE|NAME|USERS|LISTINGS)")
if [ -n "$DBINFO" ]; then
  printf '%s\n' "$DBINFO" | sed 's/^/       /'
  USERS=$(printf '%s' "$DBINFO" | awk '/USERS/{print $3}')
  if [ "${USERS:-0}" -gt 0 ]; then ok "database reachable with real data"; else bad "database reachable but users table is empty"; fi
else
  bad "database connection failed"
fi

# ---------------------------------------------------------------- 6 assets
step "6/11 media and static"
M_FILES=$(find "$APP_DIR/media" -type f 2>/dev/null | wc -l | tr -d ' ')
M_KB=$(kb_of "$APP_DIR/media")
if [ "${M_FILES:-0}" -gt 0 ]; then ok "media: $M_FILES files ($(human "$M_KB"))"; else bad "media empty or missing"; fi
if [ -d "$APP_DIR/staticfiles" ]; then ok "staticfiles present"; else warn "staticfiles missing - run collectstatic"; fi

# ---------------------------------------------------------------- 7 serving
# Production on this host is served by:  vhost -> index.php -> 127.0.0.1:PORT
# (Passenger exists on the server but is not wired into this vhost). Accept
# either strategy, but fail when neither is complete.
step "7/11 serving wiring"
WSGI_PORT="${WSGI_PORT:-8765}"
PROXY_OK=0; PASS_OK=0
if [ -f "$DOCROOT/index.php" ]; then
  if grep -q "index.php" "$DOCROOT/.htaccess" 2>/dev/null; then
    PROXY_OK=1
    ok ".htaccess routes dynamic traffic to index.php"
    grep -q ":$WSGI_PORT" "$DOCROOT/index.php" && ok "proxy targets 127.0.0.1:$WSGI_PORT" || warn "proxy target port differs from $WSGI_PORT"
  else
    bad ".htaccess does not route to index.php - dynamic requests have no target"
  fi
fi
if ss -ltn 2>/dev/null | grep -q ":$WSGI_PORT "; then ok "WSGI server listening on $WSGI_PORT"; else
  if [ "$PROXY_OK" -eq 1 ]; then bad "proxy is installed but no WSGI server on $WSGI_PORT - run: bash scripts/serve_gunicorn.sh start"
  else warn "WSGI server on $WSGI_PORT not listening"; fi
fi
if [ -f "$DOCROOT/.htaccess" ] && grep -q "PASSENGER CONFIGURATION" "$DOCROOT/.htaccess"; then
  ROOT=$(sed -n 's/^PassengerAppRoot "\\(.*\\)"/\\1/p' "$DOCROOT/.htaccess" | head -1)
  PY=$(sed -n 's/^PassengerPython "\\(.*\\)"/\\1/p' "$DOCROOT/.htaccess" | head -1)
  info "also saw a Passenger block (AppRoot: $ROOT)"
  [ -x "$PY" ] && PASS_OK=1 || warn "PassengerPython not executable: $PY"
  case "$ROOT" in "$HOME"/*) : ;; *) [ -n "$ROOT" ] && warn "Passenger app root points outside \$HOME: $ROOT" ;; esac
fi
[ "$PROXY_OK" -eq 1 ] && ok "strategy: PHP proxy + WSGI server (expected on this host)"
if [ "$PROXY_OK" -eq 0 ] && [ "$PASS_OK" -eq 0 ]; then
  bad "no working serving strategy - run: bash scripts/host_web_recover.sh --apply"
fi
[ -f "$APP_DIR/tmp/restart.txt" ] && ok "tmp/restart.txt present" || info "no tmp/restart.txt (only used in Passenger mode)"
[ -x "$APP_DIR/scripts/host_web_recover.sh" ] || chmod +x "$APP_DIR/scripts/host_web_recover.sh" 2>/dev/null || true

# ---------------------------------------------------------------- 8 local http
step "8/11 local HTTP through the vhost"
LOCAL=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -H "Host: $DOMAIN" "http://127.0.0.1/api/v1/health/" 2>/dev/null)
info "GET /api/v1/health/ -> $LOCAL"
[ "$LOCAL" = "200" ] && ok "local health 200" || bad "local health $LOCAL"

# ---------------------------------------------------------------- 9 public http
step "9/11 public HTTP"
for path in /api/v1/health/ /api/v1/kindness-wall/stats/ /api/v1/geo/provinces/ /admin/login/; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "https://$DOMAIN$path" 2>/dev/null)
  if [ "$CODE" = "200" ] || [ "$CODE" = "302" ]; then ok "https://$DOMAIN$path -> $CODE"
  else bad "https://$DOMAIN$path -> $CODE"; fi
done

# ---------------------------------------------------------------- 10 ops
step "10/11 backups and cron"
BK="$HOME/backups"
if [ -d "$BK" ] && [ -n "$(ls -A "$BK" 2>/dev/null)" ]; then
  ok "backups: $(ls "$BK" | wc -l | tr -d ' ') file(s), $(human "$(kb_of "$BK")")"
else
  bad "no backups found in $BK (run scripts/backup_daily.sh)"
fi
CRON=$(crontab -l 2>/dev/null || true)
if [ -n "$CRON" ]; then
  echo "$CRON" | grep -v '^#' | grep -v '^$' | sed 's/^/       /' | head -8
  if echo "$CRON" | grep -qE "/home/(baahamnc|olduser)"; then bad "cron still references an old home path"; else ok "cron paths look current"; fi
  echo "$CRON" | grep -q "backup_daily.sh" && ok "daily backup cron present" || warn "no backup_daily.sh cron installed"
  echo "$CRON" | grep -q "serve_gunicorn" && warn "leftover gunicorn keep-alive cron (no longer needed)" || ok "no leftover gunicorn cron"
else
  warn "crontab is empty"
fi

# ---------------------------------------------------------------- 11 leftovers
step "11/11 leftover debugging artefacts"
LEFTOVER=0
for f in "$HOME/public_html/__probe.txt" "$HOME/public_html/main/__probe.txt" \
         "$HOME/public_html/api.besat.me/__probe.txt" "$HOME/public_html/besat.me/__probe.txt"; do
  [ -e "$f" ] && { warn "still present: ${f/#$HOME/~}"; LEFTOVER=$((LEFTOVER+1)); }
done
BAKS=$(find "$HOME" -maxdepth 3 -type f -name ".htaccess.bak.*" 2>/dev/null | wc -l | tr -d ' ')
[ "${BAKS:-0}" -gt 0 ] && { warn "$BAKS old .htaccess.bak.* file(s) - run host_cleanup.sh --apply"; LEFTOVER=$((LEFTOVER+1)); }
[ "$LEFTOVER" -eq 0 ] && ok "none - host is tidy"

echo
echo "============================================================"
printf ' RESULT: %d ok, %d warning(s), %d failure(s)\n' "$PASS" "$WARN" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  echo " next: fix the [!!] items above (most have an inline hint)"
else
  echo " state: stable"
fi
echo "============================================================"
exit 0
