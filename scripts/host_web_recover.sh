#!/usr/bin/env bash
# ============================================================================
#  host_web_recover.sh - bring the public serving layer back up, verifiably
#
#  WHY THIS EXISTS
#  ---------------
#  On this cPanel host Passenger is installed but the vhost does not route
#  api.besat.me through it. The configuration that actually serves production
#  (and that was live for days) is:
#
#      https://api.besat.me  ->  LiteSpeed/Apache
#            /media/* /static/*  ->  files on disk
#            everything else     ->  index.php  ->  127.0.0.1:8765 (WSGI)
#
#  If either half of that chain is missing (index.php deleted, .htaccess
#  replaced, WSGI server stopped) the domain answers 404 / 502. This script
#  rebuilds both halves, restarts the WSGI server, verifies loopback AND the
#  public URL, and reinstalls the keep-alive cron.
#
#  STEPS
#     1/7  read-only state report (docroot, .htaccess, venv, php, port, cron)
#     2/7  deploy the PHP proxy  (index.php + .htaccess, old file backed up)
#     3/7  start the WSGI server (gunicorn, stdlib fallback)
#     4/7  loopback verification through the vhost and through the port
#     5/7  public HTTPS verification (with retries while caches settle)
#     6/7  keep-alive cron (every minute, idempotent)
#     7/7  backup sanity (read-only) - dumps are checked, never produced here
#
#  USAGE
#      bash scripts/host_web_recover.sh            # DRY RUN: report + plan
#      bash scripts/host_web_recover.sh --apply    # do it, then verify
#      bash scripts/host_web_recover.sh --check     # alias of the dry run
#
#  SAFETY
#      - never touches the database, media/uploads or .env
#      - the current .htaccess is backed up before it is replaced
#      - ASCII-only output (cPanel terminals mangle unicode)
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
DOCROOT="${DOCROOT:-$HOME/public_html/api.besat.me}"
PORT="${PORT:-8765}"
DOMAIN="${DOMAIN:-api.besat.me}"
APPLY=0
for a in "$@"; do [ "$a" = "--apply" ] && APPLY=1; done

