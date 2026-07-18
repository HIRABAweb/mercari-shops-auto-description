param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,
    [string]$ClientId = "",
    [securestring]$ClientSecret
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. Install Google Cloud CLI first."
    }
}

function ConvertFrom-SecureStringToPlainText([securestring]$SecureValue) {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}

Require-Command "gcloud"

if (-not $ClientId) {
    $ClientId = Read-Host "OAuth client ID"
}

if (-not $ClientSecret) {
    $ClientSecret = Read-Host "OAuth client secret" -AsSecureString
}

$plainSecret = ConvertFrom-SecureStringToPlainText $ClientSecret
$settingsPath = Join-Path $env:TEMP "iap_settings_$([Guid]::NewGuid().ToString('N')).yaml"

try {
    @"
access_settings:
  oauth_settings:
    client_id: $ClientId
    client_secret: $plainSecret
"@ | Set-Content -Path $settingsPath -Encoding UTF8

    gcloud iap settings set $settingsPath --project=$ProjectId
}
finally {
    if (Test-Path $settingsPath) {
        Remove-Item -LiteralPath $settingsPath -Force
    }
}

Write-Host "IAP OAuth settings updated for project $ProjectId."
