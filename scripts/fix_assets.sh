#!/usr/bin/env bash
# ============================================================================
#  fix_assets.sh - make /media/ and /static/ answer 200 instead of 404
#
#  ROOT CAUSE (measured on the live host, not guessed)
#  ---------------------------------------------------
#  The vhost docroot (public_html/api.besat.me) has NO `media` and NO `static`
#  entry, while .htaccess says "serve /media and /static from disk"
#  (`RewriteRule ^media/(.*)$ - [L]`). So LiteSpeed looks for a file that is not
#  there, sets 404, and then runs its ErrorDocument - which is our index.php -
#  so the app's bytes are streamed back to the client **with the 404 status
#  still attached**:
#
#      GET /media/public/.../page-001.webp  ->  404, 50952 bytes, image/webp
#      GET /static/admin/css/base.css       ->  404, 24538 bytes, text/css
#
#  Consequences: a browser refuses to execute CSS/JS delivered with a non-2xx
#  status (that is the "unstyled admin"), and /_next/image refuses the images
#  (that is the "broken images" on the homepage).
#
#  WHAT THIS SCRIPT DOES
#      1  report: does the docroot carry media/static, and does the app have them
#      2  ensure staticfiles/ is present (collectstatic if missing)
#      3  symlink  <docroot>/media  -> <app>/media
#                  <docroot>/static -> <app>/staticfiles      (idempotent)
#      4  prove it: loopback request through the vhost must be 200 + right type
#      5  if symlinks cannot be followed (open_basedir / no FollowSymLinks),
#         fall back to copying static (regenerable) and say exactly what to do
#         for media (30 MB - opt-in with --copy-media)
#      6  touch tmp/restart.txt and print the final table
#
#  USAGE
#      bash scripts/fix_assets.sh              # dry run: report + plan
#      bash scripts/fix_assets.sh --apply      # do it, then verify
#      bash scripts/fix_assets.sh --apply --copy-media   # copy media too
#
#  SAFETY: never deletes anything; a real directory is never replaced by a
#  symlink (it is reported instead), and the app's own media/static are only read.
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
DOCROOT="${DOCROOT:-$HOME/public_html/api.besat.me}"
DOMAIN="${DOMAIN:-api.besat.me}"
SETTINGS="${SETTINGS:-config.settings.production}"
PORT="${PORT:-8765}"

APPLY=0
COPY_MEDIA=0
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    --copy-media) COPY_MEDIA=1 ;;
  esac
done

