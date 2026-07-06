"""Tests for the optional Flask review UI."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


pytest.importorskip("flask")
pytest.importorskip("google.cloud.storage")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "review-ui" / "app.py"


def load_review_ui_module():
    spec = importlib.util.spec_from_file_location("review_ui_app_under_test", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_batches_page_renders_without_live_sheets(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(module, "list_batch_summaries", lambda: [])

    response = module.app.test_client().get("/")

    assert response.status_code == 200
    assert b"Batches" in response.data
    assert b"No batches found." in response.data


def test_item_page_renders_main_fields(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(
        module,
        "get_review_item",
        lambda batch_id, product_code: (
            {
                "review_status": "needs_review",
                "reason": "brand review",
                "suggested_action": "check brand",
            },
            {
                module.TITLE_FIELD: "Coach shoulder bag",
                module.DESCRIPTION_FIELD: "Description",
                "SKU1_商品管理コード": "A0001",
            },
        ),
    )

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001")

    assert response.status_code == 200
    assert b"Coach shoulder bag" in response.data
    assert b"brand review" in response.data
    assert b"Main Fields" in response.data


def test_batch_page_uses_batch_scoped_items(monkeypatch):
    module = load_review_ui_module()
    item = SimpleNamespace(
        first_image_url="https://storage.googleapis.com/bucket/exports/2026-07-07/A0001/001.jpg",
        title="Coach shoulder bag",
        product_code="A0001",
        reason="category review",
        review_status="needs_review",
    )
    monkeypatch.setattr(module, "list_review_items", lambda batch_id: [item])

    response = module.app.test_client().get("/batches/2026-07-07")

    assert response.status_code == 200
    assert b"Coach shoulder bag" in response.data
    assert b"category review" in response.data


def test_export_posts_generates_gcs_object_without_live_gcs(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(module, "list_review_items", lambda batch_id: [])
    monkeypatch.setattr(
        module,
        "export_approved_mercari_rows_and_csv",
        lambda batch_prefix: (1, "header\nrow\n"),
    )
    uploaded = {}
    monkeypatch.setattr(
        module,
        "upload_approved_csv",
        lambda batch_id, csv_text: uploaded.setdefault("object", module.approved_csv_object_name(batch_id)),
    )

    response = module.app.test_client().post("/batches/2026-07-07/export")

    assert response.status_code == 302
    assert uploaded["object"] == "exports/2026-07-07/approved/mercari_shops.csv"
