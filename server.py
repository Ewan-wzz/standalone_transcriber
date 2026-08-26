"""Standalone local service for XHS video transcription.

This module intentionally has no NoteAI imports and uses only the Python
standard library. The speech runtime, model and FFmpeg are external files
installed beside the executable by setup.ps1.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_VERSION = "0.2.0"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_VIDEO_BYTES = 1536 * 1024 * 1024
MAX_METADATA_BYTES = 16 * 1024
CLIENT_HEADER = "xhs-offline-extension"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
LEADING_TAGS_RE = re.compile(r"^(?:<\|[^|>]+\|>)+\s*")


def application_home() -> Path:
    configured = os.environ.get("XHS_TRANSCRIBER_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            app_bundle = next(
                (parent for parent in executable.parents if parent.suffix == ".app"), None
            )
            if app_bundle is not None:
                return app_bundle.parent
        return executable.parent
    return Path(__file__).resolve().parent


def safe_filename(value: str, fallback: str = "transcript") -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\r\n\x00-\x1f]", "_", value or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._")
    return (cleaned[:80] or fallback).strip()


def parse_transcription_output(stdout: str) -> str:
    text = ANSI_RE.sub("", stdout or "").strip()
    if not text:
        return ""
    lines = []
    for line in text.splitlines():
        value = line.strip()
        if not value:
            continue
        if value.startswith(("build:", "system_info:", "main:", "load_")):
            continue
        lines.append(value)
    result = "\n".join(lines).strip()
    return LEADING_TAGS_RE.sub("", result).strip()


def format_transcript(text: str, paragraph_length: int = 110) -> str:
    """按标点做轻量分段，不改写识别内容。"""
    source = re.sub(r"[ \t]+", " ", text or "").strip()
    if not source:
        return ""
    paragraphs: list[str] = []
    current = ""
    for part in re.split(r"(?<=[。！？!?])", source):
        value = part.strip()
        if not value:
            continue
        current += value
        if len(current) >= paragraph_length:
            paragraphs.append(current)
            current = ""
    if current:
        paragraphs.append(current)
    return "\n\n".join(paragraphs) if paragraphs else source


@dataclass(slots=True)
class RuntimeStatus:
    ready: bool
    missing: list[str]
    ffmpeg: str | None
    sensevoice: str | None
    model: str | None
    vad_model: str | None


@dataclass(slots=True)
class TranscriptionResult:
    text: str
    title: str
    note_id: str
    output_file: str
    elapsed_seconds: float


class TranscriptionEngine:
    def __init__(self, home: Path | None = None):
        self.home = (home or application_home()).resolve()
        self.output_dir = self.home / "output"
        self.sensevoice_dir = self.home / "runtime" / "sensevoice"
        self.ffmpeg_dir = self.home / "runtime" / "ffmpeg"
        self.model_dir = self.home / "runtime" / "models"

    @staticmethod
    def _first_existing(candidates: list[Path]) -> Path | None:
        return next((path for path in candidates if path.is_file()), None)

    def runtime_status(self) -> RuntimeStatus:
        ffmpeg = self._first_existing(
            [
                self.ffmpeg_dir / "ffmpeg.exe",
                self.ffmpeg_dir / "ffmpeg",
                self.ffmpeg_dir / "bin" / "ffmpeg.exe",
                self.ffmpeg_dir / "bin" / "ffmpeg",
            ]
        )
        if ffmpeg is None:
            from_path = shutil.which("ffmpeg")
            ffmpeg = Path(from_path) if from_path else None

        sensevoice = self._first_existing(
            [
                self.sensevoice_dir / "llama-funasr-sensevoice.exe",
                self.sensevoice_dir / "llama-funasr-sensevoice",
                self.sensevoice_dir / "bin" / "llama-funasr-sensevoice.exe",
                self.sensevoice_dir / "bin" / "llama-funasr-sensevoice",
            ]
        )
        model = self.model_dir / "sensevoice-small-q8.gguf"
        vad = self.model_dir / "fsmn-vad.gguf"
        missing = []
        if ffmpeg is None:
            missing.append("FFmpeg")
        if sensevoice is None:
            missing.append("SenseVoice 本地运行程序")
        if not model.is_file():
            missing.append("SenseVoice Q8 模型")
        if not vad.is_file():
            missing.append("FSMN-VAD 模型")
        return RuntimeStatus(
            ready=not missing,
            missing=missing,
            ffmpeg=str(ffmpeg) if ffmpeg else None,
            sensevoice=str(sensevoice) if sensevoice else None,
            model=str(model) if model.is_file() else None,
            vad_model=str(vad) if vad.is_file() else None,
        )

    @staticmethod
    def _run(command: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        kwargs: dict[str, Any] = {
            "args": command,
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": timeout,
            "check": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run(**kwargs)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "未知错误").strip()
            raise RuntimeError(detail[-1200:])
        return completed

    def transcribe_file(
        self, media_path: Path, title: str = "", note_id: str = ""
    ) -> TranscriptionResult:
        status = self.runtime_status()
        if not status.ready:
            raise RuntimeError("运行环境未安装：" + "、".join(status.missing))
        media_path = media_path.resolve()
        if not media_path.is_file():
            raise FileNotFoundError(f"找不到媒体文件：{media_path}")

        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="xhs-transcribe-") as temp_name:
            wav_path = Path(temp_name) / "audio.wav"
            self._run(
                [
                    status.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(media_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "pcm_s16le",
                    str(wav_path),
                ],
                timeout=600,
            )
            completed = self._run(
                [
                    status.sensevoice,
                    "-m",
                    status.model,
                    "-a",
                    str(wav_path),
                    "--vad",
                    status.vad_model,
                ],
                timeout=1800,
            )
        text = format_transcript(parse_transcription_output(completed.stdout))
        if not text:
            raise RuntimeError("转写程序没有返回文本")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output_name = f"{safe_filename(title, note_id or '未命名视频')}_转写结果_{stamp}.txt"
        output_path = self.output_dir / output_name
        output_path.write_text(text, encoding="utf-8")
        return TranscriptionResult(
            text=text,
            title=title,
            note_id=note_id,
            output_file=str(output_path.resolve()),
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )

class TranscriberServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, engine: TranscriptionEngine, event_callback=None):
        super().__init__(address, handler)
        self.engine = engine
        self.transcription_lock = threading.Lock()
        self.event_callback = event_callback

    def notify(self, event: str, **payload: Any) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event, payload)
        except Exception:
            pass


class RequestHandler(BaseHTTPRequestHandler):
    server: TranscriberServer

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def _origin_allowed(self) -> bool:
        origin = (self.headers.get("Origin") or "").strip()
        return not origin or origin.startswith("chrome-extension://")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = (self.headers.get("Origin") or "").strip()
        if origin.startswith("chrome-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        if not self._origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "不允许的来源"})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        origin = (self.headers.get("Origin") or "").strip()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Transcriber-Client, X-Transcriber-Metadata",
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("", "/health"):
            runtime = self.server.engine.runtime_status()
            self._send_json(
                HTTPStatus.OK,
                {"service": "XHS Offline Transcriber", "version": APP_VERSION, **asdict(runtime)},
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/api/transcribe-upload":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
            return
        if not self._origin_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "不允许的来源"})
            return
        if self.headers.get("X-Transcriber-Client") != CLIENT_HEADER:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "客户端标识无效"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_VIDEO_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "视频内容无效或超过 1.5 GB"})
            return
        metadata_value = self.headers.get("X-Transcriber-Metadata") or ""
        if len(metadata_value.encode("ascii", errors="ignore")) > MAX_METADATA_BYTES:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "视频信息过长"})
            return
        try:
            metadata = json.loads(urllib.parse.unquote(metadata_value) or "{}")
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "视频信息格式无效"})
            return

        if not self.server.transcription_lock.acquire(blocking=False):
            self._send_json(HTTPStatus.CONFLICT, {"error": "已有视频正在转写"})
            return
        try:
            self.server.notify(
                "receiving",
                title=str(metadata.get("title") or ""),
                size=length,
            )
            with tempfile.TemporaryDirectory(prefix="xhs-video-") as temp_name:
                video_path = Path(temp_name) / "source.mp4"
                remaining = length
                with video_path.open("wb") as output:
                    while remaining > 0:
                        chunk = self.rfile.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        output.write(chunk)
                        remaining -= len(chunk)
                if remaining != 0:
                    raise ValueError("视频内容接收不完整")
                self.server.notify(
                    "transcribing",
                    title=str(metadata.get("title") or ""),
                    size=length,
                )
                result = self.server.engine.transcribe_file(
                    video_path,
                    title=str(metadata.get("title") or ""),
                    note_id=str(metadata.get("note_id") or ""),
                )
            self.server.notify("completed", result=asdict(result))
            self._send_json(HTTPStatus.OK, {"ok": True, **asdict(result)})
        except (ValueError, FileNotFoundError) as exc:
            self.server.notify("failed", error=str(exc))
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            self.server.notify("failed", error=str(exc))
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
        finally:
            self.server.transcription_lock.release()


def serve(host: str, port: int, home: Path | None = None) -> None:
    engine = TranscriptionEngine(home)
    server = TranscriberServer((host, port), RequestHandler, engine)
    print(f"XHS Offline Transcriber {APP_VERSION}")
    print(f"Listening on http://{host}:{port}")
    status = engine.runtime_status()
    if not status.ready:
        print("Runtime missing: " + ", ".join(status.missing))
        print("Run setup.ps1 before transcribing.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="XHS offline video transcription service")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--home", type=Path)
    parser.add_argument("--transcribe", type=Path, help="Transcribe a local media file and exit")
    parser.add_argument("--title", default="")
    args = parser.parse_args()
    if args.transcribe:
        try:
            result = TranscriptionEngine(args.home).transcribe_file(
                args.transcribe, title=args.title
            )
            print(result.text)
            print(f"\nSaved: {result.output_file}")
            print(f"Elapsed: {result.elapsed_seconds}s")
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    serve(args.host, args.port, args.home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
