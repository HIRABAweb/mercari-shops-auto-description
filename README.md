生成AIを活用したEC出品データ生成MVP

リユース商品の画像と"_SUCCESS.txt"に記載した商品情報から商品説明文を生成し、メルカリShopsおよびヤフオク向けの出品データを作成する、Google Cloud上のイベント駆動型MVPです。

商品ごとの画像と"_SUCCESS.txt"をGoogle Cloud Storageへアップロードすると、生成AIによる商品説明文の作成、画像URLの整列、販売プラットフォーム別データの生成、Googleスプレッドシートへの出力までを自動で実行します。

«本システムは、AIの生成結果をそのまま公開する完全自動出品システムではありません。
最終的に人が内容を確認・修正するHuman-in-the-loop方式を採用しています。»

---

開発背景

個人でリユース事業を運営する中で、商品数の増加に伴い、以下の出品準備業務がボトルネックになっていました。

- 商品画像の確認と整理
- 採寸情報の転記
- 商品説明文の作成
- 販売先ごとの入力形式への変換
- 商品画像URLの登録
- スプレッドシートへの転記
- メルカリShopsとヤフオクへの重複入力

これらの作業を効率化するため、実際の出品業務を基に要件を整理し、Python、Google Cloud、Vertex AI、Gemini APIを利用したMVPを開発しました。

---

主な機能

- 商品画像と"_SUCCESS.txt"本文の商品情報を利用した商品説明文の生成
- Google Cloud Storageへのファイルアップロードを起点とした自動処理
- 商品フォルダ名を商品管理コードとして利用
- 商品画像の公開URL生成
- 画像ファイル名に含まれる数字による表示順の制御
- メルカリShops向け73列データの生成
- ヤフオク・オークタウン向け114列データの生成
- Googleスプレッドシートへの出品データ追記
- Secret Managerを利用したAPIキー管理
- 処理済みファイルへの変更による重複実行の抑止
- AI生成結果を人が確認・修正するHuman-in-the-loop運用

---

システム構成

flowchart TD
    A[商品画像をGCSへアップロード] --> B[商品情報を記載した_SUCCESS.txtをアップロード]
    B --> C[image-to-descriptionが起動]
    C --> D[画像と_SUCCESS.txt本文をVertex AI Geminiへ送信]
    D --> E[_description.txtをGCSへ保存]
    E --> F[yahuoku-to-mercarishopsが起動]
    F --> G[画像URLを数字順に並び替え]
    F --> H[メルカリShops用説明文を生成]
    G --> I[メルカリShops向け73列データを作成]
    H --> I
    G --> J[ヤフオク向け114列データを作成]
    E --> J
    I --> K[Googleスプレッドシートへ追記]
    J --> K
    K --> L[人が内容を確認・修正]
    L --> M[CSVとして出力・各サービスへ登録]

本システムは、役割の異なる2つのサービスで構成されています。

1. "image-to-description"

商品画像と"_SUCCESS.txt"本文の商品情報から、ヤフオク向けの商品説明文の下書きを生成するサービスです。

主な処理は以下です。

1. "_SUCCESS.txt"の作成イベントを検知
2. "_SUCCESS.txt"から商品状態、採寸、特記事項などの商品情報を読み込み
3. 同じ商品フォルダ内の画像を取得
4. Google Cloud Storageに保存したプロンプトを読み込み
5. Vertex AI Geminiへ画像、商品情報、プロンプトを送信
6. 生成した説明文を"_description.txt"として保存

2. "yahuoku-to-mercarishops"

生成された説明文と画像URLから、販売プラットフォーム別の出品データを作成するサービスです。

主な処理は以下です。

1. "_description.txt"の作成イベントを検知
2. "_description.txt"を"_processed.txt"へ変更し、重複実行を抑止
3. 同じ商品フォルダ内の商品画像URLを取得
4. 画像ファイル名に含まれる数字を基準にURLを並び替え
5. Gemini APIを利用してメルカリShops向けの説明文を生成
6. メルカリShops向け73列データを作成
7. ヤフオク・オークタウン向け114列データを作成
8. Googleスプレッドシートへ各データを追記

---

処理フロー

1. 商品フォルダを作成する

