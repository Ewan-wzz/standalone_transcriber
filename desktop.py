"""Desktop shell for the standalone XHS offline transcriber."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from server import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    RequestHandler,
    TranscriberServer,
    TranscriptionEngine,
    application_home,
)


class DesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.home = application_home()
        self.engine = TranscriptionEngine(self.home)
        self.http_server: TranscriberServer | None = None
        self.server_thread: threading.Thread | None = None
        self.busy = False

        root.title("小红书离线视频转写")
        root.geometry("760x600")
        root.minsize(680, 520)
        root.configure(bg="#f5f6f8")
        root.protocol("WM_DELETE_WINDOW", self.close)

        self._configure_styles()
        self._build_ui()
        self._refresh_runtime()
        root.after(150, self.start_service)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(18, 10))
        style.configure("Action.TButton", font=("Microsoft YaHei UI", 9), padding=(14, 9))

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg="#f5f6f8", padx=28, pady=24)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg="#f5f6f8")
        header.pack(fill="x")
        title_box = tk.Frame(header, bg="#f5f6f8")
        title_box.pack(side="left", fill="x", expand=True)
        tk.Label(
            title_box,
            text="小红书视频文案提取",
            font=("Microsoft YaHei UI", 20, "bold"),
            fg="#202124",
            bg="#f5f6f8",
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="SenseVoice 本机离线识别，视频和文案不上传第三方",
            font=("Microsoft YaHei UI", 9),
            fg="#777c84",
            bg="#f5f6f8",
        ).pack(anchor="w", pady=(6, 0))
        self.status_label = tk.Label(
            header,
            text="正在启动",
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=12,
            pady=6,
            fg="#805b00",
            bg="#fff1bd",
        )
        self.status_label.pack(side="right", anchor="n")

        card = tk.Frame(outer, bg="#ffffff", padx=22, pady=18, highlightthickness=1, highlightbackground="#e1e3e7")
        card.pack(fill="x", pady=(22, 16))
        tk.Label(
            card,
            text="浏览器插件",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#25272b",
            bg="#ffffff",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            card,
            text="打开小红书视频笔记后，点击插件里的“提取当前视频文案”。请保持本程序运行。",
            font=("Microsoft YaHei UI", 9),
            fg="#6f747c",
            bg="#ffffff",
            wraplength=670,
            justify="left",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(7, 14))
        ttk.Button(card, text="打开插件文件夹", style="Action.TButton", command=self.open_extension).grid(row=2, column=0, sticky="w")
        ttk.Button(card, text="打开结果文件夹", style="Action.TButton", command=self.open_output).grid(row=2, column=1, sticky="w", padx=(10, 0))
        self.service_button = ttk.Button(card, text="停止本地服务", style="Action.TButton", command=self.toggle_service)
        self.service_button.grid(row=2, column=2, sticky="e", padx=(10, 0))
        card.columnconfigure(2, weight=1)

        local_card = tk.Frame(outer, bg="#ffffff", padx=22, pady=18, highlightthickness=1, highlightbackground="#e1e3e7")
        local_card.pack(fill="both", expand=True)
        local_head = tk.Frame(local_card, bg="#ffffff")
        local_head.pack(fill="x")
        tk.Label(
            local_head,
            text="本地视频转写",
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#25272b",
            bg="#ffffff",
        ).pack(side="left")
        self.local_button = ttk.Button(
            local_head,
            text="选择视频",
            style="Primary.TButton",
            command=self.choose_local_file,
        )
        self.local_button.pack(side="right")

        self.runtime_label = tk.Label(
            local_card,
            text="正在检查运行环境…",
            font=("Microsoft YaHei UI", 9),
            fg="#757a82",
            bg="#ffffff",
        )
        self.runtime_label.pack(anchor="w", pady=(8, 12))

        result_head = tk.Frame(local_card, bg="#ffffff")
        result_head.pack(fill="x")
        self.progress_label = tk.Label(
            result_head,
            text="转写结果会显示在这里",
            font=("Microsoft YaHei UI", 9),
            fg="#777c84",
            bg="#ffffff",
        )
        self.progress_label.pack(side="left")
        self.copy_button = ttk.Button(result_head, text="复制文本", command=self.copy_text, state="disabled")
        self.copy_button.pack(side="right")

        text_frame = tk.Frame(local_card, bg="#ffffff")
        text_frame.pack(fill="both", expand=True, pady=(10, 0))
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.result_text = tk.Text(
            text_frame,
            wrap="word",
            height=12,
            font=("Microsoft YaHei UI", 10),
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=10,
            fg="#26282c",
            bg="#fafafa",
            insertbackground="#26282c",
            yscrollcommand=scrollbar.set,
        )
        self.result_text.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.result_text.yview)

    def _set_status(self, text: str, state: str) -> None:
        colors = {
            "ready": ("#08783e", "#dff7e9"),
            "warning": ("#805b00", "#fff1bd"),
            "error": ("#a02b2b", "#fde5e5"),
        }
        fg, bg = colors[state]
        self.status_label.configure(text=text, fg=fg, bg=bg)

    def _refresh_runtime(self) -> bool:
        status = self.engine.runtime_status()
        if status.ready:
            self.runtime_label.configure(text="离线模型与音视频组件已就绪", fg="#08783e")
            self.local_button.configure(state="normal" if not self.busy else "disabled")
            return True
        self.runtime_label.configure(text="缺少：" + "、".join(status.missing), fg="#a02b2b")
        self.local_button.configure(state="disabled")
        return False

    def start_service(self) -> None:
        if self.http_server is not None:
            return
        if not self._refresh_runtime():
            self._set_status("组件未安装", "error")
            self.service_button.configure(text="启动本地服务", state="disabled")
            return
        try:
            self.http_server = TranscriberServer(
                (DEFAULT_HOST, DEFAULT_PORT),
                RequestHandler,
                self.engine,
                event_callback=self._queue_server_event,
            )
        except OSError as exc:
            self._set_status("端口被占用", "error")
            self.service_button.configure(text="重新启动")
            self.progress_label.configure(text=f"无法启动本地服务：{exc}", fg="#a02b2b")
            return
        self.server_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
        self.server_thread.start()
        self._set_status("插件服务运行中", "ready")
        self.service_button.configure(text="停止本地服务", state="normal")
        self.progress_label.configure(text="服务已自动启动，可以使用浏览器插件。", fg="#08783e")

    def stop_service(self) -> None:
        server = self.http_server
        if server is None:
            return
        self.http_server = None
        server.shutdown()
        server.server_close()
        self._set_status("服务已停止", "warning")
        self.service_button.configure(text="启动本地服务")
        self.progress_label.configure(text="本地服务已停止，浏览器插件暂不可用。", fg="#805b00")

    def toggle_service(self) -> None:
        if self.http_server is None:
            self.start_service()
        else:
            self.stop_service()

    def choose_local_file(self) -> None:
        if self.busy or not self._refresh_runtime():
            return
        selected = filedialog.askopenfilename(
            title="选择要转写的视频或音频",
            filetypes=[
                ("视频和音频", "*.mp4 *.mov *.mkv *.avi *.m4a *.mp3 *.wav *.aac *.flac"),
                ("所有文件", "*.*"),
            ],
        )
        if not selected:
            return
        self.busy = True
        self.local_button.configure(state="disabled", text="正在转写…")
        self.progress_label.configure(text=f"正在处理：{Path(selected).name}", fg="#805b00")
        self.copy_button.configure(state="disabled")
        self.result_text.delete("1.0", "end")
        thread = threading.Thread(target=self._transcribe_local, args=(Path(selected),), daemon=True)
        thread.start()

    def _transcribe_local(self, media_path: Path) -> None:
        try:
            result = self.engine.transcribe_file(media_path, title=media_path.stem)
            self.root.after(0, self._show_result, result.text, result.output_file, result.elapsed_seconds)
        except Exception as exc:
            self.root.after(0, self._show_error, str(exc))

    def _show_result(self, text: str, output_file: str, elapsed: float) -> None:
        self.busy = False
        self.local_button.configure(state="normal", text="选择视频")
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", text)
        self.copy_button.configure(state="normal")
        self.progress_label.configure(text=f"转写完成，用时 {elapsed:.2f} 秒；已保存到 {output_file}", fg="#08783e")

    def _show_error(self, error: str) -> None:
        self.busy = False
        self.local_button.configure(state="normal", text="选择视频")
        self.progress_label.configure(text="转写失败", fg="#a02b2b")
        messagebox.showerror("转写失败", error, parent=self.root)

    def _queue_server_event(self, event: str, payload: dict) -> None:
        self.root.after(0, self._handle_server_event, event, payload)

    def _handle_server_event(self, event: str, payload: dict) -> None:
        title = str(payload.get("title") or "当前小红书视频")
        if event == "receiving":
            size_mb = float(payload.get("size") or 0) / 1024 / 1024
            self.busy = True
            self.local_button.configure(state="disabled", text="插件任务进行中")
            self.copy_button.configure(state="disabled")
            self.result_text.delete("1.0", "end")
            self.progress_label.configure(
                text=f"正在接收插件视频：{title}（{size_mb:.1f} MB）",
                fg="#805b00",
            )
            return
        if event == "transcribing":
            self.progress_label.configure(
                text=f"视频已接收，正在离线识别：{title}",
                fg="#805b00",
            )
            return
        if event == "completed":
            result = payload.get("result") or {}
            self._show_result(
                str(result.get("text") or ""),
                str(result.get("output_file") or ""),
                float(result.get("elapsed_seconds") or 0),
            )
            return
        if event == "failed":
            self.busy = False
            self.local_button.configure(state="normal", text="选择视频")
            self.progress_label.configure(
                text=f"插件视频转写失败：{payload.get('error') or '未知错误'}",
                fg="#a02b2b",
            )

    def copy_text(self) -> None:
        text = self.result_text.get("1.0", "end").strip()
        if not text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.progress_label.configure(text="文本已复制到剪贴板", fg="#08783e")

    def open_extension(self) -> None:
        path = self.home / "extension"
        if not path.is_dir():
            messagebox.showerror("找不到插件", f"插件目录不存在：{path}", parent=self.root)
            return
        self._open_path(path)
        self.progress_label.configure(text="已打开插件文件夹，请在 Chrome/Edge 扩展页加载该文件夹。", fg="#555b64")

    def open_output(self) -> None:
        self.engine.output_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(self.engine.output_dir)

    @staticmethod
    def _open_path(path: Path) -> None:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)

    def close(self) -> None:
        if self.busy and not messagebox.askyesno("正在转写", "当前任务尚未完成，确定退出吗？", parent=self.root):
            return
        if self.http_server is not None:
            self.http_server.shutdown()
            self.http_server.server_close()
            self.http_server = None
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
