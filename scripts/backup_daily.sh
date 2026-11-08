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
#  Credentials: the SINGLE SOURCE OF TRUTH is Django itself - this script asks
#  the production settings for DATABASES["default"] and uses exactly those
#  fields. Re-parsing .env in bash was the bug behind
#  "Access denied ... (using password: YES)" while the site itself was healthy:
#  the file can hold several spellings of the same key (MYSQL_*/DB_*/DATABASE_*)
#  and a shell parser that takes the first match reads a stale one.
#  .env parsing stays as a fallback only, and then keys are tried in priority
#  order (MYSQL_* first) rather than file order.
#  Nothing secret ever appears in the crontab.
#
#  USAGE
#      bash scripts/backup_daily.sh              # run both
#      bash scripts/backup_daily.sh --db         # database only
#      bash scripts/backup_daily.sh --media      # media only
#      bash scripts/backup_daily.sh --verify     # list what exists + sizes
#      bash scripts/backup_daily.sh --whoami     # masked creds + SELECT 1 test
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"
STAMP="$(date +%F)"
DO_DB=1
DO_MEDIA=1
VERIFY=0
WHOAMI=0
PRUNE_EMPTY_ONLY=0

for a in "$@"; do
  case "$a" in
    --db)    DO_MEDIA=0 ;;
    --media) DO_DB=0 ;;
    --verify) VERIFY=1 ;;
    --prune-empty) PRUNE_EMPTY_ONLY=1 ;;
    --whoami) WHOAMI=1 ;;
  esac
done

ok()   { printf '  [OK] %s\n' "$1"; }
warn() { printf '  [--] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
human() { awk -v k="$1" 'BEGIN{ if (k>=1048576) printf "%.1f GB", k/1048576; else if (k>=1024) printf "%.2f MB", k/1024; else printf "%d KB", k }'; }
kb_of() { [ -e "$1" ] && du -sk "$1" 2>/dev/null | awk '{print $1}' || echo 0; }

mkdir -p "$BACKUP_DIR"

# ------------------------------------------------------- prune-empty-only mode
if [ "$PRUNE_EMPTY_ONLY" -eq 1 ]; then
  find "$BACKUP_DIR" -maxdepth 1 -type f \( -name "db-*.sql.gz" -o -name "media-*.tar.gz" \) -size -1k 2>/dev/null | while read -r f; do
    rm -f "$f" && info "removed truncated archive: $(basename "$f")"
  done
  ok "truncated archives pruned"
  exit 0
fi

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

# ------------------------------------------------------------- credentials
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
SETTINGS="${SETTINGS:-config.settings.production}"
ENV_FILE="$APP_DIR/.env"
CRED_SOURCE="none"
DB_NAME=""; DB_USER=""; DB_PASS=""; DB_HOST=""; DB_PORT=""

# 1) ask Django - identical to what the running site uses
if [ -x "$VENV_PY" ] && [ -d "$APP_DIR" ]; then
  DJANGO_CREDS=$(cd "$APP_DIR" && DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - 2>/tmp/besat_creds.err <<'PYCREDS'
import sys
try:
    import django
    django.setup()
    from django.conf import settings
    d = settings.DATABASES["default"]
    fields = [str(d.get(k) or "") for k in ("NAME", "USER", "PASSWORD", "HOST", "PORT")]
    if not fields[0] or not fields[1]:
        sys.stderr.write("NAME/USER empty in settings\n")
        sys.exit(1)
    sys.stdout.write("\x1f".join(fields))
except SystemExit:
    raise
except Exception as exc:
    sys.stderr.write("%s\n" % exc)
    sys.exit(1)
PYCREDS
)
  if [ -n "${DJANGO_CREDS:-}" ]; then
    IFS=$'\x1f' read -r DB_NAME DB_USER DB_PASS DB_HOST DB_PORT <<< "$DJANGO_CREDS"
    CRED_SOURCE="django ($SETTINGS)"
  fi
fi

# 2) fallback: parse .env in priority order (never file order)
get_val() {
  local key v
  for key in $1; do
    v=$(grep -ihE "^[[:space:]]*${key}[[:space:]]*=" "$ENV_FILE" 2>/dev/null \
        | head -1 | cut -d= -f2- | tr -d '"'"'"'\r' | sed 's/[[:space:]]*$//')
    if [ -n "$v" ]; then printf '%s' "$v"; return 0; fi
  done
  return 0
}
if [ "$CRED_SOURCE" = "none" ] && [ -f "$ENV_FILE" ]; then
  DB_NAME=$(get_val 'MYSQL_NAME DB_NAME DATABASE_NAME')
  DB_USER=$(get_val 'MYSQL_USER DB_USER DATABASE_USER')
  DB_PASS=$(get_val 'MYSQL_PASSWORD DB_PASSWORD DATABASE_PASSWORD')
  DB_HOST=$(get_val 'MYSQL_HOST DB_HOST DATABASE_HOST')
  DB_PORT=$(get_val 'MYSQL_PORT DB_PORT DATABASE_PORT')
  if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ]; then CRED_SOURCE=".env (fallback)"; fi
fi

