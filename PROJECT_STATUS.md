# PROJECT_STATUS.md

## 2026-07-10 更新: PR #6をmain最新ドキュメントへ追従

### 結論

mainは「安定版MVP」、PR #6は「Review UI / Google Sheets承認フローを追加する最新開発ブランチ」として扱います。

PR #7でmainへ反映した公開向け整理文に合わせ、PR #6側のREADME / PROJECT_STATUSも追従しました。コード、Review UI本体、Cloud Functions本体の処理はこの追従更新では変更していません。

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

## 最新開発: PR #6

PR #6は、フロントエンドを含む最新開発ブランチとして扱います。

### 追加内容

- Google Sheets承認ワークフロー
- `Draft_Mercari_List`
- `Review_List`
- `Approved_Mercari_CSV`
- `Yahoo_List`
- Review UI
- Cloud Run用のReview UIデプロイ構成
- 承認済みCSVを再生成するHTTP entrypoint

### 位置づけ

PR #6は、既存のGCS CSV/JSON出力を維持したまま、人間確認・承認フローを追加するための開発です。

採用向けには、次のように説明します。

```text
安定版ではメルカリShops向けCSV生成と下書き保存まで実機検証済みです。現在は、AI生成結果を人間が確認・承認できるよう、Google SheetsとReview UIを使った承認フローをPR #6で開発中です。
```

---

## PR #6の実装状況

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

---

## 本番前に確認すること

- Cloud Run IAPまたはGoogle認証設定
- Review UIの許可ユーザー設定
- Review UI runtime service accountのSpreadsheet編集権限
- Review UI runtime service accountの商品画像GCS read権限
- Review UI runtime service accountの承認済みCSV GCS write権限
- `yahuoku-to-mercarishops` runtime service accountのSpreadsheet編集権限
- `/healthz` が `ok` を返すこと
- private bucketの商品画像サムネイルがReview UIで表示できること
- 実データでMercari Shops CSVのダウンロード、アップロード、最終確認まで通し検証すること
- Cloud Run `min-instances=0`、`max-instances=1`、budget/alert、Artifact Registry画像削除運用を確認すること

---

## PR整理方針

| PR | 状態 | 扱い |
|---|---|---|
| PR #4 | open | 入力仕様・生成品質改善候補。PR #6との整合確認後に判断する |
| PR #5 | open / draft | 現時点では触らない。PR #6の旧プロトタイプ候補として保留する |
| PR #6 | open / draft | 最新開発本線。Review UI / Google Sheets承認フローとして扱う |
| PR #7 | merged | 公開向けGitHub整理としてmainへ反映済み |

---

## 採用向けの見せ方

### 書いてよい表現

```text
リユース事業の出品作業を効率化するため、商品画像と採寸・状態メモからメルカリShops向けCSVを生成するMVPを開発。メルカリShopsへのCSVアップロード、下書き保存、画像表示まで実機検証済み。現在はAI生成結果を人間が確認・承認できるReview UI / Google Sheets承認フローを開発中。
```

### 避ける表現

```text
メルカリShopsとYahooオークションへの自動出品を完全実現。
```

理由:

- Yahooオークションへの実投入は未検証
- AI生成結果は人間確認前提
- Review UI / Sheets承認フローはPR #6で開発中

---

## 直近のTODO

1. PR #6をmain最新ドキュメントへ追従させる
2. PR #6のmergeabilityを確認する
3. Review UIの本番前チェックを進める
4. PR #4をPR #6とどう整合させるか判断する
5. PR #5は現時点では触らない
6. docs/evidenceのスクショに不要な内部情報が写っていないか確認する

---

## 過去の主要マイルストーン

### 2026-07-08: Review UI / Phase 1承認フローの実装確認中

- Review UIをCloud Runで動かす構成を追加
- Google Sheets承認フローを追加
- Draft / Review / Approved / Yahoo の各シート連携を追加
- Review UIから編集・承認・承認済みCSV生成を行う構成にした
- IAP、サービスアカウント権限、Spreadsheet編集権限、画像表示、CSV投入の確認が本番前課題

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
