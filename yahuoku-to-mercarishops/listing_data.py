"""Pure functions for parsing AI output and building platform listing rows.

Keeping CSV-format mapping here makes it easy to review format changes and test the
listing data without Google Cloud credentials.
"""

from dataclasses import dataclass
import csv
from html import unescape
from io import StringIO
import re
from typing import Iterable


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
SUCCESS_FILE_NAME = "_SUCCESS.txt"

MISSING_MEASUREMENT_MARKERS = (
    "〖要確認：採寸情報なし〗",
    "【要確認：採寸情報なし】",
)
DEFAULT_TITLE = "【要修正】商品名"
MERCARI_TITLE_MAX_LENGTH = 130
YAHOO_TITLE_MAX_LENGTH = 65
PROHIBITED_MERCARI_BODY_TERMS = (
    "Yahoo",
    "ヤフオク",
    "オークション",
    "HTML",
    "管理コード",
)
APPEAL_TERMS_REQUIRING_EVIDENCE = ("希少", "限定", "入手困難")
REVIEW_REQUIRED_HEADERS = [
    "review_key",
    "item_id",
    "file_path",
    "platform",
    "field",
    "reason",
    "current_value",
    "suggested_action",
]
CONDITION_NOTE_LABELS = (
    "状態メモ",
    "状態",
    "コンディション",
    "特記事項",
    "備考",
    "注意点",
)

MERCARI_COLUMN_COUNT = 73
MERCARI_HEADERS = [
    *[f"商品画像名_{index}" for index in range(1, 21)],
    "商品名",
    "商品説明",
    "SKU1_種類",
    "SKU1_在庫数",
    "SKU1_商品管理コード",
    "SKU1_JANコード",
    "SKU1_catalog_id",
    "SKU2_種類",
    "SKU2_在庫数",
    "SKU2_商品管理コード",
    "SKU2_JANコード",
    "SKU2_catalog_id",
    "SKU3_種類",
    "SKU3_在庫数",
    "SKU3_商品管理コード",
    "SKU3_JANコード",
    "SKU3_catalog_id",
    "SKU4_種類",
    "SKU4_在庫数",
    "SKU4_商品管理コード",
    "SKU4_JANコード",
    "SKU4_catalog_id",
    "SKU5_種類",
    "SKU5_在庫数",
    "SKU5_商品管理コード",
    "SKU5_JANコード",
    "SKU5_catalog_id",
    "SKU6_種類",
    "SKU6_在庫数",
    "SKU6_商品管理コード",
    "SKU6_JANコード",
    "SKU6_catalog_id",
    "SKU7_種類",
    "SKU7_在庫数",
    "SKU7_商品管理コード",
    "SKU7_JANコード",
    "SKU7_catalog_id",
    "SKU8_種類",
    "SKU8_在庫数",
    "SKU8_商品管理コード",
    "SKU8_JANコード",
    "SKU8_catalog_id",
    "ブランドID",
    "販売価格",
    "カテゴリID",
    "商品の状態",
    "配送方法",
    "発送元の地域",
    "発送までの日数",
    "商品ステータス",
    "配送料の負担",
    "送料ID",
    "メルカリBiz配送_クール区分",
]
MERCARI_IMAGE_START = 0
MERCARI_IMAGE_LIMIT = 20
MERCARI_TITLE = 20
MERCARI_DESCRIPTION = 21
MERCARI_SKU_TYPE = 22
MERCARI_STOCK = 23
MERCARI_SKU_CODE = 24
MERCARI_BRAND_ID = 62
MERCARI_PRICE = 63
MERCARI_CATEGORY_ID = 64
MERCARI_CONDITION = 65
MERCARI_SHIPPING_METHOD = 66
MERCARI_SHIP_FROM = 67
MERCARI_SHIP_DAYS = 68
MERCARI_STATUS = 69
MERCARI_SHIPPING_PAYER = 70

