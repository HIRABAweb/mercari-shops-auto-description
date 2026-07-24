[CmdletBinding()]
param(
    [switch]$Execute
)

$ErrorActionPreference = "Stop"

$ProjectId = "gen-lang-client-0122735738"
$Region = "asia-northeast1"
$FunctionName = "image-to-description"
$Account = "hirabaaiwork@gmail.com"
$Memory = "512MiB"
$Concurrency = "1"
$Timeout = "540s"
$EntryPoint = "generate_description_from_trigger"
$Runtime = "python312"

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourcePath = Join-Path $RepositoryRoot "image-to-description"

Push-Location $RepositoryRoot
try {
    $ComponentStatus = @(
        & git status --porcelain --untracked-files=all -- image-to-description
    )
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to inspect the image-to-description source state."
    }
    if ($ComponentStatus.Count -gt 0) {
        throw "Commit and review all image-to-description changes before preparing deployment."
    }

    & python scripts/check.py
    if ($LASTEXITCODE -ne 0) {
        throw "Pre-deployment verification failed."
    }

    $SourceCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $SourceCommit) {
        throw "Failed to resolve the source commit."
    }

    $DeployArguments = @(
        "functions", "deploy", $FunctionName,
        "--gen2",
        "--project=$ProjectId",
        "--region=$Region",
        "--account=$Account",
        "--runtime=$Runtime",
        "--source=$SourcePath",
        "--entry-point=$EntryPoint",
        "--memory=$Memory",
        "--concurrency=$Concurrency",
        "--timeout=$Timeout",
        "--quiet"
    )

    Write-Host "Source commit: $SourceCommit"
    Write-Host "Project: $ProjectId"
    Write-Host "Region: $Region"
    Write-Host "Function: $FunctionName"
    Write-Host "Memory: $Memory"
    Write-Host "Concurrency: $Concurrency"
    Write-Host "Timeout: $Timeout"
    Write-Host "Command: gcloud $($DeployArguments -join ' ')"

    if (-not $Execute) {
        Write-Host "Dry run only. No external operation was executed."
        return
    }

    & gcloud @DeployArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Deployment failed. Do not retry or change permissions automatically."
    }
}
finally {
    Pop-Location
}
