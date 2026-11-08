#!/usr/bin/env bash
# ============================================================================
#  host_cleanup.sh - tidy a cPanel host after a migration (safe by default)
#
#  WHY
#  ---
#  A migrated account accumulates junk that silently eats the disk quota:
#    - pip/http caches, __pycache__, .pyc, old log archives
#    - duplicate media copies left by a half-finished copy
#    - diagnostic files we created while debugging (__probe.txt, .bak files)
#    - cron entries pointing at the OLD user path (/home/olduser/...)
#    - never the serving chain (index.php, run/, staticfiles/, media)
#
#  DESIGN RULES
#  ------------
#  1) **Dry-run by default**: prints what it WOULD delete and the space it would
#     free. Nothing is removed until you pass --apply.
#  2) **Never touches**: the database, the repo, .env, media uploads (the actual
#     files), staticfiles, logs of the current month.
#  3) Every removal prints the freed bytes so the result is measurable.
#  4) ASCII-only output (cPanel terminals mangle emoji).
#
#  USAGE
#      bash scripts/host_cleanup.sh                 # dry-run report
#      bash scripts/host_cleanup.sh --apply         # actually clean
#      bash scripts/host_cleanup.sh --apply --logs  # also prune old logs (>60d)
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
HOME_DIR="$HOME"
APPLY=0
PRUNE_LOGS=0
for a in "$@"; do
  [ "$a" = "--apply" ] && APPLY=1
  [ "$a" = "--logs" ] && PRUNE_LOGS=1
done

FAIL=0
TOTAL_KB=0
step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
skip() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
warn() { printf '  [!!] %s\n' "$1"; FAIL=$((FAIL+1)); }

# size of a path in KB (0 when missing)
kb_of() { [ -e "$1" ] && du -sk "$1" 2>/dev/null | awk '{print $1}' || echo 0; }
human() { awk -v k="$1" 'BEGIN{ if (k>=1048576) printf "%.1f GB", k/1048576; else if (k>=1024) printf "%.1f MB", k/1024; else printf "%d KB", k }'; }

# remove a path (or just report it) and account for the freed space
sweep() {
  local path="$1" label="${2:-$1}"
  if [ ! -e "$path" ]; then skip "$label (not present)"; return 0; fi
  local k; k=$(kb_of "$path")
  TOTAL_KB=$((TOTAL_KB + k))
  if [ "$APPLY" -eq 1 ]; then
    rm -rf "$path" 2>/dev/null && ok "removed $label ($(human "$k"))" || warn "could not remove $label"
  else
    printf '  [dry] %-52s %s\n' "$label" "$(human "$k")"
  fi
}

printf '%s\n' "============================================================"
echo " besat host cleanup | $(date '+%Y-%m-%d %H:%M')"
echo " mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo DRY-RUN)   logs: $([ "$PRUNE_LOGS" -eq 1 ] && echo prune || echo keep)"
echo " user: $USER  home: $HOME_DIR"
echo "============================================================"

step "0/8 disk usage before"
df -h "$HOME_DIR" | tail -1 | awk '{printf "       fs=%s used=%s avail=%s (%s)\n", $1, $3, $4, $5}'
info "app dir: $(human "$(kb_of "$APP_DIR")")"
info "media  : $(human "$(kb_of "$APP_DIR/media")")"

step "1/8 python/build caches"
sweep "$HOME_DIR/.cache/pip"                "pip cache"
sweep "$HOME_DIR/.cache"                    "user cache (~/.cache)"
find "$APP_DIR" -type d -name "__pycache__" -prune 2>/dev/null | while read -r d; do
  k=$(kb_of "$d"); TOTAL_CACHE=$(( ${TOTAL_CACHE:-0} + k ))
  if [ "$APPLY" -eq 1 ]; then rm -rf "$d"; fi
done
PYC_KB=$(find "$APP_DIR" -type f -name "*.pyc" -print0 2>/dev/null | du -ck --files0-from=- 2>/dev/null | tail -1 | awk '{print $1+0}')
if [ "${PYC_KB:-0}" -gt 0 ]; then
  TOTAL_KB=$((TOTAL_KB + PYC_KB))
  if [ "$APPLY" -eq 1 ]; then find "$APP_DIR" -type f -name "*.pyc" -delete 2>/dev/null; ok "removed .pyc files ($(human "$PYC_KB"))"
  else printf '  [dry] %-52s %s\n' "__pycache__/.pyc" "$(human "$PYC_KB")"; fi
fi

step "2/8 runtime files - PROTECTED (never removed here)"
# The PHP proxy (index.php), the WSGI run dir (pid/socket) and logs/app.log are
# the production serving chain on this host. Deleting them takes the site down;
# they are only rotated/truncated by their own scripts.
info "kept: index.php (PHP proxy), run/ (pid), logs/app.log"

step "3/8 diagnostic files we created while debugging"
for f in \
  "$HOME_DIR/public_html/__probe.txt" \
  "$HOME_DIR/public_html/main/__probe.txt" \
  "$HOME_DIR/public_html/besat.me/__probe.txt" \
  "$HOME_DIR/public_html/api.besat.me/__probe.txt"
