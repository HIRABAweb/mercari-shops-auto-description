import functions_framework
from google.cloud import storage
from google.cloud import secretmanager
import google.generativeai as genai
import os
import gspread
from google.oauth2.service_account import Credentials
import google.auth

# --- ここを自分の環境に合わせて変更 ---
# Google CloudのプロジェクトID
PROJECT_ID = ""
# Secret Managerに保存したAPIキーのシークレット名
SECRET_NAME = ""
# スプレッドシートID (URLの /d/〇〇〇/edit の〇〇〇部分)
SPREADSHEET_ID = ""
# メルカリ用シート名
SHEET_NAME_MERCARI = "Mercari_List"
# ヤフオク(オークタウン)用シート名
SHEET_NAME_YAHOO = "Yahoo_List"
# ----------------

# プロンプトを置いているバケットとファイル名
PROMPT_BUCKET_NAME = "" # prompt.txtがあるバケット
PROMPT_FILE_NAME = ".txt"
# ------------------

# Secret ManagerからAPIキーを取得
def get_api_key():
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"ERROR: APIキーの取得に失敗: {e}")
        raise

# Cloud Storageからプロンプトテキストを読み込む
def get_prompt_from_gcs():
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(PROMPT_BUCKET_NAME)
        blob = bucket.blob(PROMPT_FILE_NAME)
        return blob.download_as_text()
    except Exception as e:
        print(f"WARNING: プロンプト({PROMPT_FILE_NAME})の読み込みに失敗。デフォルトを使用します。: {e}")
        return "商品の魅力を伝える商品説明文を作成してください。"

# スプレッドシート接続設定
def get_worksheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds, _ = google.auth.default(scopes=scopes)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    
    # 両方のシートを取得 (存在しない場合はエラーになるため事前に作成が必要)
    sheet_m = spreadsheet.worksheet(SHEET_NAME_MERCARI)
    sheet_y = spreadsheet.worksheet(SHEET_NAME_YAHOO)
    return sheet_m, sheet_y

# 初期設定
genai.configure(api_key=get_api_key())
model = genai.GenerativeModel("gemini-2.5-flash-lite")
storage_client = storage.Client()

