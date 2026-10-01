# Build chatstyle.exe with PyInstaller. (ASCII only: Windows PowerShell 5.1 reads BOM-less files as ANSI.)
#   powershell -File packaging\build_exe.ps1            one file: dist\chatstyle.exe (release)
#   powershell -File packaging\build_exe.ps1 -OneDir    folder:   dist\chatstyle\    (debugging)
# Run `pip install -e .` first: the core module chatstyle._core must be importable.
param([switch]$OneDir)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# The version resource is generated from chatstyle.__version__ (single source of the version).
python packaging\make_version_info.py build\version_info.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not (Test-Path packaging\chatstyle.ico)) {
    Write-Warning 'packaging\chatstyle.ico is missing: the exe will get the default PyInstaller icon (see packaging\make_icon.py).'
}

if ($OneDir) { $env:CHATSTYLE_ONEDIR = '1' } else { Remove-Item Env:\CHATSTYLE_ONEDIR -ErrorAction SilentlyContinue }
python -m PyInstaller packaging\chatstyle.spec --noconfirm --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($OneDir) { $exe = 'dist\chatstyle\chatstyle.exe' } else { $exe = 'dist\chatstyle.exe' }
$size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
Write-Host "Built: $exe ($size MB)"
