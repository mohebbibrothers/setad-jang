#!/usr/bin/env bash
# ============================================================================
#  cache_setup.sh - give the app a WORKING cache (Redis if possible, else locmem)
#
#  WHY THIS EXISTS
#  ---------------
#  The live host has CACHE_BACKEND=redis pointing at redis://127.0.0.1:6379/1,
#  but nothing is listening there:
#
#      redis NOT reachable ([Errno 111] Connection refused)
#
#  The application survives it (both the Django settings and django_redis are
#  configured to swallow connection errors, and the auth session check falls
#  back to a database read), so this is not an outage - it is a slow, noisy,
#  half-broken deployment:
#
#      • every cache hit becomes a database query (page latency)
#      • DRF throttling silently stops counting (rate limits stop existing)
#      • each request logs a full ConnectionInterrupted traceback
#
#  This script fixes it properly, in this order of preference:
#
#      1  start a local Redis on 127.0.0.1:6379 (if the host ships redis-server)
#         + a keep-alive cron so it survives crashes and reboots
#      2  if there is no redis binary, verify a unix socket / alternate port
#      3  otherwise switch CACHE_BACKEND to locmem (per-process, honest) so the
#         deployment is at least consistent and quiet
#      4  always: prove it with a real set/get through Django, then report
#
#  USAGE
#      bash scripts/cache_setup.sh            # diagnose + plan
#      bash scripts/cache_setup.sh --apply    # do it and verify
#      bash scripts/cache_setup.sh --apply --locmem   # force the fallback
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
SETTINGS="${SETTINGS:-config.settings.production}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DIR="${REDIS_DIR:-$HOME/.redis}"

APPLY=0
FORCE_LOCMEM=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --locmem) FORCE_LOCMEM=1 ;;
  esac
done

step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
warn() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }

cd "$APP_DIR" || { echo "app dir not found: $APP_DIR"; exit 1; }

echo "============================================================"
echo " besat cache setup | $(date '+%Y-%m-%d %H:%M') | user=$USER"
echo " mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo 'DRY RUN (add --apply)')"
echo "============================================================"

# ------------------------------------------------------------------ 1 settings
step "1/6 what the app is configured to use"
DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - 2>/dev/null <<'PY'
import django
django.setup()
from django.conf import settings
cfg = settings.CACHES["default"]
print(f"       CACHE_BACKEND env : {settings.CACHE_BACKEND}")
print(f"       backend           : {cfg['BACKEND']}")
print(f"       location          : {cfg['LOCATION']}")
opts = cfg.get("OPTIONS", {})
print(f"       ignore exceptions : {opts.get('IGNORE_EXCEPTIONS', getattr(settings, 'DJANGO_REDIS_IGNORE_EXCEPTIONS', None))}")
PY

# ------------------------------------------------------------------ 2 tcp probe
probe_port() { # host port -> prints "open"/"closed"
  local host="${1:-127.0.0.1}" port="${2:-$REDIS_PORT}"
  if "$VENV_PY" - "$host" "$port" <<'PY' 2>/dev/null
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=2):
        print("open")
except OSError:
    print("closed")
PY
  then :; fi
}

step "2/6 is redis reachable today?"
STATE=$(probe_port 127.0.0.1 "$REDIS_PORT")
if [ "$STATE" = "open" ]; then
  ok "redis is listening on 127.0.0.1:$REDIS_PORT"
  REDIS_UP=1
else
  bad "nothing is listening on 127.0.0.1:$REDIS_PORT"
  REDIS_UP=0
fi

# ------------------------------------------------------------------ 3 binaries
step "3/6 what this host gives us to work with"
for candidate in redis-server redis-cli; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ok "$candidate: $(command -v "$candidate")"
  else
    warn "$candidate: not installed"
  fi
done
for sock in "$HOME/.redis/redis.sock" /tmp/redis.sock /var/run/redis/redis.sock; do
  [ -S "$sock" ] && info "unix socket found: $sock"
done
info "PHP redis extension: $(php -m 2>/dev/null | grep -ci '^redis$' || echo 0)"

# ------------------------------------------------------------------ 4 decide
step "4/6 decision"
if [ "$REDIS_UP" -eq 1 ]; then
  ok "nothing to install - redis is already serving this app"
  ACTION="none"
elif [ "$FORCE_LOCMEM" -eq 1 ]; then
  warn "forced fallback: CACHE_BACKEND=locmem"
  ACTION="locmem"
elif command -v redis-server >/dev/null 2>&1; then
  ok "redis-server exists -> start a private instance for this account"
  ACTION="start-redis"
else
  warn "no redis binary -> fall back to locmem (consistent, quiet, per-process)"
  ACTION="locmem"
fi

