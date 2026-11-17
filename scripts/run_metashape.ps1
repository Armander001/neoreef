# Run the photogrammetry batch inside Metashape Pro.
#   .\scripts\run_metashape.ps1
# Edit the USER CONFIG block in Batch_metashape.py first (TARGET_FOLDER, paths).
param(
    [string]$Metashape = "C:\Program Files\Agisoft\Metashape Pro\metashape.exe"
)
$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $Metashape)) { Write-Error "metashape.exe not found at $Metashape"; exit 1 }
& $Metashape -r (Join-Path $repo "Batch_metashape.py")
exit $LASTEXITCODE
