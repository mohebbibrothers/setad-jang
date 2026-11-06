#!/usr/bin/env bash
# ============================================================================
#  repair_backend.sh - post-migration backend repair (cPanel / Passenger)
#
#  Why: after moving a Django app to a new cPanel host, three things classically
#  break and one of them is always the cause of Passenger's
#  "Web application could not be started":
#    1) virtualenv - absolute paths in bin/* die when user/path/Python changes
#    2) .env       - providers usually skip dotfiles -> no SECRET_KEY -> no boot
#    3) database   - must be imported on the new MySQL, new creds in .env
#
#  Usage (from anywhere):
#      bash scripts/repair_backend.sh            # diagnose only (safe)
#      bash scripts/repair_backend.sh --fix      # diagnose + repair
#
#  Notes:
#  - ASCII-only output: cPanel terminals mangle emoji / box drawing.
#  - Never deletes anything: a broken venv is *renamed*, .env is backed up.
#  - Prints the server's public IP at the end (needed for Vercel).
# ============================================================================

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_DIR="${VENV_DIR:-$HOME/virtualenv/apps/besat-backend}"
SETTINGS="config.settings.production"
FIX=0
for a in "$@"; do [ "$a" = "--fix" ] && FIX=1; done

step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
FAIL=0

echo "============================================================"
echo " besat backend repair  |  $(date '+%Y-%m-%d %H:%M')"
echo " mode: $([ "$FIX" -eq 1 ] && echo 'FIX' || echo 'CHECK-ONLY')"
echo "============================================================"

# ---------------------------------------------------------------- 1. preflight
step "1/8 preflight"
info "user=$(whoami)  host=$(hostname)"
[ -d "$APP_DIR" ] || { bad "app dir not found: $APP_DIR (override with APP_DIR=/path)"; exit 1; }
cd "$APP_DIR" || exit 1
ok "app dir: $APP_DIR"
info "git HEAD: $(git log --oneline -1 2>/dev/null || echo 'no git')"
FREE=$(df -Pk "$HOME" | tail -1 | awk '{print $4}')
info "free space: $((FREE/1024)) MB"
[ "$FREE" -lt 512000 ] && bad "low disk space (<500MB) - pip install may fail"
info "system python3: $(python3 -V 2>&1)"

