# PROJECT_STATUS.md

## 2026-07-10 更新: GitHub公開状態の整理

### 結論

現時点では、mainを「安定版MVP」、PR #6を「最新開発中のReview UI / Google Sheets承認フロー」として扱います。

PR #5は旧プロトタイプに近く、現時点では触りません。closeも行いません。

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

### 追加中の内容

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

### 本番前に確認すること

- Cloud Run IAPの動作
- Review UIのサムネイル表示
- サービスアカウントのGCS / Spreadsheet / CSV出力先への権限
- `/healthz` の応答
- `Approved_Mercari_CSV` から作ったCSVのメルカリShops投入
- Save後に再承認が必要になる仕様

---

## PR整理方針

| PR | 状態 | 扱い |
|---|---|---|
| PR #4 | open | 入力仕様・生成品質改善候補。PR #6との整合確認後に判断する |
| PR #5 | open / draft | 現時点では触らない。PR #6の旧プロトタイプ候補として保留する |
| PR #6 | open / draft | 最新開発本線。Review UI / Google Sheets承認フローとして扱う |

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

1. READMEを採用担当者向けに整理する
2. TASKS.mdを最新タスクに置き換える
3. PR #6の本番前チェックを進める
4. PR #4をPR #6とどう整合させるか判断する
5. PR #5は現時点では触らない
6. docs/evidenceのスクショに不要な内部情報が写っていないか確認する

---

## 過去の主要マイルストーン

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
