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
    def test_mercari_headers_match_73_column_mapping(self):
        self.assertEqual(len(listing_data.MERCARI_HEADERS), 73)
        self.assertEqual(listing_data.MERCARI_HEADERS[0], "商品画像名_1")
        self.assertEqual(listing_data.MERCARI_HEADERS[19], "商品画像名_20")
        self.assertEqual(listing_data.MERCARI_HEADERS[20], "商品名")
        self.assertEqual(listing_data.MERCARI_HEADERS[21], "商品説明")
        self.assertEqual(listing_data.MERCARI_HEADERS[24], "SKU1_商品管理コード")
        self.assertEqual(listing_data.MERCARI_HEADERS[62], "ブランドID")
        self.assertEqual(listing_data.MERCARI_HEADERS[63], "販売価格")
        self.assertEqual(listing_data.MERCARI_HEADERS[64], "カテゴリID")
        self.assertEqual(listing_data.MERCARI_HEADERS[72], "メルカリBiz配送_クール区分")

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
        row = listing_data.build_mercari_row(
            ["image-1", "image-2"], "A0001", "商品名", "説明文"
        )

        self.assertEqual(len(row), 73)
        self.assertEqual(row[0:2], ["image-1", "image-2"])
        self.assertEqual(row[20], "商品名")
        self.assertEqual(row[21], "説明文")
        self.assertEqual(row[24], "A0001")
        self.assertEqual(row[63], "50000")

    def test_yahoo_row_preserves_114_column_format_and_image_columns(self):
        row = listing_data.build_yahoo_row(
            ["image-1", "image-2"], "A0001", "商品名", "1行目\n2行目"
        )

        self.assertEqual(len(row), 114)
        self.assertEqual(row[1], "商品名")
        self.assertEqual(row[2], "1行目<br>2行目")
        self.assertEqual(row[9], "image-1")
        self.assertEqual(row[11], "image-2")
        self.assertEqual(row[61], "2日～3日")

    def test_yahoo_description_parser_accepts_normal_format(self):
        parsed = listing_data.parse_yahoo_description(
            "タイトル:\n"
            "美品 COACH ショルダーバッグ レザー ブラック\n\n"
            "説明文（HTML）:\n"
            "<p>上品な印象のバッグです。</p>"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ レザー ブラック")
        self.assertEqual(parsed.description, "<p>上品な印象のバッグです。</p>")

    def test_yahoo_description_parser_ignores_missing_measurement_notice(self):
        parsed = listing_data.parse_yahoo_description(
            "〖要確認：採寸情報なし〗\n\n"
            "タイトル:\n"
            "美品 COACH ショルダーバッグ レザー ブラック\n\n"
            "説明文（HTML）:\n"
            "<p>上品な印象のバッグです。</p>"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ レザー ブラック")
        self.assertIn("採寸情報なし", [issue.reason for issue in parsed.review_issues])

    def test_yahoo_description_parser_accepts_fullwidth_colon(self):
        parsed = listing_data.parse_yahoo_description(
            "タイトル：\n"
            "美品 COACH ショルダーバッグ レザー ブラック\n\n"
            "説明文（HTML）：\n"
            "<p>上品な印象のバッグです。</p>"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ レザー ブラック")
        self.assertEqual(parsed.description, "<p>上品な印象のバッグです。</p>")

    def test_yahoo_description_parser_removes_markdown_code_fence(self):
        parsed = listing_data.parse_yahoo_description(
            "```html\n"
            "タイトル:\n"
            "美品 COACH ショルダーバッグ レザー ブラック\n\n"
            "説明文（HTML）:\n"
            "<p>上品な印象のバッグです。</p>\n"
            "```"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ レザー ブラック")
        self.assertNotIn("```", parsed.description)

    def test_yahoo_description_parser_ignores_extra_preface(self):
        parsed = listing_data.parse_yahoo_description(
            "以下に生成します。\n\n"
            "タイトル:\n"
            "美品 COACH ショルダーバッグ レザー ブラック\n\n"
            "説明文:\n"
            "上品な印象のバッグです。"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ レザー ブラック")
        self.assertEqual(parsed.description, "上品な印象のバッグです。")

    def test_mercari_parser_accepts_bracket_headings(self):
        parsed = listing_data.parse_mercari_description(
            "[TITLE]\n"
            "美品 COACH ショルダーバッグ\n\n"
            "[BODY]\n"
            "上品な印象のバッグです。"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ")
        self.assertEqual(parsed.description, "上品な印象のバッグです。")

    def test_mercari_parser_accepts_bracket_headings_with_colons(self):
        parsed = listing_data.parse_mercari_description(
            "[TITLE]:\n"
            "美品 COACH ショルダーバッグ\n\n"
            "[BODY]:\n"
            "上品な印象のバッグです。"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ")
        self.assertEqual(parsed.description, "上品な印象のバッグです。")

    def test_mercari_parser_accepts_english_headings(self):
        parsed = listing_data.parse_mercari_description(
            "TITLE:\n"
            "美品 COACH ショルダーバッグ\n\n"
            "BODY:\n"
            "上品な印象のバッグです。"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ")
        self.assertEqual(parsed.description, "上品な印象のバッグです。")

    def test_mercari_parser_accepts_japanese_headings(self):
        parsed = listing_data.parse_mercari_description(
            "商品名:\n"
            "美品 COACH ショルダーバッグ\n\n"
            "商品説明:\n"
            "上品な印象のバッグです。"
        )

        self.assertEqual(parsed.title, "美品 COACH ショルダーバッグ")
        self.assertEqual(parsed.description, "上品な印象のバッグです。")

    def test_mercari_parser_removes_html_tags_and_flags_review(self):
        parsed = listing_data.parse_mercari_description(
            "[TITLE]\n"
            "美品 COACH バッグ\n\n"
            "[BODY]\n"
            "<p>美品です。</p><br>おすすめです。"
        )

        self.assertEqual(parsed.description, "美品です。\nおすすめです。")
        self.assertIn(
            "Mercari本文にHTMLタグが含まれている可能性あり",
            [issue.reason for issue in parsed.review_issues],
        )

    def test_mercari_parser_removes_yahoo_terms_and_flags_review(self):
        parsed = listing_data.parse_mercari_description(
            "[TITLE]\n"
            "美品 COACH バッグ\n\n"
            "[BODY]\n"
            "ヤフオクでも人気です。\n管理コード: A0001\n上品なバッグです。"
        )

        self.assertEqual(parsed.description, "上品なバッグです。")
        self.assertIn(
            "Mercari本文にYahoo向け文言が含まれている可能性あり",
            [issue.reason for issue in parsed.review_issues],
        )

    def test_review_required_reasons_cover_missing_product_information(self):
        issues = listing_data.analyze_success_text("状態メモ:")

        self.assertIn("採寸情報なし", [issue.reason for issue in issues])
        self.assertIn("状態メモなし", [issue.reason for issue in issues])

    def test_state_note_label_is_recognized(self):
        issues = listing_data.analyze_success_text("肩幅: 43cm\n状態メモ: 目立つ傷なし")

        self.assertNotIn("状態メモなし", [issue.reason for issue in issues])

    def test_state_label_is_recognized(self):
        issues = listing_data.analyze_success_text("肩幅: 43cm\n状態: 使用感少なめ")

        self.assertNotIn("状態メモなし", [issue.reason for issue in issues])

    def test_special_note_label_is_recognized(self):
        issues = listing_data.analyze_success_text("肩幅: 43cm\n特記事項: 袖に薄汚れあり")

        self.assertNotIn("状態メモなし", [issue.reason for issue in issues])

    def test_empty_condition_labels_are_treated_as_missing(self):
        issues = listing_data.analyze_success_text(
            "肩幅: 43cm\n状態:\n特記事項:\n備考:\n注意点:"
        )

        self.assertIn("状態メモなし", [issue.reason for issue in issues])

    def test_review_required_reasons_cover_unknown_brand_and_category(self):
        issues = listing_data.add_default_review_issues([])

        self.assertIn(
            "ブランド不明のためデフォルト値を使用",
            [issue.reason for issue in issues],
        )
        self.assertIn(
            "カテゴリ不明のため確認が必要",
            [issue.reason for issue in issues],
        )

    def test_review_required_reason_for_long_title_shortening(self):
        title = "美品 COACH ショルダーバッグ レザー ブラック " * 20

        shortened, changed = listing_data.shorten_title(title, 65)

        self.assertTrue(changed)
        self.assertLessEqual(len(shortened), 65)
        self.assertTrue(shortened.startswith("美品 COACH ショルダーバッグ"))

    def test_review_required_reason_for_appeal_term_without_evidence(self):
        issues = listing_data.detect_appeal_terms_without_evidence(
            "希少なバッグです。",
            "状態メモ: 目立つ傷なし",
        )

        self.assertEqual(issues[0].reason, "訴求表現の根拠確認が必要: 希少")

    def test_review_rows_are_human_actionable_japanese(self):
        rows = listing_data.build_review_rows(
            "A0001",
            "A0001/_description.txt",
            [
                listing_data.ReviewIssue(
                    "all",
                    "measurements",
                    "採寸情報なし",
                    "",
                    "商品の縦・横・マチ等を確認して本文を修正してください",
                )
            ],
        )

        self.assertEqual(rows[0][0], "A0001|A0001/_description.txt|all|measurements|採寸情報なし")
        self.assertEqual(rows[0][1], "A0001")
        self.assertEqual(rows[0][5], "採寸情報なし")
        self.assertIn("確認", rows[0][7])

    def test_aggregates_per_item_review_csv_texts(self):
        csv_a = (
            "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
            "key-a,A0001,A0001/_description.txt,all,measurements,採寸情報なし,,確認\n"
        )
        csv_b = (
            "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
            "key-b,B0001,B0001/_description.txt,mercari,description,HTML混入,,確認\n"
        )

        aggregate = listing_data.aggregate_review_required_csv_texts([csv_a, csv_b])

        self.assertIn("key-a,A0001", aggregate)
        self.assertIn("key-b,B0001", aggregate)
        self.assertEqual(aggregate.count("review_key,item_id"), 1)

    def test_aggregate_deduplicates_by_review_key(self):
        csv_text = (
            "review_key,item_id,file_path,platform,field,reason,current_value,suggested_action\n"
            "key-a,A0001,A0001/_description.txt,all,measurements,採寸情報なし,,確認\n"
        )

        aggregate = listing_data.aggregate_review_required_csv_texts([csv_text, csv_text])

        self.assertEqual(aggregate.count("key-a,A0001"), 1)


if __name__ == "__main__":
    unittest.main()
