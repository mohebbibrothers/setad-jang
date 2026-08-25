#!/usr/bin/env bash
# ==============================================================================
#  besat.me — Backend one-command updater
#  ---------------------------------------------------------------------------
#  یک خط، و بک‌اند سایت آپدیت می‌شود:
#
#      ./update-back.sh
#
#  چرخه‌ی کامل:
#    fetch → sync → snapshot ایمیجِ فعلی → build → up (web/worker/beat/flower)
#          → health-check → rollback خودکار ایمیج در صورت هر خطا
#
#  فلسفه‌ی طراحی (هم‌خانواده با update-front.sh):
#    • سرویس هرگز در وضعیت نیمه‌کاره رها نمی‌شود (snapshot تگ + rollback خودکار)
#    • مایگریشن‌ها خودکار توسط entrypoint وب اجرا می‌شوند (RUN_MIGRATIONS=1)
#    • قفل flock: دو دیپلوی همزمان غیرممکن است
#    • فایل .env و volumeهای داده (postgres_data, media_data, …) دست نمی‌خورند
#    • هر اجرا لاگ کامل در .deploy/logs/ ذخیره می‌کند
#
#  Besat DevOps · https://besat.me
# ==============================================================================

set -Eeuo pipefail
shopt -s inherit_errexit 2>/dev/null || true
umask 022

readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_PATH="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/$(basename -- "${BASH_SOURCE[0]}")"
readonly SCRIPT_DIR="$(dirname -- "$SCRIPT_PATH")"
readonly SCRIPT_NAME="$(basename -- "$SCRIPT_PATH")"
readonly START_EPOCH=$SECONDS

# ──────────────────────────────────────────────────────────────────────────────
#  پیکربندی — هر مقدار با متغیر محیطی قابل override است
# ──────────────────────────────────────────────────────────────────────────────
REPO_URL="${REPO_URL:-https://github.com/mohebbibrothers/setad-jang.git}"
APP_DIR="${APP_DIR:-}"                          # خالی = پوشه‌ی خودِ اسکریپت
BRANCH="${BRANCH:-main}"
REMOTE="${REMOTE:-origin}"

IMAGE_NAME="${IMAGE_NAME:-setadjang:latest}"    # تگِ بیلدشده‌ی compose
ROLLBACK_TAG="${ROLLBACK_TAG:-setadjang:rollback}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-setadjang}" # name: در docker-compose.yml
WEB_SERVICE="${WEB_SERVICE:-web}"

LOCAL_HEALTH_URL="${LOCAL_HEALTH_URL:-http://127.0.0.1:8000/api/v1/health/}"
PUBLIC_HEALTH_URL="${PUBLIC_HEALTH_URL:-https://besat.me/api/v1/health/}"

HEALTH_RETRIES="${HEALTH_RETRIES:-40}"          # 40 × 3s → تا ۱۲۰ ثانیه صبر
HEALTH_INTERVAL="${HEALTH_INTERVAL:-3}"
PUBLIC_HEALTH_REQUIRED="${PUBLIC_HEALTH_REQUIRED:-0}"
KEEP_LOGS="${KEEP_LOGS:-20}"

FORCE=0; DRY_RUN=0; SKIP_HEALTH=0; DO_ROLLBACK=0; SHOW_STATUS=0; QUIET=0; SKIP_BUILD=0
ORIGINAL_ARGS=("$@")                            # برای re-exec زیر flock

# ──────────────────────────────────────────────────────────────────────────────
#  خروجی
# ──────────────────────────────────────────────────────────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  B=$'\033[1m'; D=$'\033[2m'; R=$'\033[0m'
  RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; BLU=$'\033[34m'; CYN=$'\033[36m'
else
  B=""; D=""; R=""; RED=""; GRN=""; YLW=""; BLU=""; CYN=""
fi

