"""Detect listing descriptions that need human review before publishing."""

from __future__ import annotations


REVIEW_REASON_ASSERTIVE_DESCRIPTION = "断定的または誇張の可能性がある表現を検出しました。"

PROHIBITED_EXPRESSIONS = (
    "新品同様",
    "非常に綺麗",
    "使用感少なめ",
    "まだまだご使用いただけます",
    "首回り良好",
    "袖口良好",
    "毛玉なし",
    "汚れなし",
    "傷なし",
    "美品",
)


def detect_prohibited_expressions(description: str) -> list[str]:
    """Return prohibited expressions found in description, preserving guard order."""
    return [phrase for phrase in PROHIBITED_EXPRESSIONS if phrase in description]
