# ============================================================================
# FILE: run_tests.ps1
# PATH: backend/scripts/run_tests.ps1
# PURPOSE: Full-suite gate runner. Uses pytest-xdist to parallelize the suite
#          across workers so the whole run stays well under the live-Supabase
#          connection-drop window diagnosed in CONNECTION_STABILITY_REPORT.md.
#
#   -n 4              four parallel workers
#   --dist=loadscope  group tests by module/class so related tests (and any
#                     module-level shared state) stay in one worker
#   --timeout=120     per-test bound; a stalled pooler query fails fast
#
# Usage:
#   pwsh -File backend/scripts/run_tests.ps1            # from repo root
#   pwsh -File scripts/run_tests.ps1                    # from backend/
# ============================================================================

param(
    [string]$BackendDir = (Split-Path -Parent $PSScriptRoot),
    [string]$Python = "python",
    [int]$Workers = 4,
    [int]$Timeout = 120
)

$ErrorActionPreference = "Stop"
$sw = [System.Diagnostics.Stopwatch]::StartNew()

Push-Location $BackendDir
try {
    & $Python -m pytest tests/ -n $Workers -q --dist=loadscope `
        --timeout=$Timeout --no-header -p no:cacheprovider
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

$sw.Stop()
Write-Host ("Full suite (xdist -n {0}): exit={1} ({2}s)" -f `
    $Workers, $code, [math]::Round($sw.Elapsed.TotalSeconds, 1))
exit $code
