#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This installer currently supports Apple Silicon Macs only."
  exit 1
fi

app_root="$(cd "$(dirname "$0")" && pwd)"
runtime_root="$app_root/runtime"
sensevoice_root="$runtime_root/sensevoice"
ffmpeg_root="$runtime_root/ffmpeg"
model_root="$runtime_root/models"
setup_temp="$(mktemp -d -t xhs-transcriber-setup.XXXXXX)"

cleanup() {
  case "$setup_temp" in
    /private/var/folders/*/xhs-transcriber-setup.*|/var/folders/*/xhs-transcriber-setup.*|/tmp/xhs-transcriber-setup.*)
      rm -rf -- "$setup_temp"
      ;;
  esac
}
trap cleanup EXIT

verify_sha256() {
  local file="$1"
  local expected="$2"
  local actual
  actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  if [[ "$actual" != "$expected" ]]; then
    echo "SHA256 mismatch for $file"
    exit 1
  fi
}

mkdir -p "$sensevoice_root" "$ffmpeg_root" "$model_root"

echo "Downloading official SenseVoice Apple Silicon runtime..."
runtime_archive="$setup_temp/sensevoice-runtime.tar.gz"
curl -fL --retry 3 \
  "https://github.com/QwenAudio/SenseVoice/releases/download/runtime-llamacpp-v0.1.9/funasr-llamacpp-macos-arm64.tar.gz" \
  -o "$runtime_archive"
verify_sha256 "$runtime_archive" "2d5786784ad09d8f4def1d942f678728638fe601d00acf0dad7cf094a9328363"
mkdir -p "$setup_temp/sensevoice"
tar -xzf "$runtime_archive" -C "$setup_temp/sensevoice"
cp "$setup_temp/sensevoice/llama-funasr-vad" "$sensevoice_root/llama-funasr-sensevoice"
chmod 755 "$sensevoice_root/llama-funasr-sensevoice"

echo "Downloading verified Q8 and VAD models..."
curl -fL --retry 3 \
  "https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/90c1c61912018b70ada0fcc024ea24aca62f2e63/sensevoice-small-q8.gguf" \
  -o "$model_root/sensevoice-small-q8.gguf"
verify_sha256 "$model_root/sensevoice-small-q8.gguf" "4ae45c94422de949b387e2e0fb10d7e14e4c42c69db30c3444ecc7d4b844b7c5"
curl -fL --retry 3 \
  "https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/6840bae4c5c92ee8c04faaf4db23dd0105098d7f/fsmn-vad.gguf" \
  -o "$model_root/fsmn-vad.gguf"
verify_sha256 "$model_root/fsmn-vad.gguf" "1270f2559c495f4e7b6e739541151027d360761a3fda43fc147034f5719f5479"

echo "Downloading pinned macOS FFmpeg static build..."
ffmpeg_archive="$setup_temp/ffmpeg-9.0.1.zip"
curl -fL --retry 3 "https://evermeet.cx/ffmpeg/ffmpeg-9.0.1.zip" -o "$ffmpeg_archive"
mkdir -p "$setup_temp/ffmpeg"
ditto -x -k "$ffmpeg_archive" "$setup_temp/ffmpeg"
ffmpeg_binary="$(find "$setup_temp/ffmpeg" -type f -name ffmpeg -print -quit)"
if [[ -z "$ffmpeg_binary" ]]; then
  echo "FFmpeg executable is missing from the downloaded archive."
  exit 1
fi
cp "$ffmpeg_binary" "$ffmpeg_root/ffmpeg"
chmod 755 "$ffmpeg_root/ffmpeg"

echo "macOS offline runtime is ready."
