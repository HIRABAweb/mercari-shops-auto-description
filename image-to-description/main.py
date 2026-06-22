"""Cloud Storage event handler for generating a Yahoo Auctions description."""

import os
import re

import functions_framework
import vertexai
from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage
from vertexai.generative_models import GenerativeModel, Part

# Deployment settings. Configure these values for each Cloud Run function deployment.
PROJECT_ID = ""
LOCATION = "asia-northeast1"
PROMPT_BUCKET_NAME = "t"
PROMPT_FILE_NAME = ""
MODEL_NAME = "gemini-2.5-flash"

SUCCESS_FILE_NAME = "_SUCCESS.txt"
DESCRIPTION_FILE_NAME = "_description.txt"
PROCESSING_LOCK_FILE_NAME = "_description_processing.lock"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
MAX_IMAGE_COUNT = 20
MAX_IMAGE_TOTAL_BYTES = 100 * 1000 * 1000
MISSING_MEASUREMENT_MARKER = "【要確認：採寸情報なし】"


vertexai.init(project=PROJECT_ID, location=LOCATION)
storage_client = storage.Client()
model = GenerativeModel(MODEL_NAME)


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
    if PROMPT_TEXT is None:
        PROMPT_TEXT = load_prompt_from_gcs(PROMPT_BUCKET_NAME, PROMPT_FILE_NAME)
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
    """Read measurements; allow a human-review marker when they are unavailable."""
    try:
        measurement_info = bucket.blob(object_name).download_as_text(encoding="utf-8")
        if not measurement_info.strip():
            print("WARNING: 採寸情報が空です。採寸情報なしで続行します。")
            return "", False
        print(f"INFO: 採寸情報を取得しました（文字数: {len(measurement_info)}）。")
        return measurement_info, True
    except Exception as error:
        print(f"WARNING: 採寸情報の読み込みに失敗しました。採寸情報なしで続行します: {error}")
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
            model.generate_content([prompt, *image_parts]).text,
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
