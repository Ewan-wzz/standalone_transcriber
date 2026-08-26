# 小红书离线视频转写工具

这是一个与 NoteAI 数据库和页面完全独立的本地工具。浏览器扩展只负责把当前小红书视频下载到“下载/小红书视频转写”文件夹，文件按“视频标题_下载时间”命名，每次只处理一条视频；桌面程序由用户手动批量选择本地视频，在后台顺序提取音轨并使用 SenseVoice 离线转写。两者互不依赖。

## 安装

1. 在 PowerShell 中运行 `setup.ps1`，下载并校验官方 SenseVoice Windows 运行程序、Q8 模型、VAD 模型和 FFmpeg。
2. 开发环境直接运行 `start.ps1`；给普通用户分发时，运行 `build.ps1` 生成桌面版 `XHSOfflineTranscriber.exe`，再运行 `package.ps1` 生成完整离线压缩包。
3. 在 Chrome 或 Edge 扩展管理页打开开发者模式，加载 `extension` 文件夹。
4. 打开小红书视频笔记，点击扩展并选择“下载当前视频”。
5. 下载完成后打开桌面程序，点击“选择视频（可多选）”加入批量任务。结果按“视频标题_转写结果_时间”命名并保存到 `output` 文件夹。

插件复用 NoteAI 的视频采集方式，在当前小红书页面上下文中读取并下载视频，不连接本地服务，也不要求桌面程序必须运行。转写结果保存到 `output` 文件夹。

完整压缩包解压后可直接双击 `XHSOfflineTranscriber.exe`。桌面程序提供手动选择本地视频转写、打开视频下载目录、打开结果目录和复制文本功能；不需要 Python，也不需要联网。首次安装开发版时运行 `setup.ps1` 需要联网下载并校验第三方运行文件。

macOS Apple Silicon 版使用相同界面和插件。在 Mac 上依次运行 `setup_macos.sh`、`build_macos.sh`、`package_macos.sh`，会生成包含 `.app`、离线模型、FFmpeg 和插件的完整压缩包。最终用户解压后直接打开 `XHSOfflineTranscriber.app`，不需要 Python；首次打开未公证的内部应用时需要右键选择“打开”。

## 命令行

本地文件也可以直接转写：

```powershell
python server.py --transcribe "D:\video.mp4" --title "视频标题"
```

## 第三方组件

- SenseVoice 源代码使用 MIT License，模型权重遵守 FunASR Model Open Source License Agreement。
- SenseVoice llama.cpp/GGUF 运行程序来自 QwenAudio/SenseVoice 官方 Release。
- FFmpeg Windows 构建来自 ffmpeg.org 下载页列出的 BtbN 构建，并选用 LGPL shared 版本。
