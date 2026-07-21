"""Tests for the optional Flask review UI."""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
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


def valid_mercari_row(module, product_code="A0001"):
    row = {header: "" for header in module.MERCARI_HEADERS}
    row.update(
        {
            "商品画像名_1": (
                "https://storage.googleapis.com/product-images/"
                f"exports/2026-07-07/{product_code}/001.jpg"
            ),
            "商品名": "Approved title",
            "商品説明": "Description",
            "SKU1_種類": "M",
            "SKU1_在庫数": "1",
            "SKU1_商品管理コード": product_code,
            "販売価格": "1000",
            "カテゴリID": "category-id",
            "商品の状態": "3",
            "配送方法": "3",
            "発送元の地域": "jp34",
            "発送までの日数": "2",
            "商品ステータス": "1",
            "配送料の負担": "1",
        }
    )
    return row


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


def test_category_search_api_returns_ranked_candidates(monkeypatch, tmp_path):
    module = load_review_ui_module()
    category_master = tmp_path / "category_master_updated.csv"
    category_master.write_text(
        (
            "\u30ab\u30c6\u30b4\u30eaID,"
            "\u30ab\u30c6\u30b4\u30ea\u540d,"
            "\u30ab\u30c6\u30b4\u30ea\u540d\uff08\u30d5\u30eb\uff09\n"
            "razor,\u30e1\u30f3\u30ba\u5243\u5200,"
            "\u30b3\u30b9\u30e1\u30fb\u7f8e\u5bb9 > \u7f8e\u5bb9\u5bb6\u96fb > \u30e1\u30f3\u30ba\u5243\u5200\n"
            "mens-t,\u0054\u30b7\u30e3\u30c4,"
            "\u30d5\u30a1\u30c3\u30b7\u30e7\u30f3 > \u30e1\u30f3\u30ba > \u30c8\u30c3\u30d7\u30b9 > \u0054\u30b7\u30e3\u30c4\n"
            "goods-t,\u0054\u30b7\u30e3\u30c4\u30fb\u30a2\u30d1\u30ec\u30eb,"
            "\u30b2\u30fc\u30e0 > \u30ad\u30e3\u30e9\u30af\u30bf\u30fc\u30b0\u30c3\u30ba > \u0054\u30b7\u30e3\u30c4\u30fb\u30a2\u30d1\u30ec\u30eb\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "CATEGORY_MASTER_PATH", category_master)
    module.load_category_master_rows.cache_clear()

    response = module.app.test_client().get(
        "/api/categories",
        query_string={"q": "\u30e1\u30f3\u30ba \u0054\u30b7\u30e3\u30c4"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["categories"][0]["category_id"] == "mens-t"
    assert data["categories"][0]["all_terms_matched"] is True

    module.load_category_master_rows.cache_clear()


def test_category_field_targets_category_id_not_price():
    module = load_review_ui_module()

    assert module.CATEGORY_ID_FIELD == "カテゴリID"
    assert module.CATEGORY_ID_FIELD != "販売価格"


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
    assert b"data-category-helper" in response.data
    assert 'name="カテゴリID"'.encode() in response.data
    assert 'name="販売価格" value="" data-category-id-input'.encode() not in response.data
    assert b"Image URLs" not in response.data
    assert b"Unused product image names (20)" in response.data
    for header in module.IMAGE_FIELDS:
        assert response.data.count(f'name="{header}"'.encode()) == 1
    assert b"data-price-input" in response.data


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
    assert b"Image URLs" not in response.data
    assert response.data.count(
        b'<figure class="image-preview" data-image-sort-row draggable="true">'
    ) == 2
    assert response.data.count(b'draggable="true"') == 2
    assert b"data-image-sort-input" in response.data
    assert b"data-image-drag-handle" in response.data
    assert b"data-image-move-up" in response.data
    assert b"data-image-move-down" in response.data
    assert b'addEventListener("pointerdown"' in response.data
    assert b'addEventListener("pointermove"' in response.data
    assert b"Product image name" in response.data
    assert b"Unused product image names (18)" in response.data
    assert b"data-image-url-input" not in response.data
    for header in module.IMAGE_FIELDS:
        assert response.data.count(f'name="{header}"'.encode()) == 1
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
    assert "欠けた商品を復元" in response.data.decode("utf-8")
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


def test_prepare_mercari_upload_rows_signs_private_gcs_images(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    monkeypatch.setenv("MERCARI_IMAGE_SIGNED_URL_TTL_HOURS", "168")
    signing_credentials = object()
    monkeypatch.setattr(module, "iam_signing_credentials", lambda: signing_credentials)

    class FakeBlob:
        def __init__(self, object_name):
            self.object_name = object_name

        def exists(self):
            return True

        def generate_signed_url(self, **kwargs):
            assert kwargs["version"] == "v4"
            assert kwargs["method"] == "GET"
            assert kwargs["credentials"] is signing_credentials
            return f"https://storage.googleapis.com/product-images/{self.object_name}?signed=yes"

    class FakeBucket:
        def blob(self, object_name):
            return FakeBlob(object_name)

    class FakeStorageClient:
        def bucket(self, bucket_name):
            assert bucket_name == "product-images"
            return FakeBucket()

    monkeypatch.setattr(module, "storage_client", lambda: FakeStorageClient())
    row = valid_mercari_row(module)

    upload_rows, expires_at = module.prepare_mercari_upload_rows(
        "2026-07-07",
        [module.dict_row_to_list(module.MERCARI_HEADERS, row)],
    )

    assert upload_rows[0]["商品画像名_1"].endswith("?signed=yes")
    assert expires_at > datetime.now(timezone.utc) + timedelta(days=6)


def test_prepare_mercari_upload_rows_rejects_missing_image(monkeypatch):
    module = load_review_ui_module()
    row = valid_mercari_row(module)
    row["商品画像名_1"] = ""

    with pytest.raises(module.MercariExportValidationError) as error:
        module.prepare_mercari_upload_rows(
            "2026-07-07",
            [module.dict_row_to_list(module.MERCARI_HEADERS, row)],
        )

    assert error.value.issues[0].field == "商品画像名_1"


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
    row = valid_mercari_row(module)
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    monkeypatch.setattr(
        module,
        "build_approved_mercari_sheet_rows",
        lambda batch_prefix: [
            module.MERCARI_HEADERS,
            module.dict_row_to_list(module.MERCARI_HEADERS, row),
        ],
    )
    monkeypatch.setattr(
        module,
        "prepare_mercari_upload_rows",
        lambda batch_id, rows: ([row], expires_at),
    )
    replaced = []
    monkeypatch.setattr(
        module,
        "replace_approved_mercari_sheet_rows",
        lambda rows: replaced.append(rows),
    )
    uploaded = {}
    monkeypatch.setattr(
        module,
        "upload_approved_csv",
        lambda batch_id, csv_bytes, expires: uploaded.update(
            {
                "object": module.approved_csv_object_name(batch_id),
                "csv_bytes": csv_bytes,
                "expires": expires,
            }
        )
        or uploaded["object"],
    )

    response = client.post(
        "/batches/2026-07-07/export",
        data={"csrf_token": csrf_from_session(client)},
    )

    assert response.status_code == 302
    assert uploaded["object"] == "exports/2026-07-07/approved/mercari_shops.csv"
    assert uploaded["csv_bytes"].startswith(b"\xef\xbb\xbf")
    assert uploaded["expires"] == expires_at
    assert replaced[0][0] == module.MERCARI_HEADERS


def test_export_post_does_not_upload_when_no_approved_rows(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    monkeypatch.setattr(
        module,
        "build_approved_mercari_sheet_rows",
        lambda batch_prefix: [],
    )
    uploaded = []
    monkeypatch.setattr(
        module,
        "upload_approved_csv",
        lambda batch_id, csv_bytes, expires: uploaded.append((batch_id, csv_bytes, expires)),
    )

    response = client.post(
        "/batches/2026-07-07/export",
        data={"csrf_token": csrf_from_session(client)},
    )

    assert response.status_code == 302
    assert uploaded == []


def test_export_validation_error_deletes_stale_csv_and_shows_item_error(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    monkeypatch.setattr(
        module,
        "build_approved_mercari_sheet_rows",
        lambda batch_prefix: [module.MERCARI_HEADERS, [""] * len(module.MERCARI_HEADERS)],
    )
    issue = module.MercariValidationIssue("A0001", "販売価格", "300円以上で入力してください")
    monkeypatch.setattr(
        module,
        "prepare_mercari_upload_rows",
        lambda batch_id, rows: (_ for _ in ()).throw(
            module.MercariExportValidationError([issue])
        ),
    )
    deleted = []
    monkeypatch.setattr(
        module,
        "delete_approved_csv_if_exists",
        lambda batch_id: deleted.append(batch_id),
    )
    monkeypatch.setattr(
        module,
        "upload_approved_csv",
        lambda *args: pytest.fail("invalid CSV must not be uploaded"),
    )

    response = client.post(
        "/batches/2026-07-07/export",
        data={"csrf_token": csrf_from_session(client)},
    )

    assert response.status_code == 302
    assert deleted == ["2026-07-07"]
    with client.session_transaction() as session:
        messages = [message for _, message in session["_flashes"]]
    assert any("A0001 / 販売価格" in message for message in messages)


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


def test_download_preserves_utf8_bom_bytes(monkeypatch):
    module = load_review_ui_module()
    csv_bytes = b"\xef\xbb\xbfheader\r\nrow\r\n"

    class FakeBlob:
        def download_as_bytes(self):
            return csv_bytes

    monkeypatch.setattr(module, "current_approved_csv_blob", lambda batch_id: FakeBlob())

    response = module.app.test_client().get("/batches/2026-07-07/download")

    assert response.status_code == 200
    assert response.data == csv_bytes
    assert response.headers["Content-Disposition"].endswith(
        'filename="2026-07-07_mercari_shops.csv"'
    )


def test_current_approved_csv_rejects_legacy_or_expired_file(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")

    class FakeBlob:
        def __init__(self, metadata):
            self.metadata = metadata

        def exists(self):
            return True

        def reload(self):
            return None

    class FakeBucket:
        def __init__(self, blob):
            self._blob = blob

        def blob(self, object_name):
            return self._blob

    class FakeStorageClient:
        def __init__(self, blob):
            self._blob = blob

        def bucket(self, bucket_name):
            return FakeBucket(self._blob)

    legacy_blob = FakeBlob({})
    monkeypatch.setattr(module, "storage_client", lambda: FakeStorageClient(legacy_blob))
    assert module.current_approved_csv_blob("2026-07-07") is None

    expired_blob = FakeBlob(
        {
            module.APPROVED_CSV_EXPIRES_METADATA: (
                datetime.now(timezone.utc) - timedelta(minutes=1)
            ).isoformat()
        }
    )
    monkeypatch.setattr(module, "storage_client", lambda: FakeStorageClient(expired_blob))
    assert module.current_approved_csv_blob("2026-07-07") is None


def test_upload_approved_csv_sets_expiration_metadata(monkeypatch):
    module = load_review_ui_module()
    monkeypatch.setenv("PRODUCT_BUCKET_NAME", "product-images")
    expires_at = datetime.now(timezone.utc) + timedelta(days=7)

    class FakeBlob:
        def __init__(self):
            self.metadata = None
            self.upload = None

        def upload_from_string(self, data, content_type):
            self.upload = (data, content_type)

    blob = FakeBlob()

    class FakeBucket:
        def blob(self, object_name):
            assert object_name == "exports/2026-07-07/approved/mercari_shops.csv"
            return blob

    class FakeStorageClient:
        def bucket(self, bucket_name):
            assert bucket_name == "product-images"
            return FakeBucket()

    monkeypatch.setattr(module, "storage_client", lambda: FakeStorageClient())

    object_name = module.upload_approved_csv(
        "2026-07-07",
        b"\xef\xbb\xbfcsv",
        expires_at,
    )

    assert object_name == "exports/2026-07-07/approved/mercari_shops.csv"
    assert blob.upload == (b"\xef\xbb\xbfcsv", "text/csv; charset=utf-8")
    assert blob.metadata[module.APPROVED_CSV_COLUMNS_METADATA] == "88"
    assert module.parse_approved_csv_expiration(
        blob.metadata[module.APPROVED_CSV_EXPIRES_METADATA]
    ) == expires_at


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
    monkeypatch.setattr(
        module,
        "build_approved_mercari_sheet_rows",
        lambda batch_prefix: pytest.fail("export should require CSRF"),
    )

    response = module.app.test_client().post("/batches/2026-07-07/export")

    assert response.status_code == 400


def test_save_approve_updates_draft_before_approval(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    calls = []
    monkeypatch.setattr(module, "update_draft_item", lambda *args: calls.append(("update", args)))
    monkeypatch.setattr(module, "approve_review_item", lambda *args: calls.append(("approve", args)))
    monkeypatch.setattr(
        module,
        "delete_approved_csv_if_exists",
        lambda *args: calls.append(("delete_csv", args)),
    )

    response = client.post(
        "/batches/2026-07-07/items/A0001",
        data={
            "csrf_token": csrf_from_session(client),
            "action": "save_approve",
            module.TITLE_FIELD: "Updated title",
            module.PRICE_FIELD: "１２,abc345円",
        },
    )

    assert response.status_code == 302
    assert [call[0] for call in calls] == ["update", "delete_csv", "approve"]
    assert calls[0][1][2][module.TITLE_FIELD] == "Updated title"
    assert calls[0][1][2][module.PRICE_FIELD] == "12345"
    assert calls[1][1] == ("2026-07-07",)


def test_save_preserves_reordered_hidden_image_fields(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    saved_updates = []
    monkeypatch.setattr(
        module,
        "update_draft_item",
        lambda batch_id, product_code, updates: saved_updates.append(updates),
    )
    monkeypatch.setattr(module, "delete_approved_csv_if_exists", lambda batch_id: None)
    monkeypatch.setattr(
        module,
        "mark_review_item_needs_review",
        lambda batch_id, product_code: None,
    )
    image_values = {
        header: f"https://storage.googleapis.com/product-images/{index}.jpg"
        if index <= 2
        else ""
        for index, header in enumerate(module.IMAGE_FIELDS, start=1)
    }
    first_header, second_header = module.IMAGE_FIELDS[:2]
    image_values[first_header], image_values[second_header] = (
        image_values[second_header],
        image_values[first_header],
    )

    response = client.post(
        "/batches/2026-07-07/items/A0001",
        data={
            "csrf_token": csrf_from_session(client),
            "action": "save",
            **image_values,
        },
    )

    assert response.status_code == 302
    assert len(saved_updates) == 1
    assert saved_updates[0][first_header].endswith("/2.jpg")
    assert saved_updates[0][second_header].endswith("/1.jpg")
    assert all(header in saved_updates[0] for header in module.IMAGE_FIELDS)
    csv_row = module.dict_row_to_list(module.MERCARI_HEADERS, saved_updates[0])
    assert csv_row[0].endswith("/2.jpg")
    assert csv_row[1].endswith("/1.jpg")


def test_save_without_approval_returns_item_to_needs_review(monkeypatch):
    module = load_review_ui_module()
    client = module.app.test_client()
    calls = []
    monkeypatch.setattr(module, "update_draft_item", lambda *args: calls.append(("update", args)))
    monkeypatch.setattr(
        module,
        "delete_approved_csv_if_exists",
        lambda *args: calls.append(("delete_csv", args)),
    )
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
    assert [call[0] for call in calls] == ["update", "delete_csv", "needs_review"]
    assert calls[2][1] == ("2026-07-07", "A0001")


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
