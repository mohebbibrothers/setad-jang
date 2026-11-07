#!/usr/bin/env bash
# ============================================================================
#  serve_gunicorn.sh - run the Django app on a local port (no Passenger needed)
#
#  WHY THIS EXISTS
#  ---------------
#  The new cPanel host has no Passenger/ApplicationManager (verified:
#  /etc/apache2/conf.d has no passenger config, and Cpanel::API::ApplicationManager
#  fails to load). So we serve the WSGI app ourselves on 127.0.0.1 and let a tiny
#  PHP proxy in the docroot forward requests to it.
#
#      browser -> https://api.besat.me  (Apache)
#                      |-- /media/* /static/*  -> served from disk
#                      `-- everything else     -> index.php -> 127.0.0.1:8765
#
#  USAGE (from the app root):
#      bash scripts/serve_gunicorn.sh start     # start (idempotent)
#      bash scripts/serve_gunicorn.sh stop
#      bash scripts/serve_gunicorn.sh restart
#      bash scripts/serve_gunicorn.sh status
#      bash scripts/serve_gunicorn.sh logs      # tail the log
#
#  DESIGN NOTES
#  - ASCII-only output (cPanel terminals mangle emoji).
#  - Idempotent: safe to call from cron every minute as a keep-alive.
#  - PID file + port check: never starts a second copy.
#  - Uses gunicorn when available, falls back to stdlib wsgiref (threaded).
#  - All paths default to $HOME of the *current* user, so a user rename
#    (baahamnc -> besatme) cannot break it.
# ============================================================================

set -uo pipefail

APP_DIR="${APP_DIR:-$HOME/apps/besat-backend}"
VENV_PY="${VENV_PY:-$HOME/virtualenv/apps/besat-backend/3.12/bin/python}"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
WORKERS="${WORKERS:-3}"
RUN_DIR="$APP_DIR/run"
LOG_DIR="$APP_DIR/logs"
PID_FILE="$RUN_DIR/gunicorn.pid"
LOG_FILE="$LOG_DIR/app.log"
SETTINGS="config.settings.production"

ok()   { printf '  [OK] %s\n' "$1"; }
bad()  { printf '  [!!] %s\n' "$1"; }
info() { printf '       %s\n' "$1"; }

mkdir -p "$RUN_DIR" "$LOG_DIR"

port_busy() { ss -ltn 2>/dev/null | grep -q ":$PORT "; }
pid_alive() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; }

do_status() {
  if pid_alive; then
    ok "running (pid $(cat "$PID_FILE"), port $PORT)"
    return 0
  fi
  if port_busy; then
    bad "port $PORT is busy but no PID file (orphan?)"
    return 1
  fi
  info "not running"
  return 1
}

do_stop() {
  if pid_alive; then
    PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null
    for _ in $(seq 1 20); do pid_alive || break; sleep 0.5; done
    if pid_alive; then kill -9 "$PID" 2>/dev/null; sleep 1; fi
    ok "stopped"
  else
    info "already stopped"
  fi
  rm -f "$PID_FILE"
  # reap orphans that still hold the port
  PIDS=$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oE 'pid=[0-9]+' | cut -d= -f2 | tr '\n' ' ')
  [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null && info "killed orphan pid(s): $PIDS"
  return 0
}

do_start() {
  if pid_alive && port_busy; then info "already running (pid $(cat "$PID_FILE"))"; return 0; fi
  [ -x "$VENV_PY" ] || { bad "venv python not found: $VENV_PY"; return 1; }
  cd "$APP_DIR" || return 1

  export DJANGO_SETTINGS_MODULE="$SETTINGS"
  export PYTHONUNBUFFERED=1

  # Prefer gunicorn (installed into the venv); fall back to stdlib.
  if "$VENV_PY" -c "import gunicorn" >/dev/null 2>&1; then
    info "using gunicorn ($WORKERS workers)"
    setsid "$VENV_PY" -m gunicorn config.wsgi:application \
      --bind "$HOST:$PORT" \
      --workers "$WORKERS" \
      --threads 4 \
      --timeout 90 \
      --graceful-timeout 30 \
      --keep-alive 5 \
      --max-requests 800 --max-requests-jitter 80 \
      --access-logfile - --error-logfile - \
      --chdir "$APP_DIR" \
      >>"$LOG_FILE" 2>&1 &
  else
    info "gunicorn not installed - using stdlib wsgiref (single process, threaded)"
    setsid "$VENV_PY" scripts/_wsgi_fallback.py >>"$LOG_FILE" 2>&1 &
  fi

  echo $! > "$PID_FILE"

  # wait for the port to come up (max ~15s)
  for _ in $(seq 1 30); do
    if port_busy; then ok "listening on $HOST:$PORT (pid $(cat "$PID_FILE"))"; return 0; fi
    sleep 0.5
  done

  bad "did not open port $PORT - last log lines:"
  tail -20 "$LOG_FILE" | sed 's/^/       /'
  return 1
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  logs)    tail -n "${2:-40}" "$LOG_FILE" ;;
  *) echo "usage: $0 {start|stop|restart|status|logs}"; exit 2 ;;
esac