@functions_framework.cloud_event
def generate_dual_listing(cloud_event):
    data = cloud_event.data
    bucket_name = data["bucket"]
    file_name = data["name"]

    # _description.txt 以外は処理しない
    if not file_name.endswith("_description.txt"):
        return

    print(f"INFO: 処理開始: gs://{bucket_name}/{file_name}")

    try:
        # 1. ヤフオク情報の読み込み & 重複防止のリネーム（ロック）
        source_bucket = storage_client.bucket(bucket_name)
        source_blob = source_bucket.blob(file_name)

        # ファイルが存在するか確認（二重起動防止）
        if not source_blob.exists():
            print(f"INFO: {file_name} は既に他の処理によって削除またはリネームされています。")
            return

        # テキスト内容を読み込む
        yahoo_info_text = source_blob.download_as_text()

        # フォルダ名を商品管理コードとして使用
        folder_path = os.path.dirname(file_name)
        item_manage_code = folder_path.split("/")[-1] if "/" in folder_path else folder_path

        # 即座にリネームして、後続の同一イベントが走れないようにする
        new_file_name = file_name.replace("_description.txt", "_processed.txt")
        source_bucket.copy_blob(source_blob, source_bucket, new_file_name)
        source_blob.delete()
        print(f"INFO: {file_name} を {new_file_name} にリネームしました（重複防止ロック）。")

        # 2. 画像URLのリストアップ
        blobs = storage_client.list_blobs(bucket_name, prefix=f"{folder_path}/")
        image_urls = []
        for blob in blobs:
            if blob.name.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                public_url = f"https://storage.googleapis.com/{bucket_name}/{blob.name}"
                image_urls.append(public_url)

        # ファイル名の数字順にソート（001, 002, 003...）
        import re
        def extract_number(url):
            # URLからファイル名を取得
            filename = url.split('/')[-1]
            # ファイル名から最初の数字を抽出
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else 999999
        
        image_urls.sort(key=extract_number)

        # 3. プロンプト取得とAI生成
        system_prompt = get_prompt_from_gcs()
        
        final_prompt = f"""
        {system_prompt}

        【商品情報】
        {yahoo_info_text}
        """
        
        response = model.generate_content(final_prompt)
        generated_description = response.text

        # ==========================================
        # 4-A. メルカリShops用データ作成 (既存ロジック)
        # ==========================================
        row_mercari = [""] * 73
        for i in range(min(len(image_urls), 20)):
            row_mercari[i] = image_urls[i]
        
        row_mercari[20] = "【要修正】商品名" # 商品名
        row_mercari[21] = generated_description # 説明文
        row_mercari[22] = "one size" 
        row_mercari[23] = "1"
        row_mercari[24] = item_manage_code # SKU管理コード
        row_mercari[62] = "" # ブランドID
        row_mercari[63] = "50000" # 販売価格
        row_mercari[64] = "" # カテゴリID
        row_mercari[65] = "3" # 商品の状態
        row_mercari[66] = "3" # 配送方法
        row_mercari[67] = "jp34" # 地域
        row_mercari[68] = "2" # 発送日
        row_mercari[69] = "1" # ステータス
        row_mercari[70] = "1" # 配送料負担

        # ==========================================
        # 4-B. ヤフオク(オークタウン)用データ作成
        # ==========================================
        # 取得したヘッダーマップ(0-113)に基づいて全114列を作成
        row_yahoo = [""] * 114

        # ヤフオクの説明文は元のテキストをそのまま使用（改行をHTMLタグに変換）
        yahoo_description_raw_html = yahoo_info_text.replace("\n", "<br>")

        # 基本情報
        row_yahoo[0] = "【要修正】カテゴリID" # 0: カテゴリ
        row_yahoo[1] = f"【要修正】商品名 (管理コード: {item_manage_code})" # 1: タイトル
        row_yahoo[2] = yahoo_description_raw_html # 2: 説明
        row_yahoo[3] = "49999" # 3: 開始価格
        row_yahoo[4] = "50000" # 4: 即決価格
        row_yahoo[5] = "1" # 5: 個数
        row_yahoo[6] = "3" # 6: 開催期間 (3日間)
        row_yahoo[7] = "22" # 7: 終了時間 (22時)

        # 画像設定 (9, 11, 13, 15, 17, 19, 21, 23, 25, 27)
        for i in range(min(len(image_urls), 10)):
            target_idx = 9 + (i * 2)
            if target_idx < len(row_yahoo):
                row_yahoo[target_idx] = image_urls[i]

        # 配送・支払・その他設定 (デフォルト値)
        row_yahoo[29] = "広島県" # 29: 商品発送元の都道府県
        row_yahoo[31] = "出品者" # 31: 送料負担 (1: 出品者)
        row_yahoo[32] = "先払い" # 32: 代金支払い
        row_yahoo[33] = "はい" # 33: Yahoo!かんたん決済
        row_yahoo[34] = "はい" # 34: かんたん取引
        row_yahoo[35] = "いいえ" # 35: 商品代引
        row_yahoo[36] = "目立った傷や汚れなし" # 36: 商品の状態
        row_yahoo[38] = "返品不可" # 38: 返品の可否
        row_yahoo[40] = "はい" # 40: 入札者評価制限
        row_yahoo[41] = "はい" # 41: 悪い評価の割合での制限
        row_yahoo[42] = "いいえ" # 42: 入札者認証制限
        row_yahoo[43] = "はい" # 43: 自動延長
        row_yahoo[44] = "いいえ" # 44: 早期終了
        row_yahoo[45] = "いいえ" # 45: 値下げ交渉
        row_yahoo[46] = "0" # 46: 自動再出品
        row_yahoo[47] = "いいえ" # 47: 自動値下げ
        row_yahoo[51] = "はい" # 51: 送料固定
        row_yahoo[56] = "はい" # 56: ネコ宅急便 (おてがる配送)
        row_yahoo[61] = "2日～3日" # 61: 発送までの日数
        row_yahoo[112] = "いいえ" # 112: 受け取り後決済サービス
        row_yahoo[113] = "いいえ" # 113: 海外発送

        # 5. スプレッドシートへ書き込み (両方のシートへ)
        sheet_mercari, sheet_yahoo = get_worksheets()
        
        sheet_mercari.append_row(row_mercari)
        print(f"SUCCESS: メルカリ用シート({SHEET_NAME_MERCARI})に出力しました。")

        sheet_yahoo.append_row(row_yahoo)
        print(f"SUCCESS: ヤフオク用シート({SHEET_NAME_YAHOO})に出力しました。")
        
        print(f"ALL DONE: 管理コード: {item_manage_code}")

    except Exception as e:
        print(f"ERROR: 処理中にエラーが発生しました: {e}")
