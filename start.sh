#!/usr/bin/env bash
# One-command launcher for SPLM: checks the environment, then starts the API and the
# dashboard through scripts/dev.sh.
#
#   ./start.sh            # set up anything missing, start both, open the dashboard
#   ./start.sh stop       # stop both
#   ./start.sh restart    # stop, then start
#   ./start.sh status     # check both
#   ./start.sh logs       # follow logs/api.log and logs/web.log
#
# Set SPLM_NO_OPEN=1 to skip opening the browser.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

API_PORT="${SPLM_API_PORT:-8001}"
WEB_PORT="${SPLM_WEB_PORT:-3010}"
PYTHON="${SPLM_PYTHON:-$ROOT/.venv/bin/python}"
URL="http://127.0.0.1:$WEB_PORT"

up() {
  [ "$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "$1")" = "200" ]
}

answering() {
  curl -s -o /dev/null --max-time 5 "$1"
}

preflight() {
  for tool in curl npm; do
    if ! command -v "$tool" > /dev/null; then
      echo "missing required tool: $tool" >&2
      return 1
    fi
  done

  if [ ! -x "$PYTHON" ]; then
    echo "no virtualenv at .venv; creating it and installing SPLM (this takes a while)"
    python3 -m venv .venv || return 1
    "$ROOT/.venv/bin/pip" install -e ".[parse,llm,api,ui,data,dev]" || return 1
  fi

  if [ ! -d web/node_modules ]; then
    echo "installing dashboard dependencies"
    (cd web && npm install) || return 1
  fi

  if [ ! -f data/MANIFEST.json ]; then
    echo "warning: data/MANIFEST.json not found; parser and model resources may be missing." >&2
    echo "         run: $PYTHON scripts/download_resources.py --model" >&2
  fi
}

open_browser() {
  [ -n "${SPLM_NO_OPEN:-}" ] && return 0
  if command -v wslview > /dev/null; then
    wslview "$URL"
  elif command -v explorer.exe > /dev/null; then
    explorer.exe "$URL"
  elif command -v xdg-open > /dev/null; then
    xdg-open "$URL"
  elif command -v open > /dev/null; then
    open "$URL"
  fi > /dev/null 2>&1 || true
}

start() {
  if up "http://127.0.0.1:$API_PORT/health" && up "$URL/"; then
    echo "already running:  $URL"
    open_browser
    return 0
  fi

  # Anything answering here is not a healthy SPLM, and dev.sh would wait on it forever.
  if answering "http://127.0.0.1:$API_PORT/" && ! up "http://127.0.0.1:$API_PORT/health"; then
    echo "port $API_PORT is taken by another service; stop it, or change api.port in" >&2
    echo "config/app.yaml and set SPLM_API_PORT and SPLM_API_URL to match" >&2
    return 1
  fi

  preflight || return 1
  scripts/dev.sh start || return 1
  open_browser
}

case "${1:-start}" in
  start) start ;;
  stop | status) scripts/dev.sh "$1" ;;
  restart) scripts/dev.sh stop; sleep 1; start ;;
  logs) mkdir -p logs; touch logs/api.log logs/web.log; tail -n 20 -f logs/api.log logs/web.log ;;
  *) echo "usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
