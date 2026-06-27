"""Build platform-safe listing titles in Python."""

from __future__ import annotations

from ai_service import ProductAttributes

TITLE_PART_LIMIT = 7
DEFAULT_TITLE_LIMIT = 65


def _normalize(value: str) -> str:
    return " ".join(value.strip().split())


def _append_unique(parts: list[str], seen: set[str], value: str) -> None:
    normalized = _normalize(value)
    if not normalized:
        return
    key = normalized.casefold()
    if key in seen:
        return
    seen.add(key)
    parts.append(normalized)


def build_title(attributes: ProductAttributes, brand_name: str = "", limit: int = DEFAULT_TITLE_LIMIT) -> str:
    """Build a title from condition, brand, item type, material, color, pattern, size."""
    parts: list[str] = []
    seen: set[str] = set()
    for value in (
        attributes.condition,
        brand_name or attributes.brand_name,
        attributes.item_type or attributes.category_name,
        attributes.material,
        attributes.color,
        attributes.pattern,
        attributes.size,
    ):
        _append_unique(parts, seen, value)
        if len(parts) >= TITLE_PART_LIMIT:
            break

    title = " ".join(parts).strip()
    if not title:
        raise ValueError("商品タイトルを生成できません。")
    if len(title) <= limit:
        return title
    return title[:limit].rstrip()


def ensure_size_in_description(description: str, size: str) -> str:
    normalized_size = _normalize(size)
    if not normalized_size or normalized_size in description:
        return description.strip()
    return f"{description.strip()}\n\nサイズ: {normalized_size}"
