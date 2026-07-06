"""Optional Google Sheets workflow for Phase 1 review approval."""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass

from csv_export import MERCARI_HEADERS, REVIEW_REQUIRED_HEADERS, YAHOO_HEADERS


SHEET_NAME_DRAFT_MERCARI = "Draft_Mercari_List"
SHEET_NAME_REVIEW = "Review_List"
SHEET_NAME_APPROVED_MERCARI = "Approved_Mercari_CSV"
SHEET_NAME_YAHOO = "Yahoo_List"

REVIEW_STATUS_NEEDS_REVIEW = "needs_review"
REVIEW_STATUS_APPROVED = "approved"

REVIEW_SHEET_HEADERS = [
    "review_item_key",
    "batch_prefix",
    "product_code",
    "review_status",
    "file_path",
    "reason",
    "suggested_action",
    "approved_at",
]

MERCARI_PRODUCT_CODE_HEADER = "SKU1_商品管理コード"
MERCARI_TITLE_HEADER = "商品名"
MERCARI_DESCRIPTION_HEADER = "商品説明"
MERCARI_IMAGE_HEADER_PREFIX = "商品画像名_"

WORKSHEET_SPECS = {
    SHEET_NAME_DRAFT_MERCARI: (1000, len(MERCARI_HEADERS)),
    SHEET_NAME_REVIEW: (1000, len(REVIEW_SHEET_HEADERS)),
    SHEET_NAME_APPROVED_MERCARI: (1000, len(MERCARI_HEADERS)),
    SHEET_NAME_YAHOO: (1000, len(YAHOO_HEADERS)),
}


@dataclass(frozen=True)
class BatchSummary:
    batch_prefix: str
    batch_id: str
    total_count: int
    approved_count: int
    needs_review_count: int


@dataclass(frozen=True)
class ReviewItem:
    review_item_key: str
    batch_prefix: str
    batch_id: str
    product_code: str
    review_status: str
    file_path: str
    reason: str
    suggested_action: str
    approved_at: str
    title: str
    description: str
    first_image_url: str


def phase1_sheets_enabled() -> bool:
    return bool(os.getenv("SPREADSHEET_ID", "").strip())


