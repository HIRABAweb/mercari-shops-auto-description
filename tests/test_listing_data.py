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

    def test_product_info_recognizes_supported_condition_labels(self):
        for label in (
            "状態メモ",
            "状態",
            "コンディション",
            "特記事項",
            "備考",
            "注意点",
        ):
            with self.subTest(label=label):
                result = listing_data.parse_product_info(f"{label}: 使用感は少ないです")
                self.assertTrue(result.has_condition_notes)

    def test_product_info_recognizes_multiline_condition_and_measurements(self):
        result = listing_data.parse_product_info(
            """採寸:
肩幅 45cm
身幅 52cm

特記事項:
右袖口に軽いスレあり
ファスナー開閉確認済み
"""
        )

        self.assertTrue(result.has_measurements)
        self.assertEqual(len(result.measurements), 2)
        self.assertTrue(result.has_condition_notes)
        self.assertEqual(len(result.condition_notes), 2)

    def test_empty_condition_labels_are_treated_as_missing(self):
        result = listing_data.parse_product_info(
            """状態メモ:
状態:
特記事項:
備考:
注意点:
"""
        )

        self.assertFalse(result.has_condition_notes)

    def test_product_info_review_rows_are_actionable(self):
        rows = listing_data.build_product_info_review_rows(
            "A0001",
            listing_data.parse_product_info("ブランド: Example"),
        )

        self.assertEqual([row["確認項目"] for row in rows], ["採寸", "状態メモ"])
        self.assertIn("採寸情報なし", rows[0]["理由"])
        self.assertIn("状態メモなし", rows[1]["理由"])


if __name__ == "__main__":
    unittest.main()
