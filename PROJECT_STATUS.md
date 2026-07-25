# PROJECT_STATUS.md

## 2026-07-25 更新: image-to-descriptionのメモリ対策をデプロイ

10商品テストでは、旧実装が画像本体を関数メモリへ読み込んだことで使用量が約551 MiBへ達し、512 MiB上限を超えた処理が強制終了しました。6商品が完了し、4商品には `_description_processing.lock` が残りました。

PR #12のマージコミット `ad7edae` をCloud Run Function `image-to-description` へデプロイしました。稼働中Revisionは `image-to-description-00004-hub` で、次の設定を読み取り専用確認済みです。

- Project: `gen-lang-client-0122735738`
- Region: `asia-northeast1`
- State: `ACTIVE`
- Memory: 512 MiB
- Concurrency: 1
- Timeout: 540秒
- Trigger: `test-review-ui` の `google.cloud.storage.object.v1.finalized`
- Retry: 無効
- Runtime service account: `183777458573-compute@developer.gserviceaccount.com`

新実装は画像を関数へダウンロードせず、GCS URIとしてVertex AIへ渡します。15分以上経過した処理ロックは、確認したGCS世代番号に一致する場合だけ回収します。デプロイ時にトリガー、サービスアカウント、環境変数、Secret、IAM、IAP、API、バケット設定は変更していません。

デプロイ後の商品投入、既存4商品の `_SUCCESS.txt` 再投入、Gemini呼び出しは未実施です。次は1商品をcanaryとして確認し、成功後に10商品を処理して、生成物件数、残存ロック、重複、メモリ不足の再発有無を確認します。

2026-07-25の読み取り専用GCS確認では、旧10商品テストの状態を次のように確認しました。オブジェクト内容は取得していません。

- 成功6商品: `BALLY　黒　革靴`、`CTHY　厚底靴　黒`、`Photos-3-001 (1)`、`marka　黒Vネックプルオーバー`、`セオリーユニクロポロシャツ`、`ユニクロJWA`
- 成功商品はそれぞれ `_processed.txt` と `mercari.csv`、`yahoo.csv`、`review_required.csv`、`result.json`、`_DONE.txt` を保持する。
- 失敗4商品: `BALLY　茶色タッセル革靴`、`Danner　黒　ブーツ`、`Photos-3-001 (3)`、`三陽山長　革靴(茶色)`
- 失敗商品はそれぞれ `_description_processing.lock` が残り、`_processed.txt` と後続生成物は存在しない。
- 最初のcanary候補は、10画像・1トリガー・1残存ロックを持つ `Photos-3-001 (3)` とする。

---

## 2026-07-19 更新: 承認フローのmain統合確認・AI開発基盤整備

### 結論

ローカルGit履歴では、Review UI / Google Sheets承認フローを含むPR #6のマージコミット `a724214` が `main` に含まれています。承認フローはmainへ統合済みです。

現在の作業ブランチは最新の `origin/main` を基点とし、AI開発基盤だけを追加します。2026-07-18までの記録ではCloud Run上のGoogleログイン、商品表示、編集、画像並び替え、承認、公式88列CSV生成・ダウンロード、メルカリShopsへの実投入を確認済みです。この更新ではGCPへ接続していないため、稼働中Revisionと現在のGit HEADの一致は要確認です。

---

## 現在の安定版: main

### できること

- 商品画像と `_SUCCESS.txt` を入力にする
- `_SUCCESS.txt` 本文を採寸・状態メモとして扱う
- Geminiを使って商品説明・商品属性を生成する
- メルカリShops向け `mercari.csv` を生成する
- Yahooオークション向け `yahoo.csv` を生成する
- 確認が必要な項目を `review_required.csv` に出力する
- 処理結果を `result.json` に保存する
- 成功時に `_DONE.txt` を出力する
- Google Sheetsへ下書き・確認・Yahoo行を同期する（`SPREADSHEET_ID`設定時のみ）
- Review UIで人間が確認・修正・承認する
- 承認済み商品だけから公式88列・UTF-8 BOM付きCSVを生成する