def get_spreadsheet():
    import google.auth
    import gspread

    spreadsheet_id = os.getenv("SPREADSHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("SPREADSHEET_ID is required for Phase 1 Sheets workflow.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials, _ = google.auth.default(scopes=scopes)
    return gspread.authorize(credentials).open_by_key(spreadsheet_id)


def worksheet_values(worksheet) -> list[list[str]]:
    return worksheet.get_all_values() or []


def get_or_create_worksheet(spreadsheet, sheet_name: str):
    for worksheet in spreadsheet.worksheets():
        if worksheet.title == sheet_name:
            return worksheet

    rows, columns = WORKSHEET_SPECS[sheet_name]
    return spreadsheet.add_worksheet(title=sheet_name, rows=rows, cols=columns)


def ensure_sheet_header(worksheet, headers: list[str]) -> None:
    if worksheet_values(worksheet):
        return
    worksheet.append_row(headers)


def column_letter(column_number: int) -> str:
    if column_number < 1:
        raise ValueError("column_number must be positive")
    letters = []
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        letters.append(chr(65 + remainder))
    return "".join(reversed(letters))


def replace_sheet_rows(worksheet, rows: list[list[str]], column_count: int) -> None:
    existing_row_count = len(worksheet_values(worksheet))
    worksheet.update(
        values=rows,
        range_name="A1",
        value_input_option="USER_ENTERED",
    )
    if existing_row_count > len(rows):
        worksheet.batch_clear(
            [f"A{len(rows) + 1}:{column_letter(column_count)}{existing_row_count}"]
        )


def dict_row_to_list(headers: list[str], row: dict[str, str]) -> list[str]:
    return [row.get(header, "") for header in headers]


def list_row_to_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    return {
        header: row[index] if index < len(row) else ""
        for index, header in enumerate(headers)
    }


def normalize_batch_prefix(batch_id_or_prefix: str) -> str:
    value = batch_id_or_prefix.strip().strip("/")
    if not value:
        return ""
    if value.startswith("exports/"):
        return value
    return f"exports/{value}"


def batch_id_from_prefix(batch_prefix: str) -> str:
    prefix = batch_prefix.strip("/")
    return prefix.removeprefix("exports/")


def row_value(row: list[str], header: str) -> str:
    if header not in MERCARI_HEADERS:
        return ""
    index = MERCARI_HEADERS.index(header)
    return row[index] if len(row) > index else ""


def first_image_url_from_list_row(row: list[str]) -> str:
    for header, value in zip(MERCARI_HEADERS, row):
        if header.startswith(MERCARI_IMAGE_HEADER_PREFIX) and value:
            return value
    return ""


def list_rows_to_csv_text(rows: list[list[str]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue()


def worksheet_contains_value(worksheet, column_number: int, value: str) -> bool:
    if not value:
        return False
    return value in worksheet.col_values(column_number)


def append_row_if_missing(
    worksheet,
    row: list[str],
    idempotency_column: int,
    idempotency_value: str,
) -> bool:
    if worksheet_contains_value(worksheet, idempotency_column, idempotency_value):
        return False
    worksheet.append_row(row)
    return True


def worksheet_contains_any_value(worksheet, value: str) -> bool:
    if not value:
        return False
    return any(value in row for row in worksheet_values(worksheet))


def append_row_if_missing_by_value(
    worksheet,
    row: list[str],
    idempotency_value: str,
) -> bool:
    if worksheet_contains_any_value(worksheet, idempotency_value):
        return False
    worksheet.append_row(row)
    return True


def update_worksheet_row(worksheet, row_number: int, row: list[str], column_count: int) -> None:
    end_column = column_letter(column_count)
    worksheet.update(
        values=[row],
        range_name=f"A{row_number}:{end_column}{row_number}",
        value_input_option="USER_ENTERED",
    )


def first_url_value(row: dict[str, str]) -> str:
    for value in row.values():
        if isinstance(value, str) and value.startswith("https://storage.googleapis.com/"):
            return value
    return ""


def batch_prefix_from_folder(folder_path: str) -> str:
    return os.path.dirname(folder_path.strip("/"))


def review_item_key(batch_prefix: str, product_code: str) -> str:
    return f"{batch_prefix.strip('/')}/{product_code}" if batch_prefix else product_code


def review_row_to_dict(row: list[str]) -> dict[str, str]:
    return {
        header: row[index] if index < len(row) else ""
        for index, header in enumerate(REVIEW_SHEET_HEADERS)
    }


def review_rows_for_batch(review_sheet, batch_prefix: str) -> list[dict[str, str]]:
    values = worksheet_values(review_sheet)
    if not values:
        return []
    prefix = normalize_batch_prefix(batch_prefix)
    rows = []
    for row in values[1:]:
        record = review_row_to_dict(row)
        if record["review_item_key"].strip().startswith(f"{prefix}/"):
            rows.append(record)
    return rows


def draft_rows_by_key(draft_sheet, review_keys: set[str]) -> dict[str, list[str]]:
    rows_by_key: dict[str, list[str]] = {}
    for row in worksheet_values(draft_sheet)[1:]:
        for key in review_keys:
            if draft_row_matches_review_key(row, key):
                rows_by_key[key] = row
    return rows_by_key


def list_batch_summaries() -> list[BatchSummary]:
    spreadsheet = get_spreadsheet()
    review_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW)
    ensure_sheet_header(review_sheet, REVIEW_SHEET_HEADERS)

    summaries: dict[str, dict[str, int]] = {}
    for row in worksheet_values(review_sheet)[1:]:
        record = review_row_to_dict(row)
        batch_prefix = normalize_batch_prefix(record.get("batch_prefix", ""))
        if not batch_prefix:
            key = record.get("review_item_key", "")
            batch_prefix = os.path.dirname(key)
        if not batch_prefix:
            continue
        status = record.get("review_status", "").strip().lower()
        counters = summaries.setdefault(
            batch_prefix,
            {"total": 0, "approved": 0, "needs_review": 0},
        )
        counters["total"] += 1
        if status == REVIEW_STATUS_APPROVED:
            counters["approved"] += 1
        else:
            counters["needs_review"] += 1

    return [
        BatchSummary(
            batch_prefix=batch_prefix,
            batch_id=batch_id_from_prefix(batch_prefix),
            total_count=counters["total"],
            approved_count=counters["approved"],
            needs_review_count=counters["needs_review"],
        )
        for batch_prefix, counters in sorted(summaries.items(), reverse=True)
    ]


def list_review_items(batch_id_or_prefix: str) -> list[ReviewItem]:
    spreadsheet = get_spreadsheet()
    draft_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI)
    review_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW)
    ensure_sheet_header(draft_sheet, MERCARI_HEADERS)
    ensure_sheet_header(review_sheet, REVIEW_SHEET_HEADERS)

    batch_prefix = normalize_batch_prefix(batch_id_or_prefix)
    review_records = review_rows_for_batch(review_sheet, batch_prefix)
    draft_by_key = draft_rows_by_key(
        draft_sheet,
        {record["review_item_key"] for record in review_records},
    )
    items = []
    for record in review_records:
        key = record["review_item_key"]
        draft_row = draft_by_key.get(key, [])
        items.append(
            ReviewItem(
                review_item_key=key,
                batch_prefix=batch_prefix,
                batch_id=batch_id_from_prefix(batch_prefix),
                product_code=record.get("product_code", ""),
                review_status=record.get("review_status", ""),
                file_path=record.get("file_path", ""),
                reason=record.get("reason", ""),
                suggested_action=record.get("suggested_action", ""),
                approved_at=record.get("approved_at", ""),
                title=row_value(draft_row, MERCARI_TITLE_HEADER),
                description=row_value(draft_row, MERCARI_DESCRIPTION_HEADER),
                first_image_url=first_image_url_from_list_row(draft_row),
            )
        )
    return items


