param(
    [string]$ProjectId = "gen-lang-client-0122735738",
    [string]$Region = "asia-northeast1",
    [string]$ServiceName = "mercari-review-ui",
    [string]$ProductBucketName = "test-review-ui",
    [string]$SpreadsheetId = "16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc",
    [string]$AllowedUser = "hirabaaiwork@gmail.com",
    [string]$ServiceAccountName = "mercari-review-ui-sa",
    [int]$MercariImageSignedUrlTtlHours = 168,
    [string]$FlaskSecretKey = ""
)

$ErrorActionPreference = "Stop"

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required. Install Google Cloud CLI first."
    }
}

function New-RandomSecret {
    $bytes = New-Object byte[] 48
    $rng = [System.Security.Cryptography.RNGCryptoServiceProvider]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes)
}

Require-Command "gcloud"

if (-not $FlaskSecretKey) {
    $FlaskSecretKey = New-RandomSecret
}

$ProjectNumber = (gcloud projects describe $ProjectId --format="value(projectNumber)").Trim()
$ServiceAccountEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$Image = "$Region-docker.pkg.dev/$ProjectId/review-ui/$ServiceName`:latest"

Write-Host "Project: $ProjectId"
Write-Host "Region: $Region"
Write-Host "Service: $ServiceName"
Write-Host "Bucket: $ProductBucketName"
Write-Host "Runtime service account: $ServiceAccountEmail"
Write-Host ""

gcloud config set project $ProjectId

gcloud services enable `
    run.googleapis.com `
    artifactregistry.googleapis.com `
    cloudbuild.googleapis.com `
    iap.googleapis.com `
    iamcredentials.googleapis.com `
    cloudresourcemanager.googleapis.com `
    --project=$ProjectId

if (-not (gcloud storage buckets describe "gs://$ProductBucketName" --project=$ProjectId 2>$null)) {
    gcloud storage buckets create "gs://$ProductBucketName" `
        --location=$Region `
        --project=$ProjectId
}

if (-not (gcloud artifacts repositories describe review-ui --location=$Region --project=$ProjectId 2>$null)) {
    gcloud artifacts repositories create review-ui `
        --repository-format=docker `
        --location=$Region `
        --project=$ProjectId
}

if (-not (gcloud iam service-accounts describe $ServiceAccountEmail --project=$ProjectId 2>$null)) {
    gcloud iam service-accounts create $ServiceAccountName `
        --display-name="Mercari Review UI runtime" `
        --project=$ProjectId
}

gcloud storage buckets add-iam-policy-binding "gs://$ProductBucketName" `
    --member="serviceAccount:$ServiceAccountEmail" `
    --role="roles/storage.objectAdmin" `
    --project=$ProjectId

gcloud iam service-accounts add-iam-policy-binding $ServiceAccountEmail `
    --member="serviceAccount:$ServiceAccountEmail" `
    --role="roles/iam.serviceAccountTokenCreator" `
    --project=$ProjectId

Write-Host ""
Write-Host "IMPORTANT:"
Write-Host "Share this Spreadsheet as Editor with the runtime service account:"
Write-Host "  Spreadsheet: https://docs.google.com/spreadsheets/d/$SpreadsheetId"
Write-Host "  Editor: $ServiceAccountEmail"
Write-Host ""

gcloud builds submit . `
    --config=cloudbuild.review-ui.yaml `
    --substitutions="_IMAGE=$Image" `
    --project=$ProjectId

gcloud run deploy $ServiceName `
    --image=$Image `
    --region=$Region `
    --project=$ProjectId `
    --min-instances=0 `
    --max-instances=1 `
    --memory=512Mi `
    --cpu=1 `
    --no-allow-unauthenticated `
    --iap `
    --service-account=$ServiceAccountEmail `
    --set-env-vars="SPREADSHEET_ID=$SpreadsheetId,PRODUCT_BUCKET_NAME=$ProductBucketName,APPROVED_CSV_OBJECT_TEMPLATE=exports/{batch_id}/approved/mercari_shops.csv,MERCARI_SIGNING_SERVICE_ACCOUNT_EMAIL=$ServiceAccountEmail,MERCARI_IMAGE_SIGNED_URL_TTL_HOURS=$MercariImageSignedUrlTtlHours,FLASK_SECRET_KEY=$FlaskSecretKey"

gcloud run services add-iam-policy-binding $ServiceName `
    --region=$Region `
    --project=$ProjectId `
    --member="serviceAccount:service-$ProjectNumber@gcp-sa-iap.iam.gserviceaccount.com" `
    --role="roles/run.invoker"

gcloud iap web add-iam-policy-binding `
    --member="user:$AllowedUser" `
    --role="roles/iap.httpsResourceAccessor" `
    --region=$Region `
    --resource-type=cloud-run `
    --service=$ServiceName `
    --project=$ProjectId

$ServiceUrl = (gcloud run services describe $ServiceName --region=$Region --project=$ProjectId --format="value(status.url)").Trim()

Write-Host ""
Write-Host "Deployment finished."
Write-Host "Service URL: $ServiceUrl"
Write-Host "Health check: $ServiceUrl/healthz"
