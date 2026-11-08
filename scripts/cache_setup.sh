#!/usr/bin/env bash
# ============================================================================
#  cache_setup.sh - give the app a WORKING cache, and never leave it unable to boot
#
#  WHY THIS EXISTS (and why v1 was dangerous)
#  ------------------------------------------
#  The host has CACHE_BACKEND=redis pointing at redis://127.0.0.1:6379/1 with
#  nothing listening. The site survives it (IGNORE_EXCEPTIONS + database
#  fallback) but it is degraded: every cache hit becomes a query and DRF
#  throttles stop counting.
#
#  v1 of this script "fixed" that by switching CACHE_BACKEND to locmem - which
#  production.py explicitly forbids (it raises at import). The result was a 502
#  on the whole site: a config change that cannot boot. That bug is why every
#  write in this version is followed by a BOOT TEST and an AUTOMATIC ROLLBACK.
#
#  MODES
#      bash scripts/cache_setup.sh                 # diagnose + plan (no writes)
#      bash scripts/cache_setup.sh --apply         # fix it, verify, auto-rollback
#      bash scripts/cache_setup.sh --apply --allow-locmem
#                                                 # conscious fallback: writes
#                                                 # CACHE_BACKEND=locmem AND
#                                                 # ALLOW_LOCMEM_CACHE=True
#      bash scripts/cache_setup.sh --rollback      # EMERGENCY: back to redis now
#
#  ORDER OF PREFERENCE
#      1  an already-running Redis
#      2  a redis-server binary found on PATH or in the usual cPanel locations
#         (started with a local-only config + a cron keep-alive)
#      3  --allow-locmem  (degraded but bootable, explicitly accepted)
#      4  otherwise: change nothing, and print exactly what to ask the provider
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
SETTINGS="${SETTINGS:-config.settings.production}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DIR="${REDIS_DIR:-$HOME/.redis}"

APPLY=0
ALLOW_LOCMEM=0
ROLLBACK=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --allow-locmem) ALLOW_LOCMEM=1 ;;
    --rollback) ROLLBACK=1; APPLY=1 ;;
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
if [ "$ROLLBACK" -eq 1 ]; then echo " mode: ROLLBACK (back to redis)"
elif [ "$APPLY" -eq 1 ]; then echo " mode: APPLY"
else echo " mode: DRY RUN (add --apply)"; fi
echo "============================================================"