Google Cloud Storageの対象バケット内に、商品ごとのフォルダを作成します。

フォルダ名は、出力データの商品管理コードとして使用されます。

商品管理コード/

例：

A0001/

2. 商品画像をアップロードする

商品フォルダ内に画像をアップロードします。

A0001/
├── 001.jpg
├── 002.jpg
├── 003.jpg
└── 004.jpg

対応している画像形式は以下です。

- ".jpg"
- ".jpeg"
- ".png"
- ".webp"

3. 画像の表示順を指定する

画像ファイル名に数字を付けることで、出品データ上の画像順を制御します。

001.jpg
002.jpg
003.jpg
004.jpg

システムはファイル名から最初の数字を抽出し、数字の小さい順に画像URLを並べます。

メルカリShops向けには先頭から最大20枚、ヤフオク向けには先頭から最大10枚を出力データへ設定します。

意図しない順番になることを避けるため、"1.jpg"、"2.jpg"ではなく、"001.jpg"、"002.jpg"のようなゼロ埋め形式を推奨します。

4. "_SUCCESS.txt"を作成する

商品画像のアップロードが完了した後、同じ商品フォルダ内に"_SUCCESS.txt"をアップロードします。

"_SUCCESS.txt"は正式な商品情報入力ファイルです。通常運用で外注者がアップロードするものは、商品画像と"_SUCCESS.txt"のみです。

product_info.txt は通常運用では使用しません。商品状態、採寸、特記事項などの商品情報は"_SUCCESS.txt"の本文に記載します。

"_SUCCESS.txt"は、次の2つの役割を持ちます。

- 商品状態、採寸、特記事項などの商品情報を入力する
- 商品説明文生成処理を開始するトリガーになる

入力例：

肩幅: 43cm
身幅: 50cm
袖丈: 61cm
着丈: 72cm
状態メモ: 左袖に薄汚れあり

傷や汚れなどの特記事項がない場合、"状態メモ"の値は空欄にします。

肩幅: 43cm
身幅: 50cm
袖丈: 61cm
着丈: 72cm
状態メモ:

商品カテゴリに応じて、採寸項目は変更できます。

例：

ウエスト: 80cm
股上: 27cm
股下: 72cm
わたり幅: 30cm
裾幅: 19cm
状態メモ:

採寸情報や状態メモが本文にない場合でも、"_SUCCESS.txt"自体が正常に読めていれば処理は停止しません。可能な範囲で通常CSV出力用データを作成し、確認が必要な商品は商品単位のreviewファイルに出力します。

"_SUCCESS.txt"が読めない場合、GCS read失敗、権限エラー、文字コードエラー、ファイル破損などはシステム・ファイル起因の異常として処理を停止します。商品情報が空であるケースと、ファイルそのものを読めないケースは別扱いです。

外注者向けのアップロード手順は以下に統一します。

1. 商品画像をアップロードする
2. "_SUCCESS.txt"をアップロードする
3. "_SUCCESS.txt"本文に商品状態・採寸・特記事項を書く

5. 処理が自動実行される

"_SUCCESS.txt"のアップロードを検知すると、以下の処理が順番に実行されます。

1. 商品画像と"_SUCCESS.txt"本文の商品情報を取得
2. Vertex AI Geminiで商品説明文を生成
3. "_description.txt"を保存
4. "_description.txt"の保存イベントを検知
5. メルカリShops向けデータを生成
6. ヤフオク向けデータを生成
7. Googleスプレッドシートへ追記
8. "_description.txt"を"_processed.txt"へ変更

---

入力データ構成

処理開始前の商品フォルダは、以下の構成になります。

商品管理コード/
├── 001.jpg
├── 002.jpg
├── 003.jpg
└── _SUCCESS.txt

例：

A0001/
├── 001.jpg
├── 002.jpg
├── 003.jpg
├── 004.jpg
└── _SUCCESS.txt

---

処理後のデータ構成

処理完了後は、商品フォルダ内に"_processed.txt"が作成されます。

商品管理コード/
├── 001.jpg
├── 002.jpg
├── 003.jpg
├── _SUCCESS.txt
└── _processed.txt

"_processed.txt"には、最初のサービスが生成したヤフオク向け商品説明文が保存されています。

