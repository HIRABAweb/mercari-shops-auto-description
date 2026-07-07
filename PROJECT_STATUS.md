# PROJECT_STATUS.md

## 2026-07-08 更新: Phase 1 本番導線をReview UIへ接続

### 到達点
- Review UIは `hirabaaiwork@gmail.com` でIAPログインできることを確認済み。
- `image-to-description` を再デプロイし、trigger bucketを `test-review-ui` に変更済み。
- `yahuoku-to-mercarishops` を再デプロイし、trigger bucketを `test-review-ui` に変更済み。
- `yahuoku-to-mercarishops` に `SPREADSHEET_ID=16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc` を設定済み。
- 既存のprompt bucket/file名、Gemini model、Secret名は維持した。
- Runtime service account `183777458573-compute@developer.gserviceaccount.com` に `test-review-ui` の読み書き権限を付与済み。

### 現在の構成
- 外注/運用アップロード先 bucket: `test-review-ui`
- Review UI参照Spreadsheet: `16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc`
- 商品処理Functions runtime service account: `183777458573-compute@developer.gserviceaccount.com`
- Review UI runtime service account: `mercari-review-ui-sa@gen-lang-client-0122735738.iam.gserviceaccount.com`

### 次に確認すること
- Spreadsheetに `183777458573-compute@developer.gserviceaccount.com` が編集者として追加されていること。
- `test-review-ui` にテスト商品を1件アップロードすること。
- 推奨パスは `exports/{batch_id}/{item_id}/`。
- 商品画像と `_SUCCESS.txt` を置いた後、`_description.txt`、`mercari.csv`、`review_required/{item_id}.csv`、Sheets行が生成されること。
- Review UIのbatch一覧に該当batchが表示されること。

## 2026-07-08 更新: Review UI デプロイとIAP OAuth確認中

### 到達点
- Google Cloud project `gen-lang-client-0122735738` にReview UI用Cloud Runサービス `mercari-review-ui` をデプロイ済み。
- Artifact Registry repository `review-ui` とDocker imageを作成済み。
- Product bucketは `test-review-ui` を使用。
- Cloud Run runtime service accountは `mercari-review-ui-sa@gen-lang-client-0122735738.iam.gserviceaccount.com`。
- Runtime service accountには `test-review-ui` の読み書き権限を付与済み。
- Runtime service accountはSpreadsheet編集者として追加済み。
- Cloud Run serviceはIAP有効、許可ユーザーは `hirabaaiwork@gmail.com`。

### 現在のブロッカー
- Review UI URLで出ていた `Empty Google Account OAuth client ID(s)/secret(s).` は、IAP OAuth auto-generate credentials 後に解消済み。
- これはReview UIアプリ本体のエラーではなく、IAPのOAuth client ID/secretが未設定の状態。
- 組織なしGoogle Cloud projectでは、初回のIAP OAuth設定をGoogle Cloud Consoleで行うか、手動作成したcustom OAuth clientをIAP settingsへ適用する必要がある。

### 対応済み
- `docs/review_ui_deployment.md` にIAP OAuth setup手順とトラブルシュートを追記。
- `docs/user_action_checklist.md` に、ユーザーがConsoleで確認するOAuth設定を追記。
- `scripts/apply_iap_oauth_settings.ps1` を追加し、手動作成したOAuth client ID/secretを安全にIAP project settingsへ適用できるようにした。

### 次に確認すること
- Google Cloud Consoleで `mercari-review-ui` のIAP OAuth/Google Auth Platform設定を完了する。
- Audienceは `External` とし、`hirabaaiwork@gmail.com` でログインできることを確認する。
- Consoleでauto-generated credentialsを使える場合は、それを優先する。
- 手動OAuth clientを作る場合、client secretはチャットに貼らず、Consoleまたはローカル補助スクリプトで設定する。
- OAuth設定後、Review UI URLがログイン画面またはアプリ画面へ進むことを確認する。

## 2026-07-07 更新: Phase 1 Review UI 初期実装

### 方針
- Google Sheets承認ワークフローを裏側の保存先として維持し、Cloud Run用の `review-ui` を追加した。
- 既存の `_SUCCESS.txt` → `_description.txt` → GCS CSV/JSON/Sheets同期の流れは変更しない。
- Web UIは `Draft_Mercari_List` の編集、`Review_List` の承認、`Approved_Mercari_CSV` とGCS上の承認済みCSV生成を担当する。

