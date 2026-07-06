# Draft PR: Phase 1 review approval workflow

## Summary

This change introduces a Phase 1 human review workflow for Mercari Shops CSV
generation. Instead of treating generated listing rows as final upload data,
the system now writes draft rows, review status rows, and an approved CSV sheet.

## Main Changes

- Treat `_SUCCESS.txt` as the official product information input.
- Raise on `_SUCCESS.txt` read failures instead of treating read failures as
  missing measurements.
- Parse AI output more defensively for `_description.txt` and Mercari conversion
  formats.
- Write per-item review CSV files instead of appending to one shared
  `review_required.csv`.
- Support batch-scoped review paths such as:
  - `exports/{batch_id}/review_required/{item_id}.csv`
  - `exports/{batch_id}/review_required.csv`
- Add review aggregation through `aggregate_review_required_on_marker`.
- Add Phase 1 Google Sheets workflow:
  - `Draft_Mercari_List`
  - `Review_List`
  - `Approved_Mercari_CSV`
  - `Yahoo_List`
- Add `export_approved_mercari_csv` HTTP entrypoint.
- Require `batch_prefix=exports/{batch_id}` for approved CSV export.
- Add repository-managed Mercari Shops CSV headers through `MERCARI_HEADERS`.
- Add deployment notes and roadmap documentation.

## Operational Notes

- Production upload paths should use `exports/{batch_id}/{item_id}/`.
- `review_required.csv` is a review checklist, not a Mercari Shops upload CSV.
- Operators edit `Draft_Mercari_List`, set `Review_List.review_status` to
  `approved`, then run `export_approved_mercari_csv`.
- `Approved_Mercari_CSV` is rebuilt with the Mercari Shops header row and only
  approved rows from the requested batch.
- Deployment, PR creation, and main merge are intentionally not included here
  without explicit approval.

## Tests

```text
python -m pytest -p no:cacheprovider tests
```

Current result:

```text
70 passed
```

## Pre-merge Checks

- Confirm production upload instructions use `exports/{batch_id}/{item_id}/`.
- Confirm production spreadsheet ID and service account permissions.
- Confirm `MERCARI_HEADERS` matches the Mercari Shops CSV template used in
  production.
- Confirm HTTP access control for `export_approved_mercari_csv`.
- Confirm Cloud Functions entrypoints and environment variables before deploy.

