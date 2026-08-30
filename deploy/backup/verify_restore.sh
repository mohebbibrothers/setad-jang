#!/bin/sh
# ============================================================================
# آزمونِ بازگردانی — «بکاپی که restore نشود، بکاپ نیست» (P2-11 فاز ۸)
# ----------------------------------------------------------------------------
# دو بخش:
#   A) دامپِ منطقیِ مشخص (یا تازه‌ترین) در DB موقت restore می‌شود
#      (--exit-on-error) و invariantهای ساختاری سنجیده می‌شوند؛
#   B) یکبارِ tar-integrity + manifest برای تازه‌ترین basebackup فیزیکی —
#      بازکردنِ تار و دیدنِ backup_manifest یعنی PG 17 این بکاپ را برای
#      replay وال *قابل‌استفاده* می‌شناسد (رفع F1: قبلاً basebackup اصلاً
#      وجود نداشت و PITR وعدهٔ توخالی بود).
# اجرا دستی:
#   docker compose run --rm --no-deps backup sh /backup/verify_restore.sh
# ============================================================================
set -eu

DB_PREFIX="${PGDATABASE:-setadjang}"
DUMP_DIR=/backups/dumps
BASE_DIR=/backups/base
VERIFY_DB="setadjang_verify_$(date +%s)"

log() { echo "[verify $(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

dump="${1:-}"
if [ -z "$dump" ]; then
    latest="$(ls -1t "$DUMP_DIR" 2>/dev/null | grep '^setadjang-.*\.dump$' | head -1 || true)"
    [ -n "$latest" ] || { log "FATAL: no dump found"; exit 1; }
    dump="$DUMP_DIR/$latest"
fi

# ── A) restore واقعی دامپ ─────────────────────────────────────────────────
log "checking sha256 of $dump"
( cd "$(dirname "$dump")" && sha256sum -c "$(basename "$dump").sha256" >/dev/null )

createdb -T template0 "$VERIFY_DB" >/dev/null
cleanup() {
    # هر مسیرِ خروج (موفق/خطا/سیگنال) باید DB موقت را پاک کند؛ وگرنه
    # فهرستِ verify بعدی آلوده می‌شود.
    dropdb --if-exists "$VERIFY_DB" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

log "restoring into $VERIFY_DB (full logical restore, exit-on-error)"
pg_restore --exit-on-error --no-owner --no-acl -d "$VERIFY_DB" "$dump"

migrations="$(psql -At -d "$VERIFY_DB" -c 'SELECT count(*) FROM django_migrations' 2>/dev/null || echo 0)"
tables="$(psql -At -d "$VERIFY_DB" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo 0)"
log "invariants: django_migrations=$migrations public_tables=$tables"
[ "$migrations" -ge 1 ] || { log "FATAL: restored db has no migrations row"; exit 1; }
[ "$tables" -ge 10 ] || { log "FATAL: restored db looks empty (<10 tables)"; exit 1; }

# ── B) سلامتِ پایهٔ فیزیکی (PITR anchor) ──────────────────────────────────
if [ -d "$BASE_DIR" ]; then
    base="$(ls -1t "$BASE_DIR" 2>/dev/null | grep '^setadjang-base-' | head -1 || true)"
    if [ -n "$base" ]; then
        log "checking basebackup integrity: $BASE_DIR/$base"
        [ -f "$BASE_DIR/$base/backup_manifest" ] || { log "FATAL: missing backup_manifest"; exit 1; }
        ( cd "$BASE_DIR/$base" && sha256sum -c SHA256SUMS >/dev/null )
        tar -tzf "$BASE_DIR/$base/base.tar.gz" >/dev/null 2>&1 ||
            { log "FATAL: base.tar.gz is corrupt (tar -t failed)"; exit 1; }
        tar -tzf "$BASE_DIR/$base/pg_wal.tar.gz" >/dev/null 2>&1 ||
            { log "FATAL: pg_wal.tar.gz is corrupt"; exit 1; }
        # manifest باید ساختارِ PG17 را داشته باشد؛ busybox-alpine پایتون
        # ندارد، پس grepِ صریح (خروجیِ FATAL در recovery با manifestِ خراب
        # گران است — زودتر کشف شود):
        grep -q '"Manifest Version"' "$BASE_DIR/$base/backup_manifest" ||
            { log "FATAL: backup_manifest has no version field"; exit 1; }
        grep -q '"PG-Version": "17' "$BASE_DIR/$base/backup_manifest" ||
            { log "FATAL: backup_manifest PG-Version mismatch (image drift?)"; exit 1; }
        log "backup_manifest sane"
    else
        log "WARN: no basebackup yet — PITR not usable until first pg_basebackup cycle"
    fi
fi

touch /backups/.verify_ok
log "restore-verify PASSED"
