"""Image URL collection helpers for listing exports."""

from __future__ import annotations

import re
from typing import Iterable, NamedTuple


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
CONDITION_NOTE_LABELS = {
    "状態メモ",
    "状態",
    "コンディション",
    "特記事項",
    "備考",
    "注意点",
}
MEASUREMENT_BLOCK_LABELS = {"採寸", "実寸", "採寸情報"}
MEASUREMENT_ITEM_LABELS = {
    "肩幅",
    "身幅",
    "着丈",
    "袖丈",
    "裄丈",
    "ウエスト",
    "総丈",
    "股上",
    "股下",
    "わたり幅",
    "裾幅",
    "縦",
    "横",
    "マチ",
}
_LABELED_LINE_PATTERN = re.compile(
    r"^\s*(?P<label>[^:：\r\n]{1,30}?)\s*[:：]\s*(?P<value>.*)$"
)


class ProductInfoSummary(NamedTuple):
    measurements: tuple[str, ...]
    condition_notes: tuple[str, ...]

    @property
    def has_measurements(self) -> bool:
        return bool(self.measurements)

    @property
    def has_condition_notes(self) -> bool:
        return bool(self.condition_notes)


def extract_first_number(value: str) -> int:
    """Return the first number in a filename or URL; unnumbered files sort last."""
    filename = value.rsplit("/", maxsplit=1)[-1]
    match = re.search(r"(\d+)", filename)
    return int(match.group(1)) if match else 999999


def collect_sorted_image_urls(blobs: Iterable, bucket_name: str) -> list[str]:
    """Build public GCS image URLs and sort them by the number in their file name."""
    image_urls = [
        f"https://storage.googleapis.com/{bucket_name}/{blob.name}"
        for blob in blobs
        if blob.name.lower().endswith(IMAGE_EXTENSIONS)
    ]
    return sorted(image_urls, key=extract_first_number)


def parse_product_info(text: str) -> ProductInfoSummary:
    """Extract only explicitly labelled measurements and condition notes."""
    measurements: list[str] = []
    condition_notes: list[str] = []
    active_section: str | None = None

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = _LABELED_LINE_PATTERN.match(line)
        if match:
            label = match.group("label").strip()
            value = match.group("value").strip()
            if label in CONDITION_NOTE_LABELS:
                active_section = "condition"
                if value:
                    condition_notes.append(f"{label}: {value}")
            elif label in MEASUREMENT_BLOCK_LABELS:
                active_section = "measurement"
                if value:
                    measurements.append(value)
            elif label in MEASUREMENT_ITEM_LABELS:
                active_section = None
                if value:
                    measurements.append(f"{label}: {value}")
            else:
                active_section = None
            continue

        if active_section == "condition":
            condition_notes.append(line)
        elif active_section == "measurement":
            measurements.append(line)

    return ProductInfoSummary(
        measurements=tuple(dict.fromkeys(measurements)),
        condition_notes=tuple(dict.fromkeys(condition_notes)),
    )


def build_product_info_review_rows(
    product_code: str,
    product_info: ProductInfoSummary,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not product_info.has_measurements:
        rows.append(
            {
                "商品管理コード": product_code,
                "確認項目": "採寸",
                "候補1": "",
                "候補2": "",
                "理由": "採寸情報なし。商品の採寸値を確認して本文を修正してください",
            }
        )
    if not product_info.has_condition_notes:
        rows.append(
            {
                "商品管理コード": product_code,
                "確認項目": "状態メモ",
                "候補1": "",
                "候補2": "",
                "理由": "状態メモなし。商品の状態や特記事項を確認してください",
            }
        )
    return rows