### 実装状況
- `review-ui` にFlaskアプリ、テンプレート、CSS、Dockerfile、requirementsを追加。
- batch一覧、商品一覧、商品編集、商品承認、batch単位の承認済みCSV生成・ダウンロード画面を追加。
- `sheets_workflow.py` にbatch一覧、商品取得、下書き更新、承認、承認済みCSVテキスト生成の共通処理を追加。
- 承認済みCSVのGCS保存先は `exports/{batch_id}/approved/mercari_shops.csv`。
- 編集画面は `Save & Approve` で下書き保存後に承認する方式にし、保存前の内容を誤って承認しないようにした。
- Review UIのPOST操作にCSRF tokenを追加した。
- Cloud Run上では `FLASK_SECRET_KEY` を必須にした。
- 商品一覧と編集画面の画像表示はCloud Run経由のGCS画像プロキシを使い、private bucketでも表示できるようにした。
- 商品編集画面で画像プレビューを見ながら下書きCSV項目を修正できるようにした。
- batch詳細画面に承認済み件数を表示し、承認済み商品が0件の場合はアップロード用CSVを生成しないようにした。
- 承認済み商品が0件の場合は、既存の `Approved_Mercari_CSV` も変更しないようにした。
- 承認済み商品を `Save` のみで編集した場合は `needs_review` に戻し、再承認なしに最終CSVへ入らないようにした。
- Review UIにSheets/GCSへ触らない `/healthz` を追加した。
- `export_approved_mercari_csv` HTTP entrypointはPOSTのみ再生成を許可するようにした。

### 本番前に確認すること
- Cloud Run `review-ui` のIAPまたはGoogle認証設定。
- `SPREADSHEET_ID` は `16mcXnRgC4Mqx5ghUsNqjLpg87sC4Ss591osfZNIlKsc` を使う。
- Review UIの許可ユーザーは `hirabaaiwork@gmail.com` に限定する。
- `PRODUCT_BUCKET_NAME` は新規bucketを作るより、既存の商品アップロードbucketを優先して使う。
- `FLASK_SECRET_KEY` の本番値。
- `review-ui/Dockerfile` を使う場合、ビルドコンテキストをリポジトリルートにすること。
- Cloud Buildでは `cloudbuild.review-ui.yaml` を使い、`review-ui/Dockerfile` を明示すること。
- Cloud Run service accountに、Spreadsheet編集権限、商品画像のGCS read権限、承認済みCSVのGCS write権限を付与すること。
- `/healthz` が `ok` を返すこと。
- private bucketの商品画像サムネイルがReview UIで表示できること。
- 実データでMercari Shops CSVのダウンロード、アップロード、最終確認までの通し検証。
- 課金回避のため、実デプロイ前にbudget/alert、Cloud Run `min-instances=0`、`max-instances=1`、Artifact Registry画像削除運用を確認する。

## 2026-07-06 更新: Phase 1承認ワークフローをmain現行設計へ移植中

### 方針

- PR #5はDraftのまま設計・試作ブランチとして維持する。
- `origin/main` がCSV artifact出力設計へ進んでいるため、PR #5を直接mergeせず、`origin/main` 起点の `feature/phase1-review-workflow-on-main` で移植する。
- 既存のCloud Storage成果物 `mercari.csv`、`yahoo.csv`、`review_required.csv`、`result.json`、`_DONE.txt` は維持する。
- `SPREADSHEET_ID` が設定されている場合のみ、Google Sheets上の `Draft_Mercari_List`、`Review_List`、`Approved_Mercari_CSV`、`Yahoo_List` へ追加同期する。
- Sheets同期が有効な場合は、CSV/JSON出力とSheets同期が成功した後に `_DONE.txt` を作成する。

### 実装状況

- `sheets_workflow.py` を追加し、Google Sheets承認ワークフローを既存CSV生成処理から分離した。
- `export_approved_mercari_csv` HTTP entrypointを追加した。
- Draft/Yahooの冪等キーは先頭画像URL、Reviewの冪等キーは `batch_prefix/product_code` とした。
- `Approved_Mercari_CSV` は指定された `batch_prefix` の `approved` 商品だけから再生成する。

### 検証

- `python -m pytest -p no:cacheprovider tests`
- 結果: `52 passed`

### 本番前に確認すること

- 本番Spreadsheet IDとサービスアカウントの編集権限
- `export_approved_mercari_csv` HTTP entrypointのIAMまたは呼び出し制御
- 外注先アップロードパスを `exports/{batch_id}/{item_id}/` に統一する運用
- Google Sheets上での実データ確認と、Approved CSVのメルカリShops投入テスト

## 2026-07-01 更新: PR #2最終確認と実機検証状況

### 到達点

- Cloud Functions Gen2へ `feature/title-description-separation` の最新コードをデプロイ済み。
- GCSトリガーでCSV生成が起動することを確認済み。
- メルカリShops用 `mercari.csv` の `商品画像名_1` 〜 `商品画像名_20` は、GCS公開画像URLをそのまま出力する方式へ変更済み。
- メルカリShopsへのCSVアップロード、下書き保存、下書き画面での商品画像表示まで実機検証済み。
- ローカルテストとCloud Shellテストはいずれも `45 passed`。
- PR #2はopenで、mergeable true。

