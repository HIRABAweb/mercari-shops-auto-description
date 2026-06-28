"""Tests for image-to-description safeguards without cloud credentials."""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "image-to-description" / "main.py"


class FakePreconditionFailed(Exception):
    """Stand-in for the GCS precondition exception."""


class FakePart:
    @staticmethod
    def from_data(data, mime_type):
        return {"data": data, "mime_type": mime_type}


def load_module():
    """Import the handler with small fakes for external SDK modules."""
    functions_framework = types.ModuleType("functions_framework")
    functions_framework.cloud_event = lambda function: function
    vertexai = types.ModuleType("vertexai")
    vertexai.init_calls = []
    vertexai.init = lambda **kwargs: vertexai.init_calls.append(kwargs)
    generative_models = types.ModuleType("vertexai.generative_models")
    generative_models.GenerativeModel = lambda name: object()
    generative_models.Part = FakePart
    google = types.ModuleType("google")
    google.__path__ = []
    google_cloud = types.ModuleType("google.cloud")
    google_cloud.__path__ = []
    storage = types.ModuleType("google.cloud.storage")
    storage.Client = lambda: object()
    google_cloud.storage = storage
    google_api_core = types.ModuleType("google.api_core")
    google_api_core.__path__ = []
    exceptions = types.ModuleType("google.api_core.exceptions")
    exceptions.PreconditionFailed = FakePreconditionFailed
    google_api_core.exceptions = exceptions
    google.cloud = google_cloud
    google.api_core = google_api_core

    fake_modules = {
        "functions_framework": functions_framework,
        "vertexai": vertexai,
        "vertexai.generative_models": generative_models,
        "google": google,
        "google.cloud": google_cloud,
        "google.cloud.storage": storage,
        "google.api_core": google_api_core,
        "google.api_core.exceptions": exceptions,
    }
    with patch.dict(sys.modules, fake_modules):
        spec = importlib.util.spec_from_file_location("image_description_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeBlob:
    def __init__(self, name, *, data=b"image", size=None, content_type="image/jpeg"):
        self.name = name
        self.data = data
        self.size = len(data) if size is None else size
        self.content_type = content_type
        self.exists_result = False
        self.created = False
        self.upload_calls = []
        self.delete_calls = []

    def exists(self):
        return self.exists_result

    def download_as_bytes(self):
        return self.data

    def download_as_text(self, encoding=None):
        return self.data.decode("utf-8")

    def upload_from_string(self, data, **kwargs):
        if kwargs.get("if_generation_match") == 0 and self.created:
            raise FakePreconditionFailed("already exists")
        self.created = True
        self.upload_calls.append((data, kwargs))

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)


class FakeBucket:
    def __init__(self, blobs=None):
        self.blobs = {blob.name: blob for blob in blobs or []}

    def blob(self, name):
        if name not in self.blobs:
            self.blobs[name] = FakeBlob(name)
        return self.blobs[name]


class FakeStorageClient:
    def __init__(self, bucket, listed_blobs):
        self._bucket = bucket
        self._listed_blobs = listed_blobs

    def bucket(self, bucket_name):
        return self._bucket

    def list_blobs(self, bucket_name, prefix):
        return self._listed_blobs


