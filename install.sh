#!/usr/bin/env bash
# Install Phone Vault for the current user: virtual environment, app menu entry and icon.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
cd "$APP_DIR"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { echo "Install venv support first: sudo apt install python3-venv"; exit 1; }
fi
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -e .

ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$APPS_DIR"
cp phonevault/assets/phone-vault.svg "$ICON_DIR/phone-vault.svg"
sed "s|@EXEC@|$APP_DIR/.venv/bin/phone-vault|" packaging/phone-vault.desktop > "$APPS_DIR/phone-vault.desktop"
update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true

if ! command -v adb >/dev/null 2>&1; then
  echo "Note: adb is not installed. For USB debugging scans run: sudo apt install adb"
fi
echo "Installed. Start Phone Vault from the app menu or run: $APP_DIR/.venv/bin/phone-vault"
