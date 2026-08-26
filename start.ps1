$ErrorActionPreference = 'Stop'
$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$executable = Join-Path $appRoot 'XHSOfflineTranscriber.exe'

if (Test-Path -LiteralPath $executable -PathType Leaf) {
    & $executable --home $appRoot
    exit $LASTEXITCODE
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw '未找到 XHSOfflineTranscriber.exe 或 Python。请先运行 build.ps1 生成独立程序。'
}
& $python.Source (Join-Path $appRoot 'server.py') --home $appRoot
exit $LASTEXITCODE
