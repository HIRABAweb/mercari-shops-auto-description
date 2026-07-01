"""Cloud Storage event handler for Mercari Shops and Yahoo Auctions CSV exports."""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import functions_framework
import google.generativeai as genai
from google.api_core.exceptions import PreconditionFailed
from google.cloud import secretmanager, storage

from ai_service import (
    ProductAttributes,
    build_generation_prompt,
    parse_product_attributes,
)
from brand_mapper import BrandRecord, build_brand_records, resolve_brand
from category_mapper import CategoryRecord, build_category_records, resolve_category
from csv_export import (
    DONE_FILE_NAME,
    MERCARI_CSV_FILE_NAME,
    MERCARI_HEADERS,
    RESULT_JSON_FILE_NAME,
    REVIEW_REQUIRED_CSV_FILE_NAME,
    REVIEW_REQUIRED_HEADERS,
    YAHOO_CSV_FILE_NAME,
    YAHOO_HEADERS,
    build_csv_text,
    build_export_rows,
)
from listing_data import collect_sorted_image_urls
from title_builder import build_title, ensure_size_in_description


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

BRAND_MASTER_FILE_NAME = "masters/brand_master.csv"
CATEGORY_MASTER_FILE_NAME = "masters/category_master_updated.csv"
LOCAL_MERCARI_RESOURCE_DIR = Path(__file__).resolve().parent / "resources" / "mercari"
LOCAL_BRAND_MASTER_FILE_NAME = "brand_master.csv"
LOCAL_CATEGORY_MASTER_FILE_NAME = "category_master_updated.csv"

DESCRIPTION_FILE_NAME = "_description.txt"
PROCESSED_FILE_NAME = "_processed.txt"
PROCESSING_LOCK_FILE_NAME = "_processing.lock"
EXPORT_ROOT = "exports"
_MODEL = None
_API_KEY: str | None = None


class ConfigurationError(RuntimeError):
    """Raised when required deployment settings are missing."""


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(
            f"必須環境変数 {name} が未設定です。Cloud Run Functions の環境変数に設定してください。"
        )
    return value


@dataclass(frozen=True)
class ExportContext:
    folder_path: str
    product_code: str
    batch_id: str
    export_prefix: str


@dataclass(frozen=True)
class ExportResult:
    success: bool
    product_code: str
    batch_id: str
    category_id: str
    brand_id: str
    review_required: bool
    processing_time: float
    outputs: dict[str, str]


def get_api_key() -> str:
    """Read the Gemini API key from Secret Manager."""
    global _API_KEY
    if _API_KEY is not None:
        return _API_KEY

    project_id = get_required_env("PROJECT_ID")
    secret_name = get_required_env("SECRET_NAME")
    try:
        secret_client = secretmanager.SecretManagerServiceClient()
        secret_version = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = secret_client.access_secret_version(request={"name": secret_version})
        _API_KEY = response.payload.data.decode("UTF-8")
        return _API_KEY
    except Exception:
        LOGGER.exception("APIキーの取得に失敗しました。")
        raise


def get_model():
    """Create the Gemini client lazily so imports do not require cloud settings."""
    global _MODEL
    if _MODEL is None:
        genai.configure(api_key=get_api_key())
        _MODEL = genai.GenerativeModel(get_required_env("GEMINI_MODEL"))
    return _MODEL


def get_prompt_from_gcs() -> str:
    """Load the listing metadata prompt, with the existing fallback."""
    prompt_bucket_name = get_required_env("PROMPT_BUCKET_NAME")
    prompt_file_name = get_required_env("PROMPT_FILE_NAME")
    try:
        prompt_blob = storage_client.bucket(prompt_bucket_name).blob(prompt_file_name)
        return prompt_blob.download_as_text()
    except Exception as error:
        LOGGER.warning(
            "プロンプトの読み込みに失敗したためデフォルトを使用します: bucket=%s file=%s error=%s",
            prompt_bucket_name,
            prompt_file_name,
            error,
        )
        return "商品の情報を整理し、出品用の商品説明本文と属性をJSONで作成してください。"


def is_description_file(object_name: str) -> bool:
    """Return whether an object should start CSV export generation."""
    return object_name.endswith(DESCRIPTION_FILE_NAME)


def product_folder_from(object_name: str) -> str:
    """Return the GCS product folder, which is also used to derive product code."""
    return os.path.dirname(object_name)


def replace_description_suffix(description_file_name: str, replacement_suffix: str) -> str:
    """Replace only the trigger-file suffix, leaving similarly named folders intact."""
    return f"{description_file_name.removesuffix(DESCRIPTION_FILE_NAME)}{replacement_suffix}"


