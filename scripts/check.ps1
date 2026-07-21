$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$exitCode = 1

Push-Location -LiteralPath $repoRoot
try {
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & python (Join-Path $PSScriptRoot "check.py")
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