def find_review_row_number(review_sheet, review_key: str) -> tuple[int, list[str]] | None:
    for index, row in enumerate(worksheet_values(review_sheet)[1:], start=2):
        record = review_row_to_dict(row)
        if record.get("review_item_key", "").strip() == review_key:
            return index, row
    return None


def find_draft_row_number(draft_sheet, review_key: str) -> tuple[int, list[str]] | None:
    for index, row in enumerate(worksheet_values(draft_sheet)[1:], start=2):
        if draft_row_matches_review_key(row, review_key):
            return index, row
    return None


def get_review_item(batch_id_or_prefix: str, product_code: str) -> tuple[dict[str, str], dict[str, str]]:
    spreadsheet = get_spreadsheet()
    draft_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI)
    review_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW)
    ensure_sheet_header(draft_sheet, MERCARI_HEADERS)
    ensure_sheet_header(review_sheet, REVIEW_SHEET_HEADERS)

    batch_prefix = normalize_batch_prefix(batch_id_or_prefix)
    key = review_item_key(batch_prefix, product_code)
    review_match = find_review_row_number(review_sheet, key)
    draft_match = find_draft_row_number(draft_sheet, key)
    if review_match is None or draft_match is None:
        raise KeyError(key)
    return (
        review_row_to_dict(review_match[1]),
        list_row_to_dict(MERCARI_HEADERS, draft_match[1]),
    )


def update_draft_item(batch_id_or_prefix: str, product_code: str, updates: dict[str, str]) -> None:
    spreadsheet = get_spreadsheet()
    draft_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI)
    ensure_sheet_header(draft_sheet, MERCARI_HEADERS)

    batch_prefix = normalize_batch_prefix(batch_id_or_prefix)
    key = review_item_key(batch_prefix, product_code)
    match = find_draft_row_number(draft_sheet, key)
    if match is None:
        raise KeyError(key)
    row_number, row = match
    updated_row = [row[index] if index < len(row) else "" for index in range(len(MERCARI_HEADERS))]
    for header, value in updates.items():
        if header in MERCARI_HEADERS:
            updated_row[MERCARI_HEADERS.index(header)] = value
    update_worksheet_row(draft_sheet, row_number, updated_row, len(MERCARI_HEADERS))


def approve_review_item(batch_id_or_prefix: str, product_code: str, approved_at: str) -> None:
    spreadsheet = get_spreadsheet()
    review_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW)
    ensure_sheet_header(review_sheet, REVIEW_SHEET_HEADERS)

    batch_prefix = normalize_batch_prefix(batch_id_or_prefix)
    key = review_item_key(batch_prefix, product_code)
    match = find_review_row_number(review_sheet, key)
    if match is None:
        raise KeyError(key)
    row_number, row = match
    updated_row = [row[index] if index < len(row) else "" for index in range(len(REVIEW_SHEET_HEADERS))]
    updated_row[REVIEW_SHEET_HEADERS.index("review_status")] = REVIEW_STATUS_APPROVED
    updated_row[REVIEW_SHEET_HEADERS.index("approved_at")] = approved_at
    update_worksheet_row(review_sheet, row_number, updated_row, len(REVIEW_SHEET_HEADERS))


def build_review_sheet_row(
    *,
    batch_prefix: str,
    product_code: str,
    file_path: str,
    review_rows: list[dict[str, str]],
) -> list[str]:
    reasons = []
    actions = []
    for row in review_rows:
        reason = row.get(REVIEW_REQUIRED_HEADERS[-1], "")
        field = row.get(REVIEW_REQUIRED_HEADERS[1], "")
        if reason and reason not in reasons:
            reasons.append(reason)
        if field:
            action = f"{field}を確認してください"
            if action not in actions:
                actions.append(action)

    return [
        review_item_key(batch_prefix, product_code),
        batch_prefix,
        product_code,
        REVIEW_STATUS_NEEDS_REVIEW if review_rows else REVIEW_STATUS_APPROVED,
        file_path,
        "\n".join(reasons),
        "\n".join(actions),
        "",
    ]