# ------------------------------------------------------------ helpers
port_open() {
  (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null && { exec 3<&- 2>/dev/null; exec 3>&- 2>/dev/null; return 0; }
  return 1
}

# Does the app still boot with the config currently on disk?
boot_ok() {
  ( cd "$APP_DIR" && DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" -c "
import django
django.setup()
print('BOOT_OK', django.conf.settings.CACHES['default']['BACKEND'])
" ) 2>/tmp/besat_boot.err | grep -q BOOT_OK
}

first_boot_error() {
  grep -vE 'clselect|WrongData|set_env_vars|site-packages/clselect|^Traceback|^  File|^    ' /tmp/besat_boot.err \
    | grep -E 'Error|error' | tail -1
}

set_env() { # key=value ...
  "$VENV_PY" scripts/env_set.py "$@" 2>&1 | grep -E '^\s+\[(ok|--|!!)\]' | sed 's/^/       /'
}

restart_app() {
  [ -x scripts/serve_gunicorn.sh ] && bash scripts/serve_gunicorn.sh restart >/dev/null 2>&1
  mkdir -p tmp && touch tmp/restart.txt
}

# ------------------------------------------------------------ 0 rollback
if [ "$ROLLBACK" -eq 1 ]; then
  step "ROLLBACK -> CACHE_BACKEND=redis (the only value production accepts)"
  set_env --section "cache" "CACHE_BACKEND=redis" "REDIS_URL=redis://127.0.0.1:$REDIS_PORT/1"
  if boot_ok; then
    ok "app boots again with $(DJANGO_SETTINGS_MODULE=$SETTINGS $VENV_PY -c "import django;django.setup();print(django.conf.settings.CACHES['default']['BACKEND'])" 2>/dev/null)"
    restart_app && ok "application restarted"
    info "redis itself is still absent; the app tolerates that (IGNORE_EXCEPTIONS)."
    info "to remove the degradation: bash scripts/cache_setup.sh --apply"
  else
    bad "still not booting:"
    first_boot_error | sed 's/^/       /'
  fi
  exit 0
fi

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
print(f"       allow locmem flag : {getattr(settings, 'ALLOW_LOCMEM_CACHE', 'n/a')}")
PY
if boot_ok; then ok "app boots with the current config"; else
  bad "app does NOT boot with the current config:"
  first_boot_error | sed 's/^/       /'
  info "emergency fix: bash scripts/cache_setup.sh --rollback"
fi

# ------------------------------------------------------------------ 2 probe
step "2/6 is redis reachable today?"
if port_open "$REDIS_PORT"; then ok "redis is listening on 127.0.0.1:$REDIS_PORT"; REDIS_UP=1
else bad "nothing is listening on 127.0.0.1:$REDIS_PORT"; REDIS_UP=0; fi

# ------------------------------------------------------------------ 3 binary
step "3/6 looking for a redis server binary"
REDIS_BIN=""
for candidate in \
  "$(command -v redis-server 2>/dev/null || true)" \
  /usr/local/bin/redis-server \
  /usr/bin/redis-server \
  /opt/redis/bin/redis-server \
  "$HOME/bin/redis-server" \
  /usr/local/redis/bin/redis-server
do
  if [ -n "$candidate" ] && [ -x "$candidate" ]; then REDIS_BIN="$candidate"; break; fi
done
if [ -n "$REDIS_BIN" ]; then ok "found: $REDIS_BIN"; else warn "no redis-server binary anywhere obvious"; fi

# ------------------------------------------------------------------ 4 decide
step "4/6 decision"
if [ "$REDIS_UP" -eq 1 ]; then
  ok "nothing to install"
  ACTION="none"
elif [ -n "$REDIS_BIN" ]; then
  ok "a binary exists -> start a private redis for this account"
  ACTION="start-redis"
elif [ "$ALLOW_LOCMEM" -eq 1 ]; then
  warn "--allow-locmem given -> switch to locmem WITH the explicit escape hatch"
  ACTION="locmem"
else
  warn "no Redis and no binary: NOT changing anything (a config that cannot boot is worse)"
  info "two honest options:"
  info "  1) ask the provider to enable Redis for this account (best: throttles and"
  info "     cache invalidation work as designed) - keep this script for later"
  info "  2) accept the degraded mode on purpose: bash scripts/cache_setup.sh --apply --allow-locmem"
  ACTION="none"
fi

# ------------------------------------------------------------------ 5 apply
step "5/6 applying"
case "$ACTION" in
  none) ok "no change" ;;
  start-redis)
    mkdir -p "$REDIS_DIR"
    if [ "$APPLY" -eq 1 ]; then
      printf 'port %s\nbind 127.0.0.1\nprotected-mode yes\ndaemonize yes\nsave ""\nappendonly no\nmaxmemory 64mb\nmaxmemory-policy allkeys-lru\ndir %s\nlogfile %s/redis.log\n' \
        "$REDIS_PORT" "$REDIS_DIR" "$REDIS_DIR" > "$REDIS_DIR/redis.conf"
      ok "wrote $REDIS_DIR/redis.conf (localhost only, no persistence, 64MB LRU)"
      "$REDIS_BIN" "$REDIS_DIR/redis.conf" 2>>"$REDIS_DIR/redis.log" || true
      sleep 1
      if port_open "$REDIS_PORT"; then ok "redis is up on 127.0.0.1:$REDIS_PORT"
      else bad "redis did not open the port (see $REDIS_DIR/redis.log)"; tail -3 "$REDIS_DIR/redis.log" 2>/dev/null | sed 's/^/       /'; fi
      CRON=$(crontab -l 2>/dev/null || true)
      KEEP="*/5 * * * * REDIS_PORT=$REDIS_PORT REDIS_DIR=$REDIS_DIR bash $APP_DIR/scripts/redis_keepalive.sh >/dev/null 2>&1"
      if echo "$CRON" | grep -q "redis_keepalive.sh"; then ok "keep-alive cron already present"
      else
        { printf '%s\n' "$CRON" | grep -v '^$'; echo "# besat: keep the local redis alive (added by cache_setup.sh)"; echo "$KEEP"; } | crontab - \
          && ok "keep-alive cron installed (every 5 min)"
      fi
      set_env --section "cache" "CACHE_BACKEND=redis" "REDIS_URL=redis://127.0.0.1:$REDIS_PORT/1"
    else
      info "would start $REDIS_BIN with $REDIS_DIR/redis.conf + a keep-alive cron"
      info "would ensure CACHE_BACKEND=redis REDIS_URL=redis://127.0.0.1:$REDIS_PORT/1"
    fi
    ;;
  locmem)
    if [ "$APPLY" -eq 1 ]; then
      set_env --section "cache" "CACHE_BACKEND=locmem" "ALLOW_LOCMEM_CACHE=True"
      ok "CACHE_BACKEND=locmem + ALLOW_LOCMEM_CACHE=True (both, or the app refuses to boot)"
    else
      info "would set CACHE_BACKEND=locmem AND ALLOW_LOCMEM_CACHE=True"
    fi
    ;;
esac

# ------------------------------------------------------------------ 6 verify
step "6/6 verification (boot test first, then a real set/get)"
if [ "$APPLY" -eq 1 ] && [ "$ACTION" != "none" ]; then
  if boot_ok; then
    ok "app boots with the new config"
  else
    bad "the new config does not boot -> ROLLING BACK automatically"
    first_boot_error | sed 's/^/       /'
    set_env --section "cache" "CACHE_BACKEND=redis" "REDIS_URL=redis://127.0.0.1:$REDIS_PORT/1"
    if boot_ok; then ok "rolled back: the app boots again"; else bad "rollback failed too - run --rollback by hand"; fi
    exit 1
  fi
  restart_app && ok "application restarted"
  DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - <<'PY' 2>&1 | grep -E 'backend|RESULT' | sed 's/^/       /'
import time

import django

django.setup()
from django.conf import settings
from django.core.cache import cache

cfg = settings.CACHES["default"]
print(f"backend : {cfg['BACKEND']}")
started = time.monotonic()
cache.set("besat:cache_setup", {"ok": True}, timeout=30)
value = cache.get("besat:cache_setup")
elapsed = (time.monotonic() - started) * 1000
cache.delete("besat:cache_setup")
if value == {"ok": True}:
    print(f"RESULT: cache WORKS · round-trip {elapsed:.1f} ms")
elif "redis" in cfg["BACKEND"]:
    print("RESULT: cache DEGRADED (redis absent, writes swallowed) - site is fine, throttle is not")
else:
    print("RESULT: cache works per-process (locmem)")
PY
else
  info "nothing written - dry run or no safe action"
fi

echo
echo "============================================================"
echo " Emergency command (any time): bash scripts/cache_setup.sh --rollback"
echo "============================================================"
