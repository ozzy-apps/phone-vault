#!/usr/bin/env bash
# Run Phone Vault from the source folder. Creates a local virtual environment on first run.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

if [ ! -x .venv/bin/python ]; then
  echo "Setting up .venv (first run)…"
  python3 -m venv .venv || { echo "Install venv support first: sudo apt install python3-venv"; exit 1; }
  .venv/bin/pip install --upgrade pip >/dev/null
  .venv/bin/pip install -r requirements.txt
fi

exec .venv/bin/python -m phonevault "$@"
