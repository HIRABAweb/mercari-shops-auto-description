"""Tests for parsing Yahoo title and HTML description from _description.txt."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


MODULE_DIR = Path(__file__).resolve().parents[1] / "yahuoku-to-mercarishops"
sys.path.insert(0, str(MODULE_DIR))

from yahoo_description_parser import YahooDescriptionParseError, parse_yahoo_description


def test_extracts_title_and_html_description():
    parsed = parse_yahoo_description(
        "タイトル: D&G ダウンジャケット 46\n"
        "説明文（HTML）: <p>右袖口に軽いスレあり。</p>"
    )

    assert parsed.yahoo_title == "D&G ダウンジャケット 46"
    assert parsed.yahoo_description_html == "<p>右袖口に軽いスレあり。</p>"


def test_extracts_fullwidth_colon_headings():
    parsed = parse_yahoo_description(
        "タイトル：\nD&G ダウンジャケット 46\n"
        "説明文（HTML）：\n<div>説明HTML</div>"
    )

    assert parsed.yahoo_title == "D&G ダウンジャケット 46"
    assert parsed.yahoo_description_html == "<div>説明HTML</div>"


def test_extracts_plain_description_heading():
    parsed = parse_yahoo_description(
        "タイトル: D&G ダウンジャケット 46\n"
        "説明文: <section>説明HTML</section>"
    )

    assert parsed.yahoo_title == "D&G ダウンジャケット 46"
    assert parsed.yahoo_description_html == "<section>説明HTML</section>"


def test_tolerates_legacy_missing_measurement_marker_prefix():
    parsed = parse_yahoo_description(
        "【要確認：採寸情報なし】\n"
        "タイトル: D&G ダウンジャケット 46\n"
        "説明文（HTML）: <p>説明HTML</p>"
    )

    assert parsed.yahoo_title == "D&G ダウンジャケット 46"
    assert parsed.yahoo_description_html == "<p>説明HTML</p>"


def test_empty_title_raises_error():
    with pytest.raises(YahooDescriptionParseError, match="タイトルが空"):
        parse_yahoo_description("タイトル:\n説明文（HTML）: <p>説明</p>")


def test_empty_html_description_raises_error():
    with pytest.raises(YahooDescriptionParseError, match="説明文HTMLが空"):
        parse_yahoo_description("タイトル: 商品名\n説明文（HTML）:")


def test_missing_headings_raise_error():
    with pytest.raises(YahooDescriptionParseError, match="必要な見出し"):
        parse_yahoo_description("D&G ダウンジャケット\n<p>説明</p>")
