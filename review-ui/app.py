"""Web review UI for the Phase 1 Mercari approval workflow."""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timezone
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import unquote, urlparse

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from google.cloud import storage


ROOT_DIR = Path(__file__).resolve().parents[1]
YAHUOKU_DIR = ROOT_DIR / "yahuoku-to-mercarishops"
if str(YAHUOKU_DIR) not in sys.path:
    sys.path.insert(0, str(YAHUOKU_DIR))

from csv_export import MERCARI_HEADERS  # noqa: E402
from listing_data import IMAGE_EXTENSIONS  # noqa: E402
from sheets_workflow import (  # noqa: E402
    approve_review_item,
    batch_id_from_prefix,
    export_approved_mercari_rows_and_csv,
    get_review_item,
    list_batch_summaries,
    list_review_items,
    mark_review_item_needs_review,
    normalize_batch_prefix,
    update_draft_item,
)


APPROVED_CSV_OBJECT_TEMPLATE = os.getenv(
    "APPROVED_CSV_OBJECT_TEMPLATE",
    "exports/{batch_id}/approved/mercari_shops.csv",
)

PRIMARY_FIELD_INDICES = [20, 21, 73, 72, 74, 75, 22, 23]
PRIMARY_FIELDS = [MERCARI_HEADERS[index] for index in PRIMARY_FIELD_INDICES]
TITLE_FIELD = MERCARI_HEADERS[20]
DESCRIPTION_FIELD = MERCARI_HEADERS[21]
IMAGE_FIELDS = MERCARI_HEADERS[:20]


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent / "static"),
    )
    app.secret_key = flask_secret_key()
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.get("/")
    def batches():
        return render_template("batches.html", batches=list_batch_summaries())

    @app.get("/healthz")
    def healthz():
        return ("ok\n", 200, {"Content-Type": "text/plain; charset=utf-8"})

    @app.get("/batches/<path:batch_id>")
    def batch_detail(batch_id: str):
        items = list_review_items(batch_id)
        return render_template(
            "batch_detail.html",
            batch_id=batch_id,
            batch_prefix=normalize_batch_prefix(batch_id),
            items=items,
            approved_count=approved_item_count(items),
            total_count=len(items),
        )

    @app.get("/batches/<path:batch_id>/items/<product_code>/images/<int:image_index>")
    def item_image(batch_id: str, product_code: str, image_index: int):
        if image_index < 1 or image_index > len(IMAGE_FIELDS):
            abort(404)
        try:
            _, draft_row = get_review_item(batch_id, product_code)
        except KeyError:
            abort(404)

        image_url = draft_row.get(IMAGE_FIELDS[image_index - 1], "")
        blob_ref = storage_url_to_blob_ref(image_url)
        if not blob_ref:
            abort(404)
        bucket_name, object_name = blob_ref
        if bucket_name != required_env("PRODUCT_BUCKET_NAME"):
            abort(403)
        if not object_name_matches_item(batch_id, product_code, object_name):
            abort(403)
        if not object_name.lower().endswith(IMAGE_EXTENSIONS):
            abort(404)

        blob = storage_client().bucket(bucket_name).blob(object_name)
        if not blob.exists():
            abort(404)
        content_type = blob.content_type or guess_type(object_name)[0] or "application/octet-stream"
        return Response(
            blob.download_as_bytes(),
            mimetype=content_type,
            headers={"Cache-Control": "private, max-age=300"},
        )

    @app.get("/batches/<path:batch_id>/items/<product_code>")
    def item_detail(batch_id: str, product_code: str):
        try:
            review_row, draft_row = get_review_item(batch_id, product_code)
        except KeyError:
            abort(404)
        extra_fields = [
            header
            for header in MERCARI_HEADERS
            if header not in PRIMARY_FIELDS and header not in IMAGE_FIELDS
        ]
        return render_template(
            "item_detail.html",
            batch_id=batch_id,
            product_code=product_code,
            review_row=review_row,
            draft_row=draft_row,
            primary_fields=PRIMARY_FIELDS,
            image_fields=IMAGE_FIELDS,
            image_previews=image_previews_from_draft_row(draft_row),
            extra_fields=extra_fields,
            title_field=TITLE_FIELD,
            description_field=DESCRIPTION_FIELD,
        )

    @app.post("/batches/<path:batch_id>/items/<product_code>")
    def update_item(batch_id: str, product_code: str):
        validate_csrf_token()
        updates = {
            header: request.form.get(header, "")
            for header in MERCARI_HEADERS
            if header in request.form
        }
        try:
            update_draft_item(batch_id, product_code, updates)
        except KeyError:
            abort(404)
        if request.form.get("action") == "save_approve":
            approve_review_item(batch_id, product_code, current_utc_timestamp())
            flash("Draft saved and item approved.")
            return redirect(url_for("batch_detail", batch_id=batch_id))
        mark_review_item_needs_review(batch_id, product_code)
        flash("Draft saved.")
        return redirect(url_for("item_detail", batch_id=batch_id, product_code=product_code))

    @app.post("/batches/<path:batch_id>/export")
    def export_batch(batch_id: str):
        validate_csrf_token()
        exported_count, csv_text = export_approved_mercari_rows_and_csv(
            normalize_batch_prefix(batch_id)
        )
        if exported_count < 0:
            abort(404)
        if exported_count == 0:
            flash("No approved items. Save and approve at least one item before generating CSV.")
            return redirect(url_for("batch_detail", batch_id=batch_id))
        object_name = upload_approved_csv(batch_id, csv_text)
        flash(f"Generated approved CSV with {exported_count} rows: {object_name}")
        return redirect(url_for("batch_detail", batch_id=batch_id))

    @app.get("/batches/<path:batch_id>/download")
    def download_batch(batch_id: str):
        object_name = approved_csv_object_name(batch_id)
        bucket = storage_client().bucket(required_env("PRODUCT_BUCKET_NAME"))
        blob = bucket.blob(object_name)
        if not blob.exists():
            abort(404)
        csv_text = blob.download_as_text(encoding="utf-8-sig")
        return Response(
            csv_text,
            mimetype="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{safe_filename(batch_id)}_mercari_shops.csv"'
                )
            },
        )

    return app


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def flask_secret_key() -> str:
    value = os.getenv("FLASK_SECRET_KEY", "").strip()
    if value:
        return value
    if os.getenv("K_SERVICE"):
        raise RuntimeError("FLASK_SECRET_KEY is required on Cloud Run.")
    return "local-review-ui-secret"


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf_token() -> None:
    expected = session.get("csrf_token")
    actual = request.form.get("csrf_token")
    if not expected or not actual or not secrets.compare_digest(expected, actual):
        abort(400)


