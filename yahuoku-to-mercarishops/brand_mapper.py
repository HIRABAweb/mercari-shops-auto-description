"""Brand name to brand ID mapping."""

from __future__ import annotations

from dataclasses import dataclass, field


REVIEW_REASON_NO_BRAND = "ブランド名を判定できません。"
REVIEW_REASON_UNKNOWN_BRAND = "ブランドマスタに一致するブランドがありません。"

DEFAULT_ALIAS_GROUPS: dict[str, set[str]] = {
    "Dolce&Gabbana": {"dolce&gabbana", "dolce and gabbana", "d&g", "ドルガバ", "ドルチェ&ガッバーナ"},
}


@dataclass(frozen=True)
class BrandRecord:
    brand_id: str
    brand_name: str
    aliases: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class BrandMatch:
    brand_id: str = ""
    brand_name: str = ""
    review_required: bool = False
    reason: str = ""
    candidates: list[str] = field(default_factory=list)


def normalize_brand_name(value: str) -> str:
    return value.strip().casefold().replace(" ", "")


def build_brand_records(rows: list[dict[str, str]]) -> list[BrandRecord]:
    records: list[BrandRecord] = []
    for row in rows:
        brand_id = (row.get("brand_id") or row.get("ブランドID") or "").strip()
        brand_name = (row.get("brand_name") or row.get("ブランド名") or "").strip()
        aliases_text = (row.get("aliases") or row.get("別名") or "").strip()
        aliases = {part.strip() for part in aliases_text.replace("|", ",").split(",") if part.strip()}
        aliases.update(
            value.strip()
            for value in [row.get("ブランド名（カナ）", ""), row.get("ブランド名（英語）", "")]
            if value.strip()
        )
        aliases.update(DEFAULT_ALIAS_GROUPS.get(brand_name, set()))
        if brand_id and brand_name:
            records.append(BrandRecord(brand_id=brand_id, brand_name=brand_name, aliases=aliases))
    return records


def resolve_brand(brand_name: str, records: list[BrandRecord]) -> BrandMatch:
    if not brand_name.strip():
        return BrandMatch(review_required=True, reason=REVIEW_REASON_NO_BRAND)

    target = normalize_brand_name(brand_name)
    candidates: list[str] = []
    for record in records:
        names = {record.brand_name, *record.aliases}
        normalized_names = {normalize_brand_name(name) for name in names if name.strip()}
        if target in normalized_names:
            return BrandMatch(brand_id=record.brand_id, brand_name=record.brand_name)
        if any(target in name or name in target for name in normalized_names if name):
            candidates.append(record.brand_name)

    return BrandMatch(
        brand_name=brand_name.strip(),
        review_required=True,
        reason=REVIEW_REASON_UNKNOWN_BRAND,
        candidates=sorted(set(candidates))[:3],
    )