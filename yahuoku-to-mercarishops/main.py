"""Cloud Storage event handler for Mercari Shops and Yahoo Auctions listing data."""

import csv
from io import StringIO
import os

import functions_framework
import google.auth
import google.generativeai as genai
import gspread
from google.api_core.exceptions import PreconditionFailed
from google.cloud import secretmanager, storage

from listing_data import (
    IMAGE_EXTENSIONS,
    MERCARI_HEADERS,
    REVIEW_REQUIRED_HEADERS,
    SUCCESS_FILE_NAME,
    MERCARI_SKU_CODE,
    MERCARI_TITLE_MAX_LENGTH,
    YAHOO_IMAGE_START,
    YAHOO_TITLE_MAX_LENGTH,
    ReviewIssue,
    add_default_review_issues,
    analyze_success_text,
    build_mercari_row,
    build_review_rows,
    build_yahoo_row,
    collect_sorted_image_urls,
    detect_appeal_terms_without_evidence,
    aggregate_review_required_csv_texts,
    parse_mercari_description,
    parse_yahoo_description,
    shorten_title,
)

# Deployment settings. Values are intentionally not committed to this repository.
PROJECT_ID = ""
SECRET_NAME = ""
SPREADSHEET_ID = ""
SHEET_NAME_YAHOO = "Yahoo_List"
SHEET_NAME_DRAFT_MERCARI = "Draft_Mercari_List"
SHEET_NAME_REVIEW = "Review_List"
SHEET_NAME_APPROVED_MERCARI = "Approved_Mercari_CSV"
PROMPT_BUCKET_NAME = ""
PROMPT_FILE_NAME = ".txt"
MODEL_NAME = "gemini-2.5-flash-lite"

DESCRIPTION_FILE_NAME = "_description.txt"
PROCESSED_FILE_NAME = "_processed.txt"
PROCESSING_LOCK_FILE_NAME = "_processing.lock"
REVIEW_REQUIRED_FILE_NAME = "review_required.csv"
REVIEW_REQUIRED_DIR = "review_required"
MERCARI_IDEMPOTENCY_COLUMN = MERCARI_SKU_CODE + 1
YAHOO_IDEMPOTENCY_COLUMN = YAHOO_IMAGE_START + 1
REVIEW_ITEM_KEY_COLUMN = 1
REVIEW_STATUS_COLUMN = 4
REVIEW_STATUS_NEEDS_REVIEW = "needs_review"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_SHEET_HEADERS = [
    "review_item_key",
    "batch_id",
    "item_id",
    "review_status",
    "file_path",
    "reason",
    "suggested_action",
    "operator_note",
    "approved_at",
]
WORKSHEET_SPECS = {
    SHEET_NAME_DRAFT_MERCARI: (1000, len(MERCARI_HEADERS)),
    SHEET_NAME_YAHOO: (1000, 114),
    SHEET_NAME_REVIEW: (1000, len(REVIEW_SHEET_HEADERS)),
    SHEET_NAME_APPROVED_MERCARI: (1000, len(MERCARI_HEADERS)),
}


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
    """Load the Mercari Shops description prompt from the configured GCS object."""
    try:
        prompt_blob = storage_client.bucket(PROMPT_BUCKET_NAME).blob(PROMPT_FILE_NAME)
        return prompt_blob.download_as_text(encoding="utf-8")
    except Exception as error:
        print(f"ERROR: プロンプト({PROMPT_FILE_NAME})の読み込みに失敗しました: {error}")
        raise


