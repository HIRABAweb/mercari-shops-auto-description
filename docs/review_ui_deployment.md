# Review UI deployment draft

This document records the intended production deployment shape for the Phase 1
Review UI. Do not run these commands until deployment is explicitly approved.

For a plain-language checklist of decisions and manual checks required from the
operator, see `docs/user_action_checklist.md`.

## Decisions

- Service name: `mercari-review-ui`
- Runtime: Cloud Run service, built from `review-ui/Dockerfile`
- Authentication: Cloud Run direct IAP
- Allowed user: `hirabaaiwork@gmail.com`
- Spreadsheet ID: `16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc`
- `PRODUCT_BUCKET_NAME`: `test-review-ui`
- Approved CSV object path: `exports/{batch_id}/approved/mercari_shops.csv`
- `FLASK_SECRET_KEY`: required on Cloud Run
- Cost guardrails:
  - `--min-instances=0`
  - `--max-instances=1`
  - `--no-allow-unauthenticated`
  - `--iap`
  - Do not create a new bucket unless the existing product bucket cannot be reused.
  - Delete old Artifact Registry images after deployment validation.

## Bucket choice

`PRODUCT_BUCKET_NAME` is set to `test-review-ui` for this deployment plan.
Contractors should upload product images and `_SUCCESS.txt` under this bucket if
this Review UI deployment is used for production verification.

The Review UI does not embed private GCS image URLs directly in the page. It
serves item thumbnails through a Cloud Run image proxy and only allows objects
from `PRODUCT_BUCKET_NAME`, so the Cloud Run service account must be able to read
the uploaded product images in that bucket.

Creating or using this bucket can create storage costs, so confirm the project
budget/alert before deployment.

## Service account

`hirabaaiwork@gmail.com` is the human user allowed to open the Review UI through
IAP. It is not the runtime service account used by Cloud Run.

Use a dedicated runtime service account for the service:

```text
mercari-review-ui-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

This runtime service account needs:

- Edit access to the target Google Spreadsheet.
- Read access to product images in `test-review-ui`.
- Write access to approved CSV objects in `test-review-ui`.

## Build and deploy commands

The repository now includes a PowerShell deployment helper:

```powershell
.\scripts\deploy_review_ui.ps1
```

The helper uses these approved defaults:

- `ProjectId`: `gen-lang-client-0122735738`
- `ProductBucketName`: `test-review-ui`
- `SpreadsheetId`: `16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc`
- `AllowedUser`: `hirabaaiwork@gmail.com`
- `ServiceAccountName`: `mercari-review-ui-sa`

Set these values manually only if you are not using the helper script:

```powershell
$ProjectId = "gen-lang-client-0122735738"
$Region = "asia-northeast1"
$ServiceName = "mercari-review-ui"
$Image = "$Region-docker.pkg.dev/$ProjectId/review-ui/$ServiceName:latest"
$ProductBucketName = "test-review-ui"
$SpreadsheetId = "16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc"
$AllowedUser = "hirabaaiwork@gmail.com"
$ProjectNumber = "YOUR_PROJECT_NUMBER"
$FlaskSecretKey = "REPLACE_WITH_RANDOM_SECRET"
$ServiceAccountName = "mercari-review-ui-sa"
$ServiceAccountEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
```

Enable required APIs only if they are not already enabled:

```powershell
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  iap.googleapis.com `
  --project=$ProjectId
```

Create the GCS bucket only if it does not already exist:

```powershell
gcloud storage buckets create "gs://$ProductBucketName" `
  --location=$Region `
  --project=$ProjectId
```

Create the Artifact Registry repository only if it does not already exist:

```powershell
gcloud artifacts repositories create review-ui `
  --repository-format=docker `
  --location=$Region `
  --project=$ProjectId
```

Create the Cloud Run runtime service account only if it does not already exist:

```powershell
gcloud iam service-accounts create $ServiceAccountName `
  --display-name="Mercari Review UI runtime" `
  --project=$ProjectId
```

Grant the runtime service account read/write access to the review bucket:

```powershell
gcloud storage buckets add-iam-policy-binding "gs://$ProductBucketName" `
  --member="serviceAccount:$ServiceAccountEmail" `
  --role="roles/storage.objectAdmin" `
  --project=$ProjectId
```

Share the Spreadsheet with `$ServiceAccountEmail` as an editor before using the
Review UI. Sharing it with `hirabaaiwork@gmail.com` lets the human user open the
sheet, but the Cloud Run app itself needs the runtime service account to be an
editor too.

