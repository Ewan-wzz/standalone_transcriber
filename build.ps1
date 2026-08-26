$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$appRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$venvRoot = Join-Path $appRoot '.build-venv'
$venvPython = Join-Path $venvRoot 'Scripts\python.exe'
$distRoot = Join-Path $appRoot 'dist-windows'

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $python = Get-Command python -ErrorAction Stop
    & $python.Source -m venv $venvRoot
}
& $venvPython -m pip install --disable-pip-version-check --upgrade pip pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Build dependency installation failed with exit code $LASTEXITCODE"
}
& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name XHSOfflineTranscriber `
    --distpath $distRoot `
    --workpath (Join-Path $appRoot 'build') `
    --specpath (Join-Path $appRoot 'build') `
    (Join-Path $appRoot 'desktop.py')
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "Built: $distRoot\XHSOfflineTranscriber.exe" -ForegroundColor Green