def get_spreadsheet():
    """Open the destination spreadsheet using the Cloud Run service account."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials, _ = google.auth.default(scopes=scopes)
    return gspread.authorize(credentials).open_by_key(SPREADSHEET_ID)


def get_or_create_worksheet(spreadsheet, sheet_name: str):
    """Return a worksheet, creating the expected Phase 1 tab when missing."""
    for worksheet in spreadsheet.worksheets():
        if worksheet.title == sheet_name:
            return worksheet

    rows, columns = WORKSHEET_SPECS[sheet_name]
    return spreadsheet.add_worksheet(
        title=sheet_name,
        rows=rows,
        cols=columns,
    )


def get_worksheets():
    """Open the draft listing worksheets used by the event processor."""
    spreadsheet = get_spreadsheet()
    return (
        get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI),
        get_or_create_worksheet(spreadsheet, SHEET_NAME_YAHOO),
    )


def get_review_worksheet():
    """Open the worksheet that operators use for review and approval."""
    return get_or_create_worksheet(get_spreadsheet(), SHEET_NAME_REVIEW)


def get_approved_mercari_worksheets():
    """Open draft, review, and approved worksheets for CSV generation."""
    spreadsheet = get_spreadsheet()
    return (
        get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI),
        get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW),
        get_or_create_worksheet(spreadsheet, SHEET_NAME_APPROVED_MERCARI),
    )


def is_description_file(object_name: str) -> bool:
    """Return whether an object should start listing-data generation."""
    return object_name.endswith(DESCRIPTION_FILE_NAME)


def is_review_aggregation_marker(object_name: str) -> bool:
    """Return whether an object event should try review aggregation."""
    base_name = os.path.basename(object_name)
    return base_name == SUCCESS_FILE_NAME or object_name.endswith(PROCESSED_FILE_NAME)


def product_folder_from(object_name: str) -> str:
    """Return the GCS product folder, which is also used as the management code."""
    return os.path.dirname(object_name)


def batch_prefix_from_product_folder(folder_path: str) -> str:
    """Return the batch prefix that contains a product folder, if one exists."""
    return os.path.dirname(folder_path)


def scoped_object_name(prefix: str, object_name: str) -> str:
    """Join an optional GCS prefix and object name using GCS path separators."""
    clean_prefix = prefix.strip("/")
    return f"{clean_prefix}/{object_name}" if clean_prefix else object_name


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


def load_success_text(bucket, folder_path: str) -> str:
    """Load the human-provided product information used for review checks."""
    blob = bucket.blob(f"{folder_path}/{SUCCESS_FILE_NAME}")
    try:
        return blob.download_as_text(encoding="utf-8")
    except TypeError:
        return blob.download_as_text()


def review_required_file_name(item_manage_code: str, batch_prefix: str = "") -> str:
    """Return the per-item review file path used for idempotent retry-safe output."""
    item_id = item_manage_code or "unknown-item"
    return scoped_object_name(batch_prefix, f"{REVIEW_REQUIRED_DIR}/{item_id}.csv")


def write_review_required_file(
    bucket,
    item_manage_code: str,
    review_rows: list[list[str]],
    batch_prefix: str = "",
) -> str | None:
    """Write human-actionable review reasons to one deterministic item file."""
    if not review_rows:
        return None

    output = StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(REVIEW_REQUIRED_HEADERS)
    writer.writerows(review_rows)

    file_name = review_required_file_name(item_manage_code, batch_prefix=batch_prefix)
    review_blob = bucket.blob(file_name)
    review_blob.upload_from_string(
        output.getvalue(),
        content_type="text/csv; charset=utf-8",
    )
    print(f"SUCCESS: {file_name} に確認理由を出力しました。")
    return file_name


def product_folders_with_images(blobs) -> set[str]:
    """Return product folders that contain at least one supported image."""
    return {
        os.path.dirname(blob.name)
        for blob in blobs
        if os.path.dirname(blob.name)
        and blob.name.lower().endswith(IMAGE_EXTENSIONS)
    }


def product_folders_with_file(blobs, file_name: str) -> set[str]:
    """Return product folders that contain the given marker file."""
    return {
        os.path.dirname(blob.name)
        for blob in blobs
        if os.path.basename(blob.name) == file_name and os.path.dirname(blob.name)
    }


def product_folders_with_processed_file(blobs) -> set[str]:
    """Return product folders that contain a processed description marker."""
    return {
        os.path.dirname(blob.name)
        for blob in blobs
        if blob.name.endswith(PROCESSED_FILE_NAME) and os.path.dirname(blob.name)
    }


def all_image_folders_have_success(blobs) -> bool:
    """Return whether every product folder with images has _SUCCESS.txt."""
    image_folders = product_folders_with_images(blobs)
    if not image_folders:
        return False
    success_folders = product_folders_with_file(blobs, SUCCESS_FILE_NAME)
    return image_folders.issubset(success_folders)


def item_id_from_review_file_name(file_name: str) -> str:
    """Return item id from review_required/{item_id}.csv."""
    return os.path.splitext(os.path.basename(file_name))[0]


def aggregate_review_required_files(bucket_name: str, batch_prefix: str = "") -> str | None:
    """Aggregate processed per-item review CSV files into review_required.csv."""
    bucket = storage_client.bucket(bucket_name)
    list_prefix = f"{batch_prefix.strip('/')}/" if batch_prefix.strip("/") else ""
    all_blobs = list(storage_client.list_blobs(bucket_name, prefix=list_prefix))
    if not all_image_folders_have_success(all_blobs):
        print("INFO: 画像フォルダすべてに _SUCCESS.txt が揃っていないため集約をスキップします。")
        return None

    processed_item_ids = {
        folder.split("/")[-1]
        for folder in product_folders_with_processed_file(all_blobs)
    }
    review_dir_prefix = scoped_object_name(batch_prefix, REVIEW_REQUIRED_DIR) + "/"
    csv_texts = [
        blob.download_as_text(encoding="utf-8")
        for blob in all_blobs
        if blob.name.endswith(".csv")
        and blob.name.startswith(review_dir_prefix)
        and item_id_from_review_file_name(blob.name) in processed_item_ids
    ]
    aggregate_text = aggregate_review_required_csv_texts(csv_texts)
    output_file_name = scoped_object_name(batch_prefix, REVIEW_REQUIRED_FILE_NAME)
    output_blob = bucket.blob(output_file_name)
    output_blob.upload_from_string(
        aggregate_text,
        content_type="text/csv; charset=utf-8",
    )
    print(f"SUCCESS: {output_file_name} を集約出力しました。")
    return output_file_name


@functions_framework.cloud_event
def aggregate_review_required_on_marker(cloud_event):
    """Aggregate review CSVs when _SUCCESS.txt or _processed.txt changes."""
    event_data = cloud_event.data
    bucket_name = event_data["bucket"]
    object_name = event_data["name"]

    if not is_review_aggregation_marker(object_name):
        return

    folder_path = product_folder_from(object_name)
    batch_prefix = batch_prefix_from_product_folder(folder_path)
    aggregate_review_required_files(bucket_name, batch_prefix=batch_prefix)


def worksheet_contains_value(worksheet, column_number: int, value: str) -> bool:
    """Return whether a worksheet column already contains a deterministic key."""
    if not value:
        return False
    return value in worksheet.col_values(column_number)


def append_row_if_missing(
    worksheet,
    row: list[str],
    idempotency_column: int,
    idempotency_value: str,
    sheet_name: str,
) -> bool:
    """Append a row only when the sheet does not already contain its key."""
    if worksheet_contains_value(worksheet, idempotency_column, idempotency_value):
        print(
            f"INFO: {sheet_name} は既に出力済みのためappendをスキップしました: "
            f"{idempotency_value}"
        )
        return False
    worksheet.append_row(row)
    print(f"SUCCESS: {sheet_name} に出力しました。")
    return True


def worksheet_values(worksheet) -> list[list[str]]:
    """Return all worksheet values, tolerating empty sheets."""
    values = worksheet.get_all_values()
    return values or []


def ensure_sheet_header(worksheet, headers: list[str]) -> None:
    """Create a header row when a worksheet is empty."""
    if worksheet_values(worksheet):
        return
    worksheet.append_row(headers)


def review_item_key(batch_prefix: str, item_manage_code: str) -> str:
    """Return the stable review key used by Review_List."""
    return scoped_object_name(batch_prefix, item_manage_code or "unknown-item")


def build_review_sheet_row(
    batch_prefix: str,
    item_manage_code: str,
    file_path: str,
    review_rows: list[list[str]],
) -> list[str]:
    """Build one operator-facing Review_List row for an item."""
    reasons = []
    actions = []
    for row in review_rows:
        reason = row[5] if len(row) > 5 else ""
        action = row[7] if len(row) > 7 else ""
        if reason and reason not in reasons:
            reasons.append(reason)
        if action and action not in actions:
            actions.append(action)

    return [
        review_item_key(batch_prefix, item_manage_code),
        batch_prefix,
        item_manage_code,
        REVIEW_STATUS_NEEDS_REVIEW if review_rows else REVIEW_STATUS_APPROVED,
        file_path,
        "\n".join(reasons),
        "\n".join(actions),
        "",
        "",
    ]


def write_review_sheet_row(
    review_sheet,
    batch_prefix: str,
    item_manage_code: str,
    file_path: str,
    review_rows: list[list[str]],
) -> bool:
    """Append one review row unless the item is already present."""
    ensure_sheet_header(review_sheet, REVIEW_SHEET_HEADERS)
    row = build_review_sheet_row(
        batch_prefix=batch_prefix,
        item_manage_code=item_manage_code,
        file_path=file_path,
        review_rows=review_rows,
    )
    return append_row_if_missing(
        review_sheet,
        row,
        REVIEW_ITEM_KEY_COLUMN,
        row[0],
        f"レビュー用シート({SHEET_NAME_REVIEW})",
    )


def append_listing_rows(
    mercari_row: list[str],
    yahoo_row: list[str],
    item_manage_code: str,
) -> None:
    """Append completed rows idempotently to their respective worksheets."""
    mercari_sheet, yahoo_sheet = get_worksheets()
    ensure_sheet_header(mercari_sheet, MERCARI_HEADERS)
    append_row_if_missing(
        mercari_sheet,
        mercari_row,
        MERCARI_IDEMPOTENCY_COLUMN,
        item_manage_code,
        f"メルカリ下書きシート({SHEET_NAME_DRAFT_MERCARI})",
    )
    yahoo_key = yahoo_row[YAHOO_IMAGE_START] if len(yahoo_row) > YAHOO_IMAGE_START else ""
    append_row_if_missing(
        yahoo_sheet,
        yahoo_row,
        YAHOO_IDEMPOTENCY_COLUMN,
        yahoo_key,
        f"ヤフオク用シート({SHEET_NAME_YAHOO})",
    )


def approved_review_item_keys(review_sheet, batch_prefix: str = "") -> set[str]:
    """Read approved item keys from Review_List."""
    values = worksheet_values(review_sheet)
    if not values:
        return set()

    header = values[0]
    try:
        key_index = header.index("review_item_key")
        status_index = header.index("review_status")
    except ValueError:
        key_index = REVIEW_ITEM_KEY_COLUMN - 1
        status_index = REVIEW_STATUS_COLUMN - 1

    approved_keys = set()
    for row in values[1:]:
        key = row[key_index].strip() if len(row) > key_index else ""
        status = row[status_index].strip().lower() if len(row) > status_index else ""
        if batch_prefix and not key.startswith(f"{batch_prefix.strip('/')}/"):
            continue
        if key and status == REVIEW_STATUS_APPROVED:
            approved_keys.add(key)
    return approved_keys


def review_item_keys_for_batch(review_sheet, batch_prefix: str) -> set[str]:
    """Read all review item keys for a batch, regardless of approval status."""
    values = worksheet_values(review_sheet)
    if not values:
        return set()

    header = values[0]
    try:
        key_index = header.index("review_item_key")
    except ValueError:
        key_index = REVIEW_ITEM_KEY_COLUMN - 1

    prefix = batch_prefix.strip("/")
    return {
        row[key_index].strip()
        for row in values[1:]
        if len(row) > key_index
        and row[key_index].strip().startswith(f"{prefix}/")
    }


def draft_row_matches_review_key(row: list[str], review_key: str) -> bool:
    """Return whether a Mercari draft row belongs to an approved review key."""
    item_id = row[MERCARI_SKU_CODE].strip() if len(row) > MERCARI_SKU_CODE else ""
    if not item_id:
        return False

    review_item_id = review_key.split("/")[-1]
    if item_id != review_item_id:
        return False

    review_prefix = os.path.dirname(review_key)
    if not review_prefix:
        return True

    expected_path = f"/{review_prefix}/{item_id}/"
    expected_relative_path = f"{review_prefix}/{item_id}/"
    return any(
        expected_path in value or value.startswith(expected_relative_path)
        for value in row
        if isinstance(value, str)
    )


def draft_rows_for_approved_items(
    draft_sheet,
    approved_keys: set[str],
) -> list[list[str]]:
    """Return Mercari draft rows whose SKU item id is approved."""
    rows = []
    for row in worksheet_values(draft_sheet):
        if row == MERCARI_HEADERS:
            continue
        if any(draft_row_matches_review_key(row, key) for key in approved_keys):
            rows.append(row)
    return rows


def export_approved_mercari_rows(
    draft_sheet,
    review_sheet,
    approved_sheet,
    batch_prefix: str = "",
) -> int:
    """Rebuild Approved_Mercari_CSV from currently approved draft rows."""
    approved_rows = draft_rows_for_approved_items(
        draft_sheet,
        approved_review_item_keys(review_sheet, batch_prefix=batch_prefix),
    )
    approved_sheet.clear()
    approved_sheet.append_rows(
        [MERCARI_HEADERS, *approved_rows],
        value_input_option="USER_ENTERED",
    )
    print(f"SUCCESS: 承認済みメルカリShops用CSVシートへ {len(approved_rows)} 件出力しました。")
    return len(approved_rows)


def request_batch_prefix(request) -> str:
    """Read an optional batch_prefix query parameter from an HTTP request."""
    args = getattr(request, "args", None)
    if not args:
        return ""
    return (args.get("batch_prefix") or "").strip("/")


@functions_framework.http
def export_approved_mercari_csv(request):
    """HTTP entrypoint for rebuilding the approved Mercari Shops CSV sheet."""
    draft_sheet, review_sheet, approved_sheet = get_approved_mercari_worksheets()
    batch_prefix = request_batch_prefix(request)
    if not batch_prefix:
        return ("batch_prefix is required\n", 400)
    if not review_item_keys_for_batch(review_sheet, batch_prefix):
        return (f"no review rows found for {batch_prefix}\n", 404)
    exported_count = export_approved_mercari_rows(
        draft_sheet,
        review_sheet,
        approved_sheet,
        batch_prefix=batch_prefix,
    )
    scope = batch_prefix or "all batches"
    return (f"exported {exported_count} approved Mercari rows for {scope}\n", 200)


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
        batch_prefix = batch_prefix_from_product_folder(folder_path)

        image_urls = collect_sorted_image_urls(
            storage_client.list_blobs(bucket_name, prefix=f"{folder_path}/"),
            bucket_name,
        )

        yahoo_parsed = parse_yahoo_description(yahoo_description)
        mercari_ai_output = generate_mercari_description(yahoo_description)
        success_text = load_success_text(bucket, folder_path)
        mercari_parsed = parse_mercari_description(mercari_ai_output)
        review_issues = [
            *analyze_success_text(success_text),
            *yahoo_parsed.review_issues,
            *mercari_parsed.review_issues,
            *detect_appeal_terms_without_evidence(
                "\n".join(
                    [
                        yahoo_parsed.title,
                        yahoo_parsed.description,
                        mercari_parsed.title,
                        mercari_parsed.description,
                    ]
                ),
                success_text,
            ),
        ]

        yahoo_title, yahoo_shortened = shorten_title(
            yahoo_parsed.title,
            max_length=YAHOO_TITLE_MAX_LENGTH,
        )
        if yahoo_shortened:
            review_issues.append(
                ReviewIssue(
                    platform="yahoo",
                    field="title",
                    reason="タイトル長すぎのため自動短縮",
                    current_value=yahoo_parsed.title,
                    suggested_action="短縮後の商品名を確認してください",
                )
            )
        mercari_title, mercari_shortened = shorten_title(
            mercari_parsed.title,
            max_length=MERCARI_TITLE_MAX_LENGTH,
        )
        if mercari_shortened:
            review_issues.append(
                ReviewIssue(
                    platform="mercari",
                    field="title",
                    reason="タイトル長すぎのため自動短縮",
                    current_value=mercari_parsed.title,
                    suggested_action="短縮後の商品名を確認してください",
                )
            )

        review_rows = build_review_rows(
            item_manage_code=item_manage_code,
            file_path=description_file_name,
            issues=add_default_review_issues(review_issues),
        )
        mercari_row = build_mercari_row(
            image_urls=image_urls,
            item_manage_code=item_manage_code,
            title=mercari_title,
            description=mercari_parsed.description,
        )
        yahoo_row = build_yahoo_row(
            image_urls=image_urls,
            item_manage_code=item_manage_code,
            title=yahoo_title,
            description=yahoo_parsed.description,
        )
        write_review_required_file(
            bucket,
            item_manage_code,
            review_rows,
            batch_prefix=batch_prefix,
        )
        write_review_sheet_row(
            get_review_worksheet(),
            batch_prefix=batch_prefix,
            item_manage_code=item_manage_code,
            file_path=description_file_name,
            review_rows=review_rows,
        )
        append_listing_rows(mercari_row, yahoo_row, item_manage_code)
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
