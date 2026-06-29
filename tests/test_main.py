"""Tests for CSV export handler safeguards without real cloud credentials."""

from __future__ import annotations

import importlib.util
import json
import os
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


class FakeSecretClient:
    requests = []

    def access_secret_version(self, request):
        self.requests.append(request)
        return types.SimpleNamespace(
            payload=types.SimpleNamespace(data=b"test-api-key")
        )


def load_main_module():
    FakeSecretClient.requests = []
    functions_framework = types.ModuleType("functions_framework")
    functions_framework.cloud_event = lambda function: function

    google = types.ModuleType("google")
    google.__path__ = []
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

    fake_modules = {
        "functions_framework": functions_framework,
        "google": google,
        "google.generativeai": generativeai,
        "google.cloud": google_cloud,
        "google.cloud.secretmanager": secretmanager,
        "google.cloud.storage": storage,
        "google.api_core": google_api_core,
        "google.api_core.exceptions": exceptions,
    }
    google.generativeai = generativeai
    google.cloud = google_cloud
    google.api_core = google_api_core

    with patch.dict(sys.modules, fake_modules):
        spec = importlib.util.spec_from_file_location("listing_main_under_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


class FakeBlob:
    def __init__(self, name, generation=None, text="商品説明"):
        self.name = name
        self.generation = generation
        self.text = text
        self.exists_result = True
        self.upload_calls = []
        self.delete_calls = []
        self.lock_taken = False

    def exists(self):
        return self.exists_result

    def reload(self):
        return None

    def download_as_text(self, encoding=None):
        return self.text

    def upload_from_string(self, data, **kwargs):
        if self.name.endswith("_processing.lock") and self.lock_taken:
            raise FakePreconditionFailed("lock already exists")
        self.lock_taken = True
        self.upload_calls.append((data, kwargs))

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)


class FakeBucket:
    def __init__(self, source_name="A0001/item_description.txt"):
        self.name = "product-images"
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
    def __init__(self, bucket):
        self._bucket = bucket

    def bucket(self, bucket_name):
        return self._bucket

    def list_blobs(self, bucket_name, prefix):
        return [types.SimpleNamespace(name=f"{prefix}001.jpg")]


class MainCsvExportTest(unittest.TestCase):
    def setUp(self):
        self.module = load_main_module()

    def test_missing_required_env_fails_clearly(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 PROJECT_ID が未設定",
            ):
                self.module.get_api_key()

    def test_secret_manager_path_uses_required_env_values(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ID": "sample-project",
                "SECRET_NAME": "gemini-api-key",
            },
            clear=True,
        ):
            self.assertEqual(self.module.get_api_key(), "test-api-key")

        self.assertEqual(
            FakeSecretClient.requests[0]["name"],
            "projects/sample-project/secrets/gemini-api-key/versions/latest",
        )

    def test_missing_prompt_env_fails_clearly(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ID": "sample-project",
                "SECRET_NAME": "gemini-api-key",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 PROMPT_BUCKET_NAME が未設定",
            ):
                self.module.get_prompt_from_gcs()

    def test_missing_model_env_fails_clearly(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ID": "sample-project",
                "SECRET_NAME": "gemini-api-key",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 GEMINI_MODEL が未設定",
            ):
                self.module.get_model()

    def test_replaces_only_the_filename_suffix(self):
        self.assertEqual(
            self.module.replace_description_suffix(
                "folder_description.txt/item_description.txt",
                self.module.PROCESSED_FILE_NAME,
            ),
            "folder_description.txt/item_processed.txt",
        )

    def test_csv_export_trigger_file_name_must_end_with_description_txt(self):
        self.assertEqual(self.module.DESCRIPTION_FILE_NAME, "_description.txt")
        self.assertTrue(self.module.is_description_file("A0001/_description.txt"))
        self.assertTrue(self.module.is_description_file("A0001/item_description.txt"))
        self.assertFalse(self.module.is_description_file("A0001/description.txt"))
        self.assertFalse(self.module.is_description_file("A0001/_DESCRIPTION.txt"))
        self.assertFalse(self.module.is_description_file("A0001/_success.txt"))

    def test_export_context_uses_product_folder_as_batch_id(self):
        context = self.module.build_export_context("A0001/item_description.txt")

        self.assertEqual(context.folder_path, "A0001")
        self.assertEqual(context.product_code, "A0001")
        self.assertEqual(context.batch_id, "A0001")
        self.assertEqual(context.export_prefix, "exports/A0001")

    def test_export_context_encodes_nested_paths_to_prevent_collisions(self):
        first = self.module.build_export_context("batch/A_B/item_description.txt")
        second = self.module.build_export_context("batch_A/B/item_description.txt")

        self.assertEqual(first.batch_id, "batch%2FA_B")
        self.assertEqual(second.batch_id, "batch_A%2FB")
        self.assertNotEqual(first.export_prefix, second.export_prefix)

    def test_only_one_delivery_can_acquire_the_processing_lock(self):
        bucket = FakeBucket()

        first_lock = self.module.acquire_processing_lock(bucket, "A0001/item_description.txt")
        second_lock = self.module.acquire_processing_lock(bucket, "A0001/item_description.txt")

        self.assertIsNotNone(first_lock)
        self.assertIsNone(second_lock)
        self.assertEqual(first_lock.upload_calls[0][1]["if_generation_match"], 0)

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

    def test_upload_export_artifacts_writes_all_outputs_and_done_last(self):
        bucket = FakeBucket()
        context = self.module.build_export_context("A0001/item_description.txt")
        result_payload = self.module.build_result_payload(
            context=context,
            category_id="456",
            brand_id="123",
            review_required=False,
            processing_time=1.23456,
            outputs={},
        )

        outputs = self.module.upload_export_artifacts(
            bucket,
            context,
            {"商品名": "商品名"},
            {"タイトル": "商品名"},
            [],
            result_payload,
        )

        self.assertEqual(outputs["mercari_csv"], "exports/A0001/mercari.csv")
        self.assertEqual(outputs["yahoo_csv"], "exports/A0001/yahoo.csv")
        self.assertEqual(outputs["review_required_csv"], "exports/A0001/review_required.csv")
        self.assertEqual(outputs["result_json"], "exports/A0001/result.json")
        self.assertEqual(outputs["done"], "exports/A0001/_DONE.txt")
        self.assertEqual(bucket.blobs[outputs["done"]].upload_calls[0][0], "done\n")
        result_json = bucket.blobs[outputs["result_json"]].upload_calls[0][0]
        self.assertEqual(json.loads(result_json)["outputs"], outputs)

    def test_failure_keeps_source_and_releases_lock_for_retry(self):
        bucket = FakeBucket()
        self.module.storage_client = FakeStorageClient(bucket)
        self.module.generate_product_attributes = lambda description: (_ for _ in ()).throw(
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


if __name__ == "__main__":
    unittest.main()