class ImageDescriptionTest(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_missing_project_env_fails_before_vertex_initialization(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 PROJECT_ID が未設定",
            ):
                self.module.get_model()

        self.assertEqual(self.module.vertexai.init_calls, [])

    def test_missing_vertex_location_env_fails_before_vertex_initialization(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ID": "sample-project",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 VERTEX_LOCATION が未設定",
            ):
                self.module.get_model()

        self.assertEqual(self.module.vertexai.init_calls, [])

    def test_missing_vertex_model_env_fails_before_vertex_initialization(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ID": "sample-project",
                "VERTEX_LOCATION": "asia-northeast1",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 VERTEX_MODEL が未設定",
            ):
                self.module.get_model()

        self.assertEqual(self.module.vertexai.init_calls, [])

    def test_missing_prompt_env_fails_clearly(self):
        with patch.dict(
            os.environ,
            {
                "PROJECT_ID": "sample-project",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(
                self.module.ConfigurationError,
                "必須環境変数 PROMPT_BUCKET_NAME が未設定",
            ):
                self.module.get_prompt()

    def test_missing_measurements_are_marked_for_human_review(self):
        description = self.module.add_measurement_review_marker("商品説明", False)

        self.assertEqual(description, "【要確認：採寸情報なし】\n商品説明")
        self.assertEqual(
            self.module.add_measurement_review_marker("商品説明", True), "商品説明"
        )

    def test_empty_measurement_file_is_treated_as_missing(self):
        bucket = FakeBucket([FakeBlob("A0001/_SUCCESS.txt", data=b"  \n")])

        measurement_info, measurement_available = self.module.load_measurement_info(
            bucket, "A0001/_SUCCESS.txt"
        )

        self.assertEqual(measurement_info, "")
        self.assertFalse(measurement_available)

    def test_prompt_loading_retries_after_a_transient_failure(self):
        prompt_attempts = iter([None, "商品説明を作成してください。"])
        self.module.load_prompt_from_gcs = lambda bucket, filename: next(prompt_attempts)

        with patch.dict(
            os.environ,
            {
                "PROMPT_BUCKET_NAME": "prompt-bucket",
                "PROMPT_FILE_NAME": "image-prompt.txt",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "プロンプトをGCSから読み込めません"):
                self.module.get_prompt()

            self.assertEqual(self.module.get_prompt(), "商品説明を作成してください。")

    def test_images_are_number_sorted_and_limited_to_twenty(self):
        blobs = [
            FakeBlob(f"A0001/{number:03}.jpg", data=str(number).encode())
            for number in range(21, 0, -1)
        ]
        bucket = FakeBucket(blobs)
        self.module.storage_client = FakeStorageClient(bucket, blobs)

        image_parts = self.module.load_image_parts("images", "A0001")

        self.assertEqual(len(image_parts), 20)
        self.assertEqual(image_parts[0]["data"], b"1")
        self.assertEqual(image_parts[-1]["data"], b"20")

    def test_images_over_the_total_size_limit_raise_an_error(self):
        blobs = [
            FakeBlob("A0001/001.jpg", data=b"a", size=60 * 1024 * 1024),
            FakeBlob("A0001/002.jpg", data=b"b", size=60 * 1024 * 1024),
        ]
        bucket = FakeBucket(blobs)
        self.module.storage_client = FakeStorageClient(bucket, blobs)

        with self.assertRaisesRegex(ValueError, "画像合計サイズ"):
            self.module.load_image_parts("images", "A0001")

    def test_processing_lock_allows_only_one_event_delivery(self):
        bucket = FakeBucket()

        first_lock = self.module.acquire_processing_lock(bucket, "A0001")
        second_lock = self.module.acquire_processing_lock(bucket, "A0001")

        self.assertIsNotNone(first_lock)
        self.assertIsNone(second_lock)
        self.assertEqual(first_lock.upload_calls[0][1]["if_generation_match"], 0)

    def test_failed_generation_releases_lock_and_raises_for_retry(self):
        source = FakeBlob("A0001/_SUCCESS.txt", data=b"size: 10cm")
        bucket = FakeBucket([source])
        self.module.storage_client = FakeStorageClient(bucket, [FakeBlob("A0001/001.jpg")])
        self.module.get_prompt = lambda: "prompt"
        self.module.model = types.SimpleNamespace(
            generate_content=lambda contents: (_ for _ in ()).throw(RuntimeError("Vertex unavailable"))
        )
        event = types.SimpleNamespace(
            data={"bucket": "images", "name": "A0001/_SUCCESS.txt"}
        )

        with self.assertRaisesRegex(RuntimeError, "Vertex unavailable"):
            self.module.generate_description_from_trigger(event)

        lock = bucket.blobs["A0001/_description_processing.lock"]
        self.assertEqual(lock.delete_calls, [{}])


if __name__ == "__main__":
    unittest.main()
