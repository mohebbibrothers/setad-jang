#!/usr/bin/env bash
# ============================================================
# Setad Jang — Container entrypoint
# ============================================================
# مدل اجرا:
#   - container معمولاً به‌عنوان root شروع می‌شود.
#   - entrypoint مالکیت named volumes را correct می‌کند تا user app
#     بتواند به آن‌ها بنویسد.
#   - سپس با `gosu` به user app drop می‌شود و CMD اجرا می‌شود.
#
# hardening:
#   - اگر container به هر دلیل root نباشد، entrypoint نباید بشکند.
#   - در rootless mode، مراحل bootstrap تا حد ممکن با همان user فعلی
#     اجرا می‌شوند و فقط ownership fix skip می‌شود.
#
# مراحل bootstrap:
#   1. ownership/writable پوشه‌های state را آماده کن (در صورت root بودن).
#   2. صبر برای Redis (در صورت تنظیم REDIS_URL).
#   3. opt-in: migrations.
#   4. opt-in: collectstatic.
#   5. hand over control to CMD (با privilege drop در صورت نیاز)
# ============================================================

set -euo pipefail

APP_USER="${APP_USER:-app}"
APP_GROUP="${APP_GROUP:-app}"

log() {
  printf "[entrypoint] %s\n" "$*"
}

is_root() {
  [ "$(id -u)" -eq 0 ]
}

has_gosu() {
  command -v gosu >/dev/null 2>&1
}

# ------------------------------------------------------------
# Helper: اجرای دستور به‌عنوان app اگر root هستیم،
# و در غیر این صورت با همان user فعلی.
#
# نکتهٔ حیاتی: این helper برای مراحل bootstrap است و باید **برگردد**،
# پس نباید exec کند. برای تحویل نهایی کنترل به CMD از
# `exec_as_app_or_fail` استفاده می‌شود که فرآیند را جایگزین می‌کند.
# ------------------------------------------------------------
as_app() {
  if is_root; then
    run_gosu_or_fail "$@"
  else
    "$@"
  fi
}

require_gosu() {
  if ! has_gosu; then
    log "ERROR: gosu is required for root-mode privilege dropping but was not found."
    exit 1
  fi
}

# اجرای یک مرحلهٔ bootstrap با کاربر app و بازگشت به entrypoint.
run_gosu_or_fail() {
  require_gosu
  gosu "${APP_USER}:${APP_GROUP}" "$@"
}

# ------------------------------------------------------------
# تحویل نهایی کنترل به CMD با drop کردن سطح دسترسی.
#
# چرا `exec` اینجا حیاتی است:
#   بدون exec، درخت پروسه به این شکل در می‌آمد:
#
#       PID 1  tini
#         └─ PID 7  bash (entrypoint.sh)
#              └─ PID 12 gosu
#                   └─ PID 13 gunicorn
#
#   tini سیگنال SIGTERM را فقط به فرزند مستقیمش (bash) می‌دهد و bash در
#   حالت non-interactive سیگنال را به فرزند foreground خود forward
#   نمی‌کند. نتیجه: gunicorn هرگز SIGTERM نمی‌گرفت، بعد از پایان مهلت
#   داکر با SIGKILL کشته می‌شد و تمام requestهای در حال پردازش — از جمله
#   callback تأیید پرداخت — وسط کار قطع می‌شدند. یعنی هر deploy ریسک
#   تراکنش نیمه‌کاره داشت.
#
#   با exec، دیگر bash و gosu در مسیر سیگنال نیستند و PID فرآیند نهایی
#   مستقیماً فرزند tini است، پس graceful shutdown درست کار می‌کند.
# ------------------------------------------------------------
exec_as_app_or_fail() {
  require_gosu
  exec gosu "${APP_USER}:${APP_GROUP}" "$@"
}

# ------------------------------------------------------------
# 0) آماده‌سازی پوشه‌های writable روی named volumes (فقط در root mode)
# ------------------------------------------------------------
prepare_writable_dirs() {
  local dirs=(
    "/app/data"
    "/app/data/beat"
    "/app/staticfiles"
    "/app/media"
  )

  for d in "${dirs[@]}"; do
    mkdir -p "${d}"
    chown -R "${APP_USER}:${APP_GROUP}" "${d}"
    chmod -R u+rwX "${d}"
  done

  log "Writable dirs prepared and chowned to ${APP_USER}:${APP_GROUP}."
}

# ------------------------------------------------------------
# 1) Wait for Redis
# ------------------------------------------------------------
wait_for_redis() {
  if [ -z "${REDIS_URL:-}" ]; then
    log "REDIS_URL is not set — skipping Redis readiness check."
    return 0
  fi

  local max_attempts="${REDIS_WAIT_MAX_ATTEMPTS:-30}"
  local sleep_seconds="${REDIS_WAIT_SLEEP_SECONDS:-1}"
  local attempt=1

  log "Waiting for Redis at ${REDIS_URL} ..."
  while [ "${attempt}" -le "${max_attempts}" ]; do
    if as_app python - <<'PY' >/dev/null 2>&1
import os
import sys
import redis

url = os.environ["REDIS_URL"]
client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)

try:
    if client.ping():
        sys.exit(0)
    sys.exit(1)
except Exception:
    sys.exit(1)
PY
    then
      log "Redis is reachable."
      return 0
    fi

    log "Redis not ready yet (attempt ${attempt}/${max_attempts}). Sleeping ${sleep_seconds}s..."
    attempt=$((attempt + 1))
    sleep "${sleep_seconds}"
  done

  log "ERROR: Redis did not become ready in time."
  return 1
}

# ------------------------------------------------------------
# 2) Migrations (opt-in)
# ------------------------------------------------------------
run_migrations() {
  if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    log "Running database migrations..."
    as_app python manage.py migrate --noinput
  else
    log "RUN_MIGRATIONS != 1 — skipping migrations."
  fi
}

# ------------------------------------------------------------
# 3) Collectstatic (opt-in)
# ------------------------------------------------------------
run_collectstatic() {
  if [ "${RUN_COLLECTSTATIC:-0}" = "1" ]; then
    log "Collecting static files..."
    as_app python manage.py collectstatic --noinput --clear
  else
    log "RUN_COLLECTSTATIC != 1 — skipping collectstatic."
  fi
}

# ------------------------------------------------------------
# Main
# ------------------------------------------------------------
log "Starting entrypoint as $(id -un) with command: $*"

if is_root; then
  prepare_writable_dirs
else
  log "WARN: entrypoint is not running as root; ownership fix will be skipped."
fi

wait_for_redis
run_migrations
run_collectstatic

if is_root; then
  log "Bootstrap finished. Dropping privileges to ${APP_USER} and handing over control to CMD..."
  exec_as_app_or_fail "$@"
else
  log "Bootstrap finished. Running CMD as current non-root user: $(id -un)"
  exec "$@"
fi