_ts()  { date '+%H:%M:%S'; }
log()  { ((QUIET)) || printf '%s  %s\n'       "${D}$(_ts)${R}" "$*"; }
ok()   { ((QUIET)) || printf '%s  %s✔%s %s\n' "${D}$(_ts)${R}" "$GRN" "$R" "$*"; }
warn() {              printf '%s  %s!%s %s\n' "${D}$(_ts)${R}" "$YLW" "$R" "$*" >&2; }
err()  {              printf '%s  %s✘%s %s\n' "${D}$(_ts)${R}" "$RED" "$R" "$*" >&2; }
die()  { err "$*"; exit 1; }
step() { ((++STEP_NO)); printf '\n%s%s━━ قدم %s: %s%s\n' "$B" "$BLU" "$STEP_NO" "$*" "$R"; }
STEP_NO=0

usage() {
  cat <<EOF
${B}$SCRIPT_NAME${R} — آپدیت یک‌دستوریِ بک‌اند besat.me (نسخه $SCRIPT_VERSION)

استفاده:
  ./$SCRIPT_NAME                 آپدیت کامل (پیش‌فرض)
  ./$SCRIPT_NAME --status        فقط گزارش وضعیت سرویس‌ها
  ./$SCRIPT_NAME --rollback      برگشت فوری به ایمیجِ قبلی
  ./$SCRIPT_NAME --no-health     از health-check صرف‌نظر کن
  ./$SCRIPT_NAME --skip-build    بدون build — فقط sync + up (سریع)
  ./$SCRIPT_NAME --dry-run       بدون اعمال تغییر واقعی
  ./$SCRIPT_NAME -q | --quiet    خروجی حداقلی

متغیرهای کلیدی:
  LOCAL_HEALTH_URL=…  PUBLIC_HEALTH_URL=…  PUBLIC_HEALTH_REQUIRED=1
  IMAGE_NAME=…  ROLLBACK_TAG=…  COMPOSE_PROJECT=…  BRANCH=…
EOF
}

# ──────────────────────────────────────────────────────────────────────────────
#  ابزارها
# ──────────────────────────────────────────────────────────────────────────────
need() { command -v "$1" >/dev/null 2>&1 || die "ابزار «$1» نصب نیست."; }

run() {
  if ((DRY_RUN)); then log "${D}[dry-run] $*${R}"; else "$@"; fi
}

compose() {
  docker compose -p "$COMPOSE_PROJECT" -f "$APP_DIR/docker-compose.yml" "$@"
}

wait_healthy() {
  local url="$1" label="$2" i code
  for ((i = 1; i <= HEALTH_RETRIES; i++)); do
    code="$(curl -fsS -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null || true)"
    if [[ "$code" =~ ^2 ]]; then
      ok "$label سالم شد (HTTP $code) پس از $((i * HEALTH_INTERVAL)) ثانیه."
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

# ──────────────────────────────────────────────────────────────────────────────
#  rollback — بازگردانیِ ایمیجِ قبلی و بالا آوردن سرویس‌ها با آن
# ──────────────────────────────────────────────────────────────────────────────
ROLLBACK_ARMED=0
PREV_COMMIT=""

do_rollback() {
  warn "شروع rollback…"
  if docker image inspect "$ROLLBACK_TAG" >/dev/null 2>&1; then
    run docker tag "$ROLLBACK_TAG" "$IMAGE_NAME"
    [[ -n "$PREV_COMMIT" ]] && run git reset --hard --quiet "$PREV_COMMIT" || true
    run compose up -d --no-deps --force-recreate "$WEB_SERVICE" || true
    if ((SKIP_HEALTH)) || wait_healthy "$LOCAL_HEALTH_URL" "بک‌اند (بعد از rollback)"; then
      ok "به ایمیج قبلی برگشتیم. لاگ: $LOG_FILE"
      exit 2
    fi
    err "rollback هم سالم بالا نیامد — بررسی دستی لازم است. لاگ: $LOG_FILE"
    exit 3
  fi
  warn "هیچ ایمیجِ rollbackی ($ROLLBACK_TAG) موجود نیست — اقدام دستی لازم است."
  exit 3
}

on_fail() {
  local code=$?
  ((code == 0)) && return 0
  warn "دیپلوی با خطا متوقف شد (exit=$code)."
  if ((ROLLBACK_ARMED)); then do_rollback; fi
  exit "$code"
}
trap on_fail ERR

# ──────────────────────────────────────────────────────────────────────────────
#  آرگومان‌ها
# ──────────────────────────────────────────────────────────────────────────────
while (($#)); do
  case "$1" in
    --force)      FORCE=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    --no-health)  SKIP_HEALTH=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --rollback)   DO_ROLLBACK=1; shift ;;
    --status)     SHOW_STATUS=1; shift ;;
    -q|--quiet)   QUIET=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    --) shift; break ;;
    *) die "آرگومان ناشناخته: $1 (راهنما: --help)" ;;
  esac
