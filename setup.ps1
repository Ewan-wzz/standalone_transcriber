$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$runtimeRoot = Join-Path $appRoot 'runtime'
$senseVoiceRoot = Join-Path $runtimeRoot 'sensevoice'
$ffmpegRoot = Join-Path $runtimeRoot 'ffmpeg'
$modelRoot = Join-Path $runtimeRoot 'models'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}

function Receive-VerifiedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )
    if (Test-Path -LiteralPath $Destination -PathType Leaf) {
        if ((Get-Sha256 $Destination) -eq $ExpectedSha256.ToLowerInvariant()) {
            Write-Host "Already verified: $Destination"
            return
        }
    }
    $downloadPath = "$Destination.download"
    Invoke-WebRequest -Uri $Uri -OutFile $downloadPath -UseBasicParsing
    $actual = Get-Sha256 $downloadPath
    if ($actual -ne $ExpectedSha256.ToLowerInvariant()) {
        throw "SHA256 mismatch for $Uri. Expected $ExpectedSha256, got $actual"
    }
    Move-Item -LiteralPath $downloadPath -Destination $Destination -Force
}

New-Item -ItemType Directory -Path $senseVoiceRoot -Force | Out-Null
New-Item -ItemType Directory -Path $ffmpegRoot -Force | Out-Null
New-Item -ItemType Directory -Path $modelRoot -Force | Out-Null

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$setupTemp = Join-Path $tempRoot ("xhs-transcriber-setup-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $setupTemp -ErrorAction Stop | Out-Null

try {
    Write-Host 'Downloading official SenseVoice native runtime...'
    $release = Invoke-RestMethod -Uri 'https://api.github.com/repos/QwenAudio/SenseVoice/releases/latest' -Headers @{ 'User-Agent' = 'XHS-Offline-Transcriber' }
    $runtimeAsset = $release.assets | Where-Object { $_.name -eq 'funasr-llamacpp-windows-x64.zip' } | Select-Object -First 1
    if (-not $runtimeAsset -or -not $runtimeAsset.digest) {
        throw 'Official Windows x64 runtime asset was not found.'
    }
    $runtimeZip = Join-Path $setupTemp 'sensevoice-runtime.zip'
    Receive-VerifiedFile -Uri $runtimeAsset.browser_download_url -Destination $runtimeZip -ExpectedSha256 ($runtimeAsset.digest -replace '^sha256:', '')
    $runtimeExtract = Join-Path $setupTemp 'sensevoice-runtime'
    Expand-Archive -LiteralPath $runtimeZip -DestinationPath $runtimeExtract -Force
    $runtimeExe = Get-ChildItem -LiteralPath $runtimeExtract -Filter 'llama-funasr-sensevoice.exe' -File -Recurse | Select-Object -First 1
    if (-not $runtimeExe) { throw 'SenseVoice executable is missing from the official archive.' }
    Copy-Item -LiteralPath $runtimeExe.FullName -Destination (Join-Path $senseVoiceRoot 'llama-funasr-sensevoice.exe') -Force
    $runtimeReadme = Join-Path $runtimeExe.Directory.FullName 'README.md'
    if (Test-Path -LiteralPath $runtimeReadme -PathType Leaf) {
        Copy-Item -LiteralPath $runtimeReadme -Destination (Join-Path $senseVoiceRoot 'README.md') -Force
    }

    Write-Host 'Downloading verified SenseVoice Q8 and VAD models...'
    Receive-VerifiedFile `
        -Uri 'https://huggingface.co/FunAudioLLM/SenseVoiceSmall-GGUF/resolve/90c1c61912018b70ada0fcc024ea24aca62f2e63/sensevoice-small-q8.gguf' `
        -Destination (Join-Path $modelRoot 'sensevoice-small-q8.gguf') `
        -ExpectedSha256 '4ae45c94422de949b387e2e0fb10d7e14e4c42c69db30c3444ecc7d4b844b7c5'
    Receive-VerifiedFile `
        -Uri 'https://huggingface.co/FunAudioLLM/fsmn-vad-GGUF/resolve/6840bae4c5c92ee8c04faaf4db23dd0105098d7f/fsmn-vad.gguf' `
        -Destination (Join-Path $modelRoot 'fsmn-vad.gguf') `
        -ExpectedSha256 '1270f2559c495f4e7b6e739541151027d360761a3fda43fc147034f5719f5479'

    Write-Host 'Downloading FFmpeg Windows build linked by ffmpeg.org...'
    $ffmpegRelease = Invoke-RestMethod -Uri 'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest' -Headers @{ 'User-Agent' = 'XHS-Offline-Transcriber' }
    $ffmpegAsset = $ffmpegRelease.assets | Where-Object { $_.name -eq 'ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip' } | Select-Object -First 1
    if (-not $ffmpegAsset -or -not $ffmpegAsset.digest) {
        throw 'FFmpeg Windows LGPL asset was not found.'
    }
    $ffmpegZip = Join-Path $setupTemp 'ffmpeg.zip'
    Receive-VerifiedFile -Uri $ffmpegAsset.browser_download_url -Destination $ffmpegZip -ExpectedSha256 ($ffmpegAsset.digest -replace '^sha256:', '')
    $ffmpegExtract = Join-Path $setupTemp 'ffmpeg'
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegExtract -Force
    $ffmpegExe = Get-ChildItem -LiteralPath $ffmpegExtract -Filter 'ffmpeg.exe' -File -Recurse | Select-Object -First 1
    if (-not $ffmpegExe) { throw 'ffmpeg.exe is missing from the downloaded archive.' }
    Copy-Item -LiteralPath $ffmpegExe.FullName -Destination (Join-Path $ffmpegRoot 'ffmpeg.exe') -Force
    Get-ChildItem -LiteralPath $ffmpegExe.Directory.FullName -Filter '*.dll' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ffmpegRoot $_.Name) -Force
    }

    Write-Host ''
    Write-Host 'Offline runtime is ready.' -ForegroundColor Green
    Write-Host "Run: powershell -ExecutionPolicy Bypass -File `"$appRoot\start.ps1`""
    Write-Host "Load extension folder: $appRoot\extension"
}
finally {
    $resolvedTemp = [IO.Path]::GetFullPath($setupTemp).TrimEnd('\')
    $expectedParent = [IO.Path]::GetDirectoryName($resolvedTemp)
    $leaf = [IO.Path]::GetFileName($resolvedTemp)
    if ($expectedParent -eq $tempRoot -and $leaf.StartsWith('xhs-transcriber-setup-') -and (Test-Path -LiteralPath $resolvedTemp)) {
        $item = Get-Item -LiteralPath $resolvedTemp -Force -ErrorAction Stop
        if ($item.PSIsContainer -and (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction Stop
        }
    }
}
