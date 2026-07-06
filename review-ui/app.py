"""Web review UI for the Phase 1 Mercari approval workflow."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for
from google.cloud import storage


ROOT_DIR = Path(__file__).resolve().parents[1]
YAHUOKU_DIR = ROOT_DIR / "yahuoku-to-mercarishops"
if str(YAHUOKU_DIR) not in sys.path:
    sys.path.insert(0, str(YAHUOKU_DIR))

from csv_export import MERCARI_HEADERS  # noqa: E402
from sheets_workflow import (  # noqa: E402
    approve_review_item,
    batch_id_from_prefix,
    export_approved_mercari_rows_and_csv,
    get_review_item,
    list_batch_summaries,
    list_review_items,
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
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "local-review-ui-secret")

    @app.get("/")
    def batches():
        return render_template("batches.html", batches=list_batch_summaries())

    @app.get("/batches/<path:batch_id>")
    def batch_detail(batch_id: str):
        return render_template(
            "batch_detail.html",
            batch_id=batch_id,
            batch_prefix=normalize_batch_prefix(batch_id),
            items=list_review_items(batch_id),
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
            extra_fields=extra_fields,
            title_field=TITLE_FIELD,
            description_field=DESCRIPTION_FIELD,
        )

    @app.post("/batches/<path:batch_id>/items/<product_code>")
    def update_item(batch_id: str, product_code: str):
        updates = {
            header: request.form.get(header, "")
            for header in MERCARI_HEADERS
            if header in request.form
        }
        try:
            update_draft_item(batch_id, product_code, updates)
        except KeyError:
            abort(404)
        flash("Draft saved.")
        return redirect(url_for("item_detail", batch_id=batch_id, product_code=product_code))

    @app.post("/batches/<path:batch_id>/items/<product_code>/approve")
    def approve_item(batch_id: str, product_code: str):
        approved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            approve_review_item(batch_id, product_code, approved_at)
        except KeyError:
            abort(404)
        flash("Item approved.")
        return redirect(url_for("batch_detail", batch_id=batch_id))

    @app.post("/batches/<path:batch_id>/export")
    def export_batch(batch_id: str):
        exported_count, csv_text = export_approved_mercari_rows_and_csv(
            normalize_batch_prefix(batch_id)
        )
        if exported_count < 0:
            abort(404)
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


def approved_csv_object_name(batch_id: str) -> str:
    normalized_batch_id = batch_id_from_prefix(normalize_batch_prefix(batch_id))
    return APPROVED_CSV_OBJECT_TEMPLATE.format(batch_id=normalized_batch_id)


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
