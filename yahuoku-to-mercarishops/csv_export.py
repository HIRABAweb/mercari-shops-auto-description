"""CSV export builders for Mercari Shops and Yahoo Auctions."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from ai_service import ProductAttributes
from brand_mapper import BrandMatch
from category_mapper import CategoryMatch


MERCARI_CSV_FILE_NAME = "mercari.csv"
YAHOO_CSV_FILE_NAME = "yahoo.csv"
REVIEW_REQUIRED_CSV_FILE_NAME = "review_required.csv"
RESULT_JSON_FILE_NAME = "result.json"
DONE_FILE_NAME = "_DONE.txt"

MERCARI_IMAGE_LIMIT = 20
YAHOO_IMAGE_LIMIT = 10
MERCARI_TEMPLATE_PATH = Path(__file__).resolve().parent / "resources" / "mercari" / "product_import_template_sample.csv"

FALLBACK_MERCARI_HEADERS = [
    *[f"商品画像名_{index}" for index in range(1, MERCARI_IMAGE_LIMIT + 1)],
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
    "SKU9_種類",
    "SKU9_在庫数",
    "SKU9_商品管理コード",
    "SKU9_JANコード",
    "SKU9_catalog_id",
    "SKU10_種類",
    "SKU10_在庫数",
    "SKU10_商品管理コード",
    "SKU10_JANコード",
    "SKU10_catalog_id",
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
    "発売日",
    "予約受付開始日",
    "予約受付終了日",
    "キャンセル期限",
    "お届け予定",
]

YAHOO_HEADERS = [
    "カテゴリID",
    "タイトル",
    "説明",
    "開始価格",
    "即決価格",
    "個数",
    "開催期間",
    "終了時間",
    *[f"画像{i}" for i in range(1, YAHOO_IMAGE_LIMIT + 1)],
    "商品発送元の都道府県",
    "送料負担",
    "代金支払い",
    "Yahoo!かんたん決済",
    "かんたん取引",
    "商品代引",
    "商品の状態",
    "返品の可否",
    "入札者評価制限",
    "悪い評価の割合での制限",
    "入札者認証制限",
    "自動延長",
    "早期終了",
    "値下げ交渉",
    "自動再出品",
    "自動値下げ",
    "送料固定",
    "ネコ宅急便",
    "発送までの日数",
    "受け取り後決済サービス",
    "海外発送",
]

REVIEW_REQUIRED_HEADERS = ["商品管理コード", "確認項目", "候補1", "候補2", "理由"]

MERCARI_TITLE_HEADER = "商品名"
MERCARI_DESCRIPTION_HEADER = "商品説明"
MERCARI_PRODUCT_CODE_HEADER = "SKU1_商品管理コード"
MERCARI_STOCK_HEADER = "SKU1_在庫数"
MERCARI_PRICE_HEADER = "販売価格"
MERCARI_CATEGORY_HEADER = "カテゴリID"
MERCARI_CONDITION_HEADER = "商品の状態"
MERCARI_SHIPPING_METHOD_HEADER = "配送方法"
MERCARI_SHIP_FROM_HEADER = "発送元の地域"
MERCARI_SHIP_DAYS_HEADER = "発送までの日数"
MERCARI_STATUS_HEADER = "商品ステータス"
MERCARI_SHIPPING_PAYER_HEADER = "配送料の負担"
MERCARI_SHIPPING_FEE_HEADER = "送料ID"
MERCARI_BIZ_COOL_HEADER = "メルカリBiz配送_クール区分"


@dataclass(frozen=True)
class MercariValidationIssue:
    product_code: str
    field: str
    message: str

    def display_message(self) -> str:
        code = self.product_code or "商品管理コードなし"
        return f"{code} / {self.field}: {self.message}"


def load_csv_headers(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        return next(csv.reader(csv_file))


def validate_mercari_headers(headers: list[str]) -> None:
    required_headers = {
        "商品画像名_1",
        "商品名",
        "商品説明",
        "SKU1_種類",
        "SKU1_在庫数",
        "SKU1_商品管理コード",
        "ブランドID",
        "販売価格",
        "カテゴリID",
        "商品の状態",
        "配送方法",
        "発送元の地域",
        "発送までの日数",
        "商品ステータス",
        "配送料の負担",
    }
    missing_headers = sorted(required_headers - set(headers))
    if len(headers) != len(FALLBACK_MERCARI_HEADERS) or missing_headers:
        raise RuntimeError(
            "Mercari Shops公式CSVテンプレートの列が想定と一致しません。"
            f" columns={len(headers)} missing={missing_headers}"
        )


def load_mercari_headers(path: Path) -> list[str]:
    try:
        headers = load_csv_headers(path)
    except (FileNotFoundError, StopIteration, OSError) as error:
        raise RuntimeError(f"Mercari Shops公式CSVテンプレートを読み込めません: {path}") from error
    validate_mercari_headers(headers)
    return headers


MERCARI_HEADERS = load_mercari_headers(MERCARI_TEMPLATE_PATH)


@dataclass(frozen=True)
class ListingDefaults:
    mercari_stock: str = "1"
    mercari_price: str = "50000"
    mercari_condition: str = "3"
    mercari_shipping_method: str = "3"
    mercari_ship_from: str = "jp34"
    mercari_ship_days: str = "2"
    mercari_status: str = "1"
    mercari_shipping_payer: str = "1"
    yahoo_start_price: str = "49999"
    yahoo_buy_now_price: str = "50000"
    yahoo_quantity: str = "1"
    yahoo_duration: str = "3"
    yahoo_end_hour: str = "22"
    yahoo_prefecture: str = "広島県"
    yahoo_condition: str = "目立った傷や汚れなし"


@dataclass(frozen=True)
class ExportRows:
    mercari_row: dict[str, str]
    yahoo_row: dict[str, str]
    review_rows: list[dict[str, str]] = field(default_factory=list)


def empty_row(headers: list[str]) -> dict[str, str]:
    return {header: "" for header in headers}


def build_mercari_row(
    *,
    image_urls: list[str],
    product_code: str,
    title: str,
    description: str,
    size: str,
    brand_match: BrandMatch,
    category_match: CategoryMatch,
    defaults: ListingDefaults = ListingDefaults(),
) -> dict[str, str]:
    row = empty_row(MERCARI_HEADERS)
    for index, image_url in enumerate(image_urls[:MERCARI_IMAGE_LIMIT], start=1):
        row[f"商品画像名_{index}"] = image_url
    row["商品名"] = title
    row["商品説明"] = description
    row["SKU1_種類"] = size or "フリーサイズ"
    row["SKU1_在庫数"] = defaults.mercari_stock
    row["SKU1_商品管理コード"] = product_code
    row["ブランドID"] = brand_match.brand_id
    row["販売価格"] = defaults.mercari_price
    row["カテゴリID"] = category_match.category_id
    row["商品の状態"] = defaults.mercari_condition
    row["配送方法"] = defaults.mercari_shipping_method
    row["発送元の地域"] = defaults.mercari_ship_from
    row["発送までの日数"] = defaults.mercari_ship_days
    row["商品ステータス"] = defaults.mercari_status
    row["配送料の負担"] = defaults.mercari_shipping_payer
    return row


def build_yahoo_row_by_name(
    *,
    image_urls: list[str],
    product_code: str,
    title: str,
    description: str,
    category_match: CategoryMatch,
    defaults: ListingDefaults = ListingDefaults(),
) -> dict[str, str]:
    row = empty_row(YAHOO_HEADERS)
    row["カテゴリID"] = category_match.category_id
    row["タイトル"] = f"{title} (管理コード: {product_code})"
    row["説明"] = description.replace("\n", "<br>")
    row["開始価格"] = defaults.yahoo_start_price
    row["即決価格"] = defaults.yahoo_buy_now_price
    row["個数"] = defaults.yahoo_quantity
    row["開催期間"] = defaults.yahoo_duration
    row["終了時間"] = defaults.yahoo_end_hour
    for index, image_url in enumerate(image_urls[:YAHOO_IMAGE_LIMIT], start=1):
        row[f"画像{index}"] = image_url
    row["商品発送元の都道府県"] = defaults.yahoo_prefecture
    row["送料負担"] = "出品者"
    row["代金支払い"] = "先払い"
    row["Yahoo!かんたん決済"] = "はい"
    row["かんたん取引"] = "はい"
    row["商品代引"] = "いいえ"
    row["商品の状態"] = defaults.yahoo_condition
    row["返品の可否"] = "返品不可"
    row["入札者評価制限"] = "はい"
    row["悪い評価の割合での制限"] = "はい"
    row["入札者認証制限"] = "いいえ"
    row["自動延長"] = "はい"
    row["早期終了"] = "いいえ"
    row["値下げ交渉"] = "いいえ"
    row["自動再出品"] = "0"
    row["自動値下げ"] = "いいえ"
    row["送料固定"] = "はい"
    row["ネコ宅急便"] = "はい"
    row["発送までの日数"] = "2日～3日"
    row["受け取り後決済サービス"] = "いいえ"
    row["海外発送"] = "いいえ"
    return row


def build_review_rows(
    product_code: str,
    brand_match: BrandMatch,
    category_match: CategoryMatch,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if brand_match.review_required:
        rows.append(
            {
                "商品管理コード": product_code,
                "確認項目": "ブランドID",
                "候補1": brand_match.candidates[0] if brand_match.candidates else brand_match.brand_name,
                "候補2": brand_match.candidates[1] if len(brand_match.candidates) > 1 else "",
                "理由": brand_match.reason,
            }
        )
    if category_match.review_required:
        rows.append(
            {
                "商品管理コード": product_code,
                "確認項目": "カテゴリID",
                "候補1": category_match.candidates[0] if category_match.candidates else category_match.category_name,
                "候補2": category_match.candidates[1] if len(category_match.candidates) > 1 else "",
                "理由": category_match.reason,
            }
        )
    return rows


def build_export_rows(
    *,
    image_urls: list[str],
    product_code: str,
    title: str,
    description: str,
    attributes: ProductAttributes,
    brand_match: BrandMatch,
    category_match: CategoryMatch,
    defaults: ListingDefaults = ListingDefaults(),
) -> ExportRows:
    return ExportRows(
        mercari_row=build_mercari_row(
            image_urls=image_urls,
            product_code=product_code,
            title=title,
            description=description,
            size=attributes.size,
            brand_match=brand_match,
            category_match=category_match,
            defaults=defaults,
        ),
        yahoo_row=build_yahoo_row_by_name(
            image_urls=image_urls,
            product_code=product_code,
            title=title,
            description=description,
            category_match=category_match,
            defaults=defaults,
        ),
        review_rows=build_review_rows(product_code, brand_match, category_match),
    )


def build_csv_text(headers: list[str], rows: list[dict[str, str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


def build_mercari_csv_bytes(rows: list[dict[str, str]]) -> bytes:
    """Build a Mercari Shops upload CSV using the official UTF-8 BOM format."""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=MERCARI_HEADERS,
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def validate_mercari_upload_rows(
    rows: list[dict[str, str]],
) -> list[MercariValidationIssue]:
    issues: list[MercariValidationIssue] = []
    for row_number, row in enumerate(rows, start=1):
        product_code = _clean(row.get(MERCARI_PRODUCT_CODE_HEADER))
        item_label = product_code or f"row-{row_number}"

        _require_image(row, item_label, issues)
        _validate_text(
            row,
            item_label,
            MERCARI_TITLE_HEADER,
            issues,
            required=True,
            max_length=130,
        )
        _validate_text(
            row,
            item_label,
            MERCARI_DESCRIPTION_HEADER,
            issues,
            max_length=3000,
        )
        _validate_product_code(product_code, item_label, issues)
        _validate_integer(
            row,
            item_label,
            MERCARI_STOCK_HEADER,
            issues,
            minimum=0,
            required=True,
        )
        _validate_integer(
            row,
            item_label,
            MERCARI_PRICE_HEADER,
            issues,
            minimum=300,
            maximum=9_999_999,
            required=True,
        )
        _validate_text(
            row,
            item_label,
            MERCARI_CATEGORY_HEADER,
            issues,
            required=True,
        )
        _validate_choice(
            row,
            item_label,
            MERCARI_CONDITION_HEADER,
            issues,
            set("123456"),
        )
        _validate_choice(
            row,
            item_label,
            MERCARI_SHIPPING_METHOD_HEADER,
            issues,
            set("123456"),
        )
        _validate_pattern(
            row,
            item_label,
            MERCARI_SHIP_FROM_HEADER,
            issues,
            r"jp(?:0[1-9]|[1-3][0-9]|4[0-7])",
            "jp01～jp47の地域コードを指定してください",
        )
        _validate_choice(
            row,
            item_label,
            MERCARI_SHIP_DAYS_HEADER,
            issues,
            set("12345"),
        )
        _validate_choice(
            row,
            item_label,
            MERCARI_STATUS_HEADER,
            issues,
            set("12"),
        )
        _validate_choice(
            row,
            item_label,
            MERCARI_SHIPPING_PAYER_HEADER,
            issues,
            set("12"),
        )

        if _clean(row.get(MERCARI_SHIPPING_PAYER_HEADER)) == "2":
            _validate_text(
                row,
                item_label,
                MERCARI_SHIPPING_FEE_HEADER,
                issues,
                required=True,
            )
        if _clean(row.get(MERCARI_SHIPPING_METHOD_HEADER)) == "6":
            _validate_choice(
                row,
                item_label,
                MERCARI_BIZ_COOL_HEADER,
                issues,
                set("123"),
            )

        for header in MERCARI_HEADERS:
            if header in {MERCARI_TITLE_HEADER, MERCARI_DESCRIPTION_HEADER}:
                continue
            if " " in str(row.get(header, "")):
                issues.append(
                    MercariValidationIssue(
                        item_label,
                        header,
                        "半角スペースを削除してください",
                    )
                )
    return issues


def _clean(value: object) -> str:
    return str(value or "").strip()


def _require_image(
    row: dict[str, str],
    product_code: str,
    issues: list[MercariValidationIssue],
) -> None:
    first_image = _clean(row.get("商品画像名_1"))
    if not first_image:
        issues.append(
            MercariValidationIssue(
                product_code,
                "商品画像名_1",
                "商品画像を1枚以上指定してください",
            )
        )


def _validate_text(
    row: dict[str, str],
    product_code: str,
    field_name: str,
    issues: list[MercariValidationIssue],
    *,
    required: bool = False,
    max_length: int | None = None,
) -> None:
    value = _clean(row.get(field_name))
    if required and not value:
        issues.append(MercariValidationIssue(product_code, field_name, "入力が必要です"))
        return
    if max_length is not None and len(value) > max_length:
        issues.append(
            MercariValidationIssue(
                product_code,
                field_name,
                f"{max_length}文字以内にしてください（現在{len(value)}文字）",
            )
        )


def _validate_product_code(
    value: str,
    product_code: str,
    issues: list[MercariValidationIssue],
) -> None:
    if not value:
        return
    if len(value) > 50 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        issues.append(
            MercariValidationIssue(
                product_code,
                MERCARI_PRODUCT_CODE_HEADER,
                "50文字以内の半角英数字・ハイフン・アンダーバーで入力してください",
            )
        )


def _validate_integer(
    row: dict[str, str],
    product_code: str,
    field_name: str,
    issues: list[MercariValidationIssue],
    *,
    minimum: int,
    maximum: int | None = None,
    required: bool,
) -> None:
    value = _clean(row.get(field_name))
    if not value:
        if required:
            issues.append(MercariValidationIssue(product_code, field_name, "入力が必要です"))
        return
    if not value.isascii() or not value.isdigit():
        issues.append(MercariValidationIssue(product_code, field_name, "半角数字で入力してください"))
        return
    number = int(value)
    if number < minimum or (maximum is not None and number > maximum):
        if maximum is None:
            message = f"{minimum}以上で入力してください"
        else:
            message = f"{minimum}～{maximum}の範囲で入力してください"
        issues.append(MercariValidationIssue(product_code, field_name, message))


def _validate_choice(
    row: dict[str, str],
    product_code: str,
    field_name: str,
    issues: list[MercariValidationIssue],
    choices: set[str],
) -> None:
    value = _clean(row.get(field_name))
    if value not in choices:
        issues.append(
            MercariValidationIssue(
                product_code,
                field_name,
                f"{', '.join(sorted(choices))}のいずれかを指定してください",
            )
        )


def _validate_pattern(
    row: dict[str, str],
    product_code: str,
    field_name: str,
    issues: list[MercariValidationIssue],
    pattern: str,
    message: str,
) -> None:
    value = _clean(row.get(field_name))
    if not re.fullmatch(pattern, value):
        issues.append(MercariValidationIssue(product_code, field_name, message))
