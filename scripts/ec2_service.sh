#!/usr/bin/env bash
# Install and operate SPLM as two systemd services on an Ubuntu EC2 instance.
#
#   ./scripts/ec2_service.sh install   # install dependencies, build, enable and start
#   ./scripts/ec2_service.sh deploy    # rebuild and restart after a git pull
#   ./scripts/ec2_service.sh status
#   ./scripts/ec2_service.sh logs
#   ./scripts/ec2_service.sh restart
#   ./scripts/ec2_service.sh uninstall
#
# The Next.js dashboard listens publicly on SPLM_WEB_PORT (3010 by default). The
# Python API remains private on 127.0.0.1 and is reached through the Next.js proxy.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${SPLM_API_PORT:-8001}"
WEB_PORT="${SPLM_WEB_PORT:-3010}"
SERVICE_USER="${SPLM_SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
LEXICON_AUTO_DOWNLOAD="${SPLM_LEXICON_AUTO_DOWNLOAD:-false}"
API_SERVICE="splm-api.service"
WEB_SERVICE="splm-web.service"

usage() {
  echo "usage: $0 {install|deploy|status|logs|restart|uninstall}" >&2
  exit 2
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" > /dev/null 2>&1 || die "missing required command: $1"
}

validate_port() {
  case "$2" in
    '' | *[!0-9]*) die "$1 must be a number" ;;
  esac
  [ "$2" -ge 1 ] && [ "$2" -le 65535 ] || die "$1 must be between 1 and 65535"
}

as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

as_service_user() {
  if [ "$(id -un)" = "$SERVICE_USER" ]; then
    "$@"
  elif [ "$(id -u)" -eq 0 ]; then
    runuser -u "$SERVICE_USER" -- "$@"
  else
    sudo -u "$SERVICE_USER" -- "$@"
  fi
}

check_platform() {
  require_command systemctl
  require_command curl
  require_command python3
  require_command node
  require_command npm
  if [ "$(id -u)" -ne 0 ]; then
    require_command sudo
  fi

  id "$SERVICE_USER" > /dev/null 2>&1 || die "service user does not exist: $SERVICE_USER"
  case "$ROOT" in
    *[[:space:]]*) die "the repository path cannot contain whitespace: $ROOT" ;;
  esac
  validate_port SPLM_API_PORT "$API_PORT"
  validate_port SPLM_WEB_PORT "$WEB_PORT"
  [ "$API_PORT" != "$WEB_PORT" ] || die "API and dashboard ports must be different"

  local node_major
  node_major="$(node --version | sed -E 's/^v([0-9]+).*/\1/')"
  [ "$node_major" -ge 20 ] || die "Node.js 20 or newer is required (found $(node --version))"
}

prepare_application() {
  local python="$ROOT/.venv/bin/python"

  echo "preparing Python environment"
  as_service_user env SPLM_ROOT="$ROOT" SPLM_PYTHON="$python" \
    SPLM_TORCH_MODE="${SPLM_TORCH_MODE:-cpu}" \
    SPLM_TORCH_INDEX_URL="${SPLM_TORCH_INDEX_URL:-}" \
    "$ROOT/scripts/install_runtime.sh"

  # Optional: ACM (a separate repository) enables Live text on the Multimodal page.
  # Without it the page still works fully in Demo mode and says why Live is off.
  local acm_dir="${SPLM_ACM_DIR:-$ROOT/../ACM}"
  if [ -f "$acm_dir/pyproject.toml" ]; then
    echo "installing ACM from $acm_dir (enables Live text on /multimodal)"
    as_service_user "$python" -m pip install --quiet -e "$acm_dir"
  else
    echo "ACM not found at $acm_dir; /multimodal runs in Demo mode (set SPLM_ACM_DIR to enable Live text)"
  fi

  echo "installing and building dashboard"
  as_service_user env SPLM_API_URL="http://127.0.0.1:$API_PORT" \
    npm --prefix "$ROOT/web" ci
  as_service_user env NODE_ENV=production SPLM_API_URL="http://127.0.0.1:$API_PORT" \
    npm --prefix "$ROOT/web" run build

  if [ "${SPLM_SKIP_RESOURCES:-0}" != "1" ]; then
    echo "downloading/verifying parser models and base Transformer"
    as_service_user env SPLM_ROOT="$ROOT" HF_HOME="$ROOT/data/raw/hf" \
      "$python" "$ROOT/scripts/download_resources.py" --model
  else
    echo "skipping model downloads because SPLM_SKIP_RESOURCES=1"
  fi
}