mask() {
  local v="$1" stars
  if [ -z "$v" ]; then printf '(empty)'; return; fi
  stars=$(printf '%*s' $(( ${#v} > 2 ? ${#v} - 2 : 0 )) '' | tr ' ' '*')
  printf '%s%s (%d chars)' "${v:0:2}" "$stars" "${#v}"
}

if [ "$WHOAMI" -eq 1 ]; then
  echo "=== resolved database credentials (masked) ==="
  info "source  : $CRED_SOURCE"
  info "NAME    : ${DB_NAME:-(missing)}"
  info "USER    : ${DB_USER:-(missing)}"
  info "PASSWORD: $(mask "$DB_PASS")"
  info "HOST    : ${DB_HOST:-(local socket)}"
  info "PORT    : ${DB_PORT:-(default)}"
  if [ -f "$ENV_FILE" ]; then
    info ".env database keys (lengths only):"
    grep -iE '^[[:space:]]*(MYSQL|DB|DATABASE)_(NAME|USER|PASSWORD|HOST|PORT)[[:space:]]*=' "$ENV_FILE" 2>/dev/null |
      while IFS= read -r line; do
        k="${line%%=*}"
        v="${line#*=}"
        v="${v%$'\r'}"
        v="${v//\"/}"
        printf '         %-20s %s\n' "$k" "$(mask "$v")"
      done
  fi
  if [ -s /tmp/besat_creds.err ]; then
    info "django creds reader said:"
    tail -3 /tmp/besat_creds.err | sed 's/^/         /'
  fi
  if command -v mariadb >/dev/null 2>&1 || command -v mysql >/dev/null 2>&1; then
    CLI=$(command -v mariadb 2>/dev/null || command -v mysql)
    CONN=()
    [ -n "$DB_HOST" ] && CONN+=(-h "$DB_HOST")
    [ -n "$DB_PORT" ] && CONN+=(-P "$DB_PORT")
    OUT=$(MYSQL_PWD="$DB_PASS" "$CLI" "${CONN[@]}" -u "$DB_USER" -N -B -e 'SELECT 1' 2>&1)
    if [ "$(printf '%s' "$OUT" | tr -d '[:space:]')" = "1" ]; then
      ok "SELECT 1 succeeded - these credentials work"
    else
      bad "SELECT 1 failed: $(printf '%s' "$OUT" | head -2 | tr '\n' ' ')"
    fi
  else
    warn "no mariadb/mysql CLI - cannot test the connection"
  fi
  info "next: bash scripts/backup_daily.sh --db"
  exit 0
fi

if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ]; then
  bad "could not resolve database credentials (django import failed and .env unusable)"
  [ -s /tmp/besat_creds.err ] && tail -3 /tmp/besat_creds.err | sed 's/^/       /'
  exit 1
fi
info "credentials: $CRED_SOURCE"

# ---------------------------------------------------------------- database dump
if [ "$DO_DB" -eq 1 ]; then
  OUT="$BACKUP_DIR/db-$STAMP.sql.gz"
  if command -v mariadb-dump >/dev/null 2>&1; then DUMP_BIN="$(command -v mariadb-dump)"
  elif command -v mysqldump >/dev/null 2>&1; then DUMP_BIN="$(command -v mysqldump)"
  else bad "neither mariadb-dump nor mysqldump is available"; exit 1; fi
  info "dump tool: $DUMP_BIN"
  # --single-transaction = consistent snapshot without locking the site
  CONN=()
  [ -n "$DB_HOST" ] && CONN+=(-h "$DB_HOST")
  [ -n "$DB_PORT" ] && CONN+=(-P "$DB_PORT")
  # --no-tablespaces: shared-hosting users usually lack PROCESS -> error 1227
  if MYSQL_PWD="$DB_PASS" "$DUMP_BIN" "${CONN[@]}" -u "$DB_USER" \
      --single-transaction --quick --skip-lock-tables --no-tablespaces \
      --default-character-set=utf8mb4 \
      "$DB_NAME" 2>/tmp/dump_err.txt | gzip -9 > "$OUT"; then
    SIZE=$(kb_of "$OUT")
    if [ "${SIZE:-0}" -lt 10 ]; then
      bad "dump looks too small ($(human "$SIZE")) - real error below"
      tail -3 /tmp/dump_err.txt | sed 's/^/       /'
      rm -f "$OUT" && info "truncated dump deleted so rotation cannot keep it"
    else
      ok "database dump: $OUT ($(human "$SIZE"))"
    fi
  else
    bad "$(basename "$DUMP_BIN") failed:"
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
# a 0-byte / truncated archive is worse than none: it looks like a backup but
# restores nothing, and rotation would happily keep it for KEEP_DAYS days.
EMPTY=$(find "$BACKUP_DIR" -maxdepth 1 -type f \( -name "db-*.sql.gz" -o -name "media-*.tar.gz" \) -size -1k 2>/dev/null)
if [ -n "$EMPTY" ]; then
  printf '%s\n' "$EMPTY" | while read -r f; do rm -f "$f" && info "removed truncated archive: $(basename "$f")"; done
  bad "truncated archive(s) found and removed - investigate the dump/tar error"
else
  ok "no truncated archives"
fi

echo "  [..] current backups:"
ls -lh "$BACKUP_DIR" 2>/dev/null | tail -n +2 | awk '{printf "       %-34s %s\n", $9, $5}' | tail -12
info "total: $(human "$(kb_of "$BACKUP_DIR")")"