### 実機検証済み

- メルカリShops用CSVアップロード
- メルカリShops下書き保存
- 下書き画面での商品画像表示
- GCS公開画像URL方式による画像列出力

### 未検証

- Yahooオークション側へのCSV実投入
- 複数商品での広範囲な再現性検証
- 生成文の完全な品質安定化

---

## mainに統合済みの承認フロー

Google Sheets承認フローとReview UIはローカル `main` に統合済みです。現在の作業ブランチには、業務コードを変更しないAI開発基盤の整備だけが含まれます。

### 追加内容

- Google Sheets承認ワークフロー
- `Draft_Mercari_List`
- `Review_List`
- `Approved_Mercari_CSV`
- `Yahoo_List`
- Review UI
- Cloud Run用のReview UIデプロイ構成
- 承認済みCSVを再生成するHTTP entrypoint

既存の `scripts/deploy_review_ui.ps1` はアプリ配備とAPI・IAM・IAP・bucket初期設定を混在させています。現在はAI実行対象外とし、将来のアプリ専用デプロイ設計を `docs/deployment-safety.md` に分離しています。

### 位置づけ

既存のGCS CSV/JSON出力を維持したまま、人間確認・承認フローを追加した機能です。

採用向けには、次のように説明します。

```text
商品画像とメモから出品用データを生成し、AI生成結果をGoogle SheetsとReview UIで確認・修正・承認したうえで、公式CSVを生成するフローを実装・実機検証しました。
```

---

## 承認フローの実装状況

### Google Sheets承認ワークフロー

- `sheets_workflow.py` を追加し、Google Sheets承認ワークフローを既存CSV生成処理から分離
- `SPREADSHEET_ID` が設定されている場合のみSheets同期を実行
- 既存のCloud Storage成果物 `mercari.csv`、`yahoo.csv`、`review_required.csv`、`result.json`、`_DONE.txt` は維持
- Sheets同期が有効な場合は、CSV/JSON出力とSheets同期が成功した後に `_DONE.txt` を作成
- Draft/Yahooの冪等キーは先頭画像URL、Reviewの冪等キーは `batch_prefix/product_code`
- `Approved_Mercari_CSV` は指定された `batch_prefix` の `approved` 商品だけから再生成

### Review UI

- `review-ui` にFlaskアプリ、テンプレート、CSS、Dockerfile、requirementsを追加
- batch一覧、商品一覧、商品編集、商品承認、batch単位の承認済みCSV生成・ダウンロード画面を追加
- 商品編集画面で画像プレビューを見ながら下書きCSV項目を修正できるようにした
- 商品一覧と編集画面の画像表示はCloud Run経由のGCS画像プロキシを使う
- batch詳細画面に承認済み件数を表示
- 承認済み商品が0件の場合はアップロード用CSVを生成しない
- 承認済み商品を `Save` のみで編集した場合は `needs_review` に戻し、再承認なしに最終CSVへ入らないようにした
- Review UIにSheets/GCSへ触らない `/healthz` を追加
- `export_approved_mercari_csv` HTTP entrypointはPOSTのみ再生成を許可
- 最終CSVは公式88列・UTF-8 BOM付きで生成し、非公開GCS画像を7日間有効の署名付きURLへ変換
- 公式必須項目や価格・文字数・配送コード・画像取得を生成前に検証し、違反時はCSV生成を停止

---

## 確認済み

以下の実機項目は2026-07-18までの記録です。現在の本番状態は、この文書更新では外部接続していないため再確認していません。

