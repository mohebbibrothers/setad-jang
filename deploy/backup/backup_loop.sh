#!/bin/sh
# ==============================================================================
# setad-jang — حلقۀ backup خودکار (یافتۀ P2-11 فاز 8)
# ------------------------------------------------------------------------------
# در سرویس `backup` (postgres:17-alpine — نسخهٔ pg_dump قفل‌شده با سرور) اجرا
# می‌شود. هر BACKUP_INTERVAL_SECONDS یک pg_dump منطقیِ custom-format + checksum،
# و هر BACKUP_VERIFY_EVERY بار restore-verification واقعی اجرا می‌کند — چون
# بکاپی که بازگردانی‌اش آزموده نشده، بکاپ نیست؛ آرزوست.
#
# POSIX sh عمدی است (alpine/busybox): bash‌گراییِ بی‌دلیل، سطح حملهٔ image و
# وابستگی اضافه می‌آورد.
#
# Retention: dumpها BACKUP_KEEP_DAYS، WAL آرشیو BACKUP_WAL_KEEP_DAYS نگه داشته
# می‌شوند (PITR تا همین پنجره). همه‌چیز روی volume مشترک /backups.
#
# محدودیت صادقانۀ این توپولوژی (مستند در runbook): /backups همان هاست است —
# از حذف/فاسدشدگی *منطقی* محافظت می‌کند، نه از مرگ دیسک؛ offsite با
# rclone/restic از بیرون همین دایرکتوری انجام شود.
# ==============================================================================
set -eu

INTERVAL="${BACKUP_INTERVAL_SECONDS:-21600}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
WAL_KEEP_DAYS="${BACKUP_WAL_KEEP_DAYS:-7}"
VERIFY_EVERY="${BACKUP_VERIFY_EVERY:-4}"
DUMP_DIR="/backups/dumps"
OK_FILE="/backups/.backup_ok"
FAILED_FLAG="/backups/.backup_failed"

log() {
    printf '[backup %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

count=0
mkdir -p "$DUMP_DIR"

# یک اجرای اولِ فوری (نه خوابِ INTERVAL ثانیه): بلافاصله پس از بالا آمدن
# سرویس، «نخستین بکاپِ این استقرار» ثبت شود و healthcheck زنده بماند.
while :; do
    ts="$(date -u +%Y%m%d-%H%M%S)"
    dump="$DUMP_DIR/setadjang-$ts.dump"

    # -Fc (custom, قابل فیلتر با pg_restore) + -Z6: فشرده‌سازی in-band؛
    # --no-owner/--no-acl: بازگردانی روی cluster تازه را شکننده نمی‌کند.
    if pg_dump --format=custom --compress=6 --no-owner --no-acl -f "$dump"; then
        sha256sum "$dump" >"$dump.sha256"
        # فقط اندازهٔ ۰ نه؛ dumpِ سالم باید قابل خواندن باشد:
        if [ -s "$dump" ] && sha256sum -c "$dump.sha256" >/dev/null 2>&1; then
            touch "$OK_FILE"
            rm -f "$FAILED_FLAG"
            log "ok: $dump ($(du -h "$dump" | cut -f1))"
        else
            log "error: dump نوشته شد ولی checksum/size معتبر نیست — $dump"
            touch "$FAILED_FLAG"
        fi
    else
        log "error: pg_dump شکست خورد"
        rm -f "$dump" "$dump.sha256"
        touch "$FAILED_FLAG"
    fi

    # Retention — عمداً *پس از* موفقیت: اگر دیسک پُر باشد و پاک‌سازی لازم
    # شود، نسخه‌های تازه‌تر قربانی نمی‌شوند.
    find "$DUMP_DIR" -name 'setadjang-*.dump' -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true
    find "$DUMP_DIR" -name 'setadjang-*.dump.sha256' -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true
    find /backups/wal -type f -mtime "+$WAL_KEEP_DAYS" -delete 2>/dev/null || true

    # verify چرخشی — روی *تازه‌ترین* dump؛ اگر همین الان تولید شده همان است.
    count=$((count + 1))
    if [ $((count % VERIFY_EVERY)) -eq 0 ]; then
        latest="$(ls -1t "$DUMP_DIR" 2>/dev/null | grep '^setadjang-.*\.dump$' | head -1 || true)"
        if [ -n "$latest" ]; then
            if sh /backup/verify_restore.sh "$DUMP_DIR/$latest"; then
                log "verify ok (rotational)"
            else
                log "verify FAILED — بکاپ‌ها قابل بازگردانی نیستند! (runbook §7)"
                touch "$FAILED_FLAG"
            fi
        fi
    fi

    sleep "$INTERVAL"
done
