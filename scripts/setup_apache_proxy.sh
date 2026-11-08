#!/usr/bin/env bash
# ============================================================================
#  setup_apache_proxy.sh - wire api.besat.me -> Django without Passenger
#
#  WHAT IT DOES (each step is idempotent and prints what it changed)
#    1) copies scripts/apache-proxy/index.php into the docroot
#    2) writes the proxy .htaccess (timestamped backup of the old one)
#    3) proves the WSGI app can be imported with production settings
#    4) installs gunicorn into the venv (falls back to stdlib if PyPI is blocked)
#    5) starts the WSGI server on 127.0.0.1:8765
#    6) runs a full loopback health check through the PHP proxy
#    7) installs a cron keep-alive (cron is the only supervisor we have)
#
#  USAGE
#      bash scripts/setup_apache_proxy.sh              # apply
#      bash scripts/setup_apache_proxy.sh --check      # diagnose only
#
#  ASCII-only output. Nothing is deleted: the previous .htaccess is backed up
#  and the old Passenger block is preserved inside that backup.
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
DOCROOT="${DOCROOT:-$HOME/public_html/api.besat.me}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
VENV_PIP="${VENV_PIP:-$HOME/virtualenv/apps/besat-backend/3.12/bin/pip}"
PORT="${PORT:-8765}"
CHECK_ONLY=0
for a in "$@"; do [ "$a" = "--check" ] && CHECK_ONLY=1; done

FAIL=0
step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; FAIL=$((FAIL+1)); }
warn() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }

echo "============================================================"
echo " besat apache proxy setup | $(date '+%Y-%m-%d %H:%M')"
echo " mode: $([ "$CHECK_ONLY" -eq 1 ] && echo CHECK || echo APPLY)"
echo "============================================================"

step "1/7 preflight"
info "user=$USER app=$APP_DIR"
info "docroot=$DOCROOT"
info "venv=$VENV_PY  port=$PORT"
[ -d "$APP_DIR" ] || { bad "app dir missing"; exit 1; }
[ -d "$DOCROOT" ] || { bad "docroot missing (create the subdomain first)"; exit 1; }
[ -x "$VENV_PY" ] || { bad "venv python missing"; exit 1; }
ok "paths look right"
cd "$APP_DIR" || exit 1

step "2/7 WSGI import test (production settings)"
if DJANGO_SETTINGS_MODULE=config.settings.production "$VENV_PY" -c "
import django; django.setup()
from django.core.wsgi import get_wsgi_application
get_wsgi_application()
print('IMPORT_OK')
" 2>/tmp/wsgi_probe.txt | grep -q IMPORT_OK; then
  ok "Django WSGI app builds with production settings"
else
  bad "WSGI import failed - real error:"
  tail -15 /tmp/wsgi_probe.txt | sed 's/^/       /'
fi

step "3/7 gunicorn (preferred) "
if "$VENV_PY" -c "import gunicorn" >/dev/null 2>&1; then
  ok "gunicorn already installed"
elif [ "$CHECK_ONLY" -eq 1 ]; then
  warn "gunicorn not installed (would install on APPLY)"
else
  info "installing gunicorn from PyPI ..."
  if "$VENV_PIP" install --quiet --disable-pip-version-check gunicorn 2>/tmp/pip_g.txt; then
    ok "gunicorn installed: $("$VENV_PY" -m gunicorn --version 2>&1 | head -1)"
  else
    warn "could not install gunicorn -> will use the stdlib fallback server"
    tail -5 /tmp/pip_g.txt | sed 's/^/       /'
  fi
fi

step "4/7 PHP proxy into the docroot"
if [ "$CHECK_ONLY" -eq 1 ]; then
  info "would copy scripts/apache-proxy/index.php -> $DOCROOT/index.php"
else
  cp scripts/apache-proxy/index.php "$DOCROOT/index.php" && ok "index.php deployed"
  [ -f "$DOCROOT/.htaccess" ] && cp "$DOCROOT/.htaccess" "$DOCROOT/.htaccess.bak.$(date +%s)" && info "old .htaccess backed up"
  cp scripts/apache-proxy/htaccess.txt "$DOCROOT/.htaccess" && ok ".htaccess written (proxy rules)"
  chmod 644 "$DOCROOT/index.php" "$DOCROOT/.htaccess"
fi

step "5/7 WSGI server (127.0.0.1:$PORT)"
if [ "$CHECK_ONLY" -eq 1 ]; then
  bash scripts/serve_gunicorn.sh status
else
  bash scripts/serve_gunicorn.sh restart
fi

step "6/7 loopback health check through the proxy"
if [ "$CHECK_ONLY" -eq 0 ]; then
  sleep 1
  CODE=$(curl -s -o /tmp/hc.json -w '%{http_code}' --max-time 25 -H 'Host: api.besat.me' "http://127.0.0.1/api/v1/health/" 2>/dev/null)
  info "Apache+PHP -> Django -> HTTP $CODE"
  head -c 200 /tmp/hc.json | sed 's/^/       /'
  echo
  [ "$CODE" = "200" ] && ok "end-to-end health is 200" || bad "end-to-end health is $CODE"
fi

step "7/7 cron keep-alive + log rotation"
CRON_LINE="* * * * * APP_DIR=$APP_DIR PORT=$PORT bash $APP_DIR/scripts/serve_gunicorn.sh start >/dev/null 2>&1"
if [ "$CHECK_ONLY" -eq 1 ]; then
  info "would ensure: $CRON_LINE"
else
  CURRENT=$(crontab -l 2>/dev/null || true)
  if echo "$CURRENT" | grep -q "serve_gunicorn.sh start"; then
    ok "cron keep-alive already present"
  else
    { echo "$CURRENT"; echo "# besat: keep the WSGI server alive (added by setup_apache_proxy.sh)"; echo "$CRON_LINE"; } | crontab -
    ok "cron keep-alive installed (runs every minute, idempotent)"
  fi
fi

echo
if [ "$FAIL" -eq 0 ]; then
  echo " RESULT: all green."
  echo " NEXT  : point DNS/SSL at this host, then check https://api.besat.me/api/v1/health/"
else
  echo " RESULT: $FAIL issue(s) above."
  echo " Send the full output back."
fi
exit 0
