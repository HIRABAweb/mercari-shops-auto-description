# 必要なライブラリをインポート
import functions_framework
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from google.cloud import storage
import os

# --- ▼▼▼ あなたが設定する項目 ▼▼▼ ---

# Google CloudプロジェクトIDとリージョン
PROJECT_ID = ""
LOCATION = "asia-northeast1"

# プロンプトが保存されているGCSの場所
PROMPT_BUCKET_NAME = "t"
PROMPT_FILE_NAME = ""

# 使用するAIモデル名
MODEL_NAME = "gemini-2.5-flash"  # ★設定値として独立させ、管理しやすくした

# --- ▲▲▲ 設定はここまで ▲▲▲ ---

# --- ▼▼▼ グローバルスコープでの初期化処理 ▼▼▼ ---

vertexai.init(project=PROJECT_ID, location=LOCATION)
storage_client = storage.Client()
model = GenerativeModel(MODEL_NAME)


def load_prompt_from_gcs(bucket_name, file_name):
    """GCSからプロンプトファイルを読み込む関数"""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(file_name)
        prompt_text = blob.download_as_text(encoding="utf-8")
        print("GCSからプロンプトを正常に読み込みました。")
        return prompt_text
    except Exception as e:
        print(f"致命的なエラー: GCSからのプロンプト読み込みに失敗しました。 Bucket: {bucket_name}, File: {file_name}, Error: {e}")
        return None

# Cloud Functionsのインスタンス起動時に一度だけプロンプトを読み込む
PROMPT_TEXT = load_prompt_from_gcs(PROMPT_BUCKET_NAME, PROMPT_FILE_NAME)

# --- ▲▲▲ 初期化処理はここまで ▲▲▲ ---


@functions_framework.cloud_event
def XXXtrigger(cloud_event):
    """GCSにトリガーファイルが作成されたことを検知して商品説明文を生成する関数"""
    # プロンプトが正常に読み込めているか最初にチェック
    if PROMPT_TEXT is None:
        print("エラー: プロンプトが初期化されていないため、処理を中断します。")
        return

    data = cloud_event.data
    bucket_name = data["bucket"]
    triggered_file_name = data["name"]

    print(f"トリガー発生: バケット'{bucket_name}' ファイル'{triggered_file_name}'")

    # トリガーが「_SUCCESS.txt」でなければ、処理を終了
    if not triggered_file_name.endswith('/_SUCCESS.txt'):
        print(f"処理対象外のファイルです: {triggered_file_name}。")
        return

    print(f"トリガーファイル '{triggered_file_name}' を検知。商品説明文の生成を開始します。")

    folder_path = os.path.dirname(triggered_file_name)
    output_file_name = f"{folder_path}/_description.txt"

    bucket = storage_client.bucket(bucket_name)
    output_blob = bucket.blob(output_file_name)

    # 万が一の重複実行を防止するチェック
    if output_blob.exists():
        print(f"フォルダ'{folder_path}'は既に処理済みです。")
        return

    try:
        # ★★★ 追加・変更部分ここから ★★★
        # 1. トリガーファイル（_SUCCESS.txt）の中身（採寸情報）を読み込む
        print("トリガーファイル内の採寸情報を読み込んでいます...")
        trigger_blob = bucket.blob(triggered_file_name)
        measurement_info = ""
        try:
            measurement_info = trigger_blob.download_as_text(encoding="utf-8")
            print(f"採寸情報を取得しました（文字数: {len(measurement_info)}）")
        except Exception as e:
            print(f"警告: 採寸情報の読み込みに失敗しました。採寸情報なしで続行します: {e}")

        # 2. 基本プロンプトと採寸情報を結合して、今回の実行用プロンプトを作成
        #    プロンプトの内容に合わせて、接続詞などは調整してください
        current_prompt = f"{PROMPT_TEXT}\n\n【商品データ・採寸情報】\n{measurement_info}\n\n上記の採寸情報を必ず含めて説明文を作成してください。"
        # ★★★ 追加・変更部分ここまで ★★★

        # フォルダ内のすべての画像ファイルをリストアップ
        print(f"フォルダ'{folder_path}'内の画像ファイルを検索します...")
        blobs = storage_client.list_blobs(bucket_name, prefix=f"{folder_path}/")

        image_parts = []
        for blob in blobs:
            # 画像ファイルのみを対象とする
            if blob.name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                print(f"  - 処理対象の画像を発見: {blob.name}")
                image_bytes = blob.download_as_bytes()
                image_parts.append(Part.from_data(data=image_bytes, mime_type=blob.content_type))

        # 画像が1枚も見つからなかった場合は終了
        if not image_parts:
            print(f"エラー: フォルダ'{folder_path}'内に処理対象の画像が見つかりませんでした。")
            return

        # AIに画像とプロンプトを渡して、説明文を生成
        print(f"{len(image_parts)}枚の画像を元に、AIによる商品説明文の生成を開始します...")
        response = model.generate_content([current_prompt] + image_parts)
        description_text = response.text  # ★ここでValueErrorが発生する可能性がある

        print("AIによる商品説明文の生成が完了しました。")

        # 生成された説明文をテキストファイルとしてGCSに保存
        output_blob.upload_from_string(description_text, content_type='text/plain; charset=utf-8')
        print(f"処理完了：商品説明文を'{output_file_name}'として保存しました。")

    except ValueError as e:
        # ★Vertex AIの安全フィルター等でレスポンスがブロックされた場合の処理を追加
        print(f"AIからのレスポンス取得に失敗しました。コンテンツがブロックされた可能性があります: {e}")
        return
    except Exception as e:
        print(f"処理中に予期せぬエラーが発生しました：{e}")
        return