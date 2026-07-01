"""Tests for structured AI metadata parsing and title generation."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


MODULE_DIR = Path(__file__).resolve().parents[1] / "yahuoku-to-mercarishops"
sys.path.insert(0, str(MODULE_DIR))

import ai_service
import title_builder


def test_parses_normal_json():
    content = ai_service.parse_product_attributes(
        json.dumps(
            {
                "description": "上質なワンピースです。",
                "brand_name": "CELINE",
                "category_name": "ワンピース",
                "item_type": "ワンピース",
                "color": "黒",
                "size": "M",
                "condition": "美品",
                "confidence": {"category_name": 0.91},
            },
            ensure_ascii=False,
        )
    )

    assert content.description == "上質なワンピースです。"
    assert content.brand_name == "CELINE"
    assert content.confidence["category_name"] == 0.91


def test_parses_json_code_fence():
    content = ai_service.parse_product_attributes(
        """```json
{"description":"鮮やかな赤のバッグです。","brand_name":"D&G","item_type":"バッグ"}
```"""
    )

    assert content.description == "鮮やかな赤のバッグです。"
    assert content.brand_name == "D&G"


def test_description_headings_are_removed():
    content = ai_service.parse_product_attributes(
        json.dumps(
            {
                "description": (
                    "タイトル：良品 コート ウール 紺 L\n"
                    "商品名：良品 コート ウール 紺 L\n"
                    "説明文：暖かいコートです。"
                )
            },
            ensure_ascii=False,
        )
    )

    assert content.description == "暖かいコートです。"
    assert "タイトル" not in content.description
    assert "商品名" not in content.description
    assert "説明文" not in content.description


def test_empty_description_fails():
    with pytest.raises(ai_service.InputValidationError, match="商品説明本文が空"):
        ai_service.parse_product_attributes('{"description":""}')


def test_preserves_japanese_newlines_and_fullwidth_symbols():
    content = ai_service.parse_product_attributes(
        json.dumps(
            {
                "description": "肩幅：約45cm\n状態：目立つ傷みなし。\n価格はご相談ください。",
                "size": "２",
            },
            ensure_ascii=False,
        )
    )

    assert content.description == "肩幅：約45cm\n状態：目立つ傷みなし。\n価格はご相談ください。"
    assert content.size == "２"


def test_python_builds_title_without_ai_title():
    attributes = ai_service.ProductAttributes(
        description="説明文です。",
        brand_name="D&G",
        item_type="ダウンジャケット",
        color="ブラック",
        size="46",
        condition="美品",
    )

    assert title_builder.build_title(attributes) == "美品 D&G ダウンジャケット ブラック 46"


def test_description_gets_size_when_missing():
    assert title_builder.ensure_size_in_description("説明文です。", "46") == "説明文です。\n\nサイズ: 46"
