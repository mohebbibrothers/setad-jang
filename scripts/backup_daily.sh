#!/usr/bin/env bash
# ============================================================================
#  backup_daily.sh - database + media backup with retention (cPanel friendly)
#
#  Produces, under $HOME/backups:
#      db-YYYY-MM-DD.sql.gz      mysqldump of the live database (gzip)
#      media-YYYY-MM-DD.tar.gz   the uploads folder
#
#  Retention: keeps the last KEEP_DAYS daily archives (default 7) and removes
#  older ones, so the account never fills up again (the exact failure mode that
#  broke the previous host: 101% disk).
#
#  Credentials are read from the project .env (MYSQL_* is what production uses),
#  so nothing secret appears in the crontab.
#
#  USAGE
#      bash scripts/backup_daily.sh              # run both
#      bash scripts/backup_daily.sh --db         # database only
#      bash scripts/backup_daily.sh --media      # media only
#      bash scripts/backup_daily.sh --verify     # list what exists + sizes
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
STAMP="$(date +%F)"
DO_DB=1
DO_MEDIA=1
VERIFY=0

for a in "$@"; do
  case "$a" in
    --db)    DO_MEDIA=0 ;;
    --media) DO_DB=0 ;;
    --verify) VERIFY=1 ;;
  esac
done

ok()   { printf '  [OK] %s\n' "$1"; }
warn() { printf '  [--] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
human() { awk -v k="$1" 'BEGIN{ if (k>=1048576) printf "%.1f GB", k/1048576; else if (k>=1024) printf "%.2f MB", k/1024; else printf "%d KB", k }'; }
kb_of() { [ -e "$1" ] && du -sk "$1" 2>/dev/null | awk '{print $1}' || echo 0; }

mkdir -p "$BACKUP_DIR"

# ------------------------------------------------------------------ verify mode
if [ "$VERIFY" -eq 1 ]; then
  echo "=== backups in $BACKUP_DIR ==="
  if [ -z "$(ls -A "$BACKUP_DIR" 2>/dev/null)" ]; then
    warn "no backups yet"
  else
    ls -lh "$BACKUP_DIR" | sed 's/^/       /'
    echo "       total: $(human "$(kb_of "$BACKUP_DIR")")"
  fi
  exit 0
fi

# ------------------------------------------------------------- read .env values
ENV_FILE="$APP_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  bad ".env not found at $ENV_FILE - cannot read database credentials"
  exit 1
fi

get_val() {
  # First NON-EMPTY value among the given key spellings.
  local keys="$1"
  grep -ihE "^[[:space:]]*($keys)[[:space:]]*=" "$ENV_FILE" 2>/dev/null \
    | cut -d= -f2- | tr -d '"'\''\r' | grep -v '^[[:space:]]*$' | head -1
}

DB_NAME=$(get_val 'MYSQL_NAME|DB_NAME|DATABASE_NAME')
DB_USER=$(get_val 'MYSQL_USER|DB_USER|DATABASE_USER')
DB_PASS=$(get_val 'MYSQL_PASSWORD|DB_PASSWORD|DATABASE_PASSWORD')
DB_HOST=$(get_val 'MYSQL_HOST|DB_HOST|DATABASE_HOST')
DB_HOST="${DB_HOST:-127.0.0.1}"

[ -n "$DB_NAME" ] && [ -n "$DB_USER" ] || { bad "could not read DB name/user from .env"; exit 1; }

# ---------------------------------------------------------------- database dump
if [ "$DO_DB" -eq 1 ]; then
  OUT="$BACKUP_DIR/db-$STAMP.sql.gz"
  command -v mysqldump >/dev/null 2>&1 || { bad "mysqldump not available"; exit 1; }
  # --single-transaction = consistent snapshot without locking the site
  if MYSQL_PWD="$DB_PASS" mysqldump -h "$DB_HOST" -u "$DB_USER" \
      --single-transaction --quick --skip-lock-tables --default-character-set=utf8mb4 \
      "$DB_NAME" 2>/tmp/dump_err.txt | gzip -9 > "$OUT"; then
    SIZE=$(kb_of "$OUT")
    if [ "${SIZE:-0}" -lt 10 ]; then
      bad "dump looks too small ($(human "$SIZE")) - check /tmp/dump_err.txt"
    else
      ok "database dump: $OUT ($(human "$SIZE"))"
    fi
  else
    bad "mysqldump failed:"
    tail -3 /tmp/dump_err.txt | sed 's/^/       /'
  fi
fi

# ------------------------------------------------------------------ media tar
if [ "$DO_MEDIA" -eq 1 ]; then
  if [ -d "$APP_DIR/media" ]; then
    OUT="$BACKUP_DIR/media-$STAMP.tar.gz"
    if tar czf "$OUT" -C "$APP_DIR" media 2>/dev/null; then
      ok "media archive: $OUT ($(human "$(kb_of "$OUT")"))"
    else
      bad "tar failed for media"
    fi
  else
    warn "no media/ directory - skipped"
  fi
fi

# ------------------------------------------------------------------- retention
echo "  [..] retention: keeping last $KEEP_DAYS days"
find "$BACKUP_DIR" -maxdepth 1 -type f -name "db-*.sql.gz"    -mtime "+$KEEP_DAYS" -delete 2>/dev/null
find "$BACKUP_DIR" -maxdepth 1 -type f -name "media-*.tar.gz" -mtime "+$KEEP_DAYS" -delete 2>/dev/null
ok "retention applied"

echo "  [..] current backups:"
ls -lh "$BACKUP_DIR" 2>/dev/null | tail -n +2 | awk '{printf "       %-34s %s\n", $9, $5}' | tail -12
info "total: $(human "$(kb_of "$BACKUP_DIR")")"
