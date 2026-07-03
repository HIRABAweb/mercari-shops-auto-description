"""Tests for parsing Mercari Shops conversion output."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


MODULE_DIR = Path(__file__).resolve().parents[1] / "yahuoku-to-mercarishops"
sys.path.insert(0, str(MODULE_DIR))

from mercari_response_parser import MercariResponseParseError, parse_mercari_response


def test_extracts_title_and_body():
    parsed = parse_mercari_response(
        "[TITLE]\n"
        "D&G ダウンジャケット ナイロン ブラック サイズ46\n"
        "[BODY]\n"
        "右袖口に軽いスレがあります。"
    )

    assert parsed.mercari_title == "D&G ダウンジャケット ナイロン ブラック サイズ46"
    assert parsed.mercari_body == "右袖口に軽いスレがあります。"


def test_ignores_horizontal_rules():
    parsed = parse_mercari_response(
        "[TITLE]\n"
        "--------------------------------------------------\n"
        "D&G ダウンジャケット\n"
        "--------------------------------------------------\n"
        "[BODY]\n"
        "--------------------------------------------------\n"
        "本文です。\n"
        "--------------------------------------------------"
    )

    assert parsed.mercari_title == "D&G ダウンジャケット"
    assert parsed.mercari_body == "本文です。"


def test_empty_title_raises_error():
    with pytest.raises(MercariResponseParseError, match="タイトルが空"):
        parse_mercari_response("[TITLE]\n[BODY]\n本文です。")


def test_empty_body_raises_error():
    with pytest.raises(MercariResponseParseError, match="商品説明文が空"):
        parse_mercari_response("[TITLE]\n商品名\n[BODY]\n")
