#!/usr/bin/env bash
# ============================================================================
#  serve_gunicorn.sh - run the Django app on a local port (cPanel friendly)
#
#  WHY THIS EXISTS
#  ---------------
#  This cPanel host does not route the vhost through Passenger, so production
#  is served by a tiny PHP proxy in the docroot:
#
#      browser -> https://api.besat.me  (LiteSpeed)
#                      |-- /media/* /static/*  -> served from disk
#                      `-- everything else     -> index.php -> 127.0.0.1:8765
#
#  This script is the 8765 half of that chain (the other half is
#  scripts/apache-proxy/, deployed by scripts/host_web_recover.sh).
#
#  USAGE (from the app root):
#      bash scripts/serve_gunicorn.sh start     # start (idempotent, adopts orphans)
#      bash scripts/serve_gunicorn.sh stop
#      bash scripts/serve_gunicorn.sh restart
#      bash scripts/serve_gunicorn.sh status
#      bash scripts/serve_gunicorn.sh logs      # tail the log
#
#  DESIGN NOTES
#  - ASCII-only output (cPanel terminals mangle emoji).
#  - Idempotent: safe to call from cron every minute as a keep-alive.
#  - Port detection never depends on `ss`: it uses bash /dev/tcp first and only
#    falls back to ss/netstat/lsof. On this host `ss` reports nothing even when
#    the port is open - that made an earlier version start a second server.
#  - Orphan safety: if the port is open but the PID file is missing, the running
#    process is *adopted* (pid file repaired) instead of being duplicated.
# - All paths default to $HOME of the current user, so a user rename
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

# ---------------------------------------------------------------- primitives
port_open() {
  # 1) a real TCP connect - works everywhere bash does
  if (exec 3<>"/dev/tcp/$HOST/$PORT") 2>/dev/null; then
    exec 3<&- 2>/dev/null; exec 3>&- 2>/dev/null
    return 0
  fi
  # 2) classic tools, if the host allows them
  command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -qE "[:.]$PORT[[:space:]]" && return 0
  command -v netstat >/dev/null 2>&1 && netstat -ltn 2>/dev/null | grep -qE "[:.]$PORT[[:space:]]" && return 0
  command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  return 1
}

# every pid that looks like one of OUR servers. Two independent signals, so a
# relative invocation ("python3 scripts/_wsgi_fallback.py") is still recognised:
#   - the command line mentions this app dir, or
#   - the process working directory IS this app dir.
# Anything else (another account's gunicorn!) is never touched.
APPDIR_REAL=$(readlink -f "$APP_DIR" 2>/dev/null || echo "$APP_DIR")
server_pids() {
  for p in /proc/[0-9]*; do
    pid="${p#/proc/}"
    [ "$pid" = "$$" ] && continue
    [ "$pid" = "${PPID:-0}" ] && continue
    cmd=$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null) || continue
    [ -n "$cmd" ] || continue
    case "$cmd" in *serve_gunicorn.sh*) continue ;; esac
    case "$cmd" in *gunicorn*|*_wsgi_fallback.py*) ;; *) continue ;; esac
    case "$cmd" in *besat-backend*|*"$APP_DIR"*) echo "$pid"; continue ;; esac
    cwd=$(readlink -f "$p/cwd" 2>/dev/null || true)
    [ -n "$cwd" ] && [ "$cwd" = "$APPDIR_REAL" ] && echo "$pid"
  done
}

pid_alive() { [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE" 2>/dev/null)" 2>/dev/null; }

adopt_if_possible() {
  # port is open but we have no PID file -> take ownership instead of duplicating
  first=$(server_pids | head -1)
  if [ -n "$first" ]; then
    echo "$first" > "$PID_FILE"
    ok "adopted running server (pid $first, port $PORT)"
    return 0
  fi
  bad "port $PORT is open but no matching besat process was found (foreign service?)"
  return 1
}

# --------------------------------------------------------------------- verbs
do_status() {
  if pid_alive && port_open; then
    ok "running (pid $(cat "$PID_FILE"), port $PORT)"
    return 0
  fi
  if port_open; then adopt_if_possible; return $?; fi
  if pid_alive; then bad "pid $(cat "$PID_FILE") is alive but port $PORT is closed"; return 1; fi
  info "not running"
  return 1
}

do_stop() {
  STOPPED=0
  if pid_alive; then
    PID=$(cat "$PID_FILE")
    kill "$PID" 2>/dev/null && info "sent TERM to pid $PID"
    for _ in $(seq 1 20); do pid_alive || break; sleep 0.5; done
    if pid_alive; then kill -9 "$PID" 2>/dev/null; sleep 1; info "pid $PID needed SIGKILL"; fi
    STOPPED=1
  fi
  # orphans (running server whose pid file was lost)
  ORPHANS=$(server_pids | tr '\n' ' ')
  if [ -n "${ORPHANS// /}" ]; then
    info "stopping orphan pid(s): $ORPHANS"
    kill $ORPHANS 2>/dev/null
    for _ in $(seq 1 20); do port_open || break; sleep 0.5; done
    port_open && { kill -9 $ORPHANS 2>/dev/null; sleep 1; }
    STOPPED=1
  fi
  rm -f "$PID_FILE"
  if [ "$STOPPED" -eq 1 ]; then ok "stopped"; else info "already stopped"; fi
  port_open && { bad "port $PORT is still open after stop"; return 1; }
  return 0
}

do_start() {
  if port_open; then
    if pid_alive; then info "already running (pid $(cat "$PID_FILE"))"; return 0; fi
    if adopt_if_possible; then return 0; fi
    bad "refusing to start: port $PORT is held by another service"
    return 1
  fi
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

  # wait for the port to come up (max ~20s)
  for _ in $(seq 1 40); do
    if port_open && pid_alive; then ok "listening on $HOST:$PORT (pid $(cat "$PID_FILE"))"; return 0; fi
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