"_description.txt"は、後続サービスの処理開始時に"_processed.txt"へ変更されます。これにより、同じイベントが重複して実行されることを抑止しています。

---

商品画像の公開設定

メルカリShopsのCSV一括登録では、商品画像に直接アクセスできるURLをCSVへ入力できます。

本システムでは、Google Cloud Storage上の商品画像から、以下の形式のURLを生成します。

https://storage.googleapis.com/{bucket-name}/{object-name}

そのため、出品データに使用する画像は、URLへアクセスした利用者が認証なしで閲覧できる状態にする必要があります。

現在の運用では、対象バケットまたは対象画像オブジェクトを、匿名ユーザーが読み取り可能な状態に設定しています。

セキュリティ上の注意

- 公開する権限は、画像の読み取り権限だけに限定してください
- 匿名ユーザーへ書き込み権限を付与しないでください
- APIキー、認証ファイル、プロンプト、スプレッドシートなどを公開バケットに保存しないでください
- 顧客情報や個人情報を含む画像は公開しないでください
- 公開用画像と非公開データは、バケットを分離することを推奨します

---

出力データ

メルカリShops向けデータ

メルカリShopsの一括登録用フォーマットを前提に、73列のデータを生成します。

主な出力項目は以下です。

- 商品画像URL：最大20枚
- 商品名
- 商品説明
- SKUの種類
- 在庫数
- 商品管理コード
- ブランドID
- 販売価格
- カテゴリID
- 商品の状態
- 配送方法
- 発送元の地域
- 発送までの日数
- 公開ステータス
- 配送料の負担

現時点では、一部の項目に仮の値または確認用の値を設定しています。

ヤフオク・オークタウン向けデータ

ヤフオク・オークタウン向けフォーマットを前提に、114列のデータを生成します。

主な出力項目は以下です。

- カテゴリID
- 商品タイトル
- 商品説明
- 開始価格
- 即決価格
- 出品個数
- 開催期間
- 終了時間
- 商品画像URL：最大10枚
- 発送元地域
- 送料負担
- 商品状態
- 返品可否
- 入札制限
- 配送方法
- 発送までの日数

Googleスプレッドシート

生成したデータは、Googleスプレッドシートの以下のワークシートで確認・承認します。

- "Draft_Mercari_List"
- "Review_List"
- "Approved_Mercari_CSV"
- "Yahoo_List"

`Draft_Mercari_List` はAIが生成したメルカリShops用73列データの下書きです。運用者はこのシート上で商品名、説明文、カテゴリID、ブランドID、価格などを確認・修正します。1行目には、リポジトリ内の `listing_data.py` で管理するメルカリShops用CSVヘッダーを自動出力します。

`Review_List` は、商品ごとの確認理由と承認状態を管理するシートです。`review_status` を `approved` にした商品だけが、最終アップロード用の `Approved_Mercari_CSV` に出力されます。`needs_review`、`hold`、`rejected` の商品は最終CSVに出しません。

`Approved_Mercari_CSV` は、メルカリShopsへアップロードするための最終CSV用シートです。`export_approved_mercari_csv` entrypointを実行すると、`Review_List` で `approved` になっている商品の `Draft_Mercari_List` 行だけをコピーして作り直します。HTTP query parameterで `batch_prefix=exports/{batch_id}` を必ず指定します。このシートは1行目に公式CSVテンプレート相当のヘッダー、2行目以降に承認済み商品行を出します。CSVとしてダウンロードし、メルカリShopsへアップロードします。

`Yahoo_List` は、ヤフオク向けデータの出力先です。

これらのワークシートは、対象スプレッドシート内に存在しない場合、処理時に自動作成します。実行用サービスアカウントには、対象スプレッドシートを編集できる権限が必要です。

現時点では、メルカリShopsへのアップロード自体は自動化していません。最終CSVをダウンロードし、メルカリShops上で最終確認して出品する運用です。

確認が必要な商品は商品単位のreviewファイルにも出力します。直下の商品フォルダ運用では `review_required/{商品管理コード}.csv`、`exports/{batch_id}/{商品管理コード}/` のようなバッチprefix運用では `exports/{batch_id}/review_required/{商品管理コード}.csv` に出力します。採寸なし、状態メモなし、ブランド不明、カテゴリ不明、タイトル自動短縮、Mercari本文へのHTMLタグやYahoo向け文言の混入など、人が確認すべき理由を日本語で記録します。

