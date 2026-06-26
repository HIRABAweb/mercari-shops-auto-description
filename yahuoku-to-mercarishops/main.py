"""Cloud Storage event handler for Mercari Shops and Yahoo Auctions listing data."""

import json
import os
import re
from dataclasses import dataclass

import functions_framework
import google.auth
import google.generativeai as genai
import gspread
from google.api_core.exceptions import PreconditionFailed
from google.cloud import secretmanager, storage

from listing_data import (
    MERCARI_COLUMN_COUNT,
    YAHOO_COLUMN_COUNT,
    build_mercari_row,
    build_yahoo_row,
    collect_sorted_image_urls,
)

# Deployment settings. Values are intentionally not committed to this repository.
PROJECT_ID = ""
SECRET_NAME = ""
SPREADSHEET_ID = ""
SHEET_NAME_MERCARI = "Mercari_List"
SHEET_NAME_YAHOO = "Yahoo_List"
PROMPT_BUCKET_NAME = ""
PROMPT_FILE_NAME = ".txt"
MODEL_NAME = "gemini-2.5-flash-lite"

DESCRIPTION_FILE_NAME = "_description.txt"
PROCESSED_FILE_NAME = "_processed.txt"
PROCESSING_LOCK_FILE_NAME = "_processing.lock"
MERCARI_APPEND_TABLE_RANGE = "A1:BU"
YAHOO_APPEND_TABLE_RANGE = "A1:DJ"
JSON_OUTPUT_INSTRUCTION = """

出力は必ず次のJSON形式だけにしてください。
Markdownコードフェンスや説明文は付けないでください。

{
  "title": "商品タイトル",
  "description": "商品説明本文"
}

titleは「状態、ブランド、アイテム名、素材、色、柄、サイズ」の順で、値がない項目は省略してください。
titleには「タイトル」「商品名」「説明文」などの見出しを含めず、同じ単語を重複させず、各プラットフォームの上限文字数を超えないようにしてください。
descriptionには商品説明本文だけを入れ、「タイトル：」「商品名：」「説明文：」などの見出しを含めないでください。
"""
JSON_CODE_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$",
    re.IGNORECASE | re.DOTALL,
)
DESCRIPTION_HEADING_PATTERN = re.compile(
    r"(?m)^\s*(?:タイトル|商品名|説明文)\s*[:：]\s*"
)
TITLE_HEADING_PATTERN = re.compile(
    r"(?m)^\s*(?:タイトル|商品名)\s*[:：]\s*(?P<title>.+?)\s*$"
)
TITLE_VALUE_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:タイトル|商品名)\s*[:：]\s*(?P<title>.*?)(?=\s*説明文\s*[:：]|\r?\n|$)",
    re.DOTALL,
)
DESCRIPTION_VALUE_PATTERN = re.compile(
    r"説明文\s*[:：]\s*(?P<description>.*)$",
    re.DOTALL,
)


class InputValidationError(ValueError):
    """Raised when generated listing content cannot be safely used."""


@dataclass(frozen=True)
class GeneratedListingContent:
    title: str
    description: str


def get_api_key() -> str:
    """Read the Gemini API key from Secret Manager."""
    try:
        secret_client = secretmanager.SecretManagerServiceClient()
        secret_version = (
            f"projects/{PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
        )
        response = secret_client.access_secret_version(request={"name": secret_version})
        return response.payload.data.decode("UTF-8")
    except Exception as error:
        print(f"ERROR: APIキーの取得に失敗しました: {error}")
        raise


def get_prompt_from_gcs() -> str:
    """Load the Mercari Shops description prompt, with the existing fallback."""
    try:
        prompt_blob = storage_client.bucket(PROMPT_BUCKET_NAME).blob(PROMPT_FILE_NAME)
        return prompt_blob.download_as_text()
    except Exception as error:
        print(
            f"WARNING: プロンプト({PROMPT_FILE_NAME})の読み込みに失敗。"
            f"デフォルトを使用します: {error}"
        )
        return "商品の魅力を伝える商品説明文を作成してください。"