def current_utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def approved_csv_object_name(batch_id: str) -> str:
    normalized_batch_id = batch_id_from_prefix(normalize_batch_prefix(batch_id))
    return APPROVED_CSV_OBJECT_TEMPLATE.format(batch_id=normalized_batch_id)


def storage_url_to_blob_ref(image_url: str) -> tuple[str, str] | None:
    parsed = urlparse((image_url or "").strip())
    if parsed.scheme != "https" or parsed.netloc != "storage.googleapis.com":
        return None
    parts = parsed.path.lstrip("/").split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], unquote(parts[1])


def object_name_matches_item(batch_id: str, product_code: str, object_name: str) -> bool:
    batch_prefix = normalize_batch_prefix(batch_id).strip("/")
    if not batch_prefix or not product_code:
        return False
    return object_name.startswith(f"{batch_prefix}/{product_code}/")


def image_previews_from_draft_row(draft_row: dict[str, str]) -> list[dict[str, str | int]]:
    previews = []
    for index, header in enumerate(IMAGE_FIELDS, start=1):
        if draft_row.get(header, "").strip():
            previews.append({"index": index, "header": header})
    return previews


def approved_item_count(items) -> int:
    return sum(
        1
        for item in items
        if getattr(item, "review_status", "").strip().lower() == "approved"
    )


def upload_approved_csv(batch_id: str, csv_text: str) -> str:
    object_name = approved_csv_object_name(batch_id)
    bucket = storage_client().bucket(required_env("PRODUCT_BUCKET_NAME"))
    bucket.blob(object_name).upload_from_string(
        csv_text,
        content_type="text/csv; charset=utf-8",
    )
    return object_name


def safe_filename(value: str) -> str:
    normalized_batch_id = batch_id_from_prefix(normalize_batch_prefix(value))
    return normalized_batch_id.replace("/", "_") or "approved"


def storage_client():
    return storage.Client()


app = create_app()
