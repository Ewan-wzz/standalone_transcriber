#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "The macOS package must be created on an Apple Silicon Mac."
  exit 1
fi

app_root="$(cd "$(dirname "$0")" && pwd)"
release_root="$app_root/release"
stamp="$(date +%Y%m%d-%H%M%S)"
package_name="XHSOfflineTranscriber-0.1.0-macos-arm64-$stamp"
package_root="$release_root/$package_name"
app_bundle="$app_root/dist-macos/XHSOfflineTranscriber.app"

required=(
  "$app_bundle"
  "$app_root/runtime/sensevoice/llama-funasr-sensevoice"
  "$app_root/runtime/ffmpeg/ffmpeg"
  "$app_root/runtime/models/sensevoice-small-q8.gguf"
  "$app_root/runtime/models/fsmn-vad.gguf"
)
for path in "${required[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "Missing package file: $path"
    exit 1
  fi
done

mkdir -p "$package_root/runtime/sensevoice" "$package_root/runtime/ffmpeg" "$package_root/runtime/models"
ditto "$app_bundle" "$package_root/XHSOfflineTranscriber.app"
ditto "$app_root/extension" "$package_root/extension"
cp "$app_root/README.md" "$package_root/README.md"
cp "$app_root/runtime/sensevoice/llama-funasr-sensevoice" "$package_root/runtime/sensevoice/"
cp "$app_root/runtime/ffmpeg/ffmpeg" "$package_root/runtime/ffmpeg/"
cp "$app_root/runtime/models/sensevoice-small-q8.gguf" "$package_root/runtime/models/"
cp "$app_root/runtime/models/fsmn-vad.gguf" "$package_root/runtime/models/"
chmod 755 "$package_root/runtime/sensevoice/llama-funasr-sensevoice" "$package_root/runtime/ffmpeg/ffmpeg"

zip_path="$release_root/$package_name.zip"
ditto -c -k --sequesterRsrc --keepParent "$package_root" "$zip_path"
echo "Package: $zip_path"
