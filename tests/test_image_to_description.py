"""Tests for _SUCCESS.txt loading behavior without cloud credentials."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = PROJECT_ROOT / "image-to-description" / "main.py"


class FakePreconditionFailed(Exception):
    """Stand-in for the GCS precondition error used by the production code."""


def load_image_main_module():
    functions_framework = types.ModuleType("functions_framework")
    functions_framework.cloud_event = lambda function: function

    vertexai = types.ModuleType("vertexai")
    vertexai.init = lambda **kwargs: None
    google = types.ModuleType("google")
    google.__path__ = []
    google_cloud = types.ModuleType("google.cloud")
    google_cloud.__path__ = []
    storage = types.ModuleType("google.cloud.storage")
    storage.Client = lambda: object()
    google_api_core = types.ModuleType("google.api_core")
    google_api_core.__path__ = []
    exceptions = types.ModuleType("google.api_core.exceptions")
    exceptions.PreconditionFailed = FakePreconditionFailed
    generative_models = types.ModuleType("vertexai.generative_models")
    generative_models.GenerativeModel = lambda name: object()
    generative_models.Part = types.SimpleNamespace(
        from_data=lambda data, mime_type: {"data": data, "mime_type": mime_type}
    )

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
    google.cloud = google_cloud
    google_cloud.storage = storage
    google.api_core = google_api_core
    google_api_core.exceptions = exceptions

    with patch.dict(sys.modules, fake_modules):
        spec = importlib.util.spec_from_file_location(
            "image_main_under_test",
            MAIN_PATH,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeTextBlob:
    def __init__(self, text="", error=None):
        self.text = text
        self.error = error

    def download_as_text(self, **kwargs):
        if self.error:
            raise self.error
        return self.text


class FakeBucket:
    def __init__(self, blob):
        self._blob = blob

    def blob(self, object_name):
        return self._blob


class SuccessTextLoadingTest(unittest.TestCase):
    def setUp(self):
        self.module = load_image_main_module()

    def test_empty_success_text_is_distinguished_from_read_failure(self):
        text, available = self.module.load_measurement_info(
            FakeBucket(FakeTextBlob("")),
            "A0001/_SUCCESS.txt",
        )

        self.assertEqual(text, "")
        self.assertFalse(available)

    def test_read_failure_is_raised(self):
        with self.assertRaisesRegex(RuntimeError, "GCS unavailable"):
            self.module.load_measurement_info(
                FakeBucket(FakeTextBlob(error=RuntimeError("GCS unavailable"))),
                "A0001/_SUCCESS.txt",
            )

    def test_decode_error_is_raised(self):
        with self.assertRaises(UnicodeDecodeError):
            self.module.load_measurement_info(
                FakeBucket(
                    FakeTextBlob(
                        error=UnicodeDecodeError(
                            "utf-8",
                            b"\xff",
                            0,
                            1,
                            "invalid start byte",
                        )
                    )
                ),
                "A0001/_SUCCESS.txt",
            )

    def test_success_text_with_product_information_is_available(self):
        text, available = self.module.load_measurement_info(
            FakeBucket(FakeTextBlob("肩幅: 43cm\n状態メモ: 目立つ傷なし")),
            "A0001/_SUCCESS.txt",
        )

        self.assertEqual(text, "肩幅: 43cm\n状態メモ: 目立つ傷なし")
        self.assertTrue(available)


if __name__ == "__main__":
    unittest.main()