YAHOO_COLUMN_COUNT = 114
YAHOO_CATEGORY_ID = 0
YAHOO_TITLE = 1
YAHOO_DESCRIPTION = 2
YAHOO_START_PRICE = 3
YAHOO_BUY_NOW_PRICE = 4
YAHOO_QUANTITY = 5
YAHOO_DURATION = 6
YAHOO_END_HOUR = 7
YAHOO_IMAGE_START = 9
YAHOO_IMAGE_STEP = 2
YAHOO_IMAGE_LIMIT = 10
YAHOO_PREFECTURE = 29
YAHOO_SHIPPING_PAYER = 31
YAHOO_PAYMENT_TIMING = 32
YAHOO_EASY_PAYMENT = 33
YAHOO_EASY_TRANSACTION = 34
YAHOO_CASH_ON_DELIVERY = 35
YAHOO_CONDITION = 36
YAHOO_RETURNS = 38
YAHOO_BIDDER_RATING_LIMIT = 40
YAHOO_NEGATIVE_RATING_LIMIT = 41
YAHOO_BIDDER_VERIFICATION = 42
YAHOO_AUTO_EXTENSION = 43
YAHOO_EARLY_END = 44
YAHOO_PRICE_NEGOTIATION = 45
YAHOO_AUTO_RELIST = 46
YAHOO_AUTO_DISCOUNT = 47
YAHOO_FIXED_SHIPPING = 51
YAHOO_NEKO_TAKKYUBIN = 56
YAHOO_SHIP_DAYS = 61
YAHOO_POST_RECEIPT_PAYMENT = 112
YAHOO_OVERSEAS_SHIPPING = 113


@dataclass(frozen=True)
class ReviewIssue:
    platform: str
    field: str
    reason: str
    current_value: str = ""
    suggested_action: str = ""


@dataclass(frozen=True)
class ParsedDescription:
    title: str
    description: str
    review_issues: list[ReviewIssue]


def extract_first_number(value: str) -> int:
    """Return the first number in a filename or URL; unnumbered files sort last."""
    filename = value.rsplit("/", maxsplit=1)[-1]
    match = re.search(r"(\d+)", filename)
    return int(match.group(1)) if match else 999999


def collect_sorted_image_urls(blobs: Iterable, bucket_name: str) -> list[str]:
    """Build public GCS image URLs and sort them by the number in their file name.

    TODO: This intentionally relies on a public bucket. Switch to an approved
    delivery mechanism (such as signed URLs) if the bucket becomes private.
    """
    image_urls = [
        f"https://storage.googleapis.com/{bucket_name}/{blob.name}"
        for blob in blobs
        if blob.name.lower().endswith(IMAGE_EXTENSIONS)
    ]
    return sorted(image_urls, key=extract_first_number)


def strip_markdown_code_fences(text: str) -> str:
    """Remove Markdown fence lines while preserving the content inside them."""
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("```")
    ).strip()


def normalize_blank_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    normalized = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", normalized)


def remove_html_tags(text: str) -> str:
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    return normalize_blank_lines(unescape(text))


def _find_heading(
    lines: list[str],
    start_index: int,
    heading_pattern: re.Pattern,
) -> tuple[int, str] | None:
    for index in range(start_index, len(lines)):
        line = lines[index].strip()
        match = heading_pattern.match(line)
        if match:
            return index, (match.group("inline") or "").strip()
    return None


def _section_text(lines: list[str], start: int, end: int | None) -> str:
    section_lines = lines[start:end] if end is not None else lines[start:]
    return normalize_blank_lines("\n".join(section_lines))


