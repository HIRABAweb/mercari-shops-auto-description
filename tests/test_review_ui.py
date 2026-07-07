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


def csrf_from_session(client) -> str:
    with client.session_transaction() as session:
        token = session.get("csrf_token")
        if not token:
            token = "test-csrf-token"
            session["csrf_token"] = token
        return token


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
    client = module.app.test_client()
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

    response = client.post(
        "/batches/2026-07-07/export",
        data={"csrf_token": csrf_from_session(client)},
    )

    assert response.status_code == 302
    assert uploaded["object"] == "exports/2026-07-07/approved/mercari_shops.csv"


def test_export_post_rejects_missing_csrf(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(module, "export_approved_mercari_rows_and_csv", lambda batch_prefix: (1, "csv"))

    response = module.app.test_client().post("/batches/2026-07-07/export")

    assert response.status_code == 400


def test_save_approve_updates_draft_before_approval(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    calls = []
    monkeypatch.setattr(module, "update_draft_item", lambda *args: calls.append(("update", args)))
    monkeypatch.setattr(module, "approve_review_item", lambda *args: calls.append(("approve", args)))

    response = client.post(
        "/batches/2026-07-07/items/A0001",
        data={
            "csrf_token": csrf_from_session(client),
            "action": "save_approve",
            module.TITLE_FIELD: "Updated title",
        },
    )

    assert response.status_code == 302
    assert [call[0] for call in calls] == ["update", "approve"]
    assert calls[0][1][2][module.TITLE_FIELD] == "Updated title"


def test_cloud_run_requires_flask_secret_key(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("K_SERVICE", "mercari-review-ui")
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        module.create_app()