def get_worksheets():
    """Open both destination worksheets using the Cloud Run service account."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials, _ = google.auth.default(scopes=scopes)
    spreadsheet = gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)
    return (
        spreadsheet.worksheet(SHEET_NAME_MERCARI),
        spreadsheet.worksheet(SHEET_NAME_YAHOO),
    )


def is_description_file(object_name: str) -> bool:
    """Return whether an object should start listing-data generation."""
    return object_name.endswith(DESCRIPTION_FILE_NAME)


def product_folder_from(object_name: str) -> str:
    """Return the GCS product folder, which is also used as the management code."""
    return os.path.dirname(object_name)


def replace_description_suffix(description_file_name: str, replacement_suffix: str) -> str:
    """Replace only the trigger-file suffix, leaving similarly named folders intact."""
    return f"{description_file_name.removesuffix(DESCRIPTION_FILE_NAME)}{replacement_suffix}"


def acquire_processing_lock(bucket, description_file_name: str):
    """Atomically claim an object so duplicate Cloud Storage events do not run twice."""
    lock_file_name = replace_description_suffix(
        description_file_name,
        PROCESSING_LOCK_FILE_NAME,
    )
    lock_blob = bucket.blob(lock_file_name)
    try:
        # GCS creates the lock only when no generation of that object exists.
        lock_blob.upload_from_string("", content_type="text/plain", if_generation_match=0)
    except PreconditionFailed:
        print(f"INFO: {description_file_name} は別の処理が実行中です。")
        return None
    return lock_blob


def mark_description_as_processed(
    bucket,
    description_blob,
    description_file_name: str,
    source_generation,
) -> None:
    """Mark the source as processed only after both listing rows were appended."""
    processed_file_name = replace_description_suffix(
        description_file_name,
        PROCESSED_FILE_NAME,
    )
    bucket.copy_blob(
        description_blob,
        bucket,
        processed_file_name,
        if_generation_match=0,
        if_source_generation_match=source_generation,
    )
    description_blob.delete(if_generation_match=source_generation)
    print(
        f"INFO: {description_file_name} を {processed_file_name} にリネームしました"
        "（処理完了）。"
    )


def strip_json_code_fence(text: str) -> str:
    match = JSON_CODE_FENCE_PATTERN.match(text)
    if match:
        return match.group("body").strip()
    return text.strip()


def clean_title(title: str) -> str:
    cleaned = DESCRIPTION_HEADING_PATTERN.sub("", title).strip()
    words = cleaned.split()
    unique_words: list[str] = []
    seen_words: set[str] = set()
    for word in words:
        if word in seen_words:
            continue
        seen_words.add(word)
        unique_words.append(word)
    return " ".join(unique_words) if unique_words else cleaned


def clean_description(description: str) -> str:
    cleaned_lines: list[str] = []

    for line in description.splitlines():
        if re.match(r"^\s*(?:タイトル|商品名)\s*[:：]", line):
            continue
        cleaned_line = re.sub(r"^\s*説明文\s*[:：]\s*", "", line)
        cleaned_lines.append(cleaned_line.rstrip())

    return "\n".join(cleaned_lines).strip()


def validate_generated_listing_content(
    title: str,
    description: str,
) -> GeneratedListingContent:
    cleaned_title = clean_title(title)
    cleaned_description = clean_description(description)

    if not cleaned_title:
        raise InputValidationError("生成AIの商品タイトルが空です。")
    if not cleaned_description:
        raise InputValidationError("生成AIの商品説明本文が空です。")

    return GeneratedListingContent(
        title=cleaned_title,
        description=cleaned_description,
    )


def parse_json_generated_content(raw_text: str) -> GeneratedListingContent:
    json_text = strip_json_code_fence(raw_text)

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError:
        start = json_text.find("{")
        end = json_text.rfind("}")
        if start == -1 or end <= start:
            raise
        parsed = json.loads(json_text[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("生成AIのJSONがオブジェクトではありません。")

    return validate_generated_listing_content(
        str(parsed.get("title", "")),
        str(parsed.get("description", "")),
    )


def parse_legacy_generated_content(raw_text: str) -> GeneratedListingContent:
    title_match = TITLE_VALUE_PATTERN.search(raw_text)
    description_match = DESCRIPTION_VALUE_PATTERN.search(raw_text)

    title = title_match.group("title") if title_match else ""
    if description_match:
        description = description_match.group("description")
    else:
        description = TITLE_HEADING_PATTERN.sub("", raw_text, count=1)

    return validate_generated_listing_content(title, description)


def parse_generated_listing_content(raw_text: str) -> GeneratedListingContent:
    if not raw_text.strip():
        raise InputValidationError("生成AIから空の商品情報が返されました。")

    try:
        return parse_json_generated_content(raw_text)
    except InputValidationError:
        raise
    except (json.JSONDecodeError, ValueError, TypeError):
        return parse_legacy_generated_content(raw_text)


def generate_mercari_description(yahoo_description: str) -> GeneratedListingContent:
    """Generate the platform-specific title and description for listings."""
    prompt = (
        f"{get_prompt_from_gcs()}\n\n"
        f"{JSON_OUTPUT_INSTRUCTION}\n\n"
        f"【商品情報】\n{yahoo_description}\n"
    )
    response_text = model.generate_content(prompt).text
    return parse_generated_listing_content(response_text)


def validate_output_row_lengths(mercari_row: list[str], yahoo_row: list[str]) -> None:
    if len(mercari_row) != MERCARI_COLUMN_COUNT:
        raise ValueError(
            f"Mercari行は{MERCARI_COLUMN_COUNT}列である必要があります: "
            f"{len(mercari_row)}列"
        )
    if len(yahoo_row) != YAHOO_COLUMN_COUNT:
        raise ValueError(
            f"Yahoo行は{YAHOO_COLUMN_COUNT}列である必要があります: "
            f"{len(yahoo_row)}列"
        )


def append_listing_rows(mercari_row: list[str], yahoo_row: list[str]) -> None:
    """Append the completed rows to their respective worksheets."""
    validate_output_row_lengths(mercari_row, yahoo_row)
    mercari_sheet, yahoo_sheet = get_worksheets()
    mercari_sheet.append_row(
        mercari_row,
        value_input_option="RAW",
        table_range=MERCARI_APPEND_TABLE_RANGE,
    )
    print(f"SUCCESS: メルカリ用シート({SHEET_NAME_MERCARI})に出力しました。")
    yahoo_sheet.append_row(
        yahoo_row,
        value_input_option="RAW",
        table_range=YAHOO_APPEND_TABLE_RANGE,
    )
    print(f"SUCCESS: ヤフオク用シート({SHEET_NAME_YAHOO})に出力しました。")


genai.configure(api_key=get_api_key())
model = genai.GenerativeModel(MODEL_NAME)
storage_client = storage.Client()


@functions_framework.cloud_event
def generate_dual_listing(cloud_event):
    """Create and append Mercari Shops and Yahoo Auctions rows for a description file."""
    event_data = cloud_event.data
    bucket_name = event_data["bucket"]
    description_file_name = event_data["name"]

    if not is_description_file(description_file_name):
        return

    print(f"INFO: 処理開始: gs://{bucket_name}/{description_file_name}")
    processing_lock = None
    try:
        bucket = storage_client.bucket(bucket_name)
        source_generation = event_data.get("generation")
        description_blob = bucket.blob(
            description_file_name,
            generation=source_generation,
        )
        if not description_blob.exists():
            print(f"INFO: {description_file_name} は既に処理されています。")
            return

        # Use the event generation when present, then lock before any external call.
        # This prevents concurrent deliveries of the same event from appending twice.
        if source_generation is None:
            description_blob.reload()
            source_generation = description_blob.generation
        processing_lock = acquire_processing_lock(bucket, description_file_name)
        if processing_lock is None:
            # Do not acknowledge this delivery while another worker owns the lock.
            # The source still exists, so an event retry can take over after failure.
            raise RuntimeError(f"処理ロックを取得できません: {description_file_name}")

        yahoo_description = description_blob.download_as_text()
        folder_path = product_folder_from(description_file_name)
        item_manage_code = folder_path.split("/")[-1] if folder_path else ""

        image_urls = collect_sorted_image_urls(
            storage_client.list_blobs(bucket_name, prefix=f"{folder_path}/"),
            bucket_name,
        )
        generated_content = generate_mercari_description(yahoo_description)
        mercari_row = build_mercari_row(
            image_urls=image_urls,
            item_manage_code=item_manage_code,
            title=generated_content.title,
            description=generated_content.description,
        )
        yahoo_row = build_yahoo_row(
            image_urls=image_urls,
            item_manage_code=item_manage_code,
            title=generated_content.title,
            description=generated_content.description,
        )
        append_listing_rows(mercari_row, yahoo_row)
        mark_description_as_processed(
            bucket,
            description_blob,
            description_file_name,
            source_generation,
        )
        print(f"SUCCESS: 管理コード {item_manage_code} の出品データを作成しました。")
    except Exception as error:
        print(f"ERROR: 処理中にエラーが発生しました: {error}")
        # Keep the description object untouched and signal failure so the event can retry.
        raise
    finally:
        if processing_lock is not None:
            try:
                processing_lock.delete()
            except Exception as error:
                print(f"WARNING: 処理ロックの削除に失敗しました: {error}")
