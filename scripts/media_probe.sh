#!/usr/bin/env bash
# ============================================================================
#  media_probe.sh - read-only: why does /media/ answer 404 while the file exists?
#
#  CONTEXT
#  -------
#  scripts/media_audit.py proves every referenced file is on disk, yet the public
#  URL https://besat.me/media/public/... returns HTTP 404 *with the real file
#  bytes in the body* (Vercel cache, image optimizer, Googlebot and any client
#  that checks the status all treat that as a broken image).
#
#  This probe runs the SAME request through every layer of the chain and prints
#  the status each layer returns, so the layer that lies becomes obvious:
#
#       Django (port 8765) -> vhost (LiteSpeed/index.php) -> api.besat.me -> besat.me
#
#  It is read-only: no writes, no restarts, no cache purges.
#
#  USAGE  (from the app root)
#      bash scripts/media_probe.sh
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
DOCROOT="${DOCROOT:-$HOME/public_html/api.besat.me}"
DOMAIN="${DOMAIN:-api.besat.me}"
PORT="${PORT:-8765}"
SETTINGS="${SETTINGS:-config.settings.production}"

# percent-encode a path for curl. This host has NO `python3` on PATH, so the
# venv interpreter is used (it always exists) with a pure-bash fallback.
urlencode() {
  if [ -x "$VENV_PY" ]; then
    "$VENV_PY" -c 'import sys,urllib.parse as u;print(u.quote(sys.argv[1]))' "$1" 2>/dev/null && return 0
  fi
  local s="$1" out="" c i
  for (( i=0; i<${#s}; i++ )); do
    c="${s:i:1}"
    case "$c" in
      [a-zA-Z0-9._~/-]) out="$out$c" ;;
      *) out="$out$(printf '%%%02X' "'$c")" ;;
    esac
  done
  printf '%s' "$out"
}

step() { printf '\n=== %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }

cd "$APP_DIR" || { echo "app dir not found: $APP_DIR"; exit 1; }

echo "============================================================"
echo " besat media probe | $(date '+%Y-%m-%d %H:%M') | user=$USER"
echo "============================================================"

# ---------------------------------------------------------------- 1 settings
step "1/6 django settings that decide whether media is served"
DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" - 2>/dev/null <<'PY'
import django
django.setup()
from django.conf import settings
from pathlib import Path
print(f"       SERVE_PUBLIC_MEDIA : {getattr(settings, 'SERVE_PUBLIC_MEDIA', None)}")
print(f"       DEBUG              : {settings.DEBUG}")
print(f"       MEDIA_URL          : {settings.MEDIA_URL}")
print(f"       MEDIA_ROOT         : {settings.MEDIA_ROOT}")
root = Path(settings.MEDIA_ROOT)
print(f"       media exists       : {root.is_dir()}")
public = root / "public"
print(f"       public exists      : {public.is_dir()}")
if public.is_dir():
    files = [p for p in public.rglob('*') if p.is_file()]
    print(f"       files under public : {len(files)}")
PY

# ---------------------------------------------------------------- 2 pick files
step "2/6 picking real files from disk and from the database"
# NOTE: this host's bash has no /dev/fd, so process substitution (`< <(...)`)
# aborts the script. Everything below uses plain pipes and temp files.
SAMPLE_FILE=$(mktemp 2>/dev/null || echo /tmp/besat-samples.txt)
find media/public -type f 2>/dev/null | head -3 | sed 's|^media/||' > "$SAMPLE_FILE"
SAMPLES=()
while IFS= read -r line; do
  [ -n "$line" ] && SAMPLES+=("$line")
done < "$SAMPLE_FILE"
rm -f "$SAMPLE_FILE"
if [ "${#SAMPLES[@]}" -eq 0 ]; then
  bad "no files under media/public - cannot probe"
  exit 1
fi
for s in "${SAMPLES[@]}"; do info "sample: media/$s"; done

# reference images that the public homepage actually shows
EXTRAS=(
  "public/lms/courses/new/cover/CHERIK_CYBER.png"
  "public/madadkar/sponsors/new/logo/12267499_252.png"
  "public/r4j/criminals/3/photos/11b75449-36ff-4430-82a4-2d7288633201.png"
)

# the Django admin is unstyled when /static/ is not served correctly, so the
# same three-layer probe runs for one admin asset as well
ADMIN_ASSET=""
for cand in static/admin/css/base.css static/admin/css/responsive.css staticfiles/admin/css/base.css; do
  if [ -f "$cand" ]; then ADMIN_ASSET="$cand"; break; fi
done
if [ -z "$ADMIN_ASSET" ]; then
  bad "no admin CSS found under static/ or staticfiles/ - that alone explains an unstyled admin"
  info "run: DJANGO_SETTINGS_MODULE=$SETTINGS $VENV_PY manage.py collectstatic --noinput"
else
  ok "admin asset on disk: $ADMIN_ASSET ($(stat -c '%s bytes' "$ADMIN_ASSET"))"
fi
STATIC_URL_PATH="${ADMIN_ASSET#static/}"
STATIC_URL_PATH="${STATIC_URL_PATH#staticfiles/}"
for e in "${EXTRAS[@]}"; do
  if [ -f "media/$e" ]; then info "on disk : media/$e"; else info "MISSING : media/$e"; fi
done

# ---------------------------------------------------------------- 3 per layer
probe() { # url -> "code bytes"
  curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 25 "$1" 2>/dev/null || echo "ERR 0"
}

step "3/6 same file through every layer (status + bytes)"
for s in "${SAMPLES[@]}" "${EXTRAS[@]}"; do
  ENC=$(urlencode "$s")
  printf '  %s\n' "$s"
  printf '      gunicorn (Host)  : %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{size_download} %{content_type}' --max-time 25 -H "Host: $DOMAIN" "http://127.0.0.1:$PORT/media/$ENC" 2>/dev/null)"
  printf '      port 8765 direct : %s\n' "$(probe "http://127.0.0.1:$PORT/media/$ENC")"
  printf '      vhost loopback   : %s\n' "$(probe "http://127.0.0.1/media/$ENC")"
  printf '      vhost + Host     : %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 25 -H "Host: $DOMAIN" "http://127.0.0.1/media/$ENC" 2>/dev/null || echo 'ERR 0')"
  printf '      api.besat.me     : %s\n' "$(probe "https://$DOMAIN/media/$ENC")"
  printf '      besat.me (proxy) : %s\n' "$(probe "https://besat.me/media/$ENC")"
done

# ------------------------------------------- 3b headers per layer (first sample)
step "3b/6 response headers for the first sample (status + who added what)"
FIRST_ENC=$(urlencode "${SAMPLES[0]}")
for layer in \
  "port8765|http://127.0.0.1:$PORT/media/$FIRST_ENC" \
  "vhost|http://127.0.0.1/media/$FIRST_ENC" \
  "api|https://$DOMAIN/media/$FIRST_ENC" \
  "vercel|https://besat.me/media/$FIRST_ENC"; do
  name="${layer%%|*}"
  url="${layer#*|}"
  printf '  --- %s : %s\n' "$name" "$url"
  curl -sI --max-time 25 -H "Host: $DOMAIN" "$url" 2>/dev/null | head -12 | sed 's/^/       /'
done

# ------------------------------------------------ 3c the admin asset, per layer
step "3c/6 the Django admin asset through every layer (unstyled admin)"
if [ -n "$ADMIN_ASSET" ]; then
  SP="static/$STATIC_URL_PATH"
  printf '  %s\n' "$SP"
  printf '      port 8765 direct : %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 20 "http://127.0.0.1:$PORT/$SP" 2>/dev/null)"
  printf '      vhost loopback   : %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 20 "http://127.0.0.1/$SP" 2>/dev/null)"
  printf '      api.besat.me     : %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 25 "https://$DOMAIN/$SP" 2>/dev/null)"
  printf '      besat.me (proxy) : %s\n' "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 25 "https://besat.me/$SP" 2>/dev/null)"
  printf '  headers via besat.me:\n'
  curl -sI --max-time 25 "https://besat.me/$SP" 2>/dev/null | head -10 | sed 's/^/       /'
else
  warn "skipped - no admin asset on disk"
fi

# ---------------------------------------------------------------- 4 vhost cfg
step "4/6 deployed vhost configuration"
if [ -f "$DOCROOT/.htaccess" ]; then
  ok ".htaccess present ($(stat -c '%s bytes' "$DOCROOT/.htaccess"))"
  grep -nE 'media|static|RewriteRule|Passenger|AddHandler|AddType' "$DOCROOT/.htaccess" | sed 's/^/       /'
else
  bad "$DOCROOT/.htaccess missing"
fi
if [ -f "$DOCROOT/index.php" ]; then
  ok "index.php present ($(stat -c '%s bytes' "$DOCROOT/index.php"))"
  grep -nE 'media|static|HTTP_|REQUEST_URI' "$DOCROOT/index.php" | head -12 | sed 's/^/       /'
else
  bad "$DOCROOT/index.php missing"
fi
if [ -L "$DOCROOT/media" ] || [ -d "$DOCROOT/media" ]; then
  info "docroot media entry exists: $(ls -ld "$DOCROOT/media" 2>/dev/null)"
else
  info "no media entry inside the docroot (Django must serve it)"
fi

# ---------------------------------------------------------------- 5 logs
step "5/6 what Django actually logged for media requests"
if [ -f logs/app.log ]; then
  grep -E 'media/' logs/app.log | tail -12 | sed 's/^/       /'
  NO_MEDIA=$(grep -cE 'media/' logs/app.log 2>/dev/null || echo 0)
  info "media lines in log: $NO_MEDIA"
else
  info "no logs/app.log (access logging goes to stdout; check ~/logs)"
fi

# ---------------------------------------------------------------- 6 perms
step "6/6 permissions along one media path"
FIRST="${SAMPLES[0]}"
namei -l "media/$FIRST" 2>/dev/null | sed 's/^/       /'
stat -c '       mode=%a owner=%U group=%G size=%s  %n' "media/$FIRST" 2>/dev/null

echo
echo "============================================================"
echo " NEXT: send this whole output back."
echo " The layer whose status is not 200 is the one that needs fixing."
echo "============================================================"
