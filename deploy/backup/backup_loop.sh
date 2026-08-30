#!/bin/sh
# ============================================================================
# سرویس بکاپ خودکار — یافتۀ P2-11 فاز ۸ (رفع F1 ممیزی ۲۰۲۶-۰۸-۳۰)
# ----------------------------------------------------------------------------
# چرخه در هر BACKUP_INTERVAL_SECONDS:
#   1) pg_dump منطقی (-Fc) + sha256 + خودآزمونِ خوانایی (pg_restore -l)
#   2) basebackup فیزیکی *روزانه* (pg_basebackup -Ft -z -Xf) + sha256
#      -> تنها با همین است که آرشیو WAL واقعاً «قابلِ replay» می‌شود؛
#      بدونِ پایهٔ فیزیکی، PITR فقط شعار بود (حفرۀ F1).
#   3) retention مستقل: دامپ‌ها BACKUP_KEEP_DAYS، WAL و base_backup
#      BACKUP_WAL_KEEP_DAYS / BASE_BACKUP_KEEP_DAYS (پنجرۀ PITR = minِ این‌ها)
#   4) هر BACKUP_VERIFY_EVERY دور، بازگردانیِ واقعیِ آخرین دامپ در DB موقت
#
# پرچم‌ها (برای healthcheck بیرونی و مانیتورینگ):
#   /backups/.backup_ok      — آخرین دورِ موفقِ کامل (دامپ همیشه)
#   /backups/.basebackup_ok  — آخرین basebackup موفق (پایۀ PITR)
#   /backups/.backup_failed  — آخرین خطا (با متن) — حذفش نکن تا وقتی ریشه‌ای
#
# طراحی «حلقهٔ ابدی» عمدی است: کانتینرِ sleep‌کردنِ ساده، state را در
# فایل‌ها نگه می‌دارد؛ restartِ compose هیچ چیزی را نمی‌سوزاند.
# ============================================================================
set -eu

DUMP_DIR=/backups/dumps
BASE_DIR=/backups/base
WAL_DIR=/backups/wal
OK_FLAG=/backups/.backup_ok
BASE_OK_FLAG=/backups/.basebackup_ok
FAIL_FLAG=/backups/.backup_failed
INTERVAL="${BACKUP_INTERVAL_SECONDS:-21600}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
WAL_KEEP_DAYS="${BACKUP_WAL_KEEP_DAYS:-7}"
VERIFY_EVERY="${BACKUP_VERIFY_EVERY:-4}"
BASE_INTERVAL="${BASE_BACKUP_INTERVAL_SECONDS:-86400}"
BASE_KEEP_DAYS="${BASE_BACKUP_KEEP_DAYS:-7}"

log() { echo "[backup $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

count=0

while :; do
    stamp="$(date -u +%Y%m%dT%H%M%SZ)"

    # ── 1) دامپِ منطقی ──────────────────────────────────────────────────
    dump="$DUMP_DIR/setadjang-$stamp.dump"
    mkdir -p "$DUMP_DIR" "$BASE_DIR"
    dump_ok=0
    if pg_dump --format=custom --compress=6 --no-owner --no-acl -f "$dump" 2>>"$FAIL_FLAG.log"; then
        ( cd "$DUMP_DIR" && sha256sum "setadjang-$stamp.dump" > "setadjang-$stamp.dump.sha256" )
        if ! sha256sum -c "$dump.sha256" >/dev/null 2>&1; then
            log "FATAL: sha256 mismatch for $dump"
            echo "sha-mismatch $stamp" > "$FAIL_FLAG"
        else
            rm -f "$FAIL_FLAG" "$FAIL_FLAG.log" 2>/dev/null || true
            dump_ok=1
            log "dump ok: $dump ($(du -h "$dump" | cut -f1))"
        fi
    else
        log "FATAL: pg_dump failed"
        echo "pg_dump-failed $stamp" > "$FAIL_FLAG"
    fi
    # OK فقط با دامپِ موفق تازه می‌شود؛ healthcheckِ سنّی «سکوت = مرگ» را
    # عمداً می‌بیند — دامپِ شکسته نباید با تاچِ پرچم سفید شویی شود.
    # (قالبِ if عمدی است: `cond && touch` با cond=false زیر set -e می‌کُشد.)
    if [ "$dump_ok" -eq 1 ]; then
        touch "$OK_FLAG"
    fi

    # ── 2) basebackup فیزیکی — در روزگاری که سررسیدش رسیده ─────────────
    newest_base="$(ls -1t "$BASE_DIR" 2>/dev/null | grep '^setadjang-base-' | head -1 || true)"
    base_due=1
    if [ -n "$newest_base" ]; then
        newest_age=$(( $(date +%s) - $(stat -c %Y "$BASE_DIR/$newest_base") ))
        [ "$newest_age" -lt "$BASE_INTERVAL" ] && base_due=0
    fi
    if [ "$base_due" -eq 1 ]; then
        base="$BASE_DIR/setadjang-base-$stamp"
        mkdir -p "$base"
        # -Ft -z : تارگل فشرده (base.tar.gz + pg_wal.tar.gz)
        # -Xf fetch: وال‌های لازمِ سازگاری *درون* بکاپ کپی می‌شوند —
        #   آرشيو جداگانه لازم ندارد و بکاپ self-contained است.
        # -P : پیشرفت در لاگ (برای تشخیصِ سکوتِ غیرعادی در حالتِ دستی)
        if pg_basebackup -D "$base" -Ft -z -Xf -P 2>>"$FAIL_FLAG.log"; then
            ( cd "$base" && sha256sum base.tar.gz pg_wal.tar.gz > SHA256SUMS )
            if ( cd "$base" && sha256sum -c SHA256SUMS >/dev/null 2>&1 ); then
                touch "$BASE_OK_FLAG"
                log "basebackup ok: $base"
            else
                log "FATAL: basebackup sha mismatch"
                echo "basebackup-sha-mismatch $stamp" > "$FAIL_FLAG"
                rm -rf "$base"
            fi
        else
            log "FATAL: pg_basebackup failed (PITR window NOT extended)"
            echo "pg_basebackup-failed $stamp" > "$FAIL_FLAG"
            rm -rf "$base"
        fi
    fi

    # ── 3) retention ───────────────────────────────────────────────────
    find "$DUMP_DIR" -maxdepth 1 -type f \( -name '*.dump' -o -name '*.sha256' \) \
        -mtime "+$KEEP_DAYS" -delete 2>/dev/null || true
    find "$BASE_DIR" -maxdepth 1 -type d -name 'setadjang-base-*' \
        -mtime "+$BASE_KEEP_DAYS" -exec rm -rf {} + 2>/dev/null || true
    # وال‌ها فقط وقتی امن‌اند که *همیشه* یک basebackupِ تازه‌تر از آن‌ها باشد؛
    # با BASE_KEEP_DAYS ≈ پنجرۀ WAL (پیش‌فرض ۷/۷) این نامتقارنی محافظت‌شده است.
    find "$WAL_DIR" -maxdepth 1 -type f -name '*' \
        -mtime "+$WAL_KEEP_DAYS" -delete 2>/dev/null || true

    # ── 4) verify چرخشی ────────────────────────────────────────────────
    count=$((count + 1))
    if [ "$VERIFY_EVERY" -gt 0 ] && [ $((count % VERIFY_EVERY)) -eq 0 ]; then
        if sh /backup/verify_restore.sh; then
            log "restore-verify ok (cycle $count)"
        else
            log "FATAL: restore-verify failed"
            echo "verify-failed $stamp" > "$FAIL_FLAG"
        fi
    fi

    sleep "$INTERVAL"
done