def build_export_context(description_file_name: str) -> ExportContext:
    folder_path = product_folder_from(description_file_name)
    parts = [part for part in folder_path.split("/") if part]
    product_code = parts[-1] if parts else "unknown"
    # Encode the full folder path so nested products cannot collide after sanitization.
    batch_id = quote(folder_path or product_code, safe="")
    return ExportContext(
        folder_path=folder_path,
        product_code=product_code,
        batch_id=batch_id,
        export_prefix=f"{EXPORT_ROOT}/{batch_id}",
    )


def export_object_name(context: ExportContext, file_name: str) -> str:
    return f"{context.export_prefix}/{file_name}"


def acquire_processing_lock(bucket, description_file_name: str):
    """Atomically claim an object so duplicate Cloud Storage events do not run twice."""
    lock_file_name = replace_description_suffix(
        description_file_name,
        PROCESSING_LOCK_FILE_NAME,
    )
    lock_blob = bucket.blob(lock_file_name)
    try:
        lock_blob.upload_from_string("", content_type="text/plain", if_generation_match=0)
    except PreconditionFailed:
        LOGGER.info("別の処理が実行中です: %s", description_file_name)
        return None
    return lock_blob


def mark_description_as_processed(
    bucket,
    description_blob,
    description_file_name: str,
    source_generation,
) -> None:
    """Mark the source as processed only after all export artifacts are written."""
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
    LOGGER.info("処理済みファイルを作成しました: %s", processed_file_name)


def load_csv_rows_from_gcs(bucket, object_name: str) -> list[dict[str, str]]:
    """Load optional master CSV rows from GCS. Missing masters are treated as empty."""
    try:
        text = bucket.blob(object_name).download_as_text(encoding="utf-8-sig")
    except Exception as error:
        LOGGER.warning("マスタCSVを読み込めません。object=%s error=%s", object_name, error)
        return []
    return list(csv.DictReader(text.splitlines()))


def load_csv_rows_from_local_resource(file_name: str) -> list[dict[str, str]]:
    """Load bundled official Mercari master files as a fallback."""
    path = LOCAL_MERCARI_RESOURCE_DIR / file_name
    try:
        with path.open(encoding="utf-8-sig", newline="") as csv_file:
            return list(csv.DictReader(csv_file))
    except OSError as error:
        LOGGER.warning("同梱マスタCSVを読み込めません。file=%s error=%s", file_name, error)
        return []


def load_brand_records(bucket) -> list[BrandRecord]:
    rows = load_csv_rows_from_gcs(bucket, BRAND_MASTER_FILE_NAME)
    if not rows:
        rows = load_csv_rows_from_local_resource(LOCAL_BRAND_MASTER_FILE_NAME)
    return build_brand_records(rows)


def load_category_records(bucket) -> list[CategoryRecord]:
    rows = load_csv_rows_from_gcs(bucket, CATEGORY_MASTER_FILE_NAME)
    if not rows:
        rows = load_csv_rows_from_local_resource(LOCAL_CATEGORY_MASTER_FILE_NAME)
    return build_category_records(rows)


def generate_product_attributes(source_description: str) -> ProductAttributes:
    """Generate structured attributes. Gemini never decides final IDs or title."""
    prompt = build_generation_prompt(get_prompt_from_gcs(), source_description)
    response_text = get_model().generate_content(prompt).text
    return parse_product_attributes(response_text)


def build_result_payload(
    *,
    context: ExportContext,
    category_id: str,
    brand_id: str,
    review_required: bool,
    processing_time: float,
    outputs: dict[str, str],
) -> dict:
    return asdict(
        ExportResult(
            success=True,
            product_code=context.product_code,
            batch_id=context.batch_id,
            category_id=category_id,
            brand_id=brand_id,
            review_required=review_required,
            processing_time=round(processing_time, 3),
            outputs=outputs,
        )
    )


def upload_text(bucket, object_name: str, text: str, content_type: str) -> None:
    bucket.blob(object_name).upload_from_string(text, content_type=content_type)
    LOGGER.info("出力ファイルを保存しました: gs://%s/%s", bucket.name, object_name)


