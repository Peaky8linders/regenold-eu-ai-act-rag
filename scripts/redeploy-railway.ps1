#Requires -Version 5.1
<#
.SYNOPSIS
  Trigger Railway production redeploy from latest Git source.

.DESCRIPTION
  Wraps `npx @railway/cli redeploy --yes --from-source`.
  Requires RAILWAY_TOKEN in the environment (or Railway CLI logged in locally).

  Optional env vars (same as GitHub Actions secrets):
    RAILWAY_SERVICE_ID, RAILWAY_ENVIRONMENT, RAILWAY_PROJECT_ID

  See docs/partners/regenold/RAILWAY_DEPLOY.md
#>
param(
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$args = @("redeploy", "--yes", "--from-source")
if ($env:RAILWAY_SERVICE_ID) { $args += @("--service", $env:RAILWAY_SERVICE_ID) }
if ($env:RAILWAY_ENVIRONMENT) { $args += @("-e", $env:RAILWAY_ENVIRONMENT) }
if ($env:RAILWAY_PROJECT_ID) { $args += @("-p", $env:RAILWAY_PROJECT_ID) }

if (-not $env:RAILWAY_TOKEN) {
    Write-Warning "RAILWAY_TOKEN is not set. Create one at https://railway.com/account/tokens"
    Write-Warning "Or run: railway login (interactive) then omit RAILWAY_TOKEN if linked."
}

$cli = "npx"
$cliArgs = @("--yes", "@railway/cli@4.65.0") + $args

Write-Host "Running: $cli $($cliArgs -join ' ')"
if ($WhatIf) { return }

& $cli @cliArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Redeploy triggered. Verify: curl https://regenold-eu-ai-act-rag-production.up.railway.app/healthz"