def parse_yahoo_description(text: str) -> ParsedDescription:
    """Parse _description.txt text even when the AI adds prefaces or warnings."""
    cleaned = strip_markdown_code_fences(text)
    lines = cleaned.splitlines()
    review_issues: list[ReviewIssue] = []

    if any(marker in cleaned for marker in MISSING_MEASUREMENT_MARKERS):
        review_issues.append(
            ReviewIssue(
                "all",
                "measurements",
                "採寸情報なし",
                "",
                "商品の縦・横・マチ等を確認して本文を修正してください",
            )
        )

    title_pattern = re.compile(r"^\s*タイトル\s*[:：]\s*(?P<inline>.*)$")
    description_pattern = re.compile(
        r"^\s*説明文(?:（HTML）)?\s*[:：]\s*(?P<inline>.*)$"
    )
    title_heading = _find_heading(lines, 0, title_pattern)
    description_heading = (
        _find_heading(lines, title_heading[0] + 1, description_pattern)
        if title_heading
        else _find_heading(lines, 0, description_pattern)
    )

    if title_heading and description_heading:
        title_start = title_heading[0] + 1
        title = normalize_blank_lines(
            "\n".join(
                [title_heading[1], _section_text(lines, title_start, description_heading[0])]
            )
        )
        description = normalize_blank_lines(
            "\n".join(
                [
                    description_heading[1],
                    _section_text(lines, description_heading[0] + 1, None),
                ]
            )
        )
    else:
        title = ""
        description = cleaned

    if not title:
        title = DEFAULT_TITLE
        review_issues.append(
            ReviewIssue(
                "yahoo",
                "title",
                "商品名を抽出できないため確認が必要",
                "",
                "商品名を確認して修正してください",
            )
        )
    if not description:
        description = cleaned
        review_issues.append(
            ReviewIssue(
                "yahoo",
                "description",
                "商品説明を抽出できないため確認が必要",
                "",
                "商品説明を確認して修正してください",
            )
        )

    return ParsedDescription(title=title, description=description, review_issues=review_issues)


def parse_mercari_description(text: str) -> ParsedDescription:
    """Parse Mercari conversion output and force its body to plain text."""
    cleaned = strip_markdown_code_fences(text)
    lines = cleaned.splitlines()
    review_issues: list[ReviewIssue] = []

    title_pattern = re.compile(
        r"^\s*(?:\[TITLE\]|TITLE|商品名)\s*[:：]?\s*(?P<inline>.*)$",
        re.IGNORECASE,
    )
    body_pattern = re.compile(
        r"^\s*(?:\[BODY\]|BODY|商品説明)\s*[:：]?\s*(?P<inline>.*)$",
        re.IGNORECASE,
    )
    title_heading = _find_heading(lines, 0, title_pattern)
    body_heading = (
        _find_heading(lines, title_heading[0] + 1, body_pattern)
        if title_heading
        else _find_heading(lines, 0, body_pattern)
    )

    if title_heading and body_heading:
        title = normalize_blank_lines(
            "\n".join(
                [
                    title_heading[1],
                    _section_text(lines, title_heading[0] + 1, body_heading[0]),
                ]
            )
        )
        body = normalize_blank_lines(
            "\n".join(
                [
                    body_heading[1],
                    _section_text(lines, body_heading[0] + 1, None),
                ]
            )
        )
    else:
        title = ""
        body = cleaned

    if not title:
        title = DEFAULT_TITLE
        review_issues.append(
            ReviewIssue(
                "mercari",
                "title",
                "商品名を抽出できないため確認が必要",
                "",
                "商品名を確認して修正してください",
            )
        )
    if re.search(r"(?s)<[^>]+>", body):
        review_issues.append(
            ReviewIssue(
                "mercari",
                "description",
                "Mercari本文にHTMLタグが含まれている可能性あり",
                body,
                "HTMLタグが残っていないか確認してください",
            )
        )
    body = remove_html_tags(body)

    filtered_lines = []
    removed_terms = set()
    for line in body.splitlines():
        matched_terms = [term for term in PROHIBITED_MERCARI_BODY_TERMS if term in line]
        if matched_terms:
            removed_terms.update(matched_terms)
            continue
        filtered_lines.append(line)
    if removed_terms:
        review_issues.append(
            ReviewIssue(
                "mercari",
                "description",
                "Mercari本文にYahoo向け文言が含まれている可能性あり",
                ", ".join(sorted(removed_terms)),
                "Mercari Shops向けの表現に直してください",
            )
        )
    body = normalize_blank_lines("\n".join(filtered_lines))

    return ParsedDescription(title=title, description=body, review_issues=review_issues)


