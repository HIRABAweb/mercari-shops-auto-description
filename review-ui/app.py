"""Web review UI for the Phase 1 Mercari approval workflow."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from functools import lru_cache
from mimetypes import guess_type
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from flask import Flask, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from google.cloud import storage


LOGGER = logging.getLogger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[1]
YAHUOKU_DIR = ROOT_DIR / "yahuoku-to-mercarishops"
if str(YAHUOKU_DIR) not in sys.path:
    sys.path.insert(0, str(YAHUOKU_DIR))

from csv_export import MERCARI_HEADERS, REVIEW_REQUIRED_HEADERS  # noqa: E402
from listing_data import IMAGE_EXTENSIONS  # noqa: E402
from sheets_workflow import (  # noqa: E402
    approve_review_item,
    batch_id_from_prefix,
    ensure_draft_item,
    ensure_review_item,
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
CATEGORY_ID_FIELD = MERCARI_HEADERS[74]
PRICE_FIELD = MERCARI_HEADERS[73]
IMAGE_FIELDS = MERCARI_HEADERS[:20]
CATEGORY_MASTER_PATH = YAHUOKU_DIR / "resources" / "mercari" / "category_master_updated.csv"
CATEGORY_MASTER_ID_HEADER = "\u30ab\u30c6\u30b4\u30eaID"
CATEGORY_MASTER_NAME_HEADER = "\u30ab\u30c6\u30b4\u30ea\u540d"
CATEGORY_MASTER_FULL_NAME_HEADER = "\u30ab\u30c6\u30b4\u30ea\u540d\uff08\u30d5\u30eb\uff09"


class RepairResult:
    def __init__(
        self,
        *,
        artifacts_found: int = 0,
        review_added: int = 0,
        draft_added: int = 0,
        skipped: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        self.artifacts_found = artifacts_found
        self.review_added = review_added
        self.draft_added = draft_added
        self.skipped = skipped
        self.errors = errors or []


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

    @app.get("/api/categories")
    def category_search_api():
        query = request.args.get("q", "")
        return jsonify({"query": query, "categories": search_categories(query)})

    @app.get("/batches/<path:batch_id>")
    def batch_detail(batch_id: str):
        items = list_review_items(batch_id)
        approved_count = approved_item_count(items)
        return render_template(
            "batch_detail.html",
            batch_id=batch_id,
            batch_prefix=normalize_batch_prefix(batch_id),
            items=items,
            approved_count=approved_count,
            total_count=len(items),
            approved_csv_available=approved_csv_exists(batch_id),
        )

    @app.post("/batches/<path:batch_id>/repair")
    def repair_batch(batch_id: str):
        validate_csrf_token()
        result = restore_batch_items_from_gcs(batch_id)
        flash(repair_result_message(result))
        return redirect(url_for("batch_detail", batch_id=batch_id))

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
            flash("Draft row is missing. Run Repair from GCS, then open the item again.")
            return redirect(url_for("batch_detail", batch_id=batch_id))
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
            category_field=CATEGORY_ID_FIELD,
            price_field=PRICE_FIELD,
        )

    @app.post("/batches/<path:batch_id>/items/<product_code>")
    def update_item(batch_id: str, product_code: str):
        validate_csrf_token()
        updates = {
            header: request.form.get(header, "")
            for header in MERCARI_HEADERS
            if header in request.form
        }
        if PRICE_FIELD in updates:
            updates[PRICE_FIELD] = sanitize_price(updates[PRICE_FIELD])
        try:
            update_draft_item(batch_id, product_code, updates)
        except KeyError:
            flash("Draft row is missing. Run Repair from GCS, then save again.")
            return redirect(url_for("batch_detail", batch_id=batch_id))
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
            flash("Approved CSV has not been generated yet. Approve at least one item and generate it first.")
            return redirect(url_for("batch_detail", batch_id=batch_id))
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


def approved_csv_exists(batch_id: str) -> bool:
    try:
        object_name = approved_csv_object_name(batch_id)
        bucket_name = required_env("PRODUCT_BUCKET_NAME")
        bucket = storage_client().bucket(bucket_name)
        return bucket.blob(object_name).exists()
    except Exception:
        LOGGER.exception("Failed to check approved CSV existence. batch_id=%s", batch_id)
        return False


def restore_batch_items_from_gcs(batch_id: str) -> RepairResult:
    result = RepairResult()
    bucket_name = required_env("PRODUCT_BUCKET_NAME")
    bucket = storage_client().bucket(bucket_name)
    batch_prefix = normalize_batch_prefix(batch_id)
    object_prefix = encoded_artifact_prefix_for_batch(batch_prefix)

    for result_blob in storage_client().list_blobs(bucket_name, prefix=object_prefix):
        artifact = artifact_from_result_blob_name(result_blob.name)
        if not artifact or artifact["batch_prefix"] != batch_prefix:
            continue
        result.artifacts_found += 1
        product_code = artifact["product_code"]
        try:
            result_data = json.loads(result_blob.download_as_text(encoding="utf-8"))
            outputs = result_data.get("outputs", {})
            mercari_csv_object = outputs.get("mercari_csv") or artifact_output_object(
                batch_prefix, product_code, "mercari.csv"
            )
            review_csv_object = outputs.get("review_required_csv") or artifact_output_object(
                batch_prefix, product_code, "review_required.csv"
            )
            mercari_row = first_mercari_csv_row(
                download_blob_text(bucket, mercari_csv_object, encoding="utf-8-sig")
            )
            if not mercari_row:
                raise ValueError(f"Mercari CSV has no data row: {mercari_csv_object}")
            review_rows = review_required_csv_rows(
                download_blob_text(bucket, review_csv_object, encoding="utf-8-sig")
            )
            review_added = ensure_review_item(
                batch_prefix,
                product_code,
                artifact["file_path"],
                review_rows,
            )
            draft_added = ensure_draft_item(batch_prefix, product_code, mercari_row)
            result.review_added += 1 if review_added else 0
            result.draft_added += 1 if draft_added else 0
            if not review_added and not draft_added:
                result.skipped += 1
        except Exception as error:
            message = f"{product_code}: {error}"
            result.errors.append(message)
            LOGGER.exception("Failed to repair review item. batch=%s product=%s", batch_prefix, product_code)

    LOGGER.info(
        "Review repair finished. batch=%s artifacts=%s review_added=%s draft_added=%s skipped=%s errors=%s",
        batch_prefix,
        result.artifacts_found,
        result.review_added,
        result.draft_added,
        result.skipped,
        len(result.errors),
    )
    return result


def encoded_artifact_prefix_for_batch(batch_prefix: str) -> str:
    normalized = batch_prefix.strip("/")
    return f"exports/{quote(f'{normalized}/', safe='')}"


def artifact_output_object(batch_prefix: str, product_code: str, file_name: str) -> str:
    artifact_prefix = quote(f"{batch_prefix.strip('/')}/{product_code}", safe="")
    return f"exports/{artifact_prefix}/{file_name}"


def download_blob_text(bucket, object_name: str, *, encoding: str) -> str:
    if not object_name:
        raise FileNotFoundError("empty object name")
    blob = bucket.blob(object_name)
    if not blob.exists():
        raise FileNotFoundError(object_name)
    return blob.download_as_text(encoding=encoding)


def repair_result_message(result: RepairResult) -> str:
    message = (
        "Repair from GCS finished: "
        f"artifacts={result.artifacts_found}, "
        f"review_added={result.review_added}, "
        f"draft_added={result.draft_added}, "
        f"skipped={result.skipped}, "
        f"errors={len(result.errors)}."
    )
    if result.errors:
        return f"{message} First errors: {'; '.join(result.errors[:3])}"
    return message


def sanitize_price(value: str) -> str:
    translated = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return re.sub(r"[^0-9]", "", translated)


@lru_cache(maxsize=1)
def load_category_master_rows() -> tuple[dict[str, str], ...]:
    with CATEGORY_MASTER_PATH.open(encoding="utf-8-sig", newline="") as category_file:
        reader = csv.DictReader(category_file)
        return tuple(
            {
                "category_id": (row.get(CATEGORY_MASTER_ID_HEADER) or "").strip(),
                "category_name": (row.get(CATEGORY_MASTER_NAME_HEADER) or "").strip(),
                "full_name": (row.get(CATEGORY_MASTER_FULL_NAME_HEADER) or "").strip(),
            }
            for row in reader
            if (row.get(CATEGORY_MASTER_ID_HEADER) or "").strip()
        )


def search_categories(query: str, limit: int = 8) -> list[dict[str, str]]:
    tokens = category_query_tokens(query)
    if not tokens:
        return []

    scored = []
    for row in load_category_master_rows():
        score, all_terms_matched = category_match_score(row, tokens)
        if score <= 0:
            continue
        scored.append((score, all_terms_matched, row))

    scored.sort(
        key=lambda item: (
            -int(item[1]),
            -item[0],
            len(item[2]["full_name"]),
            item[2]["full_name"],
        )
    )
    return [
        {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "full_name": row["full_name"],
            "all_terms_matched": all_terms_matched,
        }
        for score, all_terms_matched, row in scored[:limit]
    ]


def category_query_tokens(query: str) -> list[str]:
    return [
        normalize_category_search_text(token)
        for token in re.split(r"[\s\u3000]+", query)
        if normalize_category_search_text(token)
    ]


def normalize_category_search_text(value: str) -> str:
    return re.sub(r"[\s\u3000・/／>＞_\-ー]+", "", value.casefold())


def category_match_score(row: dict[str, str], tokens: list[str]) -> tuple[int, bool]:
    normalized_name = normalize_category_search_text(row["category_name"])
    normalized_full_name = normalize_category_search_text(row["full_name"])
    score = 0
    missing = 0
    for index, token in enumerate(tokens):
        is_last_token = index == len(tokens) - 1
        if token in normalized_name:
            score += 20 if is_last_token else 12
        elif token in normalized_full_name:
            score += 10 if is_last_token else 6
        else:
            missing += 1

    if score <= 0:
        return 0, False
    if row["category_name"] == "\u305d\u306e\u4ed6":
        score -= 2
    score -= missing * 3
    return max(score, 0), missing == 0


def artifact_from_result_blob_name(object_name: str) -> dict[str, str] | None:
    if not object_name.startswith("exports/") or not object_name.endswith("/result.json"):
        return None
    encoded_folder = object_name.removeprefix("exports/").removesuffix("/result.json")
    folder_path = unquote(encoded_folder)
    parts = [part for part in folder_path.split("/") if part]
    if len(parts) < 3 or parts[0] != "exports":
        return None
    product_code = parts[-1]
    batch_prefix = "/".join(parts[:-1])
    return {
        "batch_prefix": batch_prefix,
        "product_code": product_code,
        "file_path": f"{folder_path}/_description.txt",
    }


def download_mercari_artifact_csv(batch_id: str, product_code: str) -> str:
    bucket = storage_client().bucket(required_env("PRODUCT_BUCKET_NAME"))
    object_name = artifact_output_object(
        normalize_batch_prefix(batch_id),
        product_code,
        "mercari.csv",
    )
    return download_blob_text(bucket, object_name, encoding="utf-8-sig")


def first_mercari_csv_row(csv_text: str) -> dict[str, str] | None:
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        return {header: row.get(header, "") for header in MERCARI_HEADERS}
    return None


def review_required_csv_rows(csv_text: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    return [
        {header: row.get(header, "") for header in REVIEW_REQUIRED_HEADERS}
        for row in reader
    ]


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
