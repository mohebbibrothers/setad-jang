#!/usr/bin/env bash
# ============================================================================
#  host_stabilize.sh - one command that leaves the host clean and stable
#
#  Runs, in this order (each step is idempotent):
#     1  doctor (baseline report)
#     2  retire our temporary runtime (gunicorn / PHP proxy / probes)
#     3  clean caches, old logs, regnerable artefacts   (host_cleanup --apply)
#     4  rebuild staticfiles (collectstatic)
#     5  first real backup (db + media) with retention
#     6  install the two ops crons (backup daily + restart-file refresh)
#     7  final doctor report
#
#  WHAT THE CRONS DO
#     backup : every day 02:30  -> backups/db-YYYY-MM-DD.sql.gz, media-*.tar.gz
#              keeps KEEP_DAYS=7 days then rotates - the account can never
#              silently fill up again (that is what killed the old host).
#     restart: every day 05:10  -> touches tmp/restart.txt so Passenger reloads
#              the app at a quiet hour (memory hygiene, graceful).
#
#  SAFETY
#     - never deletes media/uploads or the database
#     - dry-run is not needed here: cleanup only targets caches, .pyc, probes,
#       *.bak files, staticfiles and rotated *.gz logs
#     - prints before/after disk usage
#
#  USAGE
#      bash scripts/host_stabilize.sh            # do everything
#      bash scripts/host_stabilize.sh --report   # only the final doctor
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
SETTINGS="config.settings.production"
KEEP_DAYS="${KEEP_DAYS:-7}"
REPORT_ONLY=0
for a in "$@"; do [ "$a" = "--report" ] && REPORT_ONLY=1; done

cd "$APP_DIR" || { echo "app dir not found: $APP_DIR"; exit 1; }

step() { printf '\n########## %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
human(){ awk -v k="$1" 'BEGIN{ if (k>=1048576) printf "%.1f GB", k/1048576; else if (k>=1024) printf "%.1f MB", k/1024; else printf "%d KB", k }'; }
kb_of(){ [ -e "$1" ] && du -sk "$1" 2>/dev/null | awk '{print $1}' || echo 0; }

echo "============================================================"
echo " besat host stabilize | $(date '+%Y-%m-%d %H:%M') | user=$USER"
echo "============================================================"
BEFORE=$(df -P "$HOME" | tail -1 | awk '{print $4}')
info "free before: $(human "$BEFORE")"

if [ "$REPORT_ONLY" -eq 1 ]; then
  step "doctor"
  bash scripts/host_doctor.sh
  exit 0
fi

# ---------------------------------------------------------------- 1 baseline
step "1/7 baseline doctor (problems only)"
bash scripts/host_doctor.sh --quiet

# ---------------------------------------------------------- 2 retire runtime
step "2/7 retiting the temporary runtime (Passenger serves the app now)"
if [ -x scripts/serve_gunicorn.sh ]; then bash scripts/serve_gunicorn.sh stop >/dev/null 2>&1 || true; fi
CRON=$(crontab -l 2>/dev/null || true)
if echo "$CRON" | grep -q "serve_gunicorn"; then
  echo "$CRON" | grep -v "serve_gunicorn.sh start" | crontab - && ok "removed gunicorn keep-alive cron"
else
  ok "no gunicorn cron to remove"
fi
ok "temporary runtime retired"

# ---------------------------------------------------------------- 3 cleanup
step "3/7 cleaning caches, probes, backups of config, staticfiles, old logs"
bash scripts/host_cleanup.sh --apply --logs 2>&1 | tail -25

# ---------------------------------------------------------------- 4 static
step "4/7 rebuilding staticfiles"
if DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" manage.py collectstatic --noinput -v 0 2>&1 | tail -2; then
  ok "staticfiles rebuilt"
else
  info "collectstatic reported an issue (non-fatal)"
fi

# ---------------------------------------------------------------- 5 backup
step "5/7 first backup with retention (KEEP_DAYS=$KEEP_DAYS)"
KEEP_DAYS="$KEEP_DAYS" bash scripts/backup_daily.sh 2>&1 | tail -12

# ---------------------------------------------------------------- 6 crons
step "6/7 installing ops crons"
CUR=$(crontab -l 2>/dev/null || true)
KEEP_LINE="20 2 * * * APP_DIR=$APP_DIR KEEP_DAYS=$KEEP_DAYS bash $APP_DIR/scripts/backup_daily.sh >> \$HOME/logs/backup.log 2>&1"
RESTART_LINE="10 5 * * * mkdir -p $APP_DIR/tmp && touch $APP_DIR/tmp/restart.txt"
NEW="$CUR"
echo "$NEW" | grep -q "backup_daily.sh" || NEW="$NEW
# besat: daily database+media backup with 7-day rotation (added by host_stabilize.sh)
$KEEP_LINE"
echo "$NEW" | grep -q "tmp/restart.txt" || NEW="$NEW
# besat: quiet-hour Passenger reload (memory hygiene, graceful)
$RESTART_LINE"
printf '%s\n' "$NEW" | sed '/^$/N;/^\n$/D' | crontab -
ok "crons installed"
info "current crontab:"
crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | sed 's/^/       /' | head -10

# ---------------------------------------------------------------- 7 doctor
step "7/7 final doctor"
bash scripts/host_doctor.sh 2>&1 | tail -40

AFTER=$(df -P "$HOME" | tail -1 | awk '{print $4}')
echo
echo "============================================================"
info "free before: $(human "$BEFORE")   free after: $(human "$AFTER")"
echo "============================================================"