単一の共有 `review_required.csv` へ通常処理から直接追記する方式は、同時実行時の上書きや欠落を避けるため使用しません。全商品分のreviewを1つのCSVにまとめる場合は、`review_required/` 配下の商品単位CSVを集約します。直下運用ではルートの `review_required.csv`、バッチprefix運用では `exports/{batch_id}/review_required.csv` として出力します。

集約処理は通常の商品イベント処理とは分離しています。`yahuoku-to-mercarishops/main.py` の `aggregate_review_required_files(bucket_name, batch_prefix="exports/{batch_id}")` から実行できます。また、Cloud Functionsの別entrypointとして `aggregate_review_required_on_marker` をデプロイすると、`_SUCCESS.txt` または `_processed.txt` の作成イベントをきっかけに、対象batch prefixだけ集約判定できます。

review集約CSVは、対象prefix内で画像があるすべての商品フォルダに `_SUCCESS.txt` が存在する場合だけ生成します。また、集約対象は `_processed.txt` が作成済みの処理完了商品だけです。これにより、アップロード途中の商品や、Google Sheets追記・processed化が完了していない商品のreview行が単一CSVへ混ざることを防ぎます。

承認済みメルカリShops用CSVの生成は、`export_approved_mercari_csv` entrypointから実行します。このentrypointはHTTP Functionとしてデプロイし、必要なタイミングで手動実行または管理用ボタンから呼び出す運用を想定しています。複数batchが混ざらないよう `?batch_prefix=exports/{batch_id}` は必須です。指定したbatchのreview行が存在しない場合は、既存の `Approved_Mercari_CSV` を消さずにエラー終了します。

本番のCloud Functionsは、次のentrypointで運用します。Cloud Functions Gen2では、entrypointごとにCloud Functionsリソースをデプロイし、対応するCloud Runサービスはデプロイ時に作成されます。

1. `image-to-description`: `_SUCCESS.txt` と画像から `_description.txt` を生成
2. `generate_dual_listing`: `_description.txt` から `Draft_Mercari_List`、`Review_List`、`Yahoo_List` へ出力
3. `aggregate_review_required_on_marker`: `_SUCCESS.txt` または `_processed.txt` のイベントからreview集約CSVを生成
4. `export_approved_mercari_csv`: HTTP実行で `Approved_Mercari_CSV` を承認済み行から再生成

実際のデプロイやCloud Runサービスの作成は、GCPプロジェクト権限と本番設定の確認が必要です。このリポジトリではentrypointと実装を管理し、デプロイは承認後に行います。

entrypointごとのデプロイ構成と本番前チェックリストは [DEPLOYMENT.md](DEPLOYMENT.md) にまとめています。

---

手動確認が必要な項目

現在のMVPでは、以下の項目を人が確認・修正する必要があります。

- 商品名
- 商品カテゴリID
- ブランドID
- 販売価格
- 商品状態
- 配送方法
- 発送元地域
- 発送までの日数
- AIが生成した商品説明文
- 画像の内容と表示順
- 状態メモが説明文に正しく反映されているか
- `review_required/{商品管理コード}.csv` または `exports/{batch_id}/review_required/{商品管理コード}.csv` に出力された確認理由と修正内容

生成AIの出力には誤りや表現の揺れが発生する可能性があるため、AI生成結果をそのまま出品には使用しません。

---

技術的に工夫した点

イベント駆動型の処理

画像をアップロードしただけでは処理を開始せず、商品情報を記載した"_SUCCESS.txt"がアップロードされた時点で処理を開始します。

これにより、画像アップロードの途中で商品説明文生成が開始されることを防いでいます。

サービスの責務を分離

以下の2つの処理を別サービスに分けています。

- 画像解析と商品説明文の生成
- 販売プラットフォーム別データの生成

これにより、商品説明文生成処理とデータ変換処理を独立して修正しやすい構成にしています。

画像順の制御

Cloud Storageから取得した画像URLをそのまま使用せず、ファイル名から数字を抽出して昇順に並べ替えています。

