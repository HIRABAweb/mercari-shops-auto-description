"""Regression tests for platform CSV-row construction."""

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

    def test_mercari_row_preserves_73_column_format(self):
        row = listing_data.build_mercari_row(["image-1", "image-2"], "A0001", "説明文")

        self.assertEqual(len(row), 73)
        self.assertEqual(row[0:2], ["image-1", "image-2"])
        self.assertEqual(row[21], "説明文")
        self.assertEqual(row[24], "A0001")
        self.assertEqual(row[63], "50000")

    def test_yahoo_row_preserves_114_column_format_and_image_columns(self):
        row = listing_data.build_yahoo_row(["image-1", "image-2"], "A0001", "1行目\n2行目")

        self.assertEqual(len(row), 114)
        self.assertEqual(row[1], "【要修正】商品名 (管理コード: A0001)")
        self.assertEqual(row[2], "1行目<br>2行目")
        self.assertEqual(row[9], "image-1")
        self.assertEqual(row[11], "image-2")
        self.assertEqual(row[61], "2日～3日")


if __name__ == "__main__":
    unittest.main()
