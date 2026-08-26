#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "The macOS app must be built on an Apple Silicon Mac."
  exit 1
fi

app_root="$(cd "$(dirname "$0")" && pwd)"
venv_root="$app_root/.build-venv-macos"
python_bin="$venv_root/bin/python"

if [[ ! -x "$python_bin" ]]; then
  python3 -m venv "$venv_root"
fi

"$python_bin" -m pip install --disable-pip-version-check --upgrade pip pyinstaller
"$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --onefile \
  --windowed \
  --name XHSOfflineTranscriber \
  --distpath "$app_root/dist-macos" \
  --workpath "$app_root/build-macos" \
  --specpath "$app_root/build-macos" \
  "$app_root/desktop.py"

app_bundle="$app_root/dist-macos/XHSOfflineTranscriber.app"
test -d "$app_bundle"
codesign --force --deep --sign - "$app_bundle"
echo "Built: $app_bundle"
