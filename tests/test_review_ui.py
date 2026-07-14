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


def test_healthz_does_not_touch_live_sheets(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(
        module,
        "list_batch_summaries",
        lambda: pytest.fail("healthz should not read Google Sheets"),
    )

    response = module.app.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.text == "ok\n"


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


def test_item_page_renders_image_previews_through_proxy(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(
        module,
        "get_review_item",
        lambda batch_id, product_code: (
            {"review_status": "needs_review", "reason": "image review"},
            {
                module.TITLE_FIELD: "Coach shoulder bag",
                module.IMAGE_FIELDS[0]: (
                    "https://storage.googleapis.com/product-images/"
                    "exports/2026-07-07/A0001/001.jpg"
                ),
                module.IMAGE_FIELDS[1]: (
                    "https://storage.googleapis.com/product-images/"
                    "exports/2026-07-07/A0001/002.jpg"
                ),
            },
        ),
    )

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001")

    assert response.status_code == 200
    assert b"Images" in response.data
    assert b'<img src="https://storage.googleapis.com' not in response.data
    assert b"/batches/2026-07-07/items/A0001/images/1" in response.data
    assert b"/batches/2026-07-07/items/A0001/images/2" in response.data


def test_batch_page_uses_batch_scoped_items(monkeypatch):
    module = load_review_ui_module()
    item = SimpleNamespace(
        first_image_url="https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001.jpg",
        title="Coach shoulder bag",
        product_code="A0001",
        reason="category review",
        review_status="needs_review",
    )
    monkeypatch.setattr(module, "list_review_items", lambda batch_id: [item])
    monkeypatch.setattr(
        module,
        "restore_batch_items_from_gcs",
        lambda batch_id: pytest.fail("batch page should not mutate Sheets"),
    )

    response = module.app.test_client().get("/batches/2026-07-07")

    assert response.status_code == 200
    assert b"Coach shoulder bag" in response.data
    assert b"category review" in response.data
    assert b"0 / 1 approved" in response.data
    assert b"storage.googleapis.com" not in response.data
    assert b"/batches/2026-07-07/items/A0001/images/1" in response.data
    assert b"disabled" in response.data


def test_batch_page_enables_export_when_item_is_approved(monkeypatch):
    module = load_review_ui_module()
    item = SimpleNamespace(
        first_image_url="",
        title="Coach shoulder bag",
        product_code="A0001",
        reason="",
        review_status="approved",
    )
    monkeypatch.setattr(module, "list_review_items", lambda batch_id: [item])
    monkeypatch.setattr(module, "approved_csv_exists", lambda batch_id: True)

    response = module.app.test_client().get("/batches/2026-07-07")

    assert response.status_code == 200
    assert b"Generate CSV" in response.data
    assert b"1 / 1 approved" in response.data
    assert b"disabled" not in response.data


def test_batch_page_disables_download_when_approved_csv_is_missing(monkeypatch):
    module = load_review_ui_module()
    item = SimpleNamespace(
        first_image_url="",
        title="Coach shoulder bag",
        product_code="A0001",
        reason="",
        review_status="approved",
    )
    monkeypatch.setattr(module, "list_review_items", lambda batch_id: [item])
    monkeypatch.setattr(module, "approved_csv_exists", lambda batch_id: False)

    response = module.app.test_client().get("/batches/2026-07-07")

    assert response.status_code == 200
    assert b"Download CSV" in response.data
    assert b"button--disabled" in response.data


def test_storage_url_to_blob_ref_accepts_storage_googleapis_url():
    module = load_review_ui_module()

    blob_ref = module.storage_url_to_blob_ref(
        "https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001%20main.jpg"
    )

    assert blob_ref == ("product-images", "exports/2026-07-07/A0001/001 main.jpg")


def test_storage_url_to_blob_ref_rejects_non_gcs_url():
    module = load_review_ui_module()

    assert module.storage_url_to_blob_ref("https://example.com/image.jpg") is None
    assert module.storage_url_to_blob_ref("gs://product-images/path/image.jpg") is None
    assert module.storage_url_to_blob_ref("https://storage.googleapis.com/product-images") is None


def test_item_image_proxies_private_gcs_image(monkeypatch):
    module = load_review_ui_module()
    image_url = "https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001.jpg"
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    monkeypatch.setattr(
        module,
        "get_review_item",
        lambda batch_id, product_code: (
            {"review_status": "needs_review"},
            {module.IMAGE_FIELDS[0]: image_url},
        ),
    )

    class FakeBlob:
        content_type = "image/jpeg"

        def exists(self):
            return True

        def download_as_bytes(self):
            return b"fake-jpeg-bytes"

    class FakeBucket:
        def __init__(self):
            self.requested_object_name = None

        def blob(self, object_name):
            self.requested_object_name = object_name
            return FakeBlob()

    class FakeStorageClient:
        def __init__(self):
            self.bucket_obj = FakeBucket()

        def bucket(self, bucket_name):
            assert bucket_name == "product-images"
            return self.bucket_obj

    fake_client = FakeStorageClient()
    monkeypatch.setattr(module, "storage_client", lambda: fake_client)

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001/images/1")

    assert response.status_code == 200
    assert response.mimetype == "image/jpeg"
    assert response.headers["Cache-Control"] == "private, max-age=300"
    assert response.data == b"fake-jpeg-bytes"
    assert fake_client.bucket_obj.requested_object_name == "exports/2026-07-07/A0001/001.jpg"


def test_item_image_rejects_other_bucket(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    monkeypatch.setattr(
        module,
        "get_review_item",
        lambda batch_id, product_code: (
            {"review_status": "needs_review"},
            {module.IMAGE_FIELDS[0]: "https://storage.googleapis.com/other-bucket/image.jpg"},
        ),
    )

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001/images/1")

    assert response.status_code == 403


def test_item_image_rejects_other_object_in_same_bucket(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    monkeypatch.setattr(
        module,
        "get_review_item",
        lambda batch_id, product_code: (
            {"review_status": "needs_review"},
            {
                module.IMAGE_FIELDS[0]: (
                    "https://storage.googleapis.com/product-images/"
                    "exports/2026-07-07/OTHER/001.jpg"
                )
            },
        ),
    )

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001/images/1")

    assert response.status_code == 403


def test_item_image_rejects_non_image_extension(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    monkeypatch.setattr(
        module,
        "get_review_item",
        lambda batch_id, product_code: (
            {"review_status": "needs_review"},
            {
                module.IMAGE_FIELDS[0]: (
                    "https://storage.googleapis.com/product-images/"
                    "exports/2026-07-07/A0001/_SUCCESS.txt"
                )
            },
        ),
    )

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001/images/1")

    assert response.status_code == 404


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


def test_export_post_does_not_upload_when_no_approved_rows(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    monkeypatch.setattr(module, "list_review_items", lambda batch_id: [])
    monkeypatch.setattr(
        module,
        "export_approved_mercari_rows_and_csv",
        lambda batch_prefix: (0, "header\n"),
    )
    uploaded = []
    monkeypatch.setattr(
        module,
        "upload_approved_csv",
        lambda batch_id, csv_text: uploaded.append((batch_id, csv_text)),
    )

    response = client.post(
        "/batches/2026-07-07/export",
        data={"csrf_token": csrf_from_session(client)},
    )

    assert response.status_code == 302
    assert uploaded == []


def test_download_redirects_when_csv_has_not_been_generated(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")

    class FakeBlob:
        def exists(self):
            return False

    class FakeBucket:
        def blob(self, object_name):
            return FakeBlob()

    class FakeStorageClient:
        def bucket(self, bucket_name):
            assert bucket_name == "product-images"
            return FakeBucket()

    monkeypatch.setattr(module, "storage_client", lambda: FakeStorageClient())

    response = module.app.test_client().get("/batches/2026-07-07/download")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/batches/2026-07-07")


def test_item_page_redirects_when_draft_is_missing(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(module, "get_review_item", lambda batch_id, product_code: (_ for _ in ()).throw(KeyError("missing")))

    response = module.app.test_client().get("/batches/2026-07-07/items/A0001")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/batches/2026-07-07")


def test_restore_batch_items_from_gcs_repairs_review_and_draft(monkeypatch):
    module = load_review_ui_module()
    calls = {"review": [], "draft": []}

    class FakeBlob:
        def __init__(self, name, text):
            self.name = name
            self.text = text

        def exists(self):
            return True

        def download_as_text(self, encoding="utf-8"):
            return self.text

    result_text = (
        '{"outputs": {'
        '"mercari_csv": "exports/exports%2F2026-07-07%2FA0001/mercari.csv",'
        '"review_required_csv": "exports/exports%2F2026-07-07%2FA0001/review_required.csv"'
        "}}"
    )
    mercari_text = (
        "商品画像名_1,商品名,商品説明,SKU1_商品管理コード\n"
        "https://storage.googleapis.com/product-images/exports/2026-07-07/A0001/001.jpg,"
        "Restored title,Restored description,A0001\n"
    )
    review_text = "商品管理コード,確認項目,候補1,候補2,理由\nA0001,カテゴリID,,,カテゴリ不明\n"
    blobs = {
        "exports/exports%2F2026-07-07%2FA0001/result.json": FakeBlob(
            "exports/exports%2F2026-07-07%2FA0001/result.json",
            result_text,
        ),
        "exports/exports%2F2026-07-07%2FA0001/mercari.csv": FakeBlob(
            "exports/exports%2F2026-07-07%2FA0001/mercari.csv",
            mercari_text,
        ),
        "exports/exports%2F2026-07-07%2FA0001/review_required.csv": FakeBlob(
            "exports/exports%2F2026-07-07%2FA0001/review_required.csv",
            review_text,
        ),
    }

    class FakeBucket:
        def blob(self, object_name):
            return blobs[object_name]

    class FakeStorageClient:
        def bucket(self, bucket_name):
            assert bucket_name == "product-images"
            return FakeBucket()

        def list_blobs(self, bucket_name, prefix):
            assert bucket_name == "product-images"
            assert prefix == "exports/exports%2F2026-07-07%2F"
            return [blobs["exports/exports%2F2026-07-07%2FA0001/result.json"]]

    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    monkeypatch.setattr(module, "storage_client", lambda: FakeStorageClient())
    monkeypatch.setattr(
        module,
        "ensure_review_item",
        lambda *args: calls["review"].append(args) or True,
    )
    monkeypatch.setattr(
        module,
        "ensure_draft_item",
        lambda *args: calls["draft"].append(args) or True,
    )

    result = module.restore_batch_items_from_gcs("2026-07-07")

    assert result.artifacts_found == 1
    assert result.review_added == 1
    assert result.draft_added == 1
    assert result.errors == []
    assert calls["review"][0][0:3] == (
        "exports/2026-07-07",
        "A0001",
        "exports/2026-07-07/A0001/_description.txt",
    )
    assert calls["draft"][0][0:2] == ("exports/2026-07-07", "A0001")


def test_repair_post_runs_gcs_restore(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    calls = []
    monkeypatch.setattr(
        module,
        "restore_batch_items_from_gcs",
        lambda batch_id: calls.append(batch_id) or module.RepairResult(
            artifacts_found=2,
            review_added=1,
            draft_added=1,
            skipped=1,
            errors=[],
        ),
    )

    response = client.post(
        "/batches/2026-07-07/repair",
        data={"csrf_token": csrf_from_session(client)},
    )

    assert response.status_code == 302
    assert calls == ["2026-07-07"]


def test_repair_post_rejects_missing_csrf(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setattr(
        module,
        "restore_batch_items_from_gcs",
        lambda batch_id: pytest.fail("repair should require CSRF"),
    )

    response = module.app.test_client().post("/batches/2026-07-07/repair")

    assert response.status_code == 400


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


def test_save_without_approval_returns_item_to_needs_review(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    calls = []
    monkeypatch.setattr(module, "update_draft_item", lambda *args: calls.append(("update", args)))
    monkeypatch.setattr(
        module,
        "mark_review_item_needs_review",
        lambda *args: calls.append(("needs_review", args)),
    )

    response = client.post(
        "/batches/2026-07-07/items/A0001",
        data={
            "csrf_token": csrf_from_session(client),
            "action": "save",
            module.TITLE_FIELD: "Edited title",
        },
    )

    assert response.status_code == 302
    assert [call[0] for call in calls] == ["update", "needs_review"]
    assert calls[1][1] == ("2026-07-07", "A0001")


def test_standalone_approve_route_is_not_available():
    module = load_review_ui_module()

    response = module.app.test_client().post("/batches/2026-07-07/items/A0001/approve")

    assert response.status_code == 405


def test_cloud_run_requires_flask_secret_key(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("K_SERVICE", "mercari-review-ui")
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        module.create_app()
