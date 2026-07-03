"""Cloud Storage event handler for generating a Yahoo Auctions description."""

import os
import re

import functions_framework
import vertexai
from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage
from vertexai.generative_models import GenerativeModel, Part

SUCCESS_FILE_NAME = "_SUCCESS.txt"
PRODUCT_INFO_FILE_NAME = "product_info.txt"
DESCRIPTION_FILE_NAME = "_description.txt"
PROCESSING_LOCK_FILE_NAME = "_description_processing.lock"
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
    prompt_measurement_info = measurement_info.strip() or MISSING_MEASUREMENT_MARKER
    return (
        f"{base_prompt}\n\n"
        f"【商品データ・採寸情報】\n{prompt_measurement_info}\n\n"
        "上記の商品情報・採寸情報・状態メモを必ず確認し、"
        "事実として確認できる内容だけで説明文を作成してください。"
    )


def load_text_if_present(bucket, object_name: str, *, require_exists: bool = False) -> str:
    """Return object text when present, treating missing or unreadable files as empty."""
    try:
        blob = bucket.blob(object_name)
        if require_exists and hasattr(blob, "exists") and not blob.exists():
            return ""
        return blob.download_as_text(encoding="utf-8")
    except Exception as error:
        print(f"WARNING: 入力ファイルを読み込めませんでした: {object_name}, error={error}")
        return ""


def load_measurement_info(bucket, object_name: str) -> tuple[str, bool]:
    """Read product information, preferring product_info.txt over the trigger body."""
    folder_path = os.path.dirname(object_name)
    product_info_name = f"{folder_path}/{PRODUCT_INFO_FILE_NAME}"

    product_info = load_text_if_present(
        bucket,
        product_info_name,
        require_exists=True,
    ).strip()
    if product_info:
        print(
            f"INFO: product_info.txtから商品情報を取得しました（文字数: {len(product_info)}）。"
        )
        return product_info, True

    trigger_text = load_text_if_present(bucket, object_name).strip()
    if trigger_text:
        print(
            f"INFO: _SUCCESS.txt本文から商品情報を取得しました（文字数: {len(trigger_text)}）。"
        )
        return trigger_text, True

    print("WARNING: product_info.txt と _SUCCESS.txt の本文が空です。")
    return "", False


def image_sort_key(blob) -> tuple[int, str]:
    """Sort images by the first number in their filename, then by name."""
    filename = blob.name.rsplit("/", maxsplit=1)[-1]
    match = re.search(r"(\d+)", filename)
    return (int(match.group(1)) if match else 999999, filename)


def load_image_parts(bucket_name: str, folder_path: str) -> list[Part]:
    """Download at most 20 number-sorted images totaling at most 100 MB."""
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
        image_bytes = blob.download_as_bytes()
        image_size = max(declared_size, len(image_bytes))
        if total_bytes + image_size > MAX_IMAGE_TOTAL_BYTES:
            raise ValueError(
                f"画像合計サイズが上限 {MAX_IMAGE_TOTAL_BYTES} bytes を超えています。"
            )
        total_bytes += image_size
        image_parts.append(Part.from_data(data=image_bytes, mime_type=blob.content_type))
    return image_parts


def acquire_processing_lock(bucket, folder_path: str):
    """Atomically claim a product folder so duplicate events run only once."""
    lock_blob = bucket.blob(f"{folder_path}/{PROCESSING_LOCK_FILE_NAME}")
    try:
        lock_blob.upload_from_string("", content_type="text/plain", if_generation_match=0)
    except PreconditionFailed:
        print(f"INFO: フォルダ '{folder_path}' は別の処理が実行中です。")
        return None
    return lock_blob


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
                processing_lock.delete()
            except Exception as error:
                print(f"WARNING: 処理ロックの削除に失敗しました: {error}")
