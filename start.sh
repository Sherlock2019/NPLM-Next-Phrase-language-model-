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
DEFAULT_PYTHON="$ROOT/.venv/bin/python"
PYTHON="${SPLM_PYTHON:-$DEFAULT_PYTHON}"
URL="http://127.0.0.1:$WEB_PORT"
export SPLM_LEXICON_AUTO_DOWNLOAD="${SPLM_LEXICON_AUTO_DOWNLOAD:-false}"

port_available() {
  python3 - "$1" "$2" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind((host, port))
    except OSError:
        raise SystemExit(1)
PY
}

next_available_port() {
  local host="$1"
  local port="$2"
  local avoid="${3:-}"

  while [ "$port" -le 65535 ]; do
    if [ "$port" != "$avoid" ] && port_available "$host" "$port"; then
      printf '%s\n' "$port"
      return 0
    fi
    port=$((port + 1))
  done
  return 1
}

select_ports() {
  local requested

  if ! port_available 127.0.0.1 "$API_PORT"; then
    requested="$API_PORT"
    API_PORT="$(next_available_port 127.0.0.1 "$((API_PORT + 1))" "$WEB_PORT")" \
      || { echo "no available API port after $requested" >&2; return 1; }
    echo "API port $requested is in use; using $API_PORT"
  fi

  if [ "$WEB_PORT" = "$API_PORT" ] || ! port_available 0.0.0.0 "$WEB_PORT"; then
    requested="$WEB_PORT"
    WEB_PORT="$(next_available_port 0.0.0.0 "$((WEB_PORT + 1))" "$API_PORT")" \
      || { echo "no available dashboard port after $requested" >&2; return 1; }
    echo "dashboard port $requested is in use; using $WEB_PORT"
  fi

  export SPLM_API_PORT="$API_PORT"
  export SPLM_API_URL="http://127.0.0.1:$API_PORT"
  export SPLM_WEB_PORT="$WEB_PORT"
  URL="http://127.0.0.1:$WEB_PORT"
}

up() {
  [ "$(curl -s -o /dev/null --max-time 5 -w '%{http_code}' "$1")" = "200" ]
}

preflight() {
  for tool in curl npm python3; do
    if ! command -v "$tool" > /dev/null; then
      echo "missing required tool: $tool" >&2
      return 1
    fi
  done

  local runtime_ready=false
  if [ "$PYTHON" = "$DEFAULT_PYTHON" ]; then
    [ -x "$PYTHON" ] && [ -f "$ROOT/.venv/.splm-runtime-ready" ] && runtime_ready=true
  elif [ -x "$PYTHON" ] \
    && "$PYTHON" -c 'import fastapi, stanza, torch, transformers' > /dev/null 2>&1; then
    runtime_ready=true
  fi

  if [ "$runtime_ready" != true ]; then
    echo "ensuring the lightweight Python runtime is installed"
    SPLM_PYTHON="$PYTHON" scripts/install_runtime.sh || return 1
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

  preflight || return 1
  select_ports || return 1
  scripts/dev.sh start || return 1
  open_browser
}

main() {
  case "${1:-start}" in
    start) start ;;
    stop | status) scripts/dev.sh "$1" ;;
    restart) scripts/dev.sh stop; sleep 1; start ;;
    logs) mkdir -p logs; touch logs/api.log logs/web.log; tail -n 20 -f logs/api.log logs/web.log ;;
    *) echo "usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
  esac
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  main "$@"
fi
