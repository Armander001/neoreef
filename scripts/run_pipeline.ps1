# Run the Cesium pipeline from the repo root.
#   .\scripts\run_pipeline.ps1                  # --stage all
#   .\scripts\run_pipeline.ps1 manifest         # one stage
#   .\scripts\run_pipeline.ps1 serve -Port 8765
param(
    [string]$Stage = "all",
    [string]$Config = "config/cesium_config.json",
    [int]$Port = 0,
    [switch]$Rescan
)
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$args = @("cesium_pipeline.py", "--config", $Config, "--stage", $Stage)
if ($Port -gt 0) { $args += @("--port", "$Port") }
if ($Rescan) { $args += "--rescan" }
# Prefer the conda env's python if active, else whatever `python` resolves to.
$py = if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX "python.exe" } else { "python" }
& $py @args
exit $LASTEXITCODE
