# Builds the Python engine sidecar into a frozen .exe for the Tauri bundle.
#
# Output: desktop/src-tauri/binaries/cutlist-engine-sidecar-x86_64-pc-windows-msvc.exe
# (Tauri appends the target triple to externalBin paths.)
#
# Requires: Python 3.11+ with the repo installed (pip install -e .)
# Run from repo root:  npm --prefix desktop run sidecar:build

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path "$PSScriptRoot\..\.."
$binDir = Join-Path $repoRoot "desktop\src-tauri\binaries"
$triple = "x86_64-pc-windows-msvc"

New-Item -ItemType Directory -Force -Path $binDir | Out-Null

Push-Location $repoRoot
try {
    # PyInstaller on demand
    python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        python -m pip install pyinstaller
    }

    python -m PyInstaller `
        --onefile `
        --name cutlist-engine-sidecar `
        --distpath "$binDir" `
        --workpath "$env:TEMP\cutlist_sidecar_build" `
        --specpath "$env:TEMP\cutlist_sidecar_build" `
        --collect-all cutlist_engine `
        --hidden-import uvicorn.logging `
        --hidden-import uvicorn.loops.auto `
        --hidden-import uvicorn.protocols.http.auto `
        --hidden-import uvicorn.protocols.websockets.auto `
        --hidden-import uvicorn.lifespan.on `
        --hidden-import anyio._backends._asyncio `
        desktop\sidecar\sidecar_main.py

    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

    # Tauri expects the binary to carry the target-triple suffix
    $src = Join-Path $binDir "cutlist-engine-sidecar.exe"
    $dst = Join-Path $binDir "cutlist-engine-sidecar-$triple.exe"
    Move-Item -Force $src $dst

    Write-Host ""
    Write-Host "Sidecar ready: $dst"
}
finally {
    Pop-Location
}
