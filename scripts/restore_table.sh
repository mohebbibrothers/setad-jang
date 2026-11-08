#!/usr/bin/env bash
# ============================================================================
#  restore_table.sh - put ONE table back from a mysqldump backup
#
#  WHY THIS EXISTS
#  ---------------
#  `zcat ~/backups/db-2026-11-01.sql.gz | grep -c 'r4j_r4jbounty'` answered 40,
#  while the live database holds ZERO bounty rows: the pre-migration data exists
#  in a backup but never made it to the new host, so the R4J page correctly said
#  "بدون جایزهٔ فعال" for every case file.
#
#  Restoring the WHOLE dump would roll back everything that happened since (new
#  users, sessions, listings). What is needed is a **surgical** restore of the
#  rows of a single table, merged into the live database.
#
#  WHAT IT DOES
#      1  reads the backup and reports how many rows the table has in it
#      2  compares with the live table (row count, PK range)
#      3  extracts ONLY that table's CREATE + INSERT statements
#      4  (--apply) loads them with FOREIGN_KEY_CHECKS=0 and UNIQUE_CHECKS=0,
#         de-duplicating on the primary key via INSERT IGNORE
#      5  verifies the row count afterwards and prints the delta
#
#  USAGE
#      bash scripts/restore_table.sh --table r4j_r4jbounty --from ~/backups/db-2026-11-03.sql.gz
#      bash scripts/restore_table.sh --table r4j_r4jbounty --from <file> --apply
#      bash scripts/restore_table.sh --list-tables --from <file>     # what is in there?
#
#  SAFETY
#      - dry-run by default: nothing is written without --apply
#      - only the named table is extracted (grep-bounded by its own markers)
#      - INSERT IGNORE => existing rows are never overwritten
#      - the table is never dropped or truncated
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
SETTINGS="${SETTINGS:-config.settings.production}"
TABLE=""
FROM=""
APPLY=0
LIST_TABLES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --table) TABLE="${2:-}"; shift ;;
    --from) FROM="${2:-}"; shift ;;
    --apply) APPLY=1 ;;
    --list-tables) LIST_TABLES=1 ;;
    *) echo "unknown argument: $1"; exit 2 ;;
  esac
  shift
done

step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
warn() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }

echo "============================================================"
echo " besat table restore | $(date '+%Y-%m-%d %H:%M')"
echo " mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo 'DRY RUN (add --apply)')"
echo "============================================================"

[ -n "$FROM" ] || { bad "--from <backup.sql.gz> is required"; exit 2; }
[ -f "$FROM" ] || { bad "backup not found: $FROM"; exit 2; }

gzip -t "$FROM" 2>/dev/null || { bad "not a valid gzip file: $FROM"; exit 2; }

# ---------------------------------------------------------------- list tables
if [ "$LIST_TABLES" -eq 1 ]; then
  step "tables inside $FROM"
  zcat "$FROM" | grep -oE '^CREATE TABLE `[^`]+`' | sed 's/CREATE TABLE `//;s/`$//' | sort | head -120
  exit 0
fi

[ -n "$TABLE" ] || { bad "--table <name> is required (or use --list-tables)"; exit 2; }

# ------------------------------------------------------------ live credentials
cd "$APP_DIR" || { bad "app dir not found"; exit 1; }
read -r DB_NAME DB_USER DB_PASS DB_HOST DB_PORT < <(
  DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - 2>/dev/null <<'PY'
import django

django.setup()
from django.conf import settings

d = settings.DATABASES["default"]
print(
    d.get("NAME") or "",
    d.get("USER") or "",
    d.get("PASSWORD") or "",
    d.get("HOST") or "",
    d.get("PORT") or "",
)
PY
)
[ -n "${DB_NAME:-}" ] || { bad "could not read database credentials from Django"; exit 1; }

CLI=$(command -v mariadb 2>/dev/null || command -v mysql 2>/dev/null || true)
[ -n "$CLI" ] || { bad "no mysql/mariadb client on this host"; exit 1; }
CONN=()
[ -n "$DB_HOST" ] && CONN+=(-h "$DB_HOST")
[ -n "$DB_PORT" ] && CONN+=(-P "$DB_PORT")

live_count() {
  MYSQL_PWD="$DB_PASS" "$CLI" --no-defaults -N -B "${CONN[@]}" -u "$DB_USER" "$DB_NAME" \
    -e "SELECT COUNT(*) FROM \`$TABLE\`" 2>/dev/null
}

