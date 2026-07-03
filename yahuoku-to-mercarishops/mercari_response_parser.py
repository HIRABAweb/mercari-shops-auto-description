"""Parse Mercari Shops title and body from mercari_prompt.txt AI output."""

from __future__ import annotations

import re
from dataclasses import dataclass


MERCARI_RESPONSE_PATTERN = re.compile(
    r"^\s*\[TITLE\]\s*(?P<title>.*?)\s*\[BODY\]\s*(?P<body>.*?)\s*$",
    re.DOTALL,
)
HORIZONTAL_RULE_PATTERN = re.compile(r"^-{3,}$")


class MercariResponseParseError(ValueError):
    """Raised when Mercari conversion output cannot be safely used."""


@dataclass(frozen=True)
class MercariListingContent:
    mercari_title: str
    mercari_body: str


def _strip_horizontal_rules(text: str) -> str:
    lines = [
        line
        for line in text.splitlines()
        if not HORIZONTAL_RULE_PATTERN.match(line.strip())
    ]
    return "\n".join(lines).strip()


def parse_mercari_response(raw_text: str) -> MercariListingContent:
    """Extract Mercari title and body without regenerating either in Python."""
    match = MERCARI_RESPONSE_PATTERN.match(raw_text)
    if not match:
        raise MercariResponseParseError(
            "メルカリ変換AI出力に必要な見出し「[TITLE]」「[BODY]」がありません。"
        )

    mercari_title = _strip_horizontal_rules(match.group("title"))
    mercari_body = _strip_horizontal_rules(match.group("body"))
    if not mercari_title:
        raise MercariResponseParseError("メルカリShops用タイトルが空です。")
    if not mercari_body:
        raise MercariResponseParseError("メルカリShops用商品説明文が空です。")

    return MercariListingContent(
        mercari_title=mercari_title,
        mercari_body=mercari_body,
    )
