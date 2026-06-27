"""Category name to category ID mapping."""

from __future__ import annotations

from dataclasses import dataclass, field


REVIEW_REASON_NO_CATEGORY = "カテゴリ情報を判定できません。"
REVIEW_REASON_UNKNOWN_CATEGORY = "カテゴリマスタに一致するカテゴリがありません。"
LOW_CONFIDENCE_REASON = "AI判定の信頼度が低いため確認が必要です。"
DEFAULT_CONFIDENCE_THRESHOLD = 0.75
GENDER_TOKENS = ("メンズ", "レディース", "ベビー", "キッズ")


@dataclass(frozen=True)
class CategoryRecord:
    category_id: str
    category_name: str
    gender: str = ""
    item_type: str = ""
    aliases: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class CategoryMatch:
    category_id: str = ""
    category_name: str = ""
    review_required: bool = False
    reason: str = ""
    candidates: list[str] = field(default_factory=list)


def normalize_category_token(value: str) -> str:
    return value.strip().casefold().replace(" ", "")


def split_full_category(full_category: str) -> set[str]:
    return {part.strip() for part in full_category.split(">") if part.strip()}


def infer_gender(full_category: str) -> str:
    for token in GENDER_TOKENS:
        if token in full_category:
            return token
    return ""


def build_category_records(rows: list[dict[str, str]]) -> list[CategoryRecord]:
    records: list[CategoryRecord] = []
    for row in rows:
        category_id = (row.get("category_id") or row.get("カテゴリID") or "").strip()
        category_name = (row.get("category_name") or row.get("カテゴリ名") or "").strip()
        full_category = (row.get("カテゴリ名（フル）") or row.get("category_full_name") or "").strip()
        gender = (row.get("gender") or row.get("性別") or infer_gender(full_category)).strip()
        item_type = (row.get("item_type") or row.get("商品種別") or category_name).strip()
        aliases_text = (row.get("aliases") or row.get("別名") or "").strip()
        aliases = {part.strip() for part in aliases_text.replace("|", ",").split(",") if part.strip()}
        aliases.update(split_full_category(full_category))
        if category_id and category_name:
            records.append(
                CategoryRecord(
                    category_id=category_id,
                    category_name=category_name,
                    gender=gender,
                    item_type=item_type,
                    aliases=aliases,
                )
            )
    return records


def _record_names(record: CategoryRecord) -> set[str]:
    return {record.category_name, record.item_type, *record.aliases}


def _gender_mismatches(gender: str, record: CategoryRecord) -> bool:
    return bool(
        gender.strip()
        and record.gender.strip()
        and normalize_category_token(gender) != normalize_category_token(record.gender)
    )


def resolve_category(
    category_name: str,
    gender: str,
    item_type: str,
    records: list[CategoryRecord],
    confidence: float | None = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> CategoryMatch:
    if confidence is not None and confidence < confidence_threshold:
        return CategoryMatch(review_required=True, reason=LOW_CONFIDENCE_REASON)

    category_tokens = [category_name, item_type]
    normalized_tokens = {normalize_category_token(token) for token in category_tokens if token.strip()}
    if not normalized_tokens:
        return CategoryMatch(review_required=True, reason=REVIEW_REASON_NO_CATEGORY)

    candidates: list[str] = []
    for record in records:
        normalized_names = {normalize_category_token(name) for name in _record_names(record) if name.strip()}
        if not normalized_names:
            continue
        has_category_match = bool(normalized_tokens & normalized_names)
        has_partial_match = any(token in name or name in token for token in normalized_tokens for name in normalized_names)
        if _gender_mismatches(gender, record):
            if has_category_match or has_partial_match:
                candidates.append(record.category_name)
            continue
        if has_category_match:
            return CategoryMatch(category_id=record.category_id, category_name=record.category_name)
        if has_partial_match:
            candidates.append(record.category_name)

    return CategoryMatch(
        category_name=category_name.strip() or item_type.strip(),
        review_required=True,
        reason=REVIEW_REASON_UNKNOWN_CATEGORY,
        candidates=sorted(set(candidates))[:3],
    )