# ------------------------------------------------------------------ 5 apply
step "5/6 applying"
case "$ACTION" in
  none)
    ok "no change needed"
    ;;
  start-redis)
    mkdir -p "$REDIS_DIR"
    if [ "$APPLY" -eq 1 ]; then
      printf 'port %s\nbind 127.0.0.1\nprotected-mode yes\ndaemonize yes\nsave ""\nappendonly no\nmaxmemory 64mb\nmaxmemory-policy allkeys-lru\ndir %s\nlogfile %s/redis.log\n' \
        "$REDIS_PORT" "$REDIS_DIR" "$REDIS_DIR" > "$REDIS_DIR/redis.conf"
      ok "wrote $REDIS_DIR/redis.conf (localhost only, no persistence, 64MB LRU)"
      if redis-server "$REDIS_DIR/redis.conf" 2>>"$REDIS_DIR/redis.log"; then
        sleep 1
        if [ "$(probe_port 127.0.0.1 "$REDIS_PORT")" = "open" ]; then
          ok "redis is up on 127.0.0.1:$REDIS_PORT"
        else
          bad "redis did not open the port - see $REDIS_DIR/redis.log"
          tail -5 "$REDIS_DIR/redis.log" 2>/dev/null | sed 's/^/       /'
        fi
      else
        bad "redis-server refused to start - see $REDIS_DIR/redis.log"
        tail -5 "$REDIS_DIR/redis.log" 2>/dev/null | sed 's/^/       /'
      fi
      # keep-alive: no systemd for the account -> cron is the supervisor. The
      # logic lives in scripts/redis_keepalive.sh because a crontab entry must
      # stay a SINGLE line (a heredoc inside crontab silently becomes two jobs).
      CRON=$(crontab -l 2>/dev/null || true)
      KEEP="*/5 * * * * REDIS_PORT=$REDIS_PORT REDIS_DIR=$REDIS_DIR bash $APP_DIR/scripts/redis_keepalive.sh >/dev/null 2>&1"
      if echo "$CRON" | grep -q "redis_keepalive.sh"; then
        ok "redis keep-alive cron already present"
      else
        { printf '%s\n' "$CRON" | grep -v '^$'; echo "# besat: keep the local redis alive (added by cache_setup.sh)"; echo "$KEEP"; } | crontab - \
          && ok "keep-alive cron installed (every 5 min, idempotent)"
      fi
      # make sure the app points at the same URL
      "$VENV_PY" scripts/env_set.py --section "cache" "CACHE_BACKEND=redis" "REDIS_URL=redis://127.0.0.1:$REDIS_PORT/1" 2>&1 | sed 's/^/       /'
    else
      info "would write $REDIS_DIR/redis.conf, start redis, add a keep-alive cron"
      info "would ensure CACHE_BACKEND=redis REDIS_URL=redis://127.0.0.1:$REDIS_PORT/1"
    fi
    ;;
  locmem)
    if [ "$APPLY" -eq 1 ]; then
      if [ -f scripts/env_set.py ]; then
        "$VENV_PY" scripts/env_set.py --section "cache" "CACHE_BACKEND=locmem" 2>&1 | sed 's/^/       /'
        ok "CACHE_BACKEND=locmem written (no Redis binary on this host)"
        info "trade-off: cache is per worker process; the auth session check still"
        info "falls back to the database, so correctness is unchanged - only hit rate."
      else
        bad "scripts/env_set.py missing (git pull)"
      fi
    else
      info "would set CACHE_BACKEND=locmem in .env"
    fi
    ;;
esac

# ------------------------------------------------------------------ 6 verify
step "6/6 verification through Django (the only verdict that counts)"
if [ "$APPLY" -eq 1 ]; then
  bash scripts/serve_gunicorn.sh restart >/dev/null 2>&1 || true
  DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - <<'PY' 2>&1 | grep -vE 'Exception ignored|clselect|WrongData|^  File |^    |^Traceback|^\w+Error|^\w+\.' | sed 's/^/       /'
import time

import django

django.setup()
from django.conf import settings
from django.core.cache import cache

cfg = settings.CACHES["default"]
print(f"backend : {cfg['BACKEND']}")
print(f"location: {cfg['LOCATION']}")
started = time.monotonic()
cache.set("besat:cache_setup", {"ok": True}, timeout=30)
value = cache.get("besat:cache_setup")
elapsed = (time.monotonic() - started) * 1000
cache.delete("besat:cache_setup")
if value == {"ok": True}:
    print(f"RESULT: OK  round-trip {elapsed:.1f} ms")
else:
    print(f"RESULT: BROKEN (got {value!r}) - cache is refusing writes")
PY
else
  info "run with --apply to execute and verify"
fi

echo
echo "============================================================"
if [ "$APPLY" -eq 0 ]; then
  echo " DRY RUN - re-run with --apply"
else
  echo " Done. The next host_doctor run should show a healthy cache."
fi
echo "============================================================"
