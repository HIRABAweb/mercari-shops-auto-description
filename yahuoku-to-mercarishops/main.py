"""Cloud Storage event handler for Mercari Shops and Yahoo Auctions listing data."""

import os

import functions_framework
import google.auth
import google.generativeai as genai
import gspread
from google.api_core.exceptions import PreconditionFailed
from google.cloud import secretmanager, storage

from listing_data import build_mercari_row, build_yahoo_row, collect_sorted_image_urls

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


def generate_mercari_description(yahoo_description: str) -> str:
    """Generate the platform-specific Mercari Shops description."""
    prompt = f"{get_prompt_from_gcs()}\n\n【商品情報】\n{yahoo_description}\n"
    return model.generate_content(prompt).text


def append_listing_rows(mercari_row: list[str], yahoo_row: list[str]) -> None:
    """Append the completed rows to their respective worksheets."""
    mercari_sheet, yahoo_sheet = get_worksheets()
    mercari_sheet.append_row(mercari_row)
    print(f"SUCCESS: メルカリ用シート({SHEET_NAME_MERCARI})に出力しました。")
    yahoo_sheet.append_row(yahoo_row)
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
        mercari_description = generate_mercari_description(yahoo_description)
        mercari_row = build_mercari_row(
            image_urls=image_urls,
            item_manage_code=item_manage_code,
            description=mercari_description,
        )
        yahoo_row = build_yahoo_row(
            image_urls=image_urls,
            item_manage_code=item_manage_code,
            description=yahoo_description,
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
