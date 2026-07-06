# Deployment Notes

This document records the deployment shape for production. Do not deploy or
merge without explicit approval.

## Cloud Functions Entrypoints

The repository contains multiple entrypoints. In Cloud Functions Gen2, deploy
each entrypoint as a separate Cloud Functions resource. The backing Cloud Run
service is created by the Cloud Functions deployment.

| Function | Source directory | Entrypoint | Trigger | Purpose |
| --- | --- | --- | --- | --- |
| Image to description | `image-to-description` | `generate_description` | Cloud Storage object create for `_SUCCESS.txt` | Generate Yahoo-oriented `_description.txt` from images and `_SUCCESS.txt` |
| Listing conversion | `yahuoku-to-mercarishops` | `generate_dual_listing` | Cloud Storage object create for `_description.txt` | Write `Draft_Mercari_List`, `Review_List`, and `Yahoo_List` rows |
| Review aggregation | `yahuoku-to-mercarishops` | `aggregate_review_required_on_marker` | Cloud Storage object create for `_SUCCESS.txt` and `_processed.txt` | Aggregate per-item review CSVs by batch |
| Approved CSV export | `yahuoku-to-mercarishops` | `export_approved_mercari_csv` | HTTP | Rebuild `Approved_Mercari_CSV` from approved review rows |

## Upload Path

Use a batch prefix so review and approved CSV output do not mix multiple upload
days or work batches.

```text
exports/{batch_id}/{item_id}/001.jpg
exports/{batch_id}/{item_id}/002.jpg
exports/{batch_id}/{item_id}/_SUCCESS.txt
```

Example:

```text
exports/2026-07-06/A0001/001.jpg
exports/2026-07-06/A0001/_SUCCESS.txt
```

## Sheets

The listing conversion service uses these worksheets:

| Worksheet | Purpose |
| --- | --- |
| `Draft_Mercari_List` | 73-column Mercari Shops draft rows with the repository-managed header. Operators edit this sheet. |
| `Review_List` | Review reasons and `review_status`. Operators set `approved`, `hold`, or `rejected`. |
| `Approved_Mercari_CSV` | Final Mercari Shops CSV sheet rebuilt from approved rows with the repository-managed header. |
| `Yahoo_List` | Yahoo Auctions rows. |

If a worksheet is missing, the service creates it. The runtime service account
must have edit access to the spreadsheet.

## Approved CSV Export

Run the HTTP entrypoint with a batch prefix to avoid mixing batches. The
`batch_prefix` query parameter is required:

```text
GET /?batch_prefix=exports/{batch_id}
```

Example:

```text
GET /?batch_prefix=exports/2026-07-06
```

The function clears `Approved_Mercari_CSV` and writes only approved draft rows
for the requested batch. If the requested batch has no rows in `Review_List`,
the function returns an error without clearing the existing approved sheet.
Download `Approved_Mercari_CSV` as CSV and upload it to Mercari Shops.

The Mercari Shops CSV header is fixed in `yahuoku-to-mercarishops/listing_data.py`
as `MERCARI_HEADERS`. If the official Mercari Shops template changes, update
that constant and the related column mapping in the same pull request.

## Pre-deploy Checklist

| Check | Required |
| --- | --- |
| GCS prompt bucket and prompt file names match the repository prompt files | Yes |
| Runtime service account can read product images, `_SUCCESS.txt`, `_description.txt`, and prompt files | Yes |
| Runtime service account can write `_description.txt`, `_processed.txt`, review CSVs, and lock files | Yes |
| Runtime service account can edit the Google Spreadsheet | Yes |
| Spreadsheet ID and worksheet names are configured for production | Yes |
| `MERCARI_HEADERS` matches the Mercari Shops CSV template used in production | Yes |
| Upload instructions tell contractors to use `exports/{batch_id}/{item_id}/` | Yes |
| `export_approved_mercari_csv` is protected by IAM or another approved access control | Yes |
| Production deployment and main merge have explicit approval | Yes |