これにより、撮影者がファイル名を指定することで、出品ページ上の画像表示順を制御できます。

重複実行の抑止

"_description.txt"処理時に処理ロックを作成し、Google Sheetsへ追記した後に"_processed.txt"へ変更することで、同じ商品データの重複処理を抑止しています。また、Sheets追記前に既存の一意キーを確認し、Cloud Functionsのリトライ時に同じ行を再appendしにくいようにしています。

Human-in-the-loop

カテゴリ、ブランド、価格、商品状態など、誤りが売上や顧客対応に影響する項目は、自動確定せず人が最終確認する設計としています。

シークレット管理

Gemini APIの認証情報は、ソースコードへ直接記載せず、Google Secret Managerから取得します。

実際のAPIキー、Google CloudプロジェクトID、スプレッドシートIDなどは、このリポジトリに含めていません。

---

使用技術

分類| 技術
言語| Python
実行基盤| Google Cloud Run functions / Functions Framework
ストレージ| Google Cloud Storage
生成AI| Vertex AI Gemini、Gemini API
AIモデル| Gemini 2.5 Flash、Gemini 2.5 Flash-Lite
シークレット管理| Google Secret Manager
データ出力| Google Sheets API
Pythonライブラリ| "google-cloud-storage"、"google-cloud-secret-manager"、"gspread"、"functions-framework"
イベント| Cloud Storageのオブジェクト作成イベント

---

ディレクトリ構成

mercari-shops-auto-description/
├── image-to-description/
│   ├── main.py
│   └── requirements.txt
├── yahuoku-to-mercarishops/
│   ├── main.py
│   ├── listing_data.py
│   └── requirements.txt
├── tests/
│   └── test_listing_data.py
├── prompt.txt
├── mercari_prompt.txt
├── .gitattributes
├── .gitignore
└── README.md

"image-to-description/"

商品画像と"_SUCCESS.txt"本文の商品情報から、商品説明文を生成するサービスです。

"yahuoku-to-mercarishops/"

生成された商品説明文と画像URLから、メルカリShops向け73列データおよびヤフオク向け114列データを生成するサービスです。

`listing_data.py`には、画像URLの並び替えと販売プラットフォーム別の行データ生成を、副作用のない関数として切り出しています。Cloud StorageやGoogle Sheetsへのアクセスを必要とせずにテストでき、CSV仕様の変更箇所も定数として確認できます。

`prompt.txt` と `mercari_prompt.txt` はリポジトリに保管していますが、実行時は各サービスの `PROMPT_BUCKET_NAME` / `PROMPT_FILE_NAME` で指定したGCS上のプロンプトを読み込みます。デプロイ時は、リポジトリ内のファイル内容とruntimeが参照するGCS prompt bucketまたは環境変数の指定が一致していることを確認してください。

テストはリポジトリのルートで以下を実行します。

```
python -m pytest -p no:cacheprovider tests
```

---

実行に必要な設定

本システムを別環境で動作させるには、以下のGoogle Cloudリソースと設定が必要です。

Google Cloud

- Google Cloudプロジェクト
- 商品画像およびトリガーファイル保存用Cloud Storageバケット
- プロンプト保存用Cloud Storageバケット
- Cloud Storageイベントを受け取る2つの実行サービス
- Vertex AI API
- Secret Manager API
- Google Sheets API
- Google Drive API
- 実行用サービスアカウント
- 必要なIAM権限

アプリケーション設定

- Google CloudプロジェクトID
- 利用リージョン
- 使用するGeminiモデル名
- プロンプト保存用バケット名
- プロンプトファイル名
- Secret Managerのシークレット名
- GoogleスプレッドシートID
- 出力先ワークシート名
- 商品画像保存用バケット名

実際の認証情報、APIキー、プロジェクトID、バケット名、スプレッドシートIDは、セキュリティ上の理由からリポジトリに含めていません。

---

必要な権限

実行用サービスアカウントには、構成に応じて以下の権限が必要です。

- Cloud Storageのオブジェクト読み取り
- Cloud Storageのオブジェクト作成・削除
- Vertex AIの利用
- Secret Managerのシークレット参照
- Googleスプレッドシートの読み書き