step() { printf '\n=== %s\n' "$1"; }
ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
warn() { printf '  [--] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }
plan() { if [ "$APPLY" -eq 1 ]; then printf '  [..] %s\n' "$1"; else printf '  [plan] %s\n' "$1"; fi; }

cd "$APP_DIR" || { echo "app dir not found: $APP_DIR"; exit 1; }
[ -d "$DOCROOT" ] || { echo "docroot not found: $DOCROOT"; exit 1; }

echo "============================================================"
echo " besat fix-assets | $(date '+%Y-%m-%d %H:%M') | user=$USER"
echo " mode: $([ "$APPLY" -eq 1 ] && echo APPLY || echo 'DRY RUN (add --apply)')"
echo "============================================================"

# ------------------------------------------------------------------ 1 report
step "1/6 current state"
info "docroot : $DOCROOT"
info "app     : $APP_DIR"
for entry in media static; do
  if [ -L "$DOCROOT/$entry" ]; then
    info "$entry -> $(readlink "$DOCROOT/$entry") (symlink)"
  elif [ -d "$DOCROOT/$entry" ]; then
    warn "$DOCROOT/$entry is a real directory ($(find "$DOCROOT/$entry" -type f 2>/dev/null | wc -l | tr -d ' ') files)"
  else
    bad "$DOCROOT/$entry is MISSING -> the vhost cannot serve /$entry and answers 404"
  fi
done
[ -d "$APP_DIR/media" ] && ok "app media/ present ($(du -sh "$APP_DIR/media" 2>/dev/null | cut -f1))" || bad "app media/ missing"
if [ -d "$APP_DIR/staticfiles" ]; then
  ok "app staticfiles/ present ($(find "$APP_DIR/staticfiles" -type f 2>/dev/null | wc -l | tr -d ' ') files)"
else
  warn "app staticfiles/ missing - collectstatic will run in step 2"
fi

# --------------------------------------------------------------- 2 staticfiles
step "2/6 staticfiles (regenerable, needed for the admin CSS/JS)"
if [ -d "$APP_DIR/staticfiles" ] && [ -f "$APP_DIR/staticfiles/admin/css/base.css" ]; then
  ok "admin assets already collected"
else
  plan "run collectstatic"
  if [ "$APPLY" -eq 1 ]; then
    if DJANGO_SETTINGS_MODULE="$SETTINGS" "$VENV_PY" manage.py collectstatic --noinput -v 0 >/tmp/collectstatic.log 2>&1; then
      ok "collectstatic done ($(find staticfiles -type f 2>/dev/null | wc -l | tr -d ' ') files)"
    else
      bad "collectstatic failed - last lines:"
      grep -v -E 'clselect|WrongData|set_env_vars' /tmp/collectstatic.log | tail -3 | sed 's/^/       /'
    fi
  fi
fi

# ------------------------------------------------------------------ 3 symlinks
step "3/6 link the assets into the docroot (so the web server serves them with 200)"
link_asset() { # $1 = name in docroot, $2 = target dir, $3 = human label
  local name="$1" target="$2" label="$3"
  if [ ! -d "$target" ]; then
    bad "$label: source missing ($target)"
    return 1
  fi
  if [ -L "$DOCROOT/$name" ]; then
    if [ "$(readlink "$DOCROOT/$name")" = "$target" ]; then
      ok "$label: symlink already correct"
      return 0
    fi
    plan "re-point $name -> $target"
    [ "$APPLY" -eq 1 ] && ln -sfn "$target" "$DOCROOT/$name" && ok "$label: symlink re-pointed"
    return 0
  fi
  if [ -d "$DOCROOT/$name" ]; then
    warn "$label: real directory already exists - left untouched (remove it yourself if it is stale)"
    return 0
  fi
  plan "ln -s $target $DOCROOT/$name"
  if [ "$APPLY" -eq 1 ]; then
    if ln -s "$target" "$DOCROOT/$name" 2>/tmp/link_err.txt; then
      ok "$label: symlink created"
    else
      bad "$label: symlink failed ($(tail -1 /tmp/link_err.txt))"
      return 1
    fi
  fi
  return 0
}

link_asset "media"  "$APP_DIR/media"       "media"  || LINK_MEDIA_FAILED=1
link_asset "static" "$APP_DIR/staticfiles" "static" || LINK_STATIC_FAILED=1

# --------------------------------------------------------------- 4 verification
step "4/6 verification through the real vhost"
if [ "$APPLY" -eq 1 ]; then
  STATIC_SAMPLE=$(find staticfiles/admin/css -name 'base.css' 2>/dev/null | head -1)
  STATIC_REL="${STATIC_SAMPLE#staticfiles/}"
  MEDIA_SAMPLE=$(find media/public -type f 2>/dev/null | head -1)
  MEDIA_REL="${MEDIA_SAMPLE#media/}"

  enc() { "$VENV_PY" -c 'import sys,urllib.parse as u;print(u.quote(sys.argv[1]))' "$1" 2>/dev/null || printf '%s' "$1"; }

  for pair in "static/$STATIC_REL|static" "media/$MEDIA_REL|media"; do
    rel="${pair%%|*}"
    label="${pair##*|}"
    [ -n "${rel#static/}" ] || continue
    [ -n "${rel#media/}" ] || continue
    ENCODED=$(enc "$rel")
    # The loopback check is informational only: on this host a request to
    # 127.0.0.1 does not always land on the api.besat.me vhost (SNI/bind), so the
    # PUBLIC url below is the verdict that counts.
    CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 -H "Host: $DOMAIN" -H 'X-Forwarded-Proto: https' "http://127.0.0.1/$ENCODED" 2>/dev/null)
    CT=$(curl -s -o /dev/null -w '%{content_type}' --max-time 25 -H "Host: $DOMAIN" "http://127.0.0.1/$ENCODED" 2>/dev/null)
    PUB=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 "https://$DOMAIN/$ENCODED" 2>/dev/null)
    printf '  %-8s %-55s local=%s (%s) public=%s\n' "$label" "${rel:0:55}" "$CODE" "$CT" "$PUB"
    if [ "$PUB" = "200" ]; then
      ok "$label serves 200 publicly${CODE:+ (local probe: $CODE - see the SNI note)}"
    elif [ "$CODE" = "200" ]; then
      warn "$label is 200 locally but $PUB publicly - check the Vercel cache/CDN"
    else
      bad "$label is $CODE locally and $PUB publicly"
    fi
  done
else
  plan "curl one static + one media file through the vhost, expect 200"
fi

# ------------------------------------------------------------- 5 fallbacks
step "5/6 fallbacks if symlinks are not followed"
if [ "${LINK_STATIC_FAILED:-0}" -eq 1 ] || [ "${LINK_MEDIA_FAILED:-0}" -eq 1 ]; then
  warn "symlink(s) could not be created - the host may restrict links outside the docroot"
  info "static (regenerable) can be copied instead:"
  info "  cp -r $APP_DIR/staticfiles/. $DOCROOT/static/"
  if [ "$COPY_MEDIA" -eq 1 ] && [ "$APPLY" -eq 1 ]; then
    mkdir -p "$DOCROOT/media"
    cp -r "$APP_DIR/media/." "$DOCROOT/media/" && ok "media copied into the docroot ($(du -sh "$DOCROOT/media" 2>/dev/null | cut -f1))"
    info "remember: uploads must be copied again after each upload (or use the symlink)"
  else
    info "media is 30 MB - add --copy-media to copy it as well"
  fi
else
  ok "nothing to fall back to"
fi

# ------------------------------------------------------------- 6 apply extras
step "6/6 restart marker + summary"
if [ "$APPLY" -eq 1 ]; then
  mkdir -p tmp && touch tmp/restart.txt && ok "tmp/restart.txt touched"
fi
info "final layout:"
ls -ld "$DOCROOT/media" "$DOCROOT/static" 2>/dev/null | sed 's/^/       /'

echo
echo "============================================================"
if [ "$APPLY" -eq 0 ]; then
  echo " DRY RUN - re-run with --apply to create the links and verify"
else
  echo " Done. Confirm from the outside:"
  echo "   curl -sI https://$DOMAIN/static/admin/css/base.css | head -1   (expect 200)"
  echo "   curl -sI https://besat.me/static/admin/css/base.css | head -1   (expect 200)"
fi
echo "============================================================"
