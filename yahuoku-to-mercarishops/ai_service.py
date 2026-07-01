"""AI response parsing for listing metadata."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


JSON_OUTPUT_INSTRUCTION = """

出力はJSONだけにしてください。Markdownコードフェンスや説明文をJSON外に付けないでください。
完成した商品タイトルは作らないでください。titleキーが必要な場合は空文字にしてください。

{
  "title": "",
  "description": "商品説明本文",
  "brand_name": "ブランド名",
  "category_name": "カテゴリ名",
  "gender": "性別",
  "item_type": "商品種別",
  "material": "素材",
  "color": "色",
  "pattern": "柄",
  "size": "サイズ",
  "condition": "状態",
  "confidence": {
    "brand_name": 0.0,
    "category_name": 0.0,
    "item_type": 0.0,
    "size": 0.0,
    "condition": 0.0
  }
}

IDは出力しないでください。商品説明は本文のみとし、「タイトル：」「商品名：」「説明文：」などの見出しを含めないでください。
"""

_CODE_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)
_DESCRIPTION_HEADING_PATTERN = re.compile(
    r"(?m)^\s*(?:タイトル|商品名|説明文)\s*[:：]\s*"
)


class InputValidationError(ValueError):
    """Raised when generated listing metadata cannot be safely used."""


@dataclass(frozen=True)
class ProductAttributes:
    description: str
    brand_name: str = ""
    category_name: str = ""
    gender: str = ""
    item_type: str = ""
    material: str = ""
    color: str = ""
    pattern: str = ""
    size: str = ""
    condition: str = ""
    confidence: dict[str, float] = field(default_factory=dict)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_confidence(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, raw_score in value.items():
        try:
            result[str(key)] = float(raw_score)
        except (TypeError, ValueError):
            continue
    return result


def strip_json_code_fence(text: str) -> str:
    match = _CODE_FENCE_PATTERN.match(text)
    if match:
        return match.group("body").strip()
    return text.strip()


def clean_description(description: str) -> str:
    cleaned_lines: list[str] = []
    for line in description.splitlines():
        if re.match(r"^\s*(?:タイトル|商品名)\s*[:：]", line):
            continue
        cleaned_lines.append(
            re.sub(r"^\s*説明文\s*[:：]\s*", "", line).rstrip()
        )
    return "\n".join(cleaned_lines).strip()


def parse_product_attributes(raw_text: str) -> ProductAttributes:
    """Parse strict or fenced JSON returned by Gemini into normalized attributes."""
    if not raw_text.strip():
        raise InputValidationError("生成AIから空の商品情報が返されました。")

    json_text = strip_json_code_fence(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        start = json_text.find("{")
        end = json_text.rfind("}")
        if start == -1 or end <= start:
            raise InputValidationError("生成AIのJSONを解析できません。")
        parsed = json.loads(json_text[start : end + 1])

    if not isinstance(parsed, dict):
        raise InputValidationError("生成AIのJSONがオブジェクトではありません。")

    description = clean_description(_as_text(parsed.get("description")))
    if not description:
        raise InputValidationError("生成AIの商品説明本文が空です。")

    return ProductAttributes(
        description=description,
        brand_name=_as_text(parsed.get("brand_name")),
        category_name=_as_text(parsed.get("category_name")),
        gender=_as_text(parsed.get("gender")),
        item_type=_as_text(parsed.get("item_type")),
        material=_as_text(parsed.get("material")),
        color=_as_text(parsed.get("color")),
        pattern=_as_text(parsed.get("pattern")),
        size=_as_text(parsed.get("size")),
        condition=_as_text(parsed.get("condition")),
        confidence=_as_confidence(parsed.get("confidence")),
    )


def build_generation_prompt(base_prompt: str, source_description: str) -> str:
    return (
        f"{base_prompt}\n\n"
        f"{JSON_OUTPUT_INSTRUCTION}\n\n"
        f"【商品情報】\n{source_description}\n"
    )
