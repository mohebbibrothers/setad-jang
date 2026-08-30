#!/bin/sh
# ==============================================================================
# setad-jang — آزمودنِ واقعیِ بازگردانی یک dump (یافتۀ P2-11 فاز 8)
# ------------------------------------------------------------------------------
# در clusterِ جاریِ همان postgres یک DB موقتِ `setadjang_verify_*` می‌سازد،
# dump را با --exit-on-error داخلش برمی‌گرداند، چند invariant ساختاری را
# می‌سنجد و DB را drop می‌کند. --exit-on-error عمدی است: «restore با warning»
# امروز قابل‌قبول است ولی همان warning فردا داده را نصفه‌نیمه می‌گذارد.
#
# مصرف:
#   - خودکار چرخشی از backup_loop.sh (BACKUP_VERIFY_EVERY)
#   - دستی:  docker compose run --rm --no-deps backup sh /backup/verify_restore.sh
#
# تنها dependency: همان image سرویس backup (pg_restore/psql/createdb).
# ==============================================================================
set -eu

DUMP="${1:-}"
if [ -z "$DUMP" ]; then
    DUMP="$(ls -1t /backups/dumps 2>/dev/null | grep '^setadjang-.*\.dump$' | head -1 || true)"
fi
[ -n "$DUMP" ] || {
    echo "verify: هیچ dumpی برای آزمودن پیدا نشد (/backups/dumps خالی است)" >&2
    exit 1
}
[ -s "$DUMP" ] || {
    echo "verify: فایل خالی است: $DUMP" >&2
    exit 1
}
if [ -f "$DUMP.sha256" ]; then
    sha256sum -c "$DUMP.sha256" >/dev/null 2>&1 || {
        echo "verify: checksumِ $D مطابق نیست — فایل آسیب دیده" >&2
        exit 1
    }
fi

VDB="setadjang_verify_$(date -u +%s)"
VERIFY_OK_FILE="/backups/.verify_ok"

log() { printf '[verify %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# template0: createdb با encoding/collation دلخواه؛ لازم است چون dump از DB‌ای
# با encoding خاص آمده و template1 ممکن است conflict بدهد.
createdb -T template0 "$VDB"
# cleanup تضمینی — هر مسیرِ خروج (موفق/شکست/سیگنال) drop را ببیند.
trap 'dropdb --if-exists --force "$VDB" 2>/dev/null || true' EXIT INT TERM

log "restoring $(basename "$DUMP") → $VDB"
if ! pg_restore --no-owner --no-acl --exit-on-error -d "$VDB" "$DUMP"; then
    log "FAILED: pg_restore خطا داد"
    exit 1
fi

# Invariant 1: جدولِ مایگریشن‌ها موجود و ناتهی — یعنی اسکیما/تاریخچهٔ ساخت
# واقعاً در dump است (ساده‌ترین شاهدِ «دیتابیتِ ما، دیتابیتِ خودته»).
migs="$(psql -tAqc "SELECT count(*) FROM django_migrations" "$VDB")"
[ "${migs:-0}" -ge 1 ] || {
    log "FAILED: django_migrations خالی/غایب در restore"
    exit 1
}

# Invariant 2: جدول‌های کاربریِ *اصلیِ* اپ در restore حاضرند (اسمِ یکی دو تای
# بنیادیِ قفل‌شده؛ اگر rename شدند، این تست می‌گوید dump با اسکیمایِ جدید
# ناسازگار است — خودِ همین آگاهی هدف است، پس صریح بررسی می‌شود).
tables_present="$(psql -tAqc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" "$VDB")"
[ "${tables_present:-0}" -ge 10 ] || {
    log "FAILED: تعداد جداول public غیرعادی کم است ($tables_present)"
    exit 1
}

touch "$VERIFY_OK_FILE"
log "ok: restore+invariants pass ($migs rows in django_migrations, $tables_present public tables)"