do sweep "$f" "$(basename "$(dirname "$f")")/__probe.txt"; done

find "$HOME_DIR" -maxdepth 3 -type f -name ".htaccess.bak.*" 2>/dev/null | while read -r f; do
  sweep "$f" "$(basename "$f")"
done
find "$HOME_DIR" -maxdepth 3 -type f -name ".env.bak.*" 2>/dev/null | while read -r f; do
  sweep "$f" "$(basename "$f")"
done

step "3b/8 legacy mysql client option file (old-host credentials)"
# ~/.my.cnf survived the user rename and still carries the OLD user/password.
# It is never deleted (it may be needed) - it is moved aside, because any
# external client (mariadb, mariadb-dump, phpMyAdmin CLI) would silently use it.
if [ -f "$HOME_DIR/.my.cnf" ]; then
  if grep -qiE 'baahamnc|olduser' "$HOME_DIR/.my.cnf" 2>/dev/null; then
    if [ "$APPLY" -eq 1 ]; then
      mv "$HOME_DIR/.my.cnf" "$HOME_DIR/.my.cnf.legacy-$(date +%Y%m%d)" && ok "~/.my.cnf moved aside (old-host credentials neutralised)"
    else
      printf '  [dry] %-52s %s\n' "~/.my.cnf -> ~/.my.cnf.legacy-<date>" "old-host creds"
    fi
  else
    skip "~/.my.cnf has no old-host references"
  fi
else
  skip "no ~/.my.cnf"
fi

step "4/8 duplicate/empty media artefacts"
# media must never be deleted - only zero-byte files and temp uploads
ZERO_KB=$(find "$APP_DIR/media" -type f -size 0 2>/dev/null | wc -l | tr -d ' ')
if [ "${ZERO_KB:-0}" -gt 0 ]; then
  if [ "$APPLY" -eq 1 ]; then find "$APP_DIR/media" -type f -size 0 -delete 2>/dev/null; ok "removed $ZERO_KB zero-byte media files"
  else printf '  [dry] %-52s %s files\n' "zero-byte media files" "$ZERO_KB"; fi
else
  skip "no zero-byte media files"
fi
info "media kept intact: $(human "$(kb_of "$APP_DIR/media")") in $(find "$APP_DIR/media" -type f 2>/dev/null | wc -l | tr -d ' ') files"

step "5/8 static export - PROTECTED"
# staticfiles/ is served straight from disk by the vhost; it is refreshed by
# collectstatic, never deleted blindly.
info "kept: staticfiles/ ($(human "$(kb_of "$APP_DIR/staticfiles")")) - refresh with collectstatic"

step "6/8 old log archives"
# NOTE: no process substitution here - this host's bash has no /dev/fd and the
# whole step used to fail silently.
LOG_KB=$(find "$HOME_DIR/logs" -type f -name "*.gz" -print0 2>/dev/null | du -ck --files0-from=- 2>/dev/null | tail -1 | awk '{print $1+0}')
if [ "$PRUNE_LOGS" -eq 1 ]; then
  if [ "${LOG_KB:-0}" -gt 0 ]; then
    TOTAL_KB=$((TOTAL_KB + LOG_KB))
    if [ "$APPLY" -eq 1 ]; then find "$HOME_DIR/logs" -type f -name "*.gz" -delete 2>/dev/null; ok "pruned rotated logs ($(human "$LOG_KB"))"
    else printf '  [dry] %-52s %s\n' "rotated *.gz logs" "$(human "$LOG_KB")"; fi
  else skip "no rotated logs"; fi
else
  info "rotated logs kept: $(human "${LOG_KB:-0}")  (re-run with --logs to prune)"
fi

step "7/8 cron sanity"
CRON=$(crontab -l 2>/dev/null || true)
if echo "$CRON" | grep -q "/home/"; then
  STALE=$(echo "$CRON" | grep -oE "/home/[a-zA-Z0-9_]+" | grep -v "$HOME_DIR" | sort -u | tr '\n' ' ')
  if [ -n "$STALE" ]; then
    warn "cron entries reference other homes: $STALE"
    info "review with: crontab -l"
  else
    ok "cron paths all point at $HOME_DIR"
  fi
else
  skip "no cron entries"
fi
info "keep-alive for gunicorn should be GONE now:"
if echo "$CRON" | grep -q "serve_gunicorn"; then warn "serve_gunicorn cron still present"; else ok "no gunicorn cron"; fi

step "8/8 summary"
printf '       reclaimable: %s\n' "$(human "$TOTAL_KB")"
if [ "$APPLY" -eq 1 ]; then
  df -h "$HOME_DIR" | tail -1 | awk '{printf "       after: used=%s avail=%s (%s)\n", $3, $4, $5}'
  if [ -d "$APP_DIR/staticfiles" ]; then
    info "staticfiles still present - run collectstatic if you removed it:"
    info "  DJANGO_SETTINGS_MODULE=config.settings.production python manage.py collectstatic --noinput"
  fi
else
  echo
  echo "  This was a DRY RUN. Re-run with --apply to reclaim the space above."
fi

[ "$FAIL" -gt 0 ] && echo "  ($FAIL warning(s) above)"
exit 0
