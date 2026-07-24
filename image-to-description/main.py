"""Cloud Storage event handler for generating a Yahoo Auctions description."""

import os
import re
from datetime import datetime, timedelta, timezone

import functions_framework
import vertexai
from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import storage
from vertexai.generative_models import GenerativeModel, Part

SUCCESS_FILE_NAME = "_SUCCESS.txt"
DESCRIPTION_FILE_NAME = "_description.txt"
PROCESSING_LOCK_FILE_NAME = "_description_processing.lock"
PROCESSING_LOCK_STALE_AFTER = timedelta(minutes=15)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGE_COUNT = 20
MAX_IMAGE_TOTAL_BYTES = 100 * 1000 * 1000
MISSING_MEASUREMENT_MARKER = "【要確認：採寸情報なし】"


storage_client = storage.Client()
model = None
_VERTEX_INITIALIZED = False


class ConfigurationError(RuntimeError):
    """Raised when required deployment settings are missing."""


def get_required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(
            f"必須環境変数 {name} が未設定です。Cloud Run Functions の環境変数に設定してください。"
        )
    return value


def get_model():
    """Initialize Vertex AI lazily so module import does not require env vars."""
    global _VERTEX_INITIALIZED, model
    if model is not None:
        return model
    project_id = get_required_env("PROJECT_ID")
    location = get_required_env("VERTEX_LOCATION")
    model_name = get_required_env("VERTEX_MODEL")
    if not _VERTEX_INITIALIZED:
        vertexai.init(project=project_id, location=location)
        _VERTEX_INITIALIZED = True
    model = GenerativeModel(model_name)
    return model


def load_prompt_from_gcs(bucket_name: str, file_name: str) -> str | None:
    """Load the base prompt once when a function instance starts."""
    try:
        prompt_blob = storage_client.bucket(bucket_name).blob(file_name)
        prompt_text = prompt_blob.download_as_text(encoding="utf-8")
        print("INFO: GCSからプロンプトを読み込みました。")
        return prompt_text
    except Exception as error:
        print(
            "ERROR: GCSからのプロンプト読み込みに失敗しました。 "
            f"bucket={bucket_name}, file={file_name}, error={error}"
        )
        return None


PROMPT_TEXT: str | None = None


def get_prompt() -> str:
    """Return a cached prompt, retrying GCS loading after a transient failure."""
    global PROMPT_TEXT
    prompt_bucket_name = get_required_env("PROMPT_BUCKET_NAME")
    prompt_file_name = get_required_env("PROMPT_FILE_NAME")
    if PROMPT_TEXT is None:
        PROMPT_TEXT = load_prompt_from_gcs(prompt_bucket_name, prompt_file_name)
    if PROMPT_TEXT is None:
        raise RuntimeError("プロンプトをGCSから読み込めませんでした。")
    return PROMPT_TEXT


def is_success_file(object_name: str) -> bool:
    """Return whether an object is the per-product processing trigger."""
    return object_name.endswith(f"/{SUCCESS_FILE_NAME}")


def build_description_prompt(base_prompt: str, measurement_info: str) -> str:
    """Append product measurements to the managed base prompt."""
    return (
        f"{base_prompt}\n\n"
        f"【商品データ・採寸情報】\n{measurement_info}\n\n"
        "上記の採寸情報を必ず含めて説明文を作成してください。"
    )


def load_measurement_info(bucket, object_name: str) -> tuple[str, bool]:
    """Read product notes, distinguishing empty content from storage failures."""
    measurement_info = bucket.blob(object_name).download_as_text(encoding="utf-8")
    if not measurement_info.strip():
        print("WARNING: 商品情報が空です。採寸情報なしで続行します。")
        return "", False
    print(f"INFO: 商品情報を取得しました（文字数: {len(measurement_info)}）。")
    return measurement_info, True


def image_sort_key(blob) -> tuple[int, str]:
    """Sort images by the first number in their filename, then by name."""
    filename = blob.name.rsplit("/", maxsplit=1)[-1]
    match = re.search(r"(\d+)", filename)
    return (int(match.group(1)) if match else 999999, filename)


def load_image_parts(bucket_name: str, folder_path: str) -> list[Part]:
    """Reference at most 20 number-sorted GCS images totaling at most 100 MB."""
    image_blobs = sorted(
        (
            blob
            for blob in storage_client.list_blobs(bucket_name, prefix=f"{folder_path}/")
            if blob.name.lower().endswith(IMAGE_EXTENSIONS)
        ),
        key=image_sort_key,
    )
    if len(image_blobs) > MAX_IMAGE_COUNT:
        print(f"WARNING: 画像は先頭{MAX_IMAGE_COUNT}枚だけを使用します。")

    image_parts = []
    total_bytes = 0
    for blob in image_blobs[:MAX_IMAGE_COUNT]:
        declared_size = blob.size or 0
        if total_bytes + declared_size > MAX_IMAGE_TOTAL_BYTES:
            raise ValueError(
                f"画像合計サイズが上限 {MAX_IMAGE_TOTAL_BYTES} bytes を超えています。"
            )
        print(f"INFO: 処理対象の画像を発見: {blob.name}")
        image_size = declared_size
        if total_bytes + image_size > MAX_IMAGE_TOTAL_BYTES:
            raise ValueError(
                f"画像合計サイズが上限 {MAX_IMAGE_TOTAL_BYTES} bytes を超えています。"
            )
        total_bytes += image_size
        image_parts.append(
            Part.from_uri(
                uri=f"gs://{bucket_name}/{blob.name}",
                mime_type=blob.content_type,
            )
        )
    return image_parts


