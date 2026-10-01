$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

python -m pip install pyinstaller
python -m PyInstaller packaging\chatstyle.spec --noconfirm --distpath dist --workpath build\pyinstaller

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Built: dist\chatstyle.exe"