# ---------------------------------------------------------------- 1 backup side
step "1/4 what the backup holds for: $TABLE"
if ! zcat "$FROM" | grep -q "CREATE TABLE \`$TABLE\`"; then
  bad "table '$TABLE' does not exist inside this backup"
  info "find the right backup with: bash scripts/restore_table.sh --list-tables --from $FROM"
  exit 1
fi
BACKUP_INSERT_LINES=$(zcat "$FROM" | grep -c "INSERT INTO \`$TABLE\`")
BACKUP_CREATE_LINES=$(zcat "$FROM" | grep -c "CREATE TABLE \`$TABLE\`")
ok "found CREATE TABLE ($BACKUP_CREATE_LINES) and $BACKUP_INSERT_LINES INSERT statement(s)"

# ---------------------------------------------------------------- 2 live side
step "2/4 what the live database holds"
BEFORE=$(live_count)
if [ -z "${BEFORE:-}" ]; then
  bad "could not read the live table (does '$TABLE' exist in $DB_NAME?)"
  exit 1
fi
info "live rows in $TABLE: $BEFORE"
if [ "$BEFORE" -gt 0 ]; then
  warn "the table is not empty; INSERT IGNORE means existing primary keys stay untouched"
fi

# ---------------------------------------------------------------- 3 extract
step "3/4 extracting only this table"
OUT=$(mktemp /tmp/besat-restore-XXXXXX.sql 2>/dev/null || echo /tmp/besat-restore.sql)
{
  echo "SET FOREIGN_KEY_CHECKS=0;"
  echo "SET UNIQUE_CHECKS=0;"
  echo "SET NAMES utf8mb4;"
  # CREATE TABLE IF NOT EXISTS: the live table already exists, and a plain
  # CREATE would abort the whole load with "table already exists".
  zcat "$FROM" | sed "s/^CREATE TABLE \`$TABLE\`/CREATE TABLE IF NOT EXISTS \`$TABLE\`/" | awk -v t="$TABLE" '
    $0 ~ "^CREATE TABLE `" t "`" { inside = 1 }
    inside { print }
    inside && /;[[:space:]]*$/ && $0 !~ /,$/ { }
    $0 ~ "^INSERT INTO `" t "`" { print; next }
  ' | awk 'BEGIN{keep=0} /^CREATE TABLE `'"$TABLE"'`/{keep=1} keep{print} keep && /ENGINE=/{keep=0}'
  # INSERTs are single logical statements in mysqldump; turn them into INSERT IGNORE
  zcat "$FROM" | grep "^INSERT INTO \`$TABLE\`" | sed "s/^INSERT INTO/INSERT IGNORE INTO/"
  echo "SET FOREIGN_KEY_CHECKS=1;"
  echo "SET UNIQUE_CHECKS=1;"
} > "$OUT" 2>/dev/null

ROWS=$(grep -c '^INSERT IGNORE INTO' "$OUT")
ok "extracted $ROWS INSERT statement(s) → $(basename "$OUT")"
info "size: $(du -h "$OUT" | cut -f1)"

if [ "$APPLY" -eq 0 ]; then
  step "4/4 dry run"
  info "nothing was written. Re-run with --apply to load the rows."
  info "command that would run:"
  info "  $CLI <db> < $OUT"
  rm -f "$OUT"
  exit 0
fi

# ---------------------------------------------------------------- 4 load
step "4/4 loading into the live database"
if MYSQL_PWD="$DB_PASS" "$CLI" --no-defaults "${CONN[@]}" -u "$DB_USER" "$DB_NAME" < "$OUT"; then
  ok "load finished"
else
  bad "load reported an error (the table was NOT dropped; existing rows are intact)"
  info "SQL file kept for inspection: $OUT"
  exit 1
fi

AFTER=$(live_count)
info "live rows before: $BEFORE · after: ${AFTER:-?}"
if [ -n "${AFTER:-}" ] && [ "${AFTER:-0}" -gt "$BEFORE" ]; then
  ok "restored $((AFTER - BEFORE)) row(s) into $TABLE"
elif [ "${AFTER:-0}" -eq "$BEFORE" ]; then
  warn "row count did not change - the backup rows were already present (same primary keys)"
else
  bad "row count decreased?! investigate before doing anything else"
fi

rm -f "$OUT"

echo
echo "============================================================"
info "next: recompute any denormalised counters that depend on this table, e.g."
info "  DJANGO_SETTINGS_MODULE=$SETTINGS $VENV_PY manage.py r4j_doctor --fix"
echo "============================================================"