def write_phase1_sheet_rows(
    *,
    mercari_row: dict[str, str],
    yahoo_row: dict[str, str],
    review_rows: list[dict[str, str]],
    folder_path: str,
    product_code: str,
    file_path: str,
) -> None:
    spreadsheet = get_spreadsheet()
    mercari_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI)
    review_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW)
    yahoo_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_YAHOO)

    ensure_sheet_header(mercari_sheet, MERCARI_HEADERS)
    ensure_sheet_header(review_sheet, REVIEW_SHEET_HEADERS)
    ensure_sheet_header(yahoo_sheet, YAHOO_HEADERS)

    mercari_key = first_url_value(mercari_row) or product_code
    yahoo_key = first_url_value(yahoo_row) or product_code
    batch_prefix = batch_prefix_from_folder(folder_path)
    review_row = build_review_sheet_row(
        batch_prefix=batch_prefix,
        product_code=product_code,
        file_path=file_path,
        review_rows=review_rows,
    )

    append_row_if_missing_by_value(
        mercari_sheet,
        dict_row_to_list(MERCARI_HEADERS, mercari_row),
        mercari_key,
    )
    append_row_if_missing(review_sheet, review_row, 1, review_row[0])
    append_row_if_missing_by_value(
        yahoo_sheet,
        dict_row_to_list(YAHOO_HEADERS, yahoo_row),
        yahoo_key,
    )


def approved_review_item_keys(review_sheet, batch_prefix: str) -> set[str]:
    values = worksheet_values(review_sheet)
    if not values:
        return set()

    header = values[0]
    key_index = header.index("review_item_key") if "review_item_key" in header else 0
    status_index = header.index("review_status") if "review_status" in header else 3
    prefix = batch_prefix.strip("/")

    approved = set()
    for row in values[1:]:
        key = row[key_index].strip() if len(row) > key_index else ""
        status = row[status_index].strip().lower() if len(row) > status_index else ""
        if key.startswith(f"{prefix}/") and status == REVIEW_STATUS_APPROVED:
            approved.add(key)
    return approved


def review_item_keys_for_batch(review_sheet, batch_prefix: str) -> set[str]:
    values = worksheet_values(review_sheet)
    if not values:
        return set()

    header = values[0]
    key_index = header.index("review_item_key") if "review_item_key" in header else 0
    prefix = batch_prefix.strip("/")
    return {
        row[key_index].strip()
        for row in values[1:]
        if len(row) > key_index and row[key_index].strip().startswith(f"{prefix}/")
    }


def draft_row_matches_review_key(row: list[str], review_key: str) -> bool:
    product_code_index = 24
    product_code = row[product_code_index].strip() if len(row) > product_code_index else ""
    if not product_code or product_code != review_key.split("/")[-1]:
        return False

    review_prefix = os.path.dirname(review_key)
    if not review_prefix:
        return True

    expected_path = f"/{review_prefix}/{product_code}/"
    expected_relative_path = f"{review_prefix}/{product_code}/"
    return any(
        expected_path in value or value.startswith(expected_relative_path)
        for value in row
        if isinstance(value, str)
    )


def build_approved_mercari_sheet_rows(batch_prefix: str, spreadsheet=None) -> list[list[str]] | None:
    if spreadsheet is None:
        spreadsheet = get_spreadsheet()
    draft_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_DRAFT_MERCARI)
    review_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_REVIEW)

    if not review_item_keys_for_batch(review_sheet, batch_prefix):
        return None

    approved_keys = approved_review_item_keys(review_sheet, batch_prefix)
    approved_rows = [
        row
        for row in worksheet_values(draft_sheet)
        if row != MERCARI_HEADERS
        and any(draft_row_matches_review_key(row, key) for key in approved_keys)
    ]
    return [MERCARI_HEADERS, *approved_rows]


def export_approved_mercari_rows_and_csv(batch_prefix: str) -> tuple[int, str]:
    spreadsheet = get_spreadsheet()
    approved_sheet = get_or_create_worksheet(spreadsheet, SHEET_NAME_APPROVED_MERCARI)
    rows = build_approved_mercari_sheet_rows(batch_prefix, spreadsheet)
    if rows is None:
        return -1, ""

    replace_sheet_rows(approved_sheet, rows, len(MERCARI_HEADERS))
    return len(rows) - 1, list_rows_to_csv_text(rows)


def export_approved_mercari_rows(batch_prefix: str) -> int:
    exported_count, _ = export_approved_mercari_rows_and_csv(batch_prefix)
    return exported_count
