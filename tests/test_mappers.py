"""Tests for brand and category master mapping."""

from __future__ import annotations

import sys
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1] / "yahuoku-to-mercarishops"
sys.path.insert(0, str(MODULE_DIR))

from brand_mapper import build_brand_records, resolve_brand
from category_mapper import build_category_records, resolve_category


def test_brand_alias_maps_to_master_id():
    records = build_brand_records(
        [
            {
                "brand_id": "123",
                "brand_name": "Dolce&Gabbana",
                "aliases": "D&G,ドルガバ,ドルチェ&ガッバーナ",
            }
        ]
    )

    match = resolve_brand("ドルガバ", records)

    assert match.brand_id == "123"
    assert match.brand_name == "Dolce&Gabbana"
    assert not match.review_required


def test_official_brand_master_columns_are_supported():
    records = build_brand_records(
        [
            {
                "ブランドID": "225nDaWCk4MpMbnFP6a5An",
                "ブランド名": "Xmiss",
                "ブランド名（カナ）": "キスミス",
                "ブランド名（英語）": "Xmiss",
            }
        ]
    )

    match = resolve_brand("キスミス", records)

    assert match.brand_id == "225nDaWCk4MpMbnFP6a5An"
    assert match.brand_name == "Xmiss"
    assert not match.review_required


def test_unknown_brand_requires_review():
    match = resolve_brand("Unknown", [])

    assert match.review_required
    assert match.reason


def test_category_maps_to_master_id():
    records = build_category_records(
        [
            {
                "category_id": "456",
                "category_name": "ジャケット",
                "gender": "メンズ",
                "item_type": "ダウンジャケット",
                "aliases": "アウター",
            }
        ]
    )

    match = resolve_category("ジャケット", "メンズ", "ダウンジャケット", records, 0.9)

    assert match.category_id == "456"
    assert match.category_name == "ジャケット"
    assert not match.review_required


def test_official_category_master_columns_are_supported():
    records = build_category_records(
        [
            {
                "カテゴリID": "abc123",
                "カテゴリ名": "ダウンジャケット",
                "カテゴリ名（フル）": "ファッション > メンズ > ジャケット・アウター > ダウンジャケット",
            }
        ]
    )

    match = resolve_category("ジャケット・アウター", "メンズ", "ダウンジャケット", records, 0.9)

    assert match.category_id == "abc123"
    assert match.category_name == "ダウンジャケット"
    assert not match.review_required


def test_low_confidence_category_requires_review():
    match = resolve_category("ジャケット", "メンズ", "ダウンジャケット", [], 0.2)

    assert match.review_required
    assert "信頼度" in match.reason

def test_gender_alone_does_not_resolve_category():
    records = build_category_records(
        [
            {
                "カテゴリID": "mens-outer",
                "カテゴリ名": "ジャケット",
                "カテゴリ名（フル）": "ファッション > メンズ > ジャケット・アウター > ジャケット",
            }
        ]
    )

    match = resolve_category("", "メンズ", "", records, 0.9)

    assert match.review_required
    assert not match.category_id
    assert "カテゴリ情報" in match.reason