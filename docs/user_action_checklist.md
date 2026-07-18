# 運用者チェックリスト

このファイルは、Review UIを日常運用するときに人が確認する項目をまとめています。実際のGoogle CloudプロジェクトID、bucket名、Spreadsheet ID、メールアドレス、secretは公開文書へ記載しません。

## 通常運用

1. 商品ごとに画像と `_SUCCESS.txt` を登録する
2. 処理完了後、Review UIで対象batchを開く
3. 商品画像、画像順、商品名、説明、価格、カテゴリ、状態、配送設定を確認する
4. 修正だけを保存する場合は `Save`、確認完了なら `Save & Approve` を押す
5. batch内の必要商品を承認したら `Generate CSV` を押す
6. `Download CSV` からCSVを取得する
7. 生成から7日以内にメルカリShopsへアップロードする
8. メルカリShops側で画像と商品情報を最終確認してから出品する

## ボタンの使い分け

- `Save`: 編集内容を保存し、商品を未承認へ戻す
- `Save & Approve`: 編集内容を保存して承認する
- `Generate CSV`: 承認済み商品だけで公式CSVを作り直す
- `Download CSV`: 最後に正常生成された有効期限内のCSVを取得する
- `Repair from GCS`: Sheetsの行が欠けた場合だけ、GCSの処理済み成果物から復元する

通常の編集・承認後に `Repair from GCS` を押す必要はありません。

## CSVの有効期限

最終CSVの画像URLは生成から7日間有効です。期限を過ぎた場合は、同じbatchで `Generate CSV` をもう一度押してからダウンロードします。

## エラー時

- 商品情報の不足: Review UIで内容を修正して再承認する
- Draft行不足: `Repair from GCS` を1回実行する
- CSV検証エラー: 画面に表示された商品管理コードと項目を修正する
- 画像が表示されない: 商品画像がGCSに残っているか確認する
- Googleログインできない: Review UIの許可ユーザーとIAP設定を管理者が確認する
- GCS、Sheets、Gemini、文字コードなどの基盤エラー: 再試行を繰り返さず、Cloud Loggingを確認する

## 本番変更で承認が必要なこと

- mainへのマージ
- Cloud Run / Cloud Run Functionsの本番デプロイ
- IAM権限の追加・変更
- 新しい有料サービスの有効化
- 保存期間やbucket構成の変更

## 管理者だけが保持する情報

次の値はSecret Manager、Cloud Run環境変数、Google Cloud Consoleなどで管理し、Gitやチャットへ貼りません。

- Google CloudプロジェクトID
- bucket名
- Spreadsheet ID
- OAuth client secret
- Flask secret
- APIキー
- service account認証情報