### 検証証跡

公開リポジトリ向けに商品名などをマスクした証跡画像を `docs/evidence/` に保存。

- `docs/evidence/mercari-shops-selected.png`: CSVファイル選択状態
- `docs/evidence/mercari-shops-draft.png`: 下書き画面で商品画像欄が表示された状態
- `docs/evidence/mercari-shops-complete.png`: CSV登録履歴が登録完了になった状態

### PR #2のスコープ確認

- `mercari.csv` の `商品画像名_1` 〜 `商品画像名_20` にはGCS公開URLがそのまま入る。
- URLからbasenameへ変換する処理は削除済み。
- 画像順序はファイル名内の数字順を維持する。
- 画像が20枚を超える場合、メルカリShops用CSVでは20枚までに制限する。
- 画像0枚時は既存どおり画像列が空になる。
- Yahooオークション用CSVは従来どおり画像URLを出力する。
- CSVヘッダー数と必須列検証は既存テストで回帰確認済み。

### Yahooオークション側の検証状況

- Yahooオークション向け `yahoo.csv` の生成処理は実装済み。
- 既存テストで、Yahooオークション用CSVの画像URL出力とヘッダー構成は回帰確認済み。
- ただし、Yahooオークションの実際の出品画面または一括出品ツールへのCSV投入は未検証。
- 公開資料やポートフォリオでは「Yahooオークション向けCSV生成機能」と表現する。
- 「Yahooオークション出品まで実機検証済み」とは表現しない。

### 生成品質改善TODO

優先度高:

1. 状態説明で、画像や状態メモから断定できない誇張表現を禁止する。
2. 商品名生成テンプレートを固定し、タイトルの揺れを抑える。
3. 商品説明欄に商品名を再掲しない。
4. カテゴリIDの自動設定精度を上げるか、半自動運用方針を決める。
5. 3〜5商品でメルカリShops CSV投入テストを行い、生成品質と再現性を確認する。

---


## 2026-06-29 更新: メルカリShops画像URL方式への修正

### 背景

CSV出力自体は成功したが、メルカリShops投入時に画像ファイル名が存在しないエラーが発生した。

原因は、メルカリShops用CSVの画像列に画像ファイル名だけを出力しており、メルカリShops側に同名画像を事前アップロードする運用が必要だったため。

### 修正方針

外注者の二重アップロードを避けるため、メルカリShops用CSVの画像列にはGCS公開画像URLを出力する方式へ変更する。

### 次に確認すること

1. 1商品で `mercari.csv` を再生成する
2. `商品画像名_1` にGCS公開URLが入っていることを確認する
3. URLをブラウザで開き、画像が表示されることを確認する
4. メルカリShopsへCSVを投入する
5. 画像が正しく取り込まれるか確認する


---


## 2026-06-29 更新: GCSトリガーからCSV出力まで成功

### やったこと

- Google Cloud Run FunctionsにPR #2最新コードを再デプロイ
- メモリ不足による起動失敗を確認し、メモリを512MiBへ変更
- 古いEventarcトリガーを整理
- GCSにテスト商品フォルダを作成
- `_SUCCESS.txt` アップロードを起点に処理を実行
- `image-to-description` と `yahuoku-to-mercarishops` の一連の処理を確認

### 出力されたファイル

- `mercari.csv`
- `yahoo.csv`
- `review_required.csv`
- `result.json`
- `_DONE.txt`

### 検証結果

- `result.json` の `success` は `true`
- `_DONE.txt` の中身は `done`
- `mercari.csv` は88列で出力
- `yahoo.csv` は39列で出力
- `review_required.csv` はヘッダーのみで、確認必要項目なし
- 処理時間は約40秒

### この時点で残っていた課題

- メルカリShopsへのCSV投入では、画像ファイル名が存在しないという理由で失敗
- CSV内の画像名と、メルカリShopsに渡す画像ファイル名の一致確認が必要
- 出力CSVと画像ファイルをセットで扱う運用仕様を決める必要がある

### その後の対応

1. メルカリShops用CSVの画像列をファイル名方式からGCS公開画像URL方式へ変更
2. `mercari.csv` の `商品画像名_1` 〜 `商品画像名_20` にURLが入ることをテストで確認
3. メルカリShopsへのCSVアップロードと下書き保存まで実機検証
4. Yahooオークション側はCSV生成と既存テストでの回帰確認まで完了、実投入は未検証


---


## 2026-06-28 更新: P0/P1修正をPR #2に反映

### やったこと

