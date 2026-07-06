"""Tests for Cloud Storage processing safeguards without real cloud credentials."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = PROJECT_ROOT / "yahuoku-to-mercarishops" / "main.py"
sys.path.insert(0, str(MAIN_PATH.parent))


class FakePreconditionFailed(Exception):
    """Stand-in for the GCS precondition error used by the production code."""


def load_main_module():
    """Load main.py with lightweight substitutes for unavailable cloud packages."""
    functions_framework = types.ModuleType("functions_framework")
    functions_framework.cloud_event = lambda function: function
    functions_framework.http = lambda function: function

    google = types.ModuleType("google")
    google.__path__ = []
    google_auth = types.ModuleType("google.auth")
    google_auth.default = lambda scopes: (object(), None)
    generativeai = types.ModuleType("google.generativeai")
    generativeai.configure = lambda **kwargs: None
    generativeai.GenerativeModel = lambda name: object()
    google_cloud = types.ModuleType("google.cloud")
    google_cloud.__path__ = []
    secretmanager = types.ModuleType("google.cloud.secretmanager")
    secretmanager.SecretManagerServiceClient = lambda: FakeSecretClient()
    storage = types.ModuleType("google.cloud.storage")
    storage.Client = lambda: object()
    google_cloud.secretmanager = secretmanager
    google_cloud.storage = storage
    google_api_core = types.ModuleType("google.api_core")
    google_api_core.__path__ = []
    exceptions = types.ModuleType("google.api_core.exceptions")
    exceptions.PreconditionFailed = FakePreconditionFailed
    google_api_core.exceptions = exceptions
    gspread = types.ModuleType("gspread")

    fake_modules = {
        "functions_framework": functions_framework,
        "google": google,
        "google.auth": google_auth,
        "google.generativeai": generativeai,
        "google.cloud": google_cloud,
        "google.cloud.secretmanager": secretmanager,
        "google.cloud.storage": storage,
        "google.api_core": google_api_core,
        "google.api_core.exceptions": exceptions,
        "gspread": gspread,
    }
    google.auth = google_auth
    google.generativeai = generativeai
    google.cloud = google_cloud
    google.api_core = google_api_core

    with patch.dict(sys.modules, fake_modules):
        spec = importlib.util.spec_from_file_location("listing_main_under_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeSecretClient:
    def access_secret_version(self, request):
        return types.SimpleNamespace(
            payload=types.SimpleNamespace(data=b"test-api-key")
        )


class FakeBlob:
    def __init__(self, name, generation=None, text="商品説明", download_error=None):
        self.name = name
        self.generation = generation
        self.text = text
        self.download_error = download_error
        self.exists_result = True
        self.upload_calls = []
        self.uploaded_data = None
        self.delete_calls = []
        self.lock_taken = False

    def exists(self):
        return self.exists_result

    def reload(self):
        return None

    def download_as_text(self, **kwargs):
        if self.download_error:
            raise self.download_error
        return self.text

    def upload_from_string(self, data, **kwargs):
        if kwargs.get("if_generation_match") == 0 and self.lock_taken:
            raise FakePreconditionFailed("lock already exists")
        self.lock_taken = True
        self.uploaded_data = data
        self.upload_calls.append((data, kwargs))

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)


class FakeBucket:
    def __init__(self, source_name="A0001/item_description.txt"):
        self.source = FakeBlob(source_name, generation="123")
        self.blobs = {source_name: self.source}
        self.copy_calls = []

    def blob(self, name, generation=None):
        if name not in self.blobs:
            self.blobs[name] = FakeBlob(name, generation=generation)
        blob = self.blobs[name]
        if generation is not None:
            blob.generation = generation
        return blob

    def copy_blob(self, source, destination_bucket, destination_name, **kwargs):
        self.copy_calls.append((source, destination_bucket, destination_name, kwargs))


class FakeStorageClient:
    def __init__(self, bucket, listed_blobs=None):
        self._bucket = bucket
        self._listed_blobs = listed_blobs or []

    def bucket(self, bucket_name):
        return self._bucket

    def list_blobs(self, bucket_name, prefix=""):
        return [blob for blob in self._listed_blobs if blob.name.startswith(prefix)]


class FakeWorksheet:
    def __init__(self, existing_values=None, values=None, title="Sheet1"):
        self.title = title
        self.existing_values = existing_values or {}
        self.values = values or []
        self.appended_rows = []
        self.appended_row_batches = []
        self.clear_calls = 0

    def col_values(self, column_number):
        if self.values:
            index = column_number - 1
            return [row[index] for row in self.values if len(row) > index]
        return self.existing_values.get(column_number, [])

    def append_row(self, row):
        self.appended_rows.append(row)
        self.values.append(row)

    def append_rows(self, rows, **kwargs):
        self.appended_row_batches.append((rows, kwargs))
        self.values.extend(rows)

    def get_all_values(self):
        return self.values

    def clear(self):
        self.clear_calls += 1
        self.values = []


class FakeSpreadsheet:
    def __init__(self, worksheets=None):
        self._worksheets = worksheets or []
        self.added_worksheets = []

    def worksheets(self):
        return self._worksheets

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title=title)
        self._worksheets.append(worksheet)
        self.added_worksheets.append((title, rows, cols))
        return worksheet


class FakeRequest:
    def __init__(self, args=None):
        self.args = args or {}


class MainSafeguardTest(unittest.TestCase):
    def setUp(self):
        self.module = load_main_module()

    def test_get_prompt_from_gcs_raises_on_read_failure(self):
        bucket = FakeBucket()
        bucket.blobs[self.module.PROMPT_FILE_NAME] = FakeBlob(
            self.module.PROMPT_FILE_NAME,
            download_error=RuntimeError("prompt unavailable"),
        )
        self.module.storage_client = FakeStorageClient(bucket)

        with self.assertRaisesRegex(RuntimeError, "prompt unavailable"):
            self.module.get_prompt_from_gcs()

    def test_get_prompt_from_gcs_reads_utf8_prompt(self):
        bucket = FakeBucket()
        bucket.blobs[self.module.PROMPT_FILE_NAME] = FakeBlob(
            self.module.PROMPT_FILE_NAME,
            text="Mercari prompt",
        )
        self.module.storage_client = FakeStorageClient(bucket)

        self.assertEqual(self.module.get_prompt_from_gcs(), "Mercari prompt")

    def test_append_row_if_missing_skips_existing_key(self):
        worksheet = FakeWorksheet(existing_values={3: ["A0001"]})

        appended = self.module.append_row_if_missing(
            worksheet,
            ["row"],
            3,
            "A0001",
            "test sheet",
        )

        self.assertFalse(appended)
        self.assertEqual(worksheet.appended_rows, [])

    def test_append_row_if_missing_appends_new_key(self):
        worksheet = FakeWorksheet(existing_values={3: ["A0001"]})

        appended = self.module.append_row_if_missing(
            worksheet,
            ["row"],
            3,
            "B0001",
            "test sheet",
        )

        self.assertTrue(appended)
        self.assertEqual(worksheet.appended_rows, [["row"]])

    def test_append_listing_rows_is_idempotent_for_existing_sheets(self):
        mercari_row = [""] * 73
        mercari_row[self.module.MERCARI_SKU_CODE] = "A0001"
        yahoo_row = [""] * 114
        yahoo_row[self.module.YAHOO_IMAGE_START] = (
            "https://storage.googleapis.com/product-images/A0001/001.jpg"
        )
        existing_mercari_row = [""] * 73
        existing_mercari_row[self.module.MERCARI_SKU_CODE] = "A0001"
        mercari_sheet = FakeWorksheet(
            values=[self.module.MERCARI_HEADERS, existing_mercari_row]
        )
        yahoo_sheet = FakeWorksheet(
            existing_values={
                self.module.YAHOO_IDEMPOTENCY_COLUMN: [
                    "https://storage.googleapis.com/product-images/A0001/001.jpg"
                ]
            }
        )
        self.module.get_worksheets = lambda: (mercari_sheet, yahoo_sheet)

        self.module.append_listing_rows(mercari_row, yahoo_row, "A0001")

        self.assertEqual(mercari_sheet.appended_rows, [])
        self.assertEqual(yahoo_sheet.appended_rows, [])

    def test_append_listing_rows_appends_missing_rows(self):
        mercari_row = [""] * 73
        mercari_row[self.module.MERCARI_SKU_CODE] = "B0001"
        yahoo_row = [""] * 114
        yahoo_row[self.module.YAHOO_IMAGE_START] = (
            "https://storage.googleapis.com/product-images/B0001/001.jpg"
        )
        existing_mercari_row = [""] * 73
        existing_mercari_row[self.module.MERCARI_SKU_CODE] = "A0001"
        mercari_sheet = FakeWorksheet(
            values=[self.module.MERCARI_HEADERS, existing_mercari_row]
        )
        yahoo_sheet = FakeWorksheet(
            existing_values={
                self.module.YAHOO_IDEMPOTENCY_COLUMN: [
                    "https://storage.googleapis.com/product-images/A0001/001.jpg"
                ]
            }
        )
        self.module.get_worksheets = lambda: (mercari_sheet, yahoo_sheet)

        self.module.append_listing_rows(mercari_row, yahoo_row, "B0001")

        self.assertEqual(mercari_sheet.appended_rows, [mercari_row])
        self.assertEqual(yahoo_sheet.appended_rows, [yahoo_row])

    def test_append_listing_rows_creates_draft_mercari_header_on_empty_sheet(self):
        mercari_row = [""] * 73
        mercari_row[self.module.MERCARI_SKU_CODE] = "A0001"
        yahoo_row = [""] * 114
        yahoo_row[self.module.YAHOO_IMAGE_START] = (
            "https://storage.googleapis.com/product-images/A0001/001.jpg"
        )
        mercari_sheet = FakeWorksheet()
        yahoo_sheet = FakeWorksheet()
        self.module.get_worksheets = lambda: (mercari_sheet, yahoo_sheet)

        self.module.append_listing_rows(mercari_row, yahoo_row, "A0001")

        self.assertEqual(mercari_sheet.values[0], self.module.MERCARI_HEADERS)
        self.assertEqual(mercari_sheet.values[1], mercari_row)

    def test_build_review_sheet_row_summarizes_item_review(self):
        review_rows = [
            ["key-a", "A0001", "path", "all", "measurements", "採寸情報なし", "", "採寸を確認"],
            ["key-b", "A0001", "path", "mercari", "category", "カテゴリ不明", "", "カテゴリを確認"],
        ]

        row = self.module.build_review_sheet_row(
            batch_prefix="exports/2026-07-06",
            item_manage_code="A0001",
            file_path="exports/2026-07-06/A0001/item_description.txt",
            review_rows=review_rows,
        )

        self.assertEqual(row[0], "exports/2026-07-06/A0001")
        self.assertEqual(row[1], "exports/2026-07-06")
        self.assertEqual(row[2], "A0001")
        self.assertEqual(row[3], "needs_review")
        self.assertIn("採寸情報なし", row[5])
        self.assertIn("カテゴリ不明", row[5])
        self.assertIn("採寸を確認", row[6])

    def test_write_review_sheet_row_creates_header_and_item_row(self):
        review_sheet = FakeWorksheet()
        review_rows = [
            ["key-a", "A0001", "path", "all", "measurements", "採寸情報なし", "", "採寸を確認"],
        ]

        appended = self.module.write_review_sheet_row(
            review_sheet,
            batch_prefix="exports/2026-07-06",
            item_manage_code="A0001",
            file_path="exports/2026-07-06/A0001/item_description.txt",
            review_rows=review_rows,
        )

        self.assertTrue(appended)
        self.assertEqual(review_sheet.values[0], self.module.REVIEW_SHEET_HEADERS)
        self.assertEqual(review_sheet.values[1][0], "exports/2026-07-06/A0001")

    def test_write_review_sheet_row_skips_existing_item(self):
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                [
                    "exports/2026-07-06/A0001",
                    "exports/2026-07-06",
                    "A0001",
                    "approved",
                    "path",
                    "採寸情報なし",
                    "確認",
                    "done",
                    "2026-07-06",
                ],
            ]
        )

        appended = self.module.write_review_sheet_row(
            review_sheet,
            batch_prefix="exports/2026-07-06",
            item_manage_code="A0001",
            file_path="exports/2026-07-06/A0001/item_description.txt",
            review_rows=[],
        )

        self.assertFalse(appended)
        self.assertEqual(len(review_sheet.values), 2)

    def test_approved_review_item_keys_reads_approved_rows(self):
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
                ["exports/2026-07-06/B0001", "exports/2026-07-06", "B0001", "needs_review"],
            ]
        )

        self.assertEqual(
            self.module.approved_review_item_keys(review_sheet),
            {"exports/2026-07-06/A0001"},
        )

    def test_approved_review_item_keys_filters_by_batch_prefix(self):
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
                ["exports/2026-07-07/A0001", "exports/2026-07-07", "A0001", "approved"],
            ]
        )

        self.assertEqual(
            self.module.approved_review_item_keys(
                review_sheet,
                batch_prefix="exports/2026-07-06",
            ),
            {"exports/2026-07-06/A0001"},
        )

    def test_review_item_keys_for_batch_reads_any_status_in_batch(self):
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
                ["exports/2026-07-06/B0001", "exports/2026-07-06", "B0001", "hold"],
                ["exports/2026-07-07/C0001", "exports/2026-07-07", "C0001", "approved"],
            ]
        )

        self.assertEqual(
            self.module.review_item_keys_for_batch(
                review_sheet,
                batch_prefix="exports/2026-07-06",
            ),
            {"exports/2026-07-06/A0001", "exports/2026-07-06/B0001"},
        )

    def test_draft_row_matches_review_key_uses_batch_image_url(self):
        draft_row = [""] * 73
        draft_row[0] = "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg"
        draft_row[self.module.MERCARI_SKU_CODE] = "A0001"

        self.assertTrue(
            self.module.draft_row_matches_review_key(
                draft_row,
                "exports/2026-07-06/A0001",
            )
        )
        self.assertFalse(
            self.module.draft_row_matches_review_key(
                draft_row,
                "exports/2026-07-07/A0001",
            )
        )

    def test_export_approved_mercari_rows_rebuilds_approved_sheet(self):
        draft_row_a = [""] * 73
        draft_row_a[0] = "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg"
        draft_row_a[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_row_b = [""] * 73
        draft_row_b[0] = "https://storage.googleapis.com/product-images/exports/2026-07-06/B0001/001.jpg"
        draft_row_b[self.module.MERCARI_SKU_CODE] = "B0001"
        draft_sheet = FakeWorksheet(values=[draft_row_a, draft_row_b])
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
                ["exports/2026-07-06/B0001", "exports/2026-07-06", "B0001", "hold"],
            ]
        )
        approved_sheet = FakeWorksheet(values=[["old row"]])

        exported_count = self.module.export_approved_mercari_rows(
            draft_sheet,
            review_sheet,
            approved_sheet,
        )

        self.assertEqual(exported_count, 1)
        self.assertEqual(approved_sheet.clear_calls, 1)
        self.assertEqual(approved_sheet.values, [self.module.MERCARI_HEADERS, draft_row_a])

    def test_export_approved_mercari_rows_filters_same_item_id_by_batch(self):
        draft_row_a = [""] * 73
        draft_row_a[0] = "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg"
        draft_row_a[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_row_b = [""] * 73
        draft_row_b[0] = "https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001.jpg"
        draft_row_b[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_sheet = FakeWorksheet(values=[draft_row_a, draft_row_b])
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
                ["exports/2026-07-07/A0001", "exports/2026-07-07", "A0001", "approved"],
            ]
        )
        approved_sheet = FakeWorksheet()

        exported_count = self.module.export_approved_mercari_rows(
            draft_sheet,
            review_sheet,
            approved_sheet,
            batch_prefix="exports/2026-07-06",
        )

        self.assertEqual(exported_count, 1)
        self.assertEqual(approved_sheet.values, [self.module.MERCARI_HEADERS, draft_row_a])

    def test_export_approved_mercari_csv_http_entrypoint_requires_batch_prefix(self):
        draft_row = [""] * 73
        draft_row[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_sheet = FakeWorksheet(values=[draft_row])
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["A0001", "", "A0001", "approved"],
            ]
        )
        approved_sheet = FakeWorksheet()
        self.module.get_approved_mercari_worksheets = lambda: (
            draft_sheet,
            review_sheet,
            approved_sheet,
        )

        body, status = self.module.export_approved_mercari_csv(FakeRequest())

        self.assertEqual(status, 400)
        self.assertIn("batch_prefix is required", body)
        self.assertEqual(approved_sheet.values, [])

    def test_export_approved_mercari_csv_http_entrypoint_rejects_unknown_batch_without_clearing(self):
        draft_row = [""] * 73
        draft_row[0] = "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg"
        draft_row[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_sheet = FakeWorksheet(values=[draft_row])
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
            ]
        )
        approved_sheet = FakeWorksheet(values=[["existing export"]])
        self.module.get_approved_mercari_worksheets = lambda: (
            draft_sheet,
            review_sheet,
            approved_sheet,
        )

        body, status = self.module.export_approved_mercari_csv(
            FakeRequest(args={"batch_prefix": "exports/2026-07-08"})
        )

        self.assertEqual(status, 404)
        self.assertIn("no review rows found", body)
        self.assertEqual(approved_sheet.values, [["existing export"]])

    def test_export_approved_mercari_csv_http_entrypoint_accepts_batch_prefix(self):
        draft_row_a = [""] * 73
        draft_row_a[0] = "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg"
        draft_row_a[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_row_b = [""] * 73
        draft_row_b[0] = "https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001.jpg"
        draft_row_b[self.module.MERCARI_SKU_CODE] = "A0001"
        draft_sheet = FakeWorksheet(values=[draft_row_a, draft_row_b])
        review_sheet = FakeWorksheet(
            values=[
                self.module.REVIEW_SHEET_HEADERS,
                ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
                ["exports/2026-07-07/A0001", "exports/2026-07-07", "A0001", "approved"],
            ]
        )
        approved_sheet = FakeWorksheet()
        self.module.get_approved_mercari_worksheets = lambda: (
            draft_sheet,
            review_sheet,
            approved_sheet,
        )

        body, status = self.module.export_approved_mercari_csv(
            FakeRequest(args={"batch_prefix": "exports/2026-07-06"})
        )

        self.assertEqual(status, 200)
        self.assertIn("exports/2026-07-06", body)
        self.assertEqual(approved_sheet.values, [self.module.MERCARI_HEADERS, draft_row_a])

    def test_get_or_create_worksheet_returns_existing_sheet(self):
        existing = FakeWorksheet(title=self.module.SHEET_NAME_REVIEW)
        spreadsheet = FakeSpreadsheet([existing])

        worksheet = self.module.get_or_create_worksheet(
            spreadsheet,
            self.module.SHEET_NAME_REVIEW,
        )

        self.assertIs(worksheet, existing)
        self.assertEqual(spreadsheet.added_worksheets, [])

    def test_get_or_create_worksheet_adds_missing_phase1_sheet(self):
        spreadsheet = FakeSpreadsheet()

        worksheet = self.module.get_or_create_worksheet(
            spreadsheet,
            self.module.SHEET_NAME_APPROVED_MERCARI,
        )

        self.assertEqual(worksheet.title, self.module.SHEET_NAME_APPROVED_MERCARI)
        self.assertEqual(
            spreadsheet.added_worksheets,
            [(self.module.SHEET_NAME_APPROVED_MERCARI, 1000, 73)],
        )

    def test_replaces_only_the_filename_suffix(self):
        self.assertEqual(
            self.module.replace_description_suffix(
                "folder_description.txt/item_description.txt",
                self.module.PROCESSED_FILE_NAME,
            ),
            "folder_description.txt/item_processed.txt",
        )

    def test_review_aggregation_marker_detects_success_and_processed_files(self):
        self.assertTrue(
            self.module.is_review_aggregation_marker(
                "exports/2026-07-06/A0001/_SUCCESS.txt"
            )
        )
        self.assertTrue(
            self.module.is_review_aggregation_marker(
                "exports/2026-07-06/A0001/item_processed.txt"
            )
        )
        self.assertFalse(
            self.module.is_review_aggregation_marker(
                "exports/2026-07-06/A0001/item_description.txt"
            )
        )

    def test_aggregate_review_required_on_marker_uses_batch_prefix(self):
        calls = []
        self.module.aggregate_review_required_files = lambda bucket_name, batch_prefix="": calls.append(
            (bucket_name, batch_prefix)
        )
        event = types.SimpleNamespace(
            data={
                "bucket": "product-images",
                "name": "exports/2026-07-06/A0001/item_processed.txt",
            }
        )

        self.module.aggregate_review_required_on_marker(event)

        self.assertEqual(calls, [("product-images", "exports/2026-07-06")])

    def test_aggregate_review_required_on_marker_ignores_non_marker_files(self):
        calls = []
        self.module.aggregate_review_required_files = lambda bucket_name, batch_prefix="": calls.append(
            (bucket_name, batch_prefix)
        )
        event = types.SimpleNamespace(
            data={
                "bucket": "product-images",
                "name": "exports/2026-07-06/A0001/001.jpg",
            }
        )

        self.module.aggregate_review_required_on_marker(event)

        self.assertEqual(calls, [])

    def test_only_one_delivery_can_acquire_the_processing_lock(self):
        bucket = FakeBucket()

        first_lock = self.module.acquire_processing_lock(
            bucket, "A0001/item_description.txt"
        )
        second_lock = self.module.acquire_processing_lock(
            bucket, "A0001/item_description.txt"
        )

        self.assertIsNotNone(first_lock)
        self.assertIsNone(second_lock)
        self.assertEqual(first_lock.upload_calls[0][1]["if_generation_match"], 0)

    def test_handler_raises_when_another_delivery_owns_the_lock(self):
        bucket = FakeBucket()
        lock = self.module.acquire_processing_lock(bucket, "A0001/item_description.txt")
        self.module.storage_client = FakeStorageClient(bucket)
        event = types.SimpleNamespace(
            data={
                "bucket": "product-images",
                "name": "A0001/item_description.txt",
                "generation": "123",
            }
        )

        with self.assertRaisesRegex(RuntimeError, "処理ロックを取得できません"):
            self.module.generate_dual_listing(event)

        self.assertEqual(lock.delete_calls, [])

    def test_marks_processed_with_source_and_destination_preconditions(self):
        bucket = FakeBucket()

        self.module.mark_description_as_processed(
            bucket,
            bucket.source,
            "A0001/item_description.txt",
            "123",
        )

        _, _, destination, copy_kwargs = bucket.copy_calls[0]
        self.assertEqual(destination, "A0001/item_processed.txt")
        self.assertEqual(copy_kwargs["if_generation_match"], 0)
        self.assertEqual(copy_kwargs["if_source_generation_match"], "123")
        self.assertEqual(bucket.source.delete_calls, [{"if_generation_match": "123"}])

    def test_failure_keeps_source_and_releases_lock_for_retry(self):
        bucket = FakeBucket()
        self.module.storage_client = FakeStorageClient(bucket)
        self.module.generate_mercari_description = lambda description: (_ for _ in ()).throw(
            RuntimeError("Gemini unavailable")
        )
        event = types.SimpleNamespace(
            data={
                "bucket": "product-images",
                "name": "A0001/item_description.txt",
                "generation": "123",
            }
        )

        with self.assertRaisesRegex(RuntimeError, "Gemini unavailable"):
            self.module.generate_dual_listing(event)

        self.assertEqual(bucket.source.delete_calls, [])
        lock = bucket.blobs["A0001/item_processing.lock"]
        self.assertEqual(lock.delete_calls, [{}])

    def test_review_required_file_path_is_per_item(self):
        self.assertEqual(
            self.module.review_required_file_name("A0001"),
            "review_required/A0001.csv",
        )

    def test_review_required_file_path_is_scoped_by_batch_prefix(self):
        self.assertEqual(
            self.module.review_required_file_name(
                "A0001",
                batch_prefix="exports/2026-07-06",
            ),
            "exports/2026-07-06/review_required/A0001.csv",
        )

    def test_batch_prefix_from_product_folder_uses_parent_path(self):
        self.assertEqual(
            self.module.batch_prefix_from_product_folder("exports/2026-07-06/A0001"),
            "exports/2026-07-06",
        )
        self.assertEqual(self.module.batch_prefix_from_product_folder("A0001"), "")

    def test_review_outputs_for_multiple_items_do_not_collide(self):
        bucket = FakeBucket()
        rows_a = [["key-a", "A0001", "A0001/item_description.txt", "all", "field", "理由A", "", "確認"]]
        rows_b = [["key-b", "B0001", "B0001/item_description.txt", "all", "field", "理由B", "", "確認"]]

        file_a = self.module.write_review_required_file(bucket, "A0001", rows_a)
        file_b = self.module.write_review_required_file(bucket, "B0001", rows_b)

        self.assertEqual(file_a, "review_required/A0001.csv")
        self.assertEqual(file_b, "review_required/B0001.csv")
        self.assertIn("理由A", bucket.blobs[file_a].uploaded_data)
        self.assertIn("理由B", bucket.blobs[file_b].uploaded_data)

    def test_review_output_for_same_item_overwrites_same_file(self):
        bucket = FakeBucket()
        rows = [["key-a", "A0001", "A0001/item_description.txt", "all", "field", "理由A", "", "確認"]]

        first = self.module.write_review_required_file(bucket, "A0001", rows)
        second = self.module.write_review_required_file(bucket, "A0001", rows)

        self.assertEqual(first, second)
        review_blob = bucket.blobs["review_required/A0001.csv"]
        self.assertEqual(len(review_blob.upload_calls), 2)
        self.assertEqual(review_blob.uploaded_data.count("理由A"), 1)

    def test_review_output_is_skipped_when_no_review_rows(self):
        bucket = FakeBucket()

        result = self.module.write_review_required_file(bucket, "A0001", [])

        self.assertIsNone(result)
        self.assertNotIn("review_required/A0001.csv", bucket.blobs)

    def test_review_output_uses_batch_prefix_when_present(self):
        bucket = FakeBucket()
        rows = [["key-a", "A0001", "exports/2026-07-06/A0001/item_description.txt", "all", "field", "理由A", "", "確認"]]

        file_name = self.module.write_review_required_file(
            bucket,
            "A0001",
            rows,
            batch_prefix="exports/2026-07-06",
        )

        self.assertEqual(file_name, "exports/2026-07-06/review_required/A0001.csv")
        self.assertIn(file_name, bucket.blobs)

    def test_aggregate_review_required_files_writes_single_csv(self):
        bucket = FakeBucket()
        image_a = FakeBlob("A0001/001.jpg")
        success_a = FakeBlob("A0001/_SUCCESS.txt")
        processed_a = FakeBlob("A0001/item_processed.txt")
        image_b = FakeBlob("B0001/001.jpg")
        success_b = FakeBlob("B0001/_SUCCESS.txt")
        processed_b = FakeBlob("B0001/item_processed.txt")
        blob_a = FakeBlob(
            "review_required/A0001.csv",
            text=(
                "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                "key-a,A0001,A0001/item_description.txt,all,measurements,採寸情報なし,,確認\n"
            ),
        )
        blob_b = FakeBlob(
            "review_required/B0001.csv",
            text=(
                "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                "key-b,B0001,B0001/item_description.txt,all,condition_note,状態メモなし,,確認\n"
            ),
        )
        self.module.storage_client = FakeStorageClient(
            bucket,
            [
                image_a,
                success_a,
                processed_a,
                image_b,
                success_b,
                processed_b,
                blob_a,
                blob_b,
            ],
        )

        output_file = self.module.aggregate_review_required_files("product-images")

        self.assertEqual(output_file, "review_required.csv")
        output_blob = bucket.blobs["review_required.csv"]
        self.assertIn("key-a,A0001", output_blob.uploaded_data)
        self.assertIn("key-b,B0001", output_blob.uploaded_data)

    def test_aggregate_review_required_files_skips_until_all_image_folders_have_success(self):
        bucket = FakeBucket()
        image_a = FakeBlob("A0001/001.jpg")
        success_a = FakeBlob("A0001/_SUCCESS.txt")
        image_b = FakeBlob("B0001/001.jpg")
        blob_a = FakeBlob(
            "review_required/A0001.csv",
            text=(
                "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                "key-a,A0001,A0001/item_description.txt,all,measurements,採寸情報なし,,確認\n"
            ),
        )
        self.module.storage_client = FakeStorageClient(
            bucket,
            [image_a, success_a, image_b, blob_a],
        )

        output_file = self.module.aggregate_review_required_files("product-images")

        self.assertIsNone(output_file)
        self.assertNotIn("review_required.csv", bucket.blobs)

    def test_aggregate_review_required_files_only_includes_processed_items(self):
        bucket = FakeBucket()
        blobs = [
            FakeBlob("A0001/001.jpg"),
            FakeBlob("A0001/_SUCCESS.txt"),
            FakeBlob("A0001/item_processed.txt"),
            FakeBlob("B0001/001.jpg"),
            FakeBlob("B0001/_SUCCESS.txt"),
            FakeBlob(
                "review_required/A0001.csv",
                text=(
                    "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                    "key-a,A0001,A0001/item_description.txt,all,measurements,採寸情報なし,,確認\n"
                ),
            ),
            FakeBlob(
                "review_required/B0001.csv",
                text=(
                    "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                    "key-b,B0001,B0001/item_description.txt,all,condition_note,状態メモなし,,確認\n"
                ),
            ),
        ]
        self.module.storage_client = FakeStorageClient(bucket, blobs)

        output_file = self.module.aggregate_review_required_files("product-images")

        self.assertEqual(output_file, "review_required.csv")
        output_blob = bucket.blobs["review_required.csv"]
        self.assertIn("key-a,A0001", output_blob.uploaded_data)
        self.assertNotIn("key-b,B0001", output_blob.uploaded_data)

    def test_aggregate_review_required_files_is_scoped_by_batch_prefix(self):
        bucket = FakeBucket()
        blobs = [
            FakeBlob("exports/2026-07-06/A0001/001.jpg"),
            FakeBlob("exports/2026-07-06/A0001/_SUCCESS.txt"),
            FakeBlob("exports/2026-07-06/A0001/item_processed.txt"),
            FakeBlob(
                "exports/2026-07-06/review_required/A0001.csv",
                text=(
                    "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                    "key-a,A0001,exports/2026-07-06/A0001/item_description.txt,all,measurements,採寸情報なし,,確認\n"
                ),
            ),
            FakeBlob("exports/2026-07-07/B0001/001.jpg"),
            FakeBlob("exports/2026-07-07/B0001/_SUCCESS.txt"),
            FakeBlob("exports/2026-07-07/B0001/item_processed.txt"),
            FakeBlob(
                "exports/2026-07-07/review_required/B0001.csv",
                text=(
                    "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
                    "key-b,B0001,exports/2026-07-07/B0001/item_description.txt,all,condition_note,状態メモなし,,確認\n"
                ),
            ),
        ]
        self.module.storage_client = FakeStorageClient(bucket, blobs)

        output_file = self.module.aggregate_review_required_files(
            "product-images",
            batch_prefix="exports/2026-07-06",
        )

        self.assertEqual(output_file, "exports/2026-07-06/review_required.csv")
        output_blob = bucket.blobs["exports/2026-07-06/review_required.csv"]
        self.assertIn("key-a,A0001", output_blob.uploaded_data)
        self.assertNotIn("key-b,B0001", output_blob.uploaded_data)


if __name__ == "__main__":
    unittest.main()
