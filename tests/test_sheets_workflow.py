"""Tests for the optional Phase 1 Google Sheets workflow."""

from __future__ import annotations

import sys
from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parents[1] / "yahuoku-to-mercarishops"
sys.path.insert(0, str(MODULE_DIR))

import sheets_workflow
from csv_export import MERCARI_HEADERS, REVIEW_REQUIRED_HEADERS, YAHOO_HEADERS


class FakeWorksheet:
    def __init__(self, title: str, values=None):
        self.title = title
        self.values = values or []
        self.appended_rows = []
        self.update_calls = []
        self.batch_clear_calls = []

    def get_all_values(self):
        return self.values

    def append_row(self, row):
        self.appended_rows.append(row)
        self.values.append(row)

    def col_values(self, column_number):
        index = column_number - 1
        return [row[index] for row in self.values if len(row) > index]

    def update(self, values=None, range_name=None, **kwargs):
        self.update_calls.append((range_name, values, kwargs))
        self.values = values or []

    def batch_clear(self, ranges):
        self.batch_clear_calls.append(ranges)


class FakeSpreadsheet:
    def __init__(self):
        self.sheets = {}

    def worksheets(self):
        return list(self.sheets.values())

    def add_worksheet(self, title, rows, cols):
        worksheet = FakeWorksheet(title)
        self.sheets[title] = worksheet
        return worksheet


def mercari_row(image_url: str, product_code: str) -> dict[str, str]:
    row = {header: "" for header in MERCARI_HEADERS}
    row[MERCARI_HEADERS[0]] = image_url
    row[MERCARI_HEADERS[24]] = product_code
    return row


def yahoo_row(image_url: str) -> dict[str, str]:
    row = {header: "" for header in YAHOO_HEADERS}
    row[YAHOO_HEADERS[8]] = image_url
    return row


def review_row(product_code: str, field: str, reason: str) -> dict[str, str]:
    return {
        REVIEW_REQUIRED_HEADERS[0]: product_code,
        REVIEW_REQUIRED_HEADERS[1]: field,
        REVIEW_REQUIRED_HEADERS[-1]: reason,
    }


def test_write_phase1_sheet_rows_creates_headers_and_is_idempotent(monkeypatch):
    spreadsheet = FakeSpreadsheet()
    monkeypatch.setattr(sheets_workflow, "get_spreadsheet", lambda: spreadsheet)
    image_url = "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg"

    kwargs = {
        "mercari_row": mercari_row(image_url, "A0001"),
        "yahoo_row": yahoo_row(image_url),
        "review_rows": [review_row("A0001", "brand_id", "brand review")],
        "folder_path": "exports/2026-07-06/A0001",
        "product_code": "A0001",
        "file_path": "exports/2026-07-06/A0001/item_description.txt",
    }

    sheets_workflow.write_phase1_sheet_rows(**kwargs)
    sheets_workflow.write_phase1_sheet_rows(**kwargs)

    draft = spreadsheet.sheets[sheets_workflow.SHEET_NAME_DRAFT_MERCARI]
    review = spreadsheet.sheets[sheets_workflow.SHEET_NAME_REVIEW]
    yahoo = spreadsheet.sheets[sheets_workflow.SHEET_NAME_YAHOO]
    assert draft.values[0] == MERCARI_HEADERS
    assert len(draft.values) == 2
    assert review.values[0] == sheets_workflow.REVIEW_SHEET_HEADERS
    assert review.values[1][0] == "exports/2026-07-06/A0001"
    assert review.values[1][3] == sheets_workflow.REVIEW_STATUS_NEEDS_REVIEW
    assert "brand review" in review.values[1][5]
    assert yahoo.values[0] == YAHOO_HEADERS
    assert len(yahoo.values) == 2


def test_export_approved_mercari_rows_filters_by_batch(monkeypatch):
    spreadsheet = FakeSpreadsheet()
    monkeypatch.setattr(sheets_workflow, "get_spreadsheet", lambda: spreadsheet)
    row_a = sheets_workflow.dict_row_to_list(
        MERCARI_HEADERS,
        mercari_row(
            "https://storage.googleapis.com/product-images/exports/2026-07-06/A0001/001.jpg",
            "A0001",
        ),
    )
    row_b = sheets_workflow.dict_row_to_list(
        MERCARI_HEADERS,
        mercari_row(
            "https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001.jpg",
            "A0001",
        ),
    )
    spreadsheet.sheets[sheets_workflow.SHEET_NAME_DRAFT_MERCARI] = FakeWorksheet(
        sheets_workflow.SHEET_NAME_DRAFT_MERCARI,
        [MERCARI_HEADERS, row_a, row_b],
    )
    spreadsheet.sheets[sheets_workflow.SHEET_NAME_REVIEW] = FakeWorksheet(
        sheets_workflow.SHEET_NAME_REVIEW,
        [
            sheets_workflow.REVIEW_SHEET_HEADERS,
            ["exports/2026-07-06/A0001", "exports/2026-07-06", "A0001", "approved"],
            ["exports/2026-07-07/A0001", "exports/2026-07-07", "A0001", "approved"],
        ],
    )
    spreadsheet.sheets[sheets_workflow.SHEET_NAME_APPROVED_MERCARI] = FakeWorksheet(
        sheets_workflow.SHEET_NAME_APPROVED_MERCARI,
        [["old row"]],
    )

    exported_count = sheets_workflow.export_approved_mercari_rows("exports/2026-07-06")

    approved = spreadsheet.sheets[sheets_workflow.SHEET_NAME_APPROVED_MERCARI]
    assert exported_count == 1
    assert approved.values == [MERCARI_HEADERS, row_a]
    assert approved.update_calls


def test_export_approved_mercari_rows_returns_minus_one_for_unknown_batch(monkeypatch):
    spreadsheet = FakeSpreadsheet()
    monkeypatch.setattr(sheets_workflow, "get_spreadsheet", lambda: spreadsheet)
    spreadsheet.sheets[sheets_workflow.SHEET_NAME_DRAFT_MERCARI] = FakeWorksheet(
        sheets_workflow.SHEET_NAME_DRAFT_MERCARI,
        [MERCARI_HEADERS],
    )
    spreadsheet.sheets[sheets_workflow.SHEET_NAME_REVIEW] = FakeWorksheet(
        sheets_workflow.SHEET_NAME_REVIEW,
        [sheets_workflow.REVIEW_SHEET_HEADERS],
    )
    spreadsheet.sheets[sheets_workflow.SHEET_NAME_APPROVED_MERCARI] = FakeWorksheet(
        sheets_workflow.SHEET_NAME_APPROVED_MERCARI,
        [["old row"]],
    )

    exported_count = sheets_workflow.export_approved_mercari_rows("exports/2026-07-06")

    approved = spreadsheet.sheets[sheets_workflow.SHEET_NAME_APPROVED_MERCARI]
    assert exported_count == -1
    assert approved.values == [["old row"]]