def shorten_title(title: str, max_length: int) -> tuple[str, bool]:
    """Shorten titles by preserving leading meaningful tokens where possible."""
    title = normalize_blank_lines(title).replace("\n", " ")
    if len(title) <= max_length:
        return title, False

    tokens = title.split()
    if not tokens:
        return title[:max_length], True

    shortened_tokens: list[str] = []
    for token in tokens:
        candidate = " ".join([*shortened_tokens, token])
        if len(candidate) > max_length:
            break
        shortened_tokens.append(token)
    if shortened_tokens:
        return " ".join(shortened_tokens), True
    return title[:max_length], True


def analyze_success_text(success_text: str) -> list[ReviewIssue]:
    """Find missing human-provided product information in _SUCCESS.txt."""
    issues: list[ReviewIssue] = []
    normalized = normalize_blank_lines(success_text)

    has_measurement = bool(re.search(r"\d+(?:\.\d+)?\s*(?:cm|ｍ|mm|㎝)", normalized, re.IGNORECASE))
    if not has_measurement:
        issues.append(
            ReviewIssue(
                "all",
                "measurements",
                "採寸情報なし",
                "",
                "商品の縦・横・マチ等を確認して本文を修正してください",
            )
        )

    condition_pattern = re.compile(
        rf"^[^\S\r\n]*(?:{'|'.join(map(re.escape, CONDITION_NOTE_LABELS))})"
        r"[^\S\r\n]*[:：][^\S\r\n]*(.*)$",
        re.MULTILINE,
    )
    has_condition_note = any(
        match.group(1).strip() for match in condition_pattern.finditer(normalized)
    )
    if not has_condition_note:
        issues.append(
            ReviewIssue(
                "all",
                "condition_note",
                "状態メモなし",
                "",
                "傷や汚れ、使用感の有無を確認してください",
            )
        )
    return issues


def detect_appeal_terms_without_evidence(
    text: str,
    success_text: str,
) -> list[ReviewIssue]:
    """Flag strong appeal terms when the source information does not mention them."""
    issues: list[ReviewIssue] = []
    for term in APPEAL_TERMS_REQUIRING_EVIDENCE:
        if term in text and term not in success_text:
            issues.append(
                ReviewIssue(
                    "all",
                    "appeal",
                    f"訴求表現の根拠確認が必要: {term}",
                    term,
                    "_SUCCESS.txtの根拠を確認し、必要に応じて表現を修正してください",
                )
            )
    return issues


def build_mercari_row(
    image_urls: list[str], item_manage_code: str, title: str, description: str
) -> list[str]:
    """Build the unchanged 73-column Mercari Shops import row."""
    row = [""] * MERCARI_COLUMN_COUNT
    for index, image_url in enumerate(image_urls[:MERCARI_IMAGE_LIMIT]):
        row[MERCARI_IMAGE_START + index] = image_url

    row[MERCARI_TITLE] = title
    row[MERCARI_DESCRIPTION] = description
    row[MERCARI_SKU_TYPE] = "one size"
    row[MERCARI_STOCK] = "1"
    row[MERCARI_SKU_CODE] = item_manage_code
    row[MERCARI_BRAND_ID] = ""
    row[MERCARI_PRICE] = "50000"
    row[MERCARI_CATEGORY_ID] = ""
    row[MERCARI_CONDITION] = "3"
    row[MERCARI_SHIPPING_METHOD] = "3"
    row[MERCARI_SHIP_FROM] = "jp34"
    row[MERCARI_SHIP_DAYS] = "2"
    row[MERCARI_STATUS] = "1"
    row[MERCARI_SHIPPING_PAYER] = "1"
    return row


