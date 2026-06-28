# PROJECT_STATUS.md

## 現在の進捗

このプロジェクトは、リユースアパレル商品の出品業務を自動化するためのPython / Google Cloud Run Functionsプロジェクトです。

目的は、外注者が商品画像と採寸情報をアップロードしたら、メルカリShopsに一括登録できるCSVを自動生成することです。

現在は、Pull Request #2「CSV出力ワークフローへ改修」まで進行しています。

## 現在のブランチ

- 作業ブランチ: `feature/title-description-separation`
- PR: #2
- 状態: Google Cloudでのテスト前

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
- ローカルテストで `35 passed` を確認

## まだやっていないこと

- Google Cloud上でのテスト
- Cloud Run Functionsへの最新ブランチのデプロイ
- Google Cloud Storageトリガーでの起動確認
- 実際の商品画像を使ったGCS経由のテスト
- 生成されたCSVのメルカリShops投入テスト
- YahooオークションCSVの最終確認
- 外注者が使えるアップロード手順の作成

## 現在の重要な注意点

ローカルテストは通っていますが、Google Cloud上ではまだ動作確認していません。

そのため、転職活動や面接では以下のように説明します。

「ローカル環境ではCSV生成ワークフローとテストまで完了しています。現在はGoogle Cloud Run FunctionsとGoogle Cloud Storageトリガーでの実行検証を進める段階です。」

「Google Cloudで運用済み」とはまだ言いません。

## 次にやること

1. CodexにPR #2をレビューしてもらう
2. Cloud Run Functionsで失敗しそうな点を事前確認する
3. Google Cloudでテストするための環境変数を確認する
4. テスト用の商品画像と採寸情報を1件用意する
5. GCSにアップロードしてCloud Run Functionsが動くか確認する
6. エラーが出たらCloud Loggingの内容を保存する
7. エラー内容をCodexまたはChatGPTに渡して修正する
8. `mercari.csv` が正しく出るか確認する