def upload_export_artifacts(
    bucket,
    context: ExportContext,
    mercari_row: dict[str, str],
    yahoo_row: dict[str, str],
    review_rows: list[dict[str, str]],
    result_payload: dict,
) -> dict[str, str]:
    """Write all final artifacts. _DONE.txt is written last only after success."""
    outputs = {
        "mercari_csv": export_object_name(context, MERCARI_CSV_FILE_NAME),
        "yahoo_csv": export_object_name(context, YAHOO_CSV_FILE_NAME),
        "review_required_csv": export_object_name(context, REVIEW_REQUIRED_CSV_FILE_NAME),
        "result_json": export_object_name(context, RESULT_JSON_FILE_NAME),
        "done": export_object_name(context, DONE_FILE_NAME),
    }
    upload_text(
        bucket,
        outputs["mercari_csv"],
        build_csv_text(MERCARI_HEADERS, [mercari_row]),
        "text/csv; charset=utf-8",
    )
    upload_text(
        bucket,
        outputs["yahoo_csv"],
        build_csv_text(YAHOO_HEADERS, [yahoo_row]),
        "text/csv; charset=utf-8",
    )
    upload_text(
        bucket,
        outputs["review_required_csv"],
        build_csv_text(REVIEW_REQUIRED_HEADERS, review_rows),
        "text/csv; charset=utf-8",
    )
    result_payload["outputs"] = outputs
    upload_text(
        bucket,
        outputs["result_json"],
        json.dumps(result_payload, ensure_ascii=False, indent=2),
        "application/json; charset=utf-8",
    )
    upload_text(
        bucket,
        outputs["done"],
        "done\n",
        "text/plain; charset=utf-8",
    )
    return outputs


storage_client = storage.Client()


@functions_framework.cloud_event
def generate_dual_listing(cloud_event):
    """Create Mercari Shops and Yahoo Auctions CSV exports for a description file."""
    started_at = time.monotonic()
    event_data = cloud_event.data
    bucket_name = event_data["bucket"]
    description_file_name = event_data["name"]

    if not is_description_file(description_file_name):
        return

    LOGGER.info("CSV生成処理を開始します: gs://%s/%s", bucket_name, description_file_name)
    processing_lock = None
    try:
        bucket = storage_client.bucket(bucket_name)
        context = build_export_context(description_file_name)
        source_generation = event_data.get("generation")
        description_blob = bucket.blob(
            description_file_name,
            generation=source_generation,
        )
        if not description_blob.exists():
            LOGGER.info("説明文ファイルは既に処理されています: %s", description_file_name)
            return

        if source_generation is None:
            description_blob.reload()
            source_generation = description_blob.generation
        processing_lock = acquire_processing_lock(bucket, description_file_name)
        if processing_lock is None:
            raise RuntimeError(f"処理ロックを取得できません: {description_file_name}")

        source_description = description_blob.download_as_text()
        image_urls = collect_sorted_image_urls(
            storage_client.list_blobs(bucket_name, prefix=f"{context.folder_path}/"),
            bucket_name,
        )
        if not image_urls:
            raise ValueError(f"商品画像が見つかりません: {context.folder_path}")

        attributes = generate_product_attributes(source_description)
        brand_records = load_brand_records(bucket)
        category_records = load_category_records(bucket)
        brand_match = resolve_brand(attributes.brand_name, brand_records)
        category_match = resolve_category(
            attributes.category_name,
            attributes.gender,
            attributes.item_type,
            category_records,
            attributes.confidence.get("category_name"),
        )
        title = build_title(attributes, brand_match.brand_name or attributes.brand_name)
        description = ensure_size_in_description(attributes.description, attributes.size)
        export_rows = build_export_rows(
            image_urls=image_urls,
            product_code=context.product_code,
            title=title,
            description=description,
            attributes=attributes,
            brand_match=brand_match,
            category_match=category_match,
        )
        review_required = bool(export_rows.review_rows)
        result_payload = build_result_payload(
            context=context,
            category_id=category_match.category_id,
            brand_id=brand_match.brand_id,
            review_required=review_required,
            processing_time=time.monotonic() - started_at,
            outputs={},
        )
        upload_export_artifacts(
            bucket,
            context,
            export_rows.mercari_row,
            export_rows.yahoo_row,
            export_rows.review_rows,
            result_payload,
        )
        mark_description_as_processed(
            bucket,
            description_blob,
            description_file_name,
            source_generation,
        )
        LOGGER.info("CSV生成が完了しました: product_code=%s", context.product_code)
    except Exception:
        LOGGER.exception("CSV生成中にエラーが発生しました。")
        raise
    finally:
        if processing_lock is not None:
            try:
                processing_lock.delete()
            except Exception:
                LOGGER.exception("処理ロックの削除に失敗しました。")
