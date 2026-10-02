# Build chatstyle.exe (console) and chatstyle-gui.exe (window) with PyInstaller.
# (ASCII only: Windows PowerShell 5.1 reads BOM-less files as ANSI.)
#   powershell -File packaging\build_exe.ps1                 both, one file each (release)
#   powershell -File packaging\build_exe.ps1 -Target cli     only dist\chatstyle.exe
#   powershell -File packaging\build_exe.ps1 -Target gui     only dist\chatstyle-gui.exe
#   powershell -File packaging\build_exe.ps1 -OneDir         folders dist\chatstyle\ (debugging)
#   powershell -File packaging\build_exe.ps1 -NoMorph        without parts of speech (pymorphy3 is in by default, about +9 MB)
# Run `pip install -e .` first: the core module chatstyle._core must be importable.
param(
    [ValidateSet('cli', 'gui', 'all')][string]$Target = 'all',
    [switch]$OneDir,
    [switch]$NoMorph
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

# Build tools come from the hash-pinned lock file (pip refuses any file whose hash differs).
if ($NoMorph) {
    python -m pip install --require-hashes -r packaging\requirements.lock
    Remove-Item Env:\CHATSTYLE_WITH_MORPH -ErrorAction SilentlyContinue
} else {
    python -m pip install --require-hashes -r packaging\requirements-morph.lock
    $env:CHATSTYLE_WITH_MORPH = '1'
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The version resource is generated from chatstyle.__version__ (single source of the version).
python packaging\make_version_info.py build\version_info.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path python\chatstyle\resources\chatstyle.ico)) {
    Write-Warning 'python\chatstyle\resources\chatstyle.ico is missing: the exe will get the default PyInstaller icon (see packaging\make_icon.py).'
}

if ($OneDir) { $env:CHATSTYLE_ONEDIR = '1' } else { Remove-Item Env:\CHATSTYLE_ONEDIR -ErrorAction SilentlyContinue }

function Build-Exe([string]$Spec, [string]$Name) {
    python -m PyInstaller $Spec --noconfirm --distpath dist --workpath build\pyinstaller\$Name
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($OneDir) { $exe = "dist\$Name\$Name.exe" } else { $exe = "dist\$Name.exe" }
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "Built: $exe ($size MB)"
}

if ($Target -eq 'cli' -or $Target -eq 'all') { Build-Exe 'packaging\chatstyle.spec' 'chatstyle' }
if ($Target -eq 'gui' -or $Target -eq 'all') { Build-Exe 'packaging\chatstyle_gui.spec' 'chatstyle-gui' }

# SHA-256 of every built exe: dist\SHA256SUMS.txt (check_exe.py verifies it).
if (-not $OneDir) {
    $lines = Get-ChildItem dist -Filter *.exe | Sort-Object Name | ForEach-Object {
        $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()
        "$hash  $($_.Name)"
    }
    Set-Content -Path dist\SHA256SUMS.txt -Value $lines -Encoding ascii
    Write-Host 'Wrote dist\SHA256SUMS.txt'
}
