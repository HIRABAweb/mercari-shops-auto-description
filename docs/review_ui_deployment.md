# Review UI deployment draft

This document records the intended production deployment shape for the Phase 1
Review UI. Do not run these commands until deployment is explicitly approved.

## Decisions

- Service name: `mercari-review-ui`
- Runtime: Cloud Run service, built from `review-ui/Dockerfile`
- Authentication: Cloud Run direct IAP
- Allowed user: `hirabaaiwork@gmail.com`
- Spreadsheet ID: `16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc`
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

The preferred `PRODUCT_BUCKET_NAME` is the existing product upload bucket used by
the two Cloud Functions. Reusing it avoids creating another storage location and
keeps final CSVs next to the generated artifacts.

The Review UI does not embed private GCS image URLs directly in the page. It
serves item thumbnails through a Cloud Run image proxy and only allows objects
from `PRODUCT_BUCKET_NAME`, so the Cloud Run service account must be able to read
the uploaded product images in that bucket.

If a separate bucket is still required, use a globally unique name such as:

```text
hiraba-mercari-review-approved-csv
```

Creating a new bucket can create storage costs, so this should be done only after
confirming it is necessary.

## Build and deploy commands

Set these values first:

```powershell
$ProjectId = "YOUR_PROJECT_ID"
$Region = "asia-northeast1"
$ServiceName = "mercari-review-ui"
$Image = "$Region-docker.pkg.dev/$ProjectId/review-ui/$ServiceName:latest"
$ProductBucketName = "YOUR_EXISTING_PRODUCT_BUCKET"
$SpreadsheetId = "16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc"
$AllowedUser = "hirabaaiwork@gmail.com"
$ProjectNumber = "YOUR_PROJECT_NUMBER"
$FlaskSecretKey = "REPLACE_WITH_RANDOM_SECRET"
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

Create the Artifact Registry repository only if it does not already exist:

```powershell
gcloud artifacts repositories create review-ui `
  --repository-format=docker `
  --location=$Region `
  --project=$ProjectId
```

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

The Cloud Run service account also needs:

- Edit access to the target Google Spreadsheet.
- Read access to product images in `$ProductBucketName`.
- Write access to approved CSV objects in `$ProductBucketName`.

## Production checklist

- Confirm billing budget/alert is configured before any deployment.
- Confirm the existing product bucket name.
- Prepare a random `FLASK_SECRET_KEY`.
- Confirm Cloud Run IAP can be enabled in the target project.
- Confirm `hirabaaiwork@gmail.com` can sign in through IAP.
- Confirm `/healthz` returns `ok` after deployment.
- Confirm private product thumbnails render in the Review UI.
- Generate one approved CSV and verify it is saved to
  `exports/{batch_id}/approved/mercari_shops.csv`.
- Download the CSV from the UI and test upload to Mercari Shops.