install_units() {
  local service_group python node_dir next_bin temp_dir
  service_group="$(id -gn "$SERVICE_USER")"
  python="$ROOT/.venv/bin/python"
  node_dir="$(dirname "$(command -v node)")"
  next_bin="$ROOT/web/node_modules/.bin/next"
  [ -x "$python" ] || die "Python environment was not created at $python"
  [ -x "$next_bin" ] || die "Next.js executable was not installed at $next_bin"

  temp_dir="$(mktemp -d)"

  cat > "$temp_dir/$API_SERVICE" <<EOF
[Unit]
Description=MLM private API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$service_group
WorkingDirectory=$ROOT
EnvironmentFile=-$ROOT/.env
Environment="SPLM_ROOT=$ROOT"
Environment="SPLM_API_HOST=127.0.0.1"
Environment="SPLM_API_PORT=$API_PORT"
Environment="SPLM_LEXICON_AUTO_DOWNLOAD=$LEXICON_AUTO_DOWNLOAD"
Environment="HF_HOME=$ROOT/data/raw/hf"
ExecStart=$python -m splm.api.main
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF

  cat > "$temp_dir/$WEB_SERVICE" <<EOF
[Unit]
Description=MLM public dashboard
Wants=network-online.target
After=network-online.target $API_SERVICE
Requires=$API_SERVICE

[Service]
Type=simple
User=$SERVICE_USER
Group=$service_group
WorkingDirectory=$ROOT/web
EnvironmentFile=-$ROOT/.env
Environment="NODE_ENV=production"
Environment="PATH=$node_dir:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="SPLM_API_URL=http://127.0.0.1:$API_PORT"
ExecStart=$next_bin start --hostname 0.0.0.0 --port $WEB_PORT
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full

[Install]
WantedBy=multi-user.target
EOF

  as_root install -m 0644 "$temp_dir/$API_SERVICE" "/etc/systemd/system/$API_SERVICE"
  as_root install -m 0644 "$temp_dir/$WEB_SERVICE" "/etc/systemd/system/$WEB_SERVICE"
  rm -f "$temp_dir/$API_SERVICE" "$temp_dir/$WEB_SERVICE"
  rmdir "$temp_dir"
  as_root systemctl daemon-reload
  as_root systemctl enable "$API_SERVICE" "$WEB_SERVICE"
  as_root systemctl restart "$API_SERVICE" "$WEB_SERVICE"
}

wait_until_ready() {
  local attempt
  for attempt in $(seq 1 120); do
    if curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/health" > /dev/null \
      && curl -fsS --max-time 3 "http://127.0.0.1:$WEB_PORT/" > /dev/null; then
      echo
      echo "MLM is running in the background and will start after reboot."
      echo "Open: http://<EC2-PUBLIC-IP>:$WEB_PORT"
      echo "Multimodal demo: http://<EC2-PUBLIC-IP>:$WEB_PORT/multimodal"
      echo "Allow inbound TCP $WEB_PORT in the instance security group; do not expose $API_PORT."
      return 0
    fi
    sleep 1
  done

  echo "services did not become ready; recent logs:" >&2
  as_root journalctl -u "$API_SERVICE" -u "$WEB_SERVICE" -n 80 --no-pager >&2
  return 1
}

deploy() {
  check_platform
  prepare_application
  install_units
  wait_until_ready
}

case "${1:-}" in
  install | deploy)
    deploy
    ;;
  status)
    as_root systemctl --no-pager --full status "$API_SERVICE" "$WEB_SERVICE"
    ;;
  logs)
    if [ "$(id -u)" -eq 0 ]; then
      exec journalctl -u "$API_SERVICE" -u "$WEB_SERVICE" -f
    else
      exec sudo journalctl -u "$API_SERVICE" -u "$WEB_SERVICE" -f
    fi
    ;;
  restart)
    as_root systemctl restart "$API_SERVICE" "$WEB_SERVICE"
    wait_until_ready
    ;;
  uninstall)
    as_root systemctl disable --now "$WEB_SERVICE" "$API_SERVICE" 2> /dev/null || true
    as_root rm -f "/etc/systemd/system/$WEB_SERVICE" "/etc/systemd/system/$API_SERVICE"
    as_root systemctl daemon-reload
    echo "removed systemd services; project files and downloaded models were kept"
    ;;
  *)
    usage
    ;;
esac
