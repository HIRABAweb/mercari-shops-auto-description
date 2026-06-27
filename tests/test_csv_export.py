"""Tests for column-name based CSV export builders."""

from __future__ import annotations

import csv
import io
import sys
import pytest
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1] / "yahuoku-to-mercarishops"
sys.path.insert(0, str(MODULE_DIR))

from ai_service import ProductAttributes
from brand_mapper import BrandMatch
from category_mapper import CategoryMatch
from csv_export import (
    MERCARI_HEADERS,
    REVIEW_REQUIRED_HEADERS,
    YAHOO_HEADERS,
    build_csv_text,
    build_export_rows,
    image_file_name,
    validate_mercari_headers,
)


def test_export_rows_use_official_mercari_column_names_and_include_ids_and_size():
    attributes = ProductAttributes(description="説明", item_type="ジャケット", size="46")
    rows = build_export_rows(
        image_urls=["https://storage.googleapis.com/bucket/A0001/001.jpg", "gs://bucket/A0001/002.png"],
        product_code="A0001",
        title="美品 D&G ジャケット 46",
        description="説明\n\nサイズ: 46",
        attributes=attributes,
        brand_match=BrandMatch(brand_id="123", brand_name="Dolce&Gabbana"),
        category_match=CategoryMatch(category_id="456", category_name="ジャケット"),
    )

    assert rows.mercari_row["商品画像名_1"] == "001.jpg"
    assert rows.mercari_row["商品画像名_2"] == "002.png"
    assert rows.mercari_row["商品名"] == "美品 D&G ジャケット 46"
    assert rows.mercari_row["商品説明"] == "説明\n\nサイズ: 46"
    assert rows.mercari_row["ブランドID"] == "123"
    assert rows.mercari_row["カテゴリID"] == "456"
    assert rows.mercari_row["SKU1_種類"] == "46"
    assert rows.mercari_row["商品ステータス"] == "1"
    assert rows.yahoo_row["タイトル"] == "美品 D&G ジャケット 46 (管理コード: A0001)"
    assert rows.yahoo_row["説明"] == "説明<br><br>サイズ: 46"


def test_review_required_rows_include_only_review_items():
    attributes = ProductAttributes(description="説明")
    rows = build_export_rows(
        image_urls=[],
        product_code="A0001",
        title="商品名",
        description="説明",
        attributes=attributes,
        brand_match=BrandMatch(review_required=True, reason="ブランド未確定", candidates=["候補A"]),
        category_match=CategoryMatch(category_id="456", category_name="ジャケット"),
    )

    assert rows.review_rows == [
        {
            "商品管理コード": "A0001",
            "確認項目": "ブランドID",
            "候補1": "候補A",
            "候補2": "",
            "理由": "ブランド未確定",
        }
    ]


def test_build_csv_text_writes_header_and_preserves_japanese_commas_and_newlines():
    csv_text = build_csv_text(["商品名", "商品説明"], [{"商品名": "商品,名", "商品説明": "1行目\n2行目"}])
    rows = list(csv.reader(io.StringIO(csv_text)))

    assert rows == [["商品名", "商品説明"], ["商品,名", "1行目\n2行目"]]
    assert csv_text.endswith("\n")


def test_mercari_headers_are_loaded_from_official_template():
    assert len(MERCARI_HEADERS) == 88
    assert MERCARI_HEADERS[:3] == ["商品画像名_1", "商品画像名_2", "商品画像名_3"]
    assert "商品名" in MERCARI_HEADERS
    assert "ブランドID" in MERCARI_HEADERS
    assert "カテゴリID" in MERCARI_HEADERS
    assert "商品ステータス" in MERCARI_HEADERS
    assert "タイトル" in YAHOO_HEADERS
    assert REVIEW_REQUIRED_HEADERS == ["商品管理コード", "確認項目", "候補1", "候補2", "理由"]


def test_image_file_name_decodes_url_paths():
    assert image_file_name("https://example.com/items/%E7%94%BB%E5%83%8F%201.jpg") == "画像 1.jpg"
    assert image_file_name("plain-name.png") == "plain-name.png"

def test_validate_mercari_headers_rejects_missing_required_columns():
    invalid_headers = [header for header in MERCARI_HEADERS if header != "商品名"]

    with pytest.raises(RuntimeError, match="公式CSVテンプレート"):
        validate_mercari_headers(invalid_headers)