done

# غیرمکفی: APP_DIR پیش‌فرض = پوشه‌ی اسکریپت
APP_DIR="${APP_DIR:-$SCRIPT_DIR}"
[[ -f "$APP_DIR/docker-compose.yml" ]] || die "docker-compose.yml در $APP_DIR یافت نشد."
[[ -f "$APP_DIR/.env" ]] || warn "فایل .env در $APP_DIR دیده نمی‌شود — compose ممکن است خطا دهد (POSTGRES_PASSWORD)."

need git; need docker; need curl
docker compose version >/dev/null 2>&1 || die "پلاگین «docker compose» در دسترس نیست."

# ──────────────────────────────────────────────────────────────────────────────
#  قفلِ تک‌نسخه‌ای (flock) — دو دیپلوی همزمان غیرممکن
# ──────────────────────────────────────────────────────────────────────────────
LOCK_DIR="$APP_DIR/.deploy"; mkdir -p "$LOCK_DIR/logs"
LOCK_FILE="$LOCK_DIR/update-back.lock"
LOG_FILE="$LOCK_DIR/logs/deploy-$(date '+%Y%m%d-%H%M%S').log"

if [[ -z "${UPDATE_BACK_LOCKED:-}" ]]; then
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    die "یک دیپلویِ دیگر در حال اجراست (lock: $LOCK_FILE)."
  fi
  export UPDATE_BACK_LOCKED=1
  # لاگِ کاملِ این اجرا + پخش روی ترمینال
  exec > >(tee -a "$LOG_FILE") 2>&1
fi

# فقط ۲۰ لاگ آخر نگه‌داری می‌شود
ls -1t "$LOCK_DIR"/logs/deploy-*.log 2>/dev/null | tail -n +$((KEEP_LOGS + 1)) | xargs -r rm -f

printf '%s%s≡ %s — %s%s\n' "$B" "$CYN" "Backend updater v$SCRIPT_VERSION" "$(date '+%Y-%m-%d %H:%M:%S')" "$R"
log "APP_DIR=$APP_DIR · IMAGE=$IMAGE_NAME · BRANCH=$BRANCH"

# ──────────────────────────────────────────────────────────────────────────────
#  مسیرهای کوتاه: --status / --rollback
# ──────────────────────────────────────────────────────────────────────────────
if ((SHOW_STATUS)); then
  compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.State}}' || compose ps
  exit 0
fi

if ((DO_ROLLBACK)); then
  do_rollback
fi

# ──────────────────────────────────────────────────────────────────────────────
#  قدم ۱ — هم‌ترازیِ کد با ریموت
# ──────────────────────────────────────────────────────────────────────────────
step "هم‌ترازی مخزن با $REMOTE/$BRANCH"
cd "$APP_DIR"
[[ -d .git ]] || die "این پوشه مخزن git نیست: $APP_DIR"

run git fetch --prune --quiet "$REMOTE" "$BRANCH"
TARGET_COMMIT="$(git rev-parse --quiet --verify "$REMOTE/$BRANCH")"
CURRENT_COMMIT="$(git rev-parse HEAD)"
PREV_COMMIT="$CURRENT_COMMIT"

