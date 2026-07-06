"""Parse Yahoo Auctions title and HTML description from _description.txt."""

from __future__ import annotations

import re
from dataclasses import dataclass


TITLE_HEADING_PATTERN = r"タイトル\s*[:：]"
DESCRIPTION_HEADING_PATTERN = r"説明文(?:[（(]\s*HTML\s*[）)])?\s*[:：]"
MISSING_MEASUREMENT_MARKER = "【要確認：採寸情報なし】"
YAHOO_DESCRIPTION_PATTERN = re.compile(
    rf"^\s*{TITLE_HEADING_PATTERN}\s*(?P<title>.*?)"
    rf"\s*{DESCRIPTION_HEADING_PATTERN}\s*(?P<description>.*?)\s*$",
    re.DOTALL,
)


class YahooDescriptionParseError(ValueError):
    """Raised when _description.txt does not match the required Yahoo format."""


@dataclass(frozen=True)
class YahooDescription:
    yahoo_title: str
    yahoo_description_html: str


def parse_yahoo_description(raw_text: str) -> YahooDescription:
    """Extract Yahoo title and HTML description without fallback generation."""
    source_text = raw_text.lstrip()
    if source_text.startswith(MISSING_MEASUREMENT_MARKER):
        source_text = source_text[len(MISSING_MEASUREMENT_MARKER) :].lstrip()

    match = YAHOO_DESCRIPTION_PATTERN.match(source_text)
    if not match:
        raise YahooDescriptionParseError(
            "_description.txtに必要な見出し「タイトル:」「説明文（HTML）:」がありません。"
        )

    yahoo_title = match.group("title").strip()
    yahoo_description_html = match.group("description").strip()
    if not yahoo_title:
        raise YahooDescriptionParseError("_description.txtのヤフオク用タイトルが空です。")
    if not yahoo_description_html:
        raise YahooDescriptionParseError("_description.txtのヤフオク用説明文HTMLが空です。")

    return YahooDescription(
        yahoo_title=yahoo_title,
        yahoo_description_html=yahoo_description_html,
    )
