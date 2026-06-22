"""Pure functions for building platform-specific listing rows.

Keeping CSV-format mapping here makes it easy to review format changes and test the
listing data without Google Cloud credentials.
"""

import re
from typing import Iterable


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

MERCARI_COLUMN_COUNT = 73
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


def build_mercari_row(
    image_urls: list[str], item_manage_code: str, description: str
) -> list[str]:
    """Build the unchanged 73-column Mercari Shops import row."""
    row = [""] * MERCARI_COLUMN_COUNT
    for index, image_url in enumerate(image_urls[:MERCARI_IMAGE_LIMIT]):
        row[MERCARI_IMAGE_START + index] = image_url

    row[MERCARI_TITLE] = "【要修正】商品名"
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
    image_urls: list[str], item_manage_code: str, description: str
) -> list[str]:
    """Build the unchanged 114-column Yahoo Auctions / AuctionTown import row."""
    row = [""] * YAHOO_COLUMN_COUNT
    row[YAHOO_CATEGORY_ID] = "【要修正】カテゴリID"
    row[YAHOO_TITLE] = f"【要修正】商品名 (管理コード: {item_manage_code})"
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