def recover_stale_processing_lock(lock_blob, folder_path: str, *, now: datetime) -> bool:
    """Delete only the observed stale lock generation, then allow one retry."""
    try:
        lock_blob.reload()
    except NotFound:
        return True

    updated = lock_blob.updated
    generation = lock_blob.generation
    if updated is None or generation is None:
        print(
            "WARNING: 処理ロックのメタデータが不足しているため回収しません: "
            f"{folder_path}"
        )
        return False
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if now - updated < PROCESSING_LOCK_STALE_AFTER:
        return False

    try:
        lock_blob.delete(if_generation_match=generation)
        print(f"WARNING: 期限切れの処理ロックを回収しました: {folder_path}")
    except (NotFound, PreconditionFailed):
        print(f"INFO: 回収中に処理ロックが更新されました: {folder_path}")
    return True


def acquire_processing_lock(bucket, folder_path: str, *, now: datetime | None = None):
    """Atomically claim a folder, safely recovering an expired lock generation."""
    lock_blob = bucket.blob(f"{folder_path}/{PROCESSING_LOCK_FILE_NAME}")
    try:
        lock_blob.upload_from_string("", content_type="text/plain", if_generation_match=0)
    except PreconditionFailed:
        recovery_time = now or datetime.now(timezone.utc)
        if not recover_stale_processing_lock(
            lock_blob,
            folder_path,
            now=recovery_time,
        ):
            print(f"INFO: フォルダ '{folder_path}' は別の処理が実行中です。")
            return None
        try:
            lock_blob.upload_from_string(
                "",
                content_type="text/plain",
                if_generation_match=0,
            )
        except PreconditionFailed:
            print(f"INFO: 別の処理が先にロックを取得しました: {folder_path}")
            return None
    return lock_blob


def release_processing_lock(lock_blob, folder_path: str) -> None:
    """Delete only the lock generation acquired by this invocation."""
    generation = lock_blob.generation
    if generation is None:
        print(
            "WARNING: 処理ロックの世代番号が不明なため削除しません: "
            f"{folder_path}"
        )
        return
    try:
        lock_blob.delete(if_generation_match=generation)
    except (NotFound, PreconditionFailed):
        print(f"INFO: 処理ロックは既に削除または更新されています: {folder_path}")


def add_measurement_review_marker(description_text: str, measurement_available: bool) -> str:
    """Make missing measurements visible to the human who reviews the listing."""
    if measurement_available:
        return description_text
    return f"{MISSING_MEASUREMENT_MARKER}\n{description_text}"


@functions_framework.cloud_event
def generate_description_from_trigger(cloud_event):
    """Generate and store a description when a product's _SUCCESS.txt is uploaded."""
    event_data = cloud_event.data
    bucket_name = event_data["bucket"]
    trigger_file_name = event_data["name"]

    if not is_success_file(trigger_file_name):
        print(f"INFO: 処理対象外のファイルです: {trigger_file_name}")
        return

    folder_path = os.path.dirname(trigger_file_name)
    output_file_name = f"{folder_path}/{DESCRIPTION_FILE_NAME}"
    bucket = storage_client.bucket(bucket_name)
    output_blob = bucket.blob(output_file_name)
    processing_lock = None
    try:
        if output_blob.exists():
            print(f"INFO: フォルダ '{folder_path}' は既に処理済みです。")
            return

        processing_lock = acquire_processing_lock(bucket, folder_path)
        if processing_lock is None:
            raise RuntimeError(f"処理ロックを取得できません: {folder_path}")
        if output_blob.exists():
            print(f"INFO: フォルダ '{folder_path}' は既に処理済みです。")
            return

        measurement_info, measurement_available = load_measurement_info(
            bucket, trigger_file_name
        )
        prompt = build_description_prompt(get_prompt(), measurement_info)
        image_parts = load_image_parts(bucket_name, folder_path)

        if not image_parts:
            raise ValueError(f"フォルダ '{folder_path}' 内に処理対象の画像が見つかりませんでした。")

        print(f"INFO: {len(image_parts)}枚の画像を使用して商品説明文を生成します。")
        description_text = add_measurement_review_marker(
            get_model().generate_content([prompt, *image_parts]).text,
            measurement_available,
        )
        output_blob.upload_from_string(
            description_text,
            content_type="text/plain; charset=utf-8",
            if_generation_match=0,
        )
        print(f"SUCCESS: 商品説明文を '{output_file_name}' として保存しました。")
    except PreconditionFailed:
        print(f"INFO: フォルダ '{folder_path}' は既に処理済みです。")
    except ValueError as error:
        print(f"ERROR: 入力画像またはAI応答が不正です: {error}")
        raise
    except Exception as error:
        print(f"ERROR: 商品説明文の生成中に予期せぬエラーが発生しました: {error}")
        raise
    finally:
        if processing_lock is not None:
            try:
                release_processing_lock(processing_lock, folder_path)
            except Exception as error:
                print(f"WARNING: 処理ロックの削除に失敗しました: {error}")