FAIL=0
WARN=0
step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf '  [--] %s\n' "$1"; WARN=$((WARN+1)); }
info() { printf '       %s\n' "$1"; }
plan() { if [ "$APPLY" -eq 1 ]; then printf '  [..] %s\n' "$1"; else printf '  [plan] %s\n' "$1"; fi; }
port_open() {
  if (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null; then exec 3<&- 2>/dev/null; exec 3>&- 2>/dev/null; return 0; fi
  command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -qE "[:.]$PORT[[:space:]]" && return 0
  command -v netstat >/dev/null 2>&1 && netstat -ltn 2>/dev/null | grep -qE "[:.]$PORT[[:space:]]" && return 0
  return 1
}
human(){ awk -v b="$1" 'BEGIN{ if (b>=1048576) printf "%.1f MB", b/1048576; else if (b>=1024) printf "%.1f KB", b/1024; else printf "%d B", b }'; }

echo "============================================================"
echo " besat web recover | $(date '+%Y-%m-%d %H:%M') | user=$USER"
echo " mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo 'DRY RUN (add --apply)')"
echo "============================================================"

# ---------------------------------------------------------------- 1 state
step "1/7 state of the serving layer (read-only)"
[ -d "$APP_DIR" ] && ok "app dir: $APP_DIR" || bad "app dir missing: $APP_DIR"
if [ -d "$DOCROOT" ]; then
  ok "docroot: $DOCROOT ($(find "$DOCROOT" -maxdepth 1 -type f | wc -l | tr -d ' ') files)"
else
  bad "docroot missing: $DOCROOT (create the api subdomain in cPanel first)"
fi

if [ -f "$DOCROOT/.htaccess" ]; then
  info ".htaccess: $(stat -c '%s bytes, mode %a' "$DOCROOT/.htaccess" 2>/dev/null)"
  if grep -q "PASSENGER CONFIGURATION" "$DOCROOT/.htaccess"; then
    warn ".htaccess carries a Passenger block (not what serves production here)"
  elif grep -q "index.php" "$DOCROOT/.htaccess"; then
    ok ".htaccess routes dynamic traffic to index.php (proxy mode)"
  else
    bad ".htaccess neither Passenger nor proxy rules - dynamic traffic has no target"
  fi
else
  bad "$DOCROOT/.htaccess is missing"
fi

if [ -f "$DOCROOT/index.php" ]; then
  ok "index.php present ($(stat -c '%s bytes' "$DOCROOT/index.php" 2>/dev/null))"
  grep -q ":$PORT" "$DOCROOT/index.php" 2>/dev/null && ok "index.php targets port $PORT" || warn "index.php does not mention port $PORT"
else
  bad "index.php missing -> every dynamic request 404s"
fi

[ -f "$APP_DIR/passenger_wsgi.py" ] && info "passenger_wsgi.py present (unused by this path)" || info "no passenger_wsgi.py (expected for proxy mode)"

if [ -x "$VENV_PY" ]; then
  ok "venv python: $("$VENV_PY" -V 2>&1)"
  "$VENV_PY" -c "import gunicorn" >/dev/null 2>&1 && ok "gunicorn installed" || warn "gunicorn not installed (stdlib fallback server will be used)"
  "$VENV_PY" -c "import django; print('django', django.get_version())" >/dev/null 2>&1 && ok "django importable" || bad "django NOT importable from the venv"
else
  bad "venv python missing: $VENV_PY"
fi

PHP_BIN=$(command -v php 2>/dev/null || echo "")
if [ -n "$PHP_BIN" ]; then ok "php: $("$PHP_BIN" -v 2>/dev/null | head -1)"; else bad "php CLI not found (the proxy cannot run)"; fi

if port_open; then ok "port $PORT is listening (WSGI server up)"; else bad "port $PORT is not listening (WSGI server down) -> 502/404"; fi

bash "$APP_DIR/scripts/serve_gunicorn.sh" status 2>&1 | sed 's/^/  | /' || true

CRON=$(crontab -l 2>/dev/null || true)
if echo "$CRON" | grep -q "serve_gunicorn.sh start"; then ok "keep-alive cron present"; else warn "no keep-alive cron (a crashed worker would stay down)"; fi
printf '%s\n' "$CRON" | grep -v '^#' | grep -v '^$' | head -6 | sed 's/^/       /'

# ---------------------------------------------------------------- 2 proxy files
step "2/7 deploy the PHP proxy into the docroot"
SRC_PHP="$APP_DIR/scripts/apache-proxy/index.php"
SRC_HT="$APP_DIR/scripts/apache-proxy/htaccess.txt"
if [ -f "$SRC_PHP" ] && [ -f "$SRC_HT" ]; then
  ok "sources present in the repo (scripts/apache-proxy/)"
else
  bad "repo proxy sources missing - run: cd $APP_DIR && git pull"
fi
if [ -d "$DOCROOT" ] && [ -f "$SRC_PHP" ]; then
  plan "install $DOCROOT/index.php (proxy to 127.0.0.1:$PORT)"
  plan "install $DOCROOT/.htaccess (proxy rules; current file backed up first)"
  if [ "$APPLY" -eq 1 ]; then
    HB=""
    if [ -f "$DOCROOT/.htaccess" ]; then
      HB="$DOCROOT/.htaccess.backup.$(date +%s)"
      cp "$DOCROOT/.htaccess" "$HB" && info "old .htaccess saved: $(basename "$HB")"
    fi
    # keep the host PHP handler line (LiteSpeed needs it) if the old file had one
    PHPLINE=""
    if [ -n "$HB" ] && [ -f "$HB" ]; then
      PHPLINE=$(grep -hE '^[[:space:]]*(AddHandler|AddType)[[:space:]].*(php|lsphp)' "$HB" 2>/dev/null | head -2)
    fi
    cp "$SRC_PHP" "$DOCROOT/index.php" && ok "index.php deployed"
    if [ -f "$APP_DIR/scripts/apache-proxy/php-ini.txt" ]; then
      cp "$APP_DIR/scripts/apache-proxy/php-ini.txt" "$DOCROOT/.user.ini" \
        && ok ".user.ini deployed (post_max_size/upload_max_filesize = 64M)"
    fi
    if [ -n "$PHPLINE" ]; then
      { printf '%s\n\n' "$PHPLINE"; cat "$SRC_HT"; } > "$DOCROOT/.htaccess"
      ok ".htaccess deployed (host PHP handler preserved)"
    else
      cp "$SRC_HT" "$DOCROOT/.htaccess" && ok ".htaccess deployed (proxy rules)"
    fi
    chmod 644 "$DOCROOT/index.php" "$DOCROOT/.htaccess" 2>/dev/null
  fi
else
  bad "cannot deploy the proxy (docroot or source missing)"
fi

# ---------------------------------------------------------------- 3 wsgi server
step "3/7 WSGI server on 127.0.0.1:$PORT"
if [ "$APPLY" -eq 1 ]; then
  bash "$APP_DIR/scripts/serve_gunicorn.sh" restart 2>&1 | sed 's/^/  | /'
else
  plan "bash $APP_DIR/scripts/serve_gunicorn.sh restart"
fi

# ---------------------------------------------------------------- 4 loopback
step "4/7 loopback verification"
if [ "$APPLY" -eq 1 ]; then
  CODE=""
  for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    # X-Forwarded-Proto is what SECURE_PROXY_SSL_HEADER looks at: without it the
    # app answers 301 (redirect to https) and the probe reports a phantom failure.
    CODE=$(curl -s -o /tmp/recover_port.json -w '%{http_code}' --max-time 10 -H "Host: $DOMAIN" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:$PORT/api/v1/health/" 2>/dev/null)
    [ "$CODE" = "200" ] && break
    sleep 2
  done
  info "direct  : http://127.0.0.1:$PORT/api/v1/health/ (Host: $DOMAIN) -> $CODE"
  if [ "$CODE" = "200" ]; then ok "WSGI server answers 200"
  elif [ "$CODE" = "301" ]; then warn "WSGI answers 301 (https redirect) - check SECURE_PROXY_SSL_HEADER on this probe"
  else bad "WSGI server answers $CODE (see: bash scripts/serve_gunicorn.sh logs)"; fi

  VCODE=""
  for i in 1 2 3 4 5 6; do
    VCODE=$(curl -s -o /tmp/recover_vhost.json -w '%{http_code}' --max-time 20 -H "Host: $DOMAIN" "http://127.0.0.1/api/v1/health/" 2>/dev/null)
    [ "$VCODE" = "200" ] && break
    sleep 2
  done
  info "via host: http://127.0.0.1/api/v1/health/ (Host: $DOMAIN) -> $VCODE"
  if [ "$VCODE" = "200" ]; then
    ok "vhost + proxy + django chain is 200"
  else
    # A loopback request does not always hit the same vhost (SNI / listener bind)
    # - the public URL in step 5 is the source of truth, so this is a warning.
    warn "loopback through the vhost answers $VCODE - public URL is checked next"
  fi
else
  plan "curl loopback on port $PORT and through the vhost"
fi

# ---------------------------------------------------------------- 5 public
step "5/7 public HTTPS verification"
if [ "$APPLY" -eq 1 ]; then
  for path in /api/v1/health/ /api/v1/kindness-wall/stats/ /api/v1/geo/provinces/ /admin/login/; do
    C=""
    for i in 1 2 3 4 5 6; do
      C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$DOMAIN$path" 2>/dev/null)
      { [ "$C" = "200" ] || [ "$C" = "302" ]; } && break
      sleep 3
    done
    if [ "$C" = "200" ] || [ "$C" = "302" ]; then ok "https://$DOMAIN$path -> $C"; else bad "https://$DOMAIN$path -> $C"; fi
  done
  # end to end through the public frontend too
  C=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://besat.me/api/v1/health/" 2>/dev/null)
  info "https://besat.me/api/v1/health/ -> $C (through the Vercel proxy, 308 is normal)"

  # ─── THE credential test ────────────────────────────────────────────────
  # A bogus Bearer token must be REJECTED as a token ("token_not_valid"), not
  # ignored as "no credentials". If Django answers "no authentication
  # credentials were provided", the Authorization header was dropped somewhere
  # in the chain - and then every logged-in user is secretly anonymous, which
  # is exactly what made the SPA sign people out right after login.
  BODY=$(curl -s --max-time 25 -H "Authorization: Bearer audit.invalid.token" \
    "https://$DOMAIN/api/v1/auth/me/" 2>/dev/null)
  if printf '%s' "$BODY" | grep -qiE 'token_not_valid|not valid|نامعتبر|invalid'; then
    ok "Authorization header reaches Django (bogus token rejected as a token)"
  elif printf '%s' "$BODY" | grep -qiE 'ارسال نشده|not provided|credentials'; then
    bad "Authorization header is DROPPED in the chain - every logged-in user is anonymous"
    info "fix: make sure index.php (with incoming_header()) and .htaccess are the ones deployed here"
    info "then: bash scripts/host_web_recover.sh --apply"
  else
    warn "credential test inconclusive: $(printf '%s' "$BODY" | head -c 120)"
  fi

  # ─── POST body test ─────────────────────────────────────────────────────
  # Any JSON POST must reach Django's validator. If the proxy emits the
  # Content-Type header twice, LiteSpeed rejects the request before PHP with
  # `400 Invalid HTTP Header: 'CONTENT-TYPE'` - which used to look like a
  # mysterious "400 on login" in the browser console.
  POST_BODY=$(curl -sL --max-time 25 -X POST -H 'Content-Type: application/json' \
    -H 'Accept: application/json' -d '{}' "https://$DOMAIN/api/v1/auth/login/password/" 2>/dev/null)
  if printf '%s' "$POST_BODY" | grep -qi 'Invalid HTTP Header'; then
    bad "duplicate/malformed header on POST (proxy emits Content-Type twice?)"
    info "$(printf '%s' "$POST_BODY" | tr -d '\n' | head -c 120)"
  elif printf '%s' "$POST_BODY" | grep -qiE 'identifier|الزام|required'; then
    ok "POST body + Content-Type reach Django (validator answered)"
  else
    warn "POST test inconclusive: $(printf '%s' "$POST_BODY" | head -c 120)"
  fi
else
  plan "curl https://$DOMAIN/{health,stats,provinces,admin/login}"
fi

# ---------------------------------------------------------------- 6 cron
step "6/7 keep-alive cron"
CRON_LINE="* * * * * APP_DIR=$APP_DIR PORT=$PORT bash $APP_DIR/scripts/serve_gunicorn.sh start >/dev/null 2>&1"
if echo "$CRON" | grep -q "serve_gunicorn.sh start"; then
  ok "already installed"
elif [ "$APPLY" -eq 1 ]; then
  { printf '%s\n' "$CRON" | grep -v '^$'; echo "# besat: keep the WSGI server alive (restored by host_web_recover.sh)"; echo "$CRON_LINE"; } | crontab - && ok "installed (every minute, idempotent)"
else
  plan "install: $CRON_LINE"
fi

# ---------------------------------------------------------------- 7 backups
step "7/7 backup sanity (read-only)"
BK="$HOME/backups"
if [ -d "$BK" ]; then
  info "contents:"
  ls -l "$BK" 2>/dev/null | tail -12 | sed 's/^/       /'
  BAD_FILES=$(find "$BK" -type f -size -1k 2>/dev/null | wc -l | tr -d ' ')
  [ "${BAD_FILES:-0}" -gt 0 ] && bad "$BAD_FILES backup file(s) are (nearly) empty - rotation will keep them" || ok "no truncated backups"
else
  warn "no backups dir yet"
fi
DUMP_BIN=$(command -v mysqldump 2>/dev/null || echo "")
if [ -n "$DUMP_BIN" ]; then
  ok "mysqldump: $("$DUMP_BIN" --version 2>&1 | head -1)"
else
  bad "mysqldump NOT installed -> daily db backups are empty (20 bytes)"
  info "fix: a pure-python dump fallback (scripts/db_dump.py) - next step"
fi
if [ -f "$HOME/logs/backup.log" ]; then
  info "backup.log tail:"
  tail -6 "$HOME/logs/backup.log" 2>/dev/null | sed 's/^/       /'
fi

echo
echo "============================================================"
printf ' RESULT: %d failure(s), %d warning(s)\n' "$FAIL" "$WARN"
if [ "$APPLY" -eq 0 ]; then
  echo " next: re-run with --apply to rebuild the serving layer and verify"
else
  if [ "$FAIL" -eq 0 ]; then echo " state: serving layer restored and verified"
  else echo " next: fix the [!!] items above, then re-run --apply"; fi
fi
echo "============================================================"
exit 0
