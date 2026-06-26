"""Tests for generated title/description parsing and spreadsheet append ranges."""

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_PATH = PROJECT_ROOT / "yahuoku-to-mercarishops" / "main.py"
sys.path.insert(0, str(MAIN_PATH.parent))


class FakePreconditionFailed(Exception):
    pass


class FakeSecretClient:
    def access_secret_version(self, request):
        return types.SimpleNamespace(
            payload=types.SimpleNamespace(data=b"test-api-key")
        )


def load_main_module():
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
        spec = importlib.util.spec_from_file_location("listing_main_parser_test", MAIN_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


listing_main = load_main_module()


class AppendOnlyWorksheet:
    def __init__(self):
        self.append_calls = []

    def append_row(self, row_values, value_input_option, table_range):
        self.append_calls.append(
            {
                "row_values": row_values,
                "value_input_option": value_input_option,
                "table_range": table_range,
            }
        )


def test_parses_normal_json():
    content = listing_main.parse_generated_listing_content(
        json.dumps(
            {
                "title": "美品 セリーヌ ワンピース 黒 M",
                "description": "上質なワンピースです。",
            },
            ensure_ascii=False,
        )
    )

    assert content.title == "美品 セリーヌ ワンピース 黒 M"
    assert content.description == "上質なワンピースです。"


def test_parses_json_code_fence():
    content = listing_main.parse_generated_listing_content(
        """```json
{"title":"未使用 バッグ レザー 赤","description":"鮮やかな赤のバッグです。"}
```"""
    )

    assert content.title == "未使用 バッグ レザー 赤"
    assert content.description == "鮮やかな赤のバッグです。"


def test_splits_legacy_title_and_description():
    content = listing_main.parse_generated_listing_content(
        "タイトル：美品 シャネル ジャケット ツイード 黒 38\n"
        "説明文：落ち着いた雰囲気のジャケットです。\n"
        "裏地もきれいです。"
    )

    assert content.title == "美品 シャネル ジャケット ツイード 黒 38"
    assert content.description == "落ち着いた雰囲気のジャケットです。\n裏地もきれいです。"


def test_description_headings_are_removed():
    content = listing_main.parse_generated_listing_content(
        json.dumps(
            {
                "title": "商品名：良品 コート ウール 紺 L",
                "description": (
                    "タイトル：良品 コート ウール 紺 L\n"
                    "商品名：良品 コート ウール 紺 L\n"
                    "説明文：暖かいコートです。"
                ),
            },
            ensure_ascii=False,
        )
    )

    assert content.title == "良品 コート ウール 紺 L"
    assert content.description == "暖かいコートです。"
    assert "タイトル" not in content.description
    assert "商品名" not in content.description
    assert "説明文" not in content.description


def test_empty_title_fails():
    with pytest.raises(listing_main.InputValidationError, match="商品タイトルが空"):
        listing_main.parse_generated_listing_content(
            '{"title":"","description":"説明があります。"}'
        )


def test_empty_description_fails():
    with pytest.raises(listing_main.InputValidationError, match="商品説明本文が空"):
        listing_main.parse_generated_listing_content(
            '{"title":"美品 バッグ","description":""}'
        )


def test_preserves_japanese_newlines_and_fullwidth_symbols():
    content = listing_main.parse_generated_listing_content(
        json.dumps(
            {
                "title": "良品 ヨウジヤマモト コート ウール 黒 ２",
                "description": "肩幅：約45cm\n状態：目立つ傷みなし。\n価格はご相談ください。",
            },
            ensure_ascii=False,
        )
    )

    assert content.title == "良品 ヨウジヤマモト コート ウール 黒 ２"
    assert content.description == "肩幅：約45cm\n状態：目立つ傷みなし。\n価格はご相談ください。"


def test_mercari_row_has_73_columns_and_uses_title():
    row = listing_main.build_mercari_row(
        ["https://example.com/1.jpg"],
        "A001",
        description="説明文です。",
        title="美品 バッグ",
    )

    assert len(row) == 73
    assert row[20] == "美品 バッグ"
    assert row[21] == "説明文です。"


def test_yahoo_row_has_114_columns_and_uses_title():
    row = listing_main.build_yahoo_row(
        ["https://example.com/1.jpg"],
        "A001",
        description="1行目\n2行目",
        title="美品 バッグ",
    )

    assert len(row) == 114
    assert row[1] == "美品 バッグ (管理コード: A001)"
    assert row[2] == "1行目<br>2行目"


def test_append_row_receives_expected_table_ranges(monkeypatch):
    mercari_sheet = AppendOnlyWorksheet()
    yahoo_sheet = AppendOnlyWorksheet()
    monkeypatch.setattr(
        listing_main,
        "get_worksheets",
        lambda: (mercari_sheet, yahoo_sheet),
    )

    listing_main.append_listing_rows(
        [""] * listing_main.MERCARI_COLUMN_COUNT,
        [""] * listing_main.YAHOO_COLUMN_COUNT,
    )

    assert mercari_sheet.append_calls[0]["table_range"] == "A1:BU"
    assert yahoo_sheet.append_calls[0]["table_range"] == "A1:DJ"
    assert mercari_sheet.append_calls[0]["value_input_option"] == "RAW"
    assert yahoo_sheet.append_calls[0]["value_input_option"] == "RAW"