- Cloud RunのGoogleログインと許可ユーザー制限
- runtime service accountのSpreadsheet / GCS / 署名権限
- private bucketの商品画像表示
- 商品編集、カテゴリ選択、画像並び替え、Save / Save & Approve
- 承認済み商品だけの公式88列CSV生成
- UTF-8 BOM、署名付き画像URLの未認証取得
- メルカリShopsへのCSVアップロード成功
- 標準テストとコンポーネントローカルテストを含む共通検証が成功（件数はCIまたは最新の実行結果を参照）
- 10商品×2batchと同一イベント再実行の自動テスト成功
- `_SUCCESS.txt`と管理プロンプトの読込・decode障害を例外停止へ統一
- `状態メモ`、`状態`、`コンディション`、`特記事項`、`備考`、`注意点`を明示ラベルとして解析

## 継続確認

- 実データで異なる日付の10商品batchを2回処理して混在しないこと
- 実環境のリトライ・途中失敗からの復旧で重複しないこと
- Yahooオークション側へのCSV実投入
- Artifact Registryの古いimage削除運用

---

## Git状態とPR情報

- ローカル `main` はPR #6のマージコミット `a724214` を含みます。
- 現在の作業ブランチは最新の `origin/main` を基点とし、AI開発基盤の4コミットだけを追加します。
- PR #4、PR #5、PR #7を含むGitHub上の現在のopen/closed/merged状態は、この更新ではGitHub APIへ接続していないため要確認です。
- 一時的なPR状態ではなく、Git履歴、CI、最新の共通検証を長期的な状態の根拠にします。

---

## 採用向けの見せ方

### 書いてよい表現

```text
リユース事業の出品作業を効率化するため、商品画像と採寸・状態メモからメルカリShops向けCSVを生成するMVPを開発。AI生成結果をReview UIで確認・修正・承認し、公式CSVをメルカリShopsへアップロードできるところまで実機検証済み。
```

### 避ける表現

```text
メルカリShopsとYahooオークションへの自動出品を完全実現。
```

理由:

- Yahooオークションへの実投入は未検証
- AI生成結果は人間確認前提
- Yahooオークション側は実投入未検証

---

## 直近のTODO

1. 現在の作業ブランチを共通検証と独立レビューで確認する
2. 稼働中Cloud Run Revisionとmainの対応を人間が確認する
3. 10商品×2batchの実データ混在・リトライ試験を人間主導で行う
4. PR #4、PR #5の現在状態と未反映機能をGitHub上で人間が確認する
5. Webアップロード画面など次段階の操作改善を進める

---

## 過去の主要マイルストーン

### 2026-07-18: Review UI / 公式CSVの実機検証完了

- Review UIをCloud Runで動かす構成を追加
- Google Sheets承認フローを追加
- Draft / Review / Approved / Yahoo の各シート連携を追加
- Review UIから編集・承認・承認済みCSV生成を行う構成にした
- 公式88列・UTF-8 BOM・署名付き画像URLのCSVを生成
- メルカリShopsへの実際のCSVアップロードに成功

### 2026-07-01: PR #2最終確認と実機検証

- Cloud Functions Gen2へデプロイ済み
- GCSトリガーでCSV生成が起動することを確認
- メルカリShops用 `mercari.csv` の `商品画像名_1` 〜 `商品画像名_20` はGCS公開画像URL方式へ変更
- メルカリShopsへのCSVアップロード、下書き保存、下書き画面での商品画像表示まで実機検証済み
- Yahooオークション向け `yahoo.csv` の生成処理は実装済み
- Yahooオークション側へのCSV実投入は未検証

### 2026-06-29: GCSトリガーからCSV出力まで成功

- `mercari.csv`
- `yahoo.csv`
- `review_required.csv`
- `result.json`
- `_DONE.txt`

上記の出力を確認。

### 2026-06-29: メルカリShops画像URL方式へ修正

メルカリShops側で画像ファイル名方式だと投入時に画像が見つからない問題があったため、メルカリShops用CSVの画像列をGCS公開画像URL方式へ変更。

### 2026-06-28: P0/P1修正をPR #2に反映

- 環境変数化
- Secret Manager連携
- Vertex AI初期化の遅延化
- CSVヘッダー検証
- `.env.example` 追加
- READMEのデプロイ手順整理
