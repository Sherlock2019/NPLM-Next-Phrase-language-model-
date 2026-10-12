#!/usr/bin/env bash
# Install only the packages required to run the API and Next.js dashboard.
# CPU-only PyTorch is the default because it avoids the multi-gigabyte CUDA stack.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${SPLM_PYTHON:-$ROOT/.venv/bin/python}"
TORCH_MODE="${SPLM_TORCH_MODE:-cpu}"

if [ ! -x "$PYTHON" ]; then
  command -v python3 > /dev/null 2>&1 || {
    echo "error: python3 is required" >&2
    exit 1
  }
  echo "creating Python environment at $ROOT/.venv"
  python3 -m venv "$ROOT/.venv"
  PYTHON="$ROOT/.venv/bin/python"
fi

if ! "$PYTHON" -c 'import torch' > /dev/null 2>&1; then
  case "$TORCH_MODE" in
    cpu)
      if [ "$(uname -s)" = "Linux" ]; then
        echo "installing CPU-only PyTorch (set SPLM_TORCH_MODE=cuda for a GPU build)"
        "$PYTHON" -m pip install \
          --index-url "${SPLM_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}" \
          "torch>=2.1"
      else
        # PyPI's macOS wheel has no NVIDIA payload.
        echo "installing PyTorch"
        "$PYTHON" -m pip install "torch>=2.1"
      fi
      ;;
    cuda)
      echo "installing CUDA-capable PyTorch"
      if [ -n "${SPLM_TORCH_INDEX_URL:-}" ]; then
        "$PYTHON" -m pip install --index-url "$SPLM_TORCH_INDEX_URL" "torch>=2.1"
      else
        "$PYTHON" -m pip install "torch>=2.1"
      fi
      ;;
    *)
      echo "error: SPLM_TORCH_MODE must be cpu or cuda" >&2
      exit 2
      ;;
  esac
else
  echo "PyTorch is already installed; keeping the existing build"
fi

echo "installing minimal SPLM runtime dependencies"
"$PYTHON" -m pip install -e "$ROOT[parse,llm,api]"

"$PYTHON" - <<'PY'
import torch

build = "CUDA" if torch.version.cuda else "CPU-only"
print(f"runtime ready: torch {torch.__version__} ({build})")
PY

if [ "$PYTHON" = "$ROOT/.venv/bin/python" ]; then
  touch "$ROOT/.venv/.splm-runtime-ready"
fi