# ---------------------------------------------- 1b. legacy home (user rename)
step "1b/8 legacy home detection (user rename baahamnc -> besatme?)"
LEGACY=""
for h in /home/*; do
  [ -d "$h" ] || continue
  case "$h" in "$HOME") continue ;; esac
  if [ -f "$h/apps/besat-backend/.env" ] || [ -d "$h/virtualenv/apps/besat-backend" ] || [ -d "$h/apps/besat-backend/media" ]; then
    LEGACY="$h"; break
  fi
done

if [ -n "$LEGACY" ]; then
  warn "legacy home found: $LEGACY  (old user's data still lives here)"
  [ -f "$LEGACY/apps/besat-backend/.env" ] && info ".env there: $(wc -l < "$LEGACY/apps/besat-backend/.env" | tr -d ' ') lines" || info "no .env there"
  [ -d "$LEGACY/apps/besat-backend/media" ] && info "media there: $(find "$LEGACY/apps/besat-backend/media" -type f 2>/dev/null | wc -l | tr -d ' ') files" || info "no media there"
  [ -d "$LEGACY/virtualenv/apps/besat-backend" ] && info "venv there: $LEGACY/virtualenv/apps/besat-backend" || true

  if [ "$FIX" -eq 1 ]; then
    step "1c/8 migrating legacy data into $HOME"
    # .env : back up current, then copy from legacy
    if [ -f "$LEGACY/apps/besat-backend/.env" ]; then
      [ -f .env ] && cp .env ".env.bak.$(date +%s)" && info "current .env backed up"
      cp "$LEGACY/apps/besat-backend/.env" .env && ok ".env copied from legacy home"
    fi
    # media : keep both, copy missing
    if [ -d "$LEGACY/apps/besat-backend/media" ]; then
      mkdir -p media
      cp -an "$LEGACY/apps/besat-backend/media/." media/ 2>/dev/null
      ok "media copied ($(find media -type f 2>/dev/null | wc -l | tr -d ' ') files now)"
    fi
    # permissions: files may still be owned by the old uid
    chmod -R u+rwX .env media 2>/dev/null || true
    info "note: venv is rebuilt fresh below (copying a venv across users is unreliable)"
  else
    info "run with --fix to copy .env and media into $HOME automatically"
  fi
else
  ok "no legacy home with backend data found (nothing to migrate)"
fi

# ---------------------------------------------------------------- 2. .env
step "2/8 .env (most common migration casualty)"
if [ -f .env ]; then
  ok ".env present ($(wc -l < .env | tr -d ' ') lines)"
  grep -qiE '^SECRET_KEY=.+'   .env && ok "SECRET_KEY set"   || bad "SECRET_KEY missing/empty"
  grep -qiE '^ALLOWED_HOSTS=.+' .env && ok "ALLOWED_HOSTS set" || bad "ALLOWED_HOSTS missing/empty"
  grep -qiE '^DB_|^DATABASE_'   .env && ok "database keys present" || warn "no DB_/DATABASE_ keys found"
  grep -qE '^(DEBUG|DJANGO_DEBUG)=True' .env && warn "DEBUG=True in production"
else
  bad ".env MISSING - providers skip dotfiles; restore it from the old host/backup"
  info "minimum keys: SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, DB_*"
fi

# ---------------------------------------------------------------- 3. venv
step "3/8 virtualenv (most common Passenger boot failure)"
PY=""
for c in "$VENV_DIR/3.12/bin/python" "$VENV_DIR/bin/python"; do
  [ -x "$c" ] && PY="$c" && break
done
if [ -z "$PY" ]; then
  OTHER=$(find "$HOME/virtualenv" -maxdepth 4 -type f -name python 2>/dev/null | head -1)
  [ -n "$OTHER" ] && PY="$OTHER"
fi

if [ -n "$PY" ]; then
  info "python: $PY ($("$PY" -V 2>&1))"
  if "$PY" -c "import django" >/dev/null 2>&1; then
    ok "venv healthy (django importable: $("$PY" -c 'import django;print(django.get_version())' 2>/dev/null))"
    VENV_OK=1
  else
    bad "venv exists but django NOT importable (paths/version changed)"
    VENV_OK=0
  fi
else
  bad "no virtualenv found at $VENV_DIR"
  VENV_OK=0
fi

if [ "$FIX" -eq 1 ] && [ "$VENV_OK" -eq 0 ]; then
  step "3b/8 rebuilding virtualenv"
  [ -d "$VENV_DIR" ] && mv "$VENV_DIR" "${VENV_DIR}.broken.$(date +%s)" && info "old venv renamed (recoverable)"
  mkdir -p "$(dirname "$VENV_DIR")"
  python3 -m venv "$VENV_DIR" && ok "venv created" || { bad "venv creation failed"; exit 1; }
  PY="$VENV_DIR/bin/python"
  ok "python: $("$PY" -V 2>&1)"
fi

# ---------------------------------------------------------------- 4. deps
step "4/8 dependencies"
if [ "$FIX" -eq 1 ] && [ -n "$PY" ]; then
  REQ=requirements-lock.txt; [ -f "$REQ" ] || REQ=requirements.txt
  info "installing from $REQ (this can take 2-5 min)"
  "$PY" -m pip install --upgrade pip -q 2>/dev/null
  if "$PY" -m pip install -r "$REQ" --disable-pip-version-check -q; then
    ok "dependencies installed"
  else
    bad "pip install failed (see output above; usually mysqlclient or disk)"
  fi
  "$PY" -m pip check 2>&1 | tail -3 | sed 's/^/       /'
else
  info "skipped (check-only, or no python)"
fi

# ---------------------------------------------------------------- 5. boot
step "5/8 django boot test (exactly what Passenger does)"
if [ -n "$PY" ]; then
  if DJANGO_SETTINGS_MODULE="$SETTINGS" "$PY" -c "import passenger_wsgi" 2>/tmp/boot_err.txt; then
    ok "passenger_wsgi imports cleanly"
  else
    bad "boot FAILED - real error below (this is the Passenger 500 cause):"
    tail -25 /tmp/boot_err.txt | sed 's/^/       /'
  fi
fi

# ---------------------------------------------------------------- 6. database
step "6/8 database connection and data"
if [ -n "$PY" ]; then
  OUT=$(DJANGO_SETTINGS_MODULE="$SETTINGS" "$PY" manage.py shell -c "
from django.db import connection
from django.contrib.auth import get_user_model
print('ENGINE:', connection.settings_dict.get('ENGINE'))
print('NAME  :', connection.settings_dict.get('NAME'))
print('HOST  :', connection.settings_dict.get('HOST'))
print('USERS :', get_user_model().objects.count())
try:
    from apps.kindness_wall.models import KindnessListing
    print('LISTINGS:', KindnessListing.all_objects.count())
except Exception as exc:
    print('LISTINGS: n/a', exc)
" 2>&1)
  echo "$OUT" | tail -12 | sed 's/^/       /'
  echo "$OUT" | grep -q "USERS : 0" && bad "users table empty - database probably NOT imported"
  echo "$OUT" | grep -qE "Error|Traceback|OperationalError" && bad "database connection/query failed"

  if [ "$FIX" -eq 1 ]; then
    info "running migrate..."
    DJANGO_SETTINGS_MODULE="$SETTINGS" "$PY" manage.py migrate --noinput 2>&1 | tail -5 | sed 's/^/       /' \
      && ok "migrate done" || bad "migrate failed"
  fi
fi

# ---------------------------------------------------------------- 7. assets
step "7/8 static and media"
if [ -d media ]; then
  MC=$(find media -type f 2>/dev/null | wc -l | tr -d ' ')
  if [ "${MC:-0}" -gt 0 ]; then ok "media: $MC files ($(du -sh media 2>/dev/null | cut -f1))"; else bad "media EMPTY - listing images will 404"; fi
else
  bad "no media/ directory - uploads were not migrated"
fi
if [ "$FIX" -eq 1 ] && [ -n "$PY" ]; then
  DJANGO_SETTINGS_MODULE="$SETTINGS" "$PY" manage.py collectstatic --noinput -v 0 2>&1 | tail -2 | sed 's/^/       /'
  ok "collectstatic done"
fi

# ---------------------------------------------------------------- 8. restart
step "8/8 permissions, restart, public IP"
chmod -R u+rwX "$APP_DIR" 2>/dev/null
if [ "$FIX" -eq 1 ]; then
  mkdir -p tmp && touch tmp/restart.txt && ok "tmp/restart.txt touched (Passenger restart)"
fi
PUBIP=$(curl -s -m 8 https://api.ipify.org 2>/dev/null)
[ -z "$PUBIP" ] && PUBIP=$(curl -s -m 8 https://ifconfig.me 2>/dev/null)
[ -z "$PUBIP" ] && PUBIP="unknown"

echo
echo "============================================================"
echo " PUBLIC IP (put this in Vercel as API_UPSTREAM_URL):"
echo "     http://$PUBIP"
echo "============================================================"
if [ -f .env ] && [ "$PUBIP" != "unknown" ]; then
  grep -q "$PUBIP" .env 2>/dev/null \
    && ok "this IP already appears in .env" \
    || warn "this IP is NOT in .env -> add to ALLOWED_HOSTS: ALLOWED_HOSTS=besat.me,www.besat.me,$PUBIP,localhost,127.0.0.1"
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo " RESULT: all checks green."
  echo " NEXT  : set Vercel API_UPSTREAM_URL=http://$PUBIP and Redeploy."
else
  echo " RESULT: $FAIL issue(s) above need attention."
  [ "$FIX" -eq 0 ] && echo " TRY   : bash scripts/repair_backend.sh --fix"
  echo " Send the full output back for the exact next step."
fi
exit 0
