"""Tests for image URL helpers."""

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "yahuoku-to-mercarishops"
    / "listing_data.py"
)
SPEC = importlib.util.spec_from_file_location("listing_data", MODULE_PATH)
listing_data = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(listing_data)


class Blob:
    def __init__(self, name: str):
        self.name = name


class ListingDataTest(unittest.TestCase):
    def test_image_urls_are_number_sorted_and_unsupported_files_are_excluded(self):
        blobs = [Blob("A0001/010.jpg"), Blob("A0001/readme.txt"), Blob("A0001/002.png")]

        image_urls = listing_data.collect_sorted_image_urls(blobs, "product-images")

        self.assertEqual(
            image_urls,
            [
                "https://storage.googleapis.com/product-images/A0001/002.png",
                "https://storage.googleapis.com/product-images/A0001/010.jpg",
            ],
        )


if __name__ == "__main__":
    unittest.main()
