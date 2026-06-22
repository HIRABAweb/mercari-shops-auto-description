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

    def download_as_text(self):
        return self.text

    def upload_from_string(self, data, **kwargs):
        if self.lock_taken:
            raise FakePreconditionFailed("lock already exists")
        self.lock_taken = True
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
    def __init__(self, bucket):
        self._bucket = bucket

    def bucket(self, bucket_name):
        return self._bucket

    def list_blobs(self, bucket_name, prefix):
        return []


class MainSafeguardTest(unittest.TestCase):
    def setUp(self):
        self.module = load_main_module()

    def test_replaces_only_the_filename_suffix(self):
        self.assertEqual(
            self.module.replace_description_suffix(
                "folder_description.txt/item_description.txt",
                self.module.PROCESSED_FILE_NAME,
            ),
            "folder_description.txt/item_processed.txt",
        )

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


if __name__ == "__main__":
    unittest.main()
