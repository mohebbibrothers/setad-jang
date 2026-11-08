#!/usr/bin/env bash
# ============================================================================
#  redis_keepalive.sh - make sure a local Redis is listening (cron-safe, 1 line)
#
#  This host has no systemd for the account, so cron is the only supervisor. A
#  multi-line heredoc cannot live inside a crontab entry, therefore the logic
#  lives here and the crontab stays a single idempotent line:
#
#      */5 * * * * APP_DIR=... bash $APP_DIR/scripts/redis_keepalive.sh
#
#  Behaviour: probe 127.0.0.1:6379; if closed and redis-server exists, start it
#  with $HOME/.redis/redis.conf. Silent on success (cron mail stays quiet).
# ============================================================================

set -uo pipefail

REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DIR="${REDIS_DIR:-$HOME/.redis}"
CONF="$REDIS_DIR/redis.conf"

port_open() {
  # bash /dev/tcp works even where ss/netstat report nothing (this host)
  (exec 3<>"/dev/tcp/127.0.0.1/$REDIS_PORT") 2>/dev/null && { exec 3<&-; exec 3>&-; return 0; }
  return 1
}

port_open && exit 0
command -v redis-server >/dev/null 2>&1 || exit 0
[ -f "$CONF" ] || exit 0

mkdir -p "$REDIS_DIR"
redis-server "$CONF" >/dev/null 2>&1 || true
sleep 1
port_open && exit 0
exit 1
