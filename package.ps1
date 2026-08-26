$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$sourceExe = Join-Path $appRoot 'dist-windows\XHSOfflineTranscriber.exe'
$runtimeRoot = Join-Path $appRoot 'runtime'
$releaseRoot = Join-Path $appRoot 'release'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$packageName = "XHSOfflineTranscriber-0.1.0-windows-x64-$stamp"
$packageRoot = Join-Path $releaseRoot $packageName

$required = @(
    $sourceExe,
    (Join-Path $runtimeRoot 'sensevoice\llama-funasr-sensevoice.exe'),
    (Join-Path $runtimeRoot 'ffmpeg\ffmpeg.exe'),
    (Join-Path $runtimeRoot 'models\sensevoice-small-q8.gguf'),
    (Join-Path $runtimeRoot 'models\fsmn-vad.gguf')
)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing package file: $path"
    }
}

New-Item -ItemType Directory -Path (Join-Path $packageRoot 'runtime\sensevoice') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'runtime\ffmpeg') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $packageRoot 'runtime\models') -Force | Out-Null

Copy-Item -LiteralPath $sourceExe -Destination (Join-Path $packageRoot 'XHSOfflineTranscriber.exe')
Copy-Item -LiteralPath (Join-Path $appRoot 'start.bat') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $appRoot 'README.md') -Destination $packageRoot
Copy-Item -LiteralPath (Join-Path $appRoot 'extension') -Destination $packageRoot -Recurse
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'sensevoice\llama-funasr-sensevoice.exe') -Destination (Join-Path $packageRoot 'runtime\sensevoice')
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'sensevoice\README.md') -Destination (Join-Path $packageRoot 'runtime\sensevoice') -ErrorAction SilentlyContinue
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'ffmpeg\ffmpeg.exe') -Destination (Join-Path $packageRoot 'runtime\ffmpeg')
Get-ChildItem -LiteralPath (Join-Path $runtimeRoot 'ffmpeg') -Filter '*.dll' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $packageRoot 'runtime\ffmpeg')
}
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'models\sensevoice-small-q8.gguf') -Destination (Join-Path $packageRoot 'runtime\models')
Copy-Item -LiteralPath (Join-Path $runtimeRoot 'models\fsmn-vad.gguf') -Destination (Join-Path $packageRoot 'runtime\models')

$zipPath = Join-Path $releaseRoot ($packageName + '.zip')
Compress-Archive -Path (Join-Path $packageRoot '*') -DestinationPath $zipPath -CompressionLevel Optimal
$size = (Get-Item -LiteralPath $zipPath).Length / 1MB
Write-Host ("Package: {0} ({1:N1} MB)" -f $zipPath, $size) -ForegroundColor Green