また、出力先のGoogleスプレッドシートを、実行用サービスアカウントから編集できる状態にする必要があります。

---

現在のステータス

本プロジェクトは、個人で運営していたリユース事業の実業務を基に開発したMVPです。

現在は、以下の処理を実装しています。

- 商品画像と"_SUCCESS.txt"本文の商品情報の取得
- 生成AIによる説明文作成
- 画像URLの数字順ソート
- メルカリShops向け73列データ作成
- ヤフオク向け114列データ作成
- Googleスプレッドシートへの出力
- 処理済みファイルへの変更による重複実行の抑止
- 出品データの列数・画像URL順・主要な列マッピングのユニットテスト

一方で、実際の出品までを完全自動化する段階には至っていません。

---

現在の制約

- AIが生成した商品情報の正確性は保証されない
- 商品名は自動確定していない
- カテゴリIDとブランドIDは人による設定が必要
- 販売価格は自動算出していない
- 商品状態は状態メモから自動判定していない
- 配送設定の一部に固定値を使用している
- スプレッドシートからCSVへの自動出力は未実装
- メルカリShopsおよびヤフオクへの自動アップロードは未実装
- エラー発生時の自動再実行は未実装
- Cloud Storage、Gemini、Google Sheetsを含む結合テストは未整備
- 監視、通知、処理状況の可視化は未整備
- 公開画像URLを利用するため、画像公開範囲の管理が必要
- 外部サービスのCSV仕様変更に応じた更新が必要

---

今後の改善予定

優先度の高い改善項目は以下です。

1. 設定値の環境変数化
2. AI出力のJSON構造化
3. 入力データと出力データのバリデーション
4. APIエラー時のリトライ処理
5. エラー発生時の再実行機能
6. ログの構造化
7. 処理状況の可視化
8. 商品カテゴリとブランドの候補推定
9. 商品状態の候補推定
10. CSVファイルの自動生成
11. GitHub Actionsによる自動テスト
12. Cloud Storage、Gemini、Google Sheetsを含む結合テスト
13. 実測データによる処理時間と削減効果の検証

---

外部仕様

本システムは、以下のメルカリShops公式仕様を参考に実装しています。

メルカリShops

- "商品を一括登録する際のCSVファイルの作り方" (https://support.mercari-shops.com/hc/ja/articles/8859698858649-%E5%95%86%E5%93%81%E3%82%92%E4%B8%80%E6%8B%AC%E7%99%BB%E9%8C%B2%E3%81%99%E3%82%8B%E9%9A%9B%E3%81%AECSV%E3%83%95%E3%82%A1%E3%82%A4%E3%83%AB%E3%81%AE%E4%BD%9C%E3%82%8A%E6%96%B9)

メルカリShops向けデータは、公式の一括登録用CSVフォーマットを前提としています。

メルカリShops用CSVのヘッダー行は、`yahuoku-to-mercarishops/listing_data.py` の `MERCARI_HEADERS` に固定しています。これは「実行時に外部テンプレートを取りに行かず、リポジトリ内の定義を正とする」という意味です。公式テンプレートが変更された場合は、`MERCARI_HEADERS` と対応する列マッピングをPRで更新します。

商品画像については、Google Cloud Storage上の公開URLを商品画像欄へ設定します。商品画像の順番は、画像ファイル名に付与した数字を基準に制御します。

ブランドID、カテゴリID、商品状態、配送設定などは、公式仕様および各種マスタを確認したうえで、出力後に人が設定・修正する運用を前提としています。

---

免責事項

本プロジェクトは個人で開発した非公式ツールです。

株式会社メルカリ、メルカリShops、LINEヤフー株式会社、ヤフオク、オークタウン、および各サービス運営会社とは関係ありません。

外部サービスの仕様変更により、出力データが利用できなくなる可能性があります。実際に使用する際は、各サービスの最新の公式仕様を確認してください。

---

## ロードマップ

レビュー承認ワークフローのPhase 1からPhase 3までの方針は [ROADMAP.md](ROADMAP.md) にまとめています。

`review_required.csv` はメルカリShopsへアップロードするCSVではなく、人間が確認すべき項目の一覧です。最終的には、レビュー済み・承認済みの商品データだけからメルカリShops用CSVを生成する運用を目指します。