if [[ "$CURRENT_COMMIT" == "$TARGET_COMMIT" && $FORCE -eq 0 ]]; then
  ok "کد از قبل به‌روز است (${CURRENT_COMMIT:0:8}) — فقط سلامت سرویس بازبینی می‌شود."
else
  log "انتقال ${CURRENT_COMMIT:0:8} → ${TARGET_COMMIT:0:8}"
fi
run git reset --hard --quiet "$TARGET_COMMIT"
ok "کد روی ${TARGET_COMMIT:0:8} است."
git log -1 --format='      %h · %s · %cr' "$TARGET_COMMIT" || true

# ──────────────────────────────────────────────────────────────────────────────
#  قدم ۲ — snapshot ایمیجِ فعلی (سپرِ rollback)
# ──────────────────────────────────────────────────────────────────────────────
step "اسنپ‌شات ایمیجِ فعلی برای rollback"
if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  run docker tag "$IMAGE_NAME" "$ROLLBACK_TAG"
  ok "ایمیج فعلی با تگ $ROLLBACK_TAG ذخیره شد."
  ROLLBACK_ARMED=1
else
  warn "ایمیج فعلی‌ای برای snapshot نیست (نخستین دیپلوی؟) — rollback غیرفعال."
fi

# ──────────────────────────────────────────────────────────────────────────────
#  قدم ۳ — build
# ──────────────────────────────────────────────────────────────────────────────
if ((SKIP_BUILD)); then
  step "رد شدن از build (--skip-build)"
  warn "از ایمیجِ موجود استفاده می‌شود؛ مطمئن شوید Dockerfile تغییری نکرده."
else
  step "build ایمیج $IMAGE_NAME"
  run compose build "$WEB_SERVICE"
  ok "ایمیج تازه ساخته شد."
fi

# ──────────────────────────────────────────────────────────────────────────────
#  قدم ۴ — استقرار (web + وابسته‌ها؛ migrate خودکار توسط entrypoint وب)
# ──────────────────────────────────────────────────────────────────────────────
step "استقرار سرویس‌ها"
run compose up -d
ok "سرویس‌ها بالا آمدند (web/worker/beat/flower + redis/postgres)."
log "مایگریشن‌ها به‌صورت خودکار توسط entrypoint وب اجرا می‌شوند (RUN_MIGRATIONS=1)."

# ──────────────────────────────────────────────────────────────────────────────
#  قدم ۵ — health-check
# ──────────────────────────────────────────────────────────────────────────────
if ((SKIP_HEALTH)); then
  warn "health-check نادیده گرفته شد (--no-health)."
else
  step "بررسی سلامت سرویس"
  if ! wait_healthy "$LOCAL_HEALTH_URL" "بک‌اند (محلی)"; then
    warn "هلث محلی سبز نشد — آخرین لاگ‌های وب:"
    compose logs --tail 40 "$WEB_SERVICE" 2>/dev/null || true
    die "health-check محلی رد شد: $LOCAL_HEALTH_URL"
  fi
  if ((PUBLIC_HEALTH_REQUIRED)); then
    if ! wait_healthy "$PUBLIC_HEALTH_URL" "بک‌اند (دامنه)"; then
      die "health-check عمومی رد شد: $PUBLIC_HEALTH_URL (rollback اجرا می‌شود)."
    fi
  elif curl -fsS -o /dev/null --max-time 10 "$PUBLIC_HEALTH_URL" 2>/dev/null; then
    ok "هلث عمومی هم سبز است."
  else
    warn "هلث عمومی در دسترس نیست (اختیاری — PUBLIC_HEALTH_REQUIRED=1 برای اجبار)."
  fi
fi

ROLLBACK_ARMED=0
printf '\n%s%s≡ تمام شد در %s ثانیه — بک‌اند به‌روز است. لاگ: %s%s\n' \
  "$B" "$GRN" "$SECONDS" "$LOG_FILE" "$R"