Build the image from the repository root. Use `cloudbuild.review-ui.yaml` so
Cloud Build uses `review-ui/Dockerfile` explicitly:

```powershell
gcloud builds submit . `
  --config=cloudbuild.review-ui.yaml `
  --substitutions="_IMAGE=$Image" `
  --project=$ProjectId
```

Deploy Cloud Run with IAP and zero idle instances:

```powershell
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
  --set-env-vars="SPREADSHEET_ID=$SpreadsheetId,PRODUCT_BUCKET_NAME=$ProductBucketName,APPROVED_CSV_OBJECT_TEMPLATE=exports/{batch_id}/approved/mercari_shops.csv,FLASK_SECRET_KEY=$FlaskSecretKey"
```

Grant Cloud Run invoker permission to the IAP service agent:

```powershell
gcloud run services add-iam-policy-binding $ServiceName `
  --region=$Region `
  --project=$ProjectId `
  --member="serviceAccount:service-$ProjectNumber@gcp-sa-iap.iam.gserviceaccount.com" `
  --role="roles/run.invoker"
```

Grant IAP access to the allowed user:

```powershell
gcloud iap web add-iam-policy-binding `
  --member="user:$AllowedUser" `
  --role="roles/iap.httpsResourceAccessor" `
  --region=$Region `
  --resource-type=cloud-run `
  --service=$ServiceName `
  --project=$ProjectId
```

## IAP OAuth setup

If the Review UI URL returns the following response, Cloud Run is deployed but
IAP does not yet have OAuth credentials configured:

```text
Empty Google Account OAuth client ID(s)/secret(s).
```

This is common when direct IAP is enabled from `gcloud` in a project that is not
under a Google Cloud Organization. Google Cloud can grant the IAP access role
from the CLI, but the first OAuth client setup must be completed in the Google
Cloud console or by applying a custom OAuth client.

Recommended manual path:

1. Open Google Cloud Console.
2. Select project `gen-lang-client-0122735738`.
3. Open Cloud Run, then service `mercari-review-ui`.
4. Open the Security or IAP settings.
5. Configure IAP OAuth/Google Auth Platform.
6. Use an External audience so `hirabaaiwork@gmail.com` can sign in.
7. Use auto-generated credentials if the console offers that option.
8. Confirm `hirabaaiwork@gmail.com` remains the only IAP user with
   `roles/iap.httpsResourceAccessor`.
9. Open the Review UI URL again.

If you manually create a custom OAuth client instead, create a Web application
OAuth client and add this redirect URI:

```text
https://iap.googleapis.com/v1/oauth/clientIds/CLIENT_ID:handleRedirect
```

Replace `CLIENT_ID` with the OAuth client ID you just created.

After creating the custom OAuth client, either apply it in the Google Cloud
Console or run the helper below. Do not paste the OAuth client secret into chat
or commit it to the repository.

```powershell
.\scripts\apply_iap_oauth_settings.ps1
```

The helper prompts for the OAuth client ID and secret, writes a temporary local
settings file, runs `gcloud iap settings set`, and deletes the temporary file.

## Production checklist

- Confirm billing budget/alert is configured before any deployment.
- Confirm the `test-review-ui` bucket exists.
- Prepare a random `FLASK_SECRET_KEY`.
- Confirm Cloud Run IAP can be enabled in the target project.
- Confirm IAP OAuth is configured; the Review UI must not show
  `Empty Google Account OAuth client ID(s)/secret(s).`
- Confirm `hirabaaiwork@gmail.com` can sign in through IAP.
- Confirm `$ServiceAccountEmail` is an editor on the Spreadsheet.
- Confirm `$ServiceAccountEmail` has read/write access to `test-review-ui`.
- Confirm `/healthz` returns `ok` after deployment.
- Confirm private product thumbnails render in the Review UI.
- Generate one approved CSV and verify it is saved to
  `exports/{batch_id}/approved/mercari_shops.csv`.
- Download the CSV from the UI and test upload to Mercari Shops.

## Optional approved CSV function

The older `export_approved_mercari_csv` HTTP function is a fallback for
rebuilding `Approved_Mercari_CSV` without the Review UI. It mutates Google
Sheets, so it accepts POST requests only:

```powershell
curl -X POST "$FunctionUrl?batch_prefix=exports/YOUR_BATCH_ID"
```