def build_yahoo_row(
    image_urls: list[str], item_manage_code: str, title: str, description: str
) -> list[str]:
    """Build the unchanged 114-column Yahoo Auctions / AuctionTown import row."""
    row = [""] * YAHOO_COLUMN_COUNT
    row[YAHOO_CATEGORY_ID] = "【要修正】カテゴリID"
    row[YAHOO_TITLE] = title
    row[YAHOO_DESCRIPTION] = description.replace("\n", "<br>")
    row[YAHOO_START_PRICE] = "49999"
    row[YAHOO_BUY_NOW_PRICE] = "50000"
    row[YAHOO_QUANTITY] = "1"
    row[YAHOO_DURATION] = "3"
    row[YAHOO_END_HOUR] = "22"

    for index, image_url in enumerate(image_urls[:YAHOO_IMAGE_LIMIT]):
        row[YAHOO_IMAGE_START + index * YAHOO_IMAGE_STEP] = image_url

    defaults = {
        YAHOO_PREFECTURE: "広島県",
        YAHOO_SHIPPING_PAYER: "出品者",
        YAHOO_PAYMENT_TIMING: "先払い",
        YAHOO_EASY_PAYMENT: "はい",
        YAHOO_EASY_TRANSACTION: "はい",
        YAHOO_CASH_ON_DELIVERY: "いいえ",
        YAHOO_CONDITION: "目立った傷や汚れなし",
        YAHOO_RETURNS: "返品不可",
        YAHOO_BIDDER_RATING_LIMIT: "はい",
        YAHOO_NEGATIVE_RATING_LIMIT: "はい",
        YAHOO_BIDDER_VERIFICATION: "いいえ",
        YAHOO_AUTO_EXTENSION: "はい",
        YAHOO_EARLY_END: "いいえ",
        YAHOO_PRICE_NEGOTIATION: "いいえ",
        YAHOO_AUTO_RELIST: "0",
        YAHOO_AUTO_DISCOUNT: "いいえ",
        YAHOO_FIXED_SHIPPING: "はい",
        YAHOO_NEKO_TAKKYUBIN: "はい",
        YAHOO_SHIP_DAYS: "2日～3日",
        YAHOO_POST_RECEIPT_PAYMENT: "いいえ",
        YAHOO_OVERSEAS_SHIPPING: "いいえ",
    }
    for column, value in defaults.items():
        row[column] = value
    return row


def add_default_review_issues(issues: list[ReviewIssue]) -> list[ReviewIssue]:
    return [
        *issues,
        ReviewIssue(
            "mercari",
            "brand_id",
            "ブランド不明のためデフォルト値を使用",
            "",
            "ブランドIDを確認してください",
        ),
        ReviewIssue(
            "mercari",
            "category_id",
            "カテゴリ不明のため確認が必要",
            "",
            "カテゴリIDを確認してください",
        ),
        ReviewIssue(
            "yahoo",
            "category_id",
            "カテゴリ不明のため確認が必要",
            "【要修正】カテゴリID",
            "カテゴリIDを確認してください",
        ),
    ]


def build_review_rows(
    item_manage_code: str,
    file_path: str,
    issues: list[ReviewIssue],
) -> list[list[str]]:
    rows = []
    seen = set()
    for issue in issues:
        review_key = "|".join(
            [
                item_manage_code,
                file_path,
                issue.platform,
                issue.field,
                issue.reason,
            ]
        )
        key = (
            review_key,
            issue.platform,
            issue.field,
            issue.reason,
            issue.current_value,
            issue.suggested_action,
        )
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            [
                review_key,
                item_manage_code,
                file_path,
                issue.platform,
                issue.field,
                issue.reason,
                issue.current_value,
                issue.suggested_action,
            ]
        )
    return rows


def aggregate_review_required_csv_texts(csv_texts: Iterable[str]) -> str:
    """Combine per-item review CSV texts into one de-duplicated CSV text."""
    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(REVIEW_REQUIRED_HEADERS)

    seen_review_keys = set()
    for csv_text in csv_texts:
        if not csv_text.strip():
            continue
        reader = csv.DictReader(StringIO(csv_text))
        if not reader.fieldnames:
            continue
        for row in reader:
            review_key = row.get("review_key") or "|".join(
                [
                    row.get("item_id", ""),
                    row.get("file_path", ""),
                    row.get("platform", ""),
                    row.get("field", ""),
                    row.get("reason", ""),
                ]
            )
            if not review_key or review_key in seen_review_keys:
                continue
            seen_review_keys.add(review_key)
            writer.writerow(
                [
                    review_key,
                    row.get("item_id", ""),
                    row.get("file_path", ""),
                    row.get("platform", ""),
                    row.get("field", ""),
                    row.get("reason", ""),
                    row.get("current_value", ""),
                    row.get("suggested_action", ""),
                ]
            )
    return output.getvalue()