- Codexレビューで指摘されたP0/P1課題を修正
- `PROJECT_ID`, `SECRET_NAME`, `PROMPT_BUCKET_NAME`, `PROMPT_FILE_NAME`, `GEMINI_MODEL` を環境変数から読むように変更
- `get_api_key()` とGemini client生成をインポート時ではなく初回実行時に遅延化
- `image-to-description` 側の `vertexai.init(...)` と `GenerativeModel(...)` も初回実行時に遅延化
- 必須環境変数未設定時に明示的なエラーを出すように変更
- Secret Managerパスが `projects/{PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest` になるように修正
- `.env.example` を追加
- READMEにCloud Run Functionsのデプロイ手順、環境変数、IAM、Console設定手順を追加
- READMEの `result.json` 例を実装に合わせて修正
- 環境変数未設定・Secret Managerパス・Vertex AI初期化前チェックのテストを追加

### 検証結果

.\.test-venv\Scripts\python.exe -m pytest -p no:cacheprovider tests

結果:
43 passed

`git diff --check` も問題なし。

### Git反映状況

* Commit: `dac7b717674816b067a471139ef81c1467c0b28b`
* Short SHA: `dac7b71`
* Message: `Fix Cloud Run configuration handling`
* Branch: `feature/title-description-separation`
* Remote: `origin/feature/title-description-separation`
* リモートとの差分: `ahead: 0 / behind: 0`

### 現在の状態

- P0/P1は修正済み。
- 修正内容はPR #2に反映済み。
- Google Cloud上での実行テストはまだ未実施。
- P2のREADME内の既存ズレは未修正。

### 次にやること

1. PR #2上で差分を確認する
2. Google Cloud Consoleで必要な環境変数を設定する
3. Secret ManagerのSecret名を確認する
4. Cloud Run Functionsで実行テストする
5. Cloud Loggingでエラーを確認する


---


## 現在の進捗

このプロジェクトは、リユースアパレル商品の出品業務を自動化するためのPython / Google Cloud Run Functionsプロジェクトです。

目的は、外注者が商品画像と採寸情報をアップロードしたら、メルカリShopsに一括登録できるCSVを自動生成することです。

現在は、Pull Request #2「CSV出力ワークフローへ改修」の実機検証と最終確認まで進行しています。

## 現在のブランチ

- 作業ブランチ: `feature/title-description-separation`
- PR: #2
- 状態: メルカリShops CSVアップロード・下書き保存まで実機検証済み

## 完了したこと

- GitHubリポジトリ作成
- 作業ブランチ作成
- Pull Request #2 作成
- 商品説明生成ツールからCSV出力ワークフローへ改修
- Googleスプレッドシート出力を廃止
- GCS上にCSV/JSONを出力する構成へ変更
- メルカリShops用CSVを生成する処理を追加
- Yahooオークション用CSVを生成する処理を追加
- 確認が必要な商品を `review_required.csv` に出す構成へ変更
- 処理結果を `result.json` に出す構成へ変更
- 成功時のみ `_DONE.txt` を作る構成へ変更
- ローカルテストとCloud Shellテストで `45 passed` を確認
- Cloud Functions Gen2へ最新ブランチをデプロイ済み
- Google Cloud Storageトリガーでの起動を確認済み
- メルカリShopsへのCSVアップロードと下書き保存を確認済み

## まだやっていないこと

- Yahooオークションの出品画面または一括出品ツールへのCSV投入テスト
- 複数商品でのメルカリShops CSV投入テスト
- AI生成文の品質改善
- 外注者が使えるアップロード手順の作成

## 現在の重要な注意点

メルカリShops用CSVは実機でアップロードと下書き保存まで確認済みです。

Yahooオークション側はCSV生成機能として実装済みで、既存テストでは回帰確認済みです。ただし、Yahooオークションの実際の出品画面または一括出品ツールへのCSV投入は未検証です。

そのため、転職活動や面接では以下のように説明します。

「GCSトリガーでメルカリShops向けCSVとYahooオークション向けCSVを生成する機能を実装しました。メルカリShopsはCSVアップロードと下書き保存まで実機検証済みです。Yahooオークション側はCSV生成機能として実装済みで、実際の出品ツールへの投入は今後検証予定です。」

「Yahooオークション出品まで実機検証済み」とはまだ言いません。

## 次にやること

1. PR #2の最終差分を確認し、問題なければmainへマージする
2. Yahooオークションの出品画面または一括出品ツールへ `yahoo.csv` を投入して検証する
3. 3〜5商品でメルカリShops CSV投入テストを行う
4. AI生成文の誇張表現、商品名再掲、タイトル揺れ、カテゴリ未設定を改善する
5. 外注者向けのアップロード手順を作成する
