#!/usr/bin/env bash
# Start the SPLM API and the dashboard together.
#
#   scripts/dev.sh start    # start both, wait until they answer
#   scripts/dev.sh stop     # stop both
#   scripts/dev.sh status   # check both
#
# The API is warmed on its first request (parser and model load once), so the first
# call after starting takes several seconds and every one after it is fast.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${SPLM_API_PORT:-8001}"
WEB_PORT="${SPLM_WEB_PORT:-3010}"
PYTHON="${SPLM_PYTHON:-$ROOT/.venv/bin/python}"

start() {
  mkdir -p "$ROOT/data/raw/hf" logs

  # setsid: each server gets its own session, so it keeps running after the shell that
  # started it exits (nohup alone does not keep `next dev` alive under WSL or ssh).
  echo "starting API on :$API_PORT"
  HF_HOME="$ROOT/data/raw/hf" setsid nohup "$PYTHON" -m splm.api.main \
    > logs/api.log 2>&1 < /dev/null &
  echo $! > logs/api.pid

  echo "starting dashboard on 0.0.0.0:$WEB_PORT (reachable on this host's public IP if the firewall allows)"
  (cd web && SPLM_API_URL="${SPLM_API_URL:-http://127.0.0.1:$API_PORT}" PORT="$WEB_PORT" \
    setsid nohup node_modules/.bin/next dev -H 0.0.0.0 -p "$WEB_PORT" > "$ROOT/logs/web.log" 2>&1 < /dev/null &
    echo $! > "$ROOT/logs/web.pid")

  for _ in $(seq 1 180); do
    api_up=$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "http://127.0.0.1:$API_PORT/health")
    web_up=$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/")
    if [ "$api_up" = "200" ] && [ "$web_up" = "200" ]; then
      echo "ready:  http://127.0.0.1:$WEB_PORT"
      return 0
    fi
    sleep 1
  done

  echo "timed out; see logs/api.log and logs/web.log" >&2
  return 1
}

stop() {
  for name in api web; do
    if [ -f "logs/$name.pid" ]; then
      kill "$(cat "logs/$name.pid")" 2>/dev/null || true
      rm -f "logs/$name.pid"
    fi
  done
  pkill -f 'splm.api.main' 2>/dev/null || true
  pkill -f 'next dev' 2>/dev/null || true
  echo stopped
}

status() {
  printf 'api  %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$API_PORT/health" || echo 000)"
  printf 'web  %s\n' "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$WEB_PORT/" || echo 000)"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 1; start ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
