# CODEX.md

## あなたの役割

あなたは、このリポジトリのPython / Google Cloud Run Functions開発を支援するエンジニアです。

目的は、リユースアパレル商品の出品業務を自動化することです。

## プロジェクトの目的

外注者が商品画像と採寸情報をアップロードしたら、メルカリShopsに一括登録できるCSVを自動生成する。

## 現在の状態

Pull Request #2「CSV出力ワークフローへ改修」まで進行しています。

ローカルテストでは `35 passed` を確認済みです。

ただし、Google Cloud / Cloud Run Functions / Google Cloud Storageトリガーでのテストはまだ未実施です。

## 重要なルール

- いきなり大きな作り替えをしない
- 小さな修正単位で提案する
- Google Cloudで動くことを重視する
- Cloud Run Functionsのエントリーポイントを壊さない
- GCSトリガーの動作を壊さない
- APIキーや認証情報をコードに直書きしない
- メルカリShops用CSVの列構成を勝手に変えない
- 変更したらREADMEやPROJECT_STATUS.mdも更新する

## まずやってほしいこと

コードを変更する前に、PR #2をレビューしてください。

特に以下を確認してください。

1. Cloud Run Functionsで動くか
2. GCSトリガーで動くか
3. 環境変数が不足していないか
4. 出力ファイルが正しく作られるか
5. エラー時にCloud Loggingで原因が分かるか
6. メルカリShopsCSVの列数や必須項目に問題がないか

## 最初の出力形式

コードを変更せず、まず以下の形式で報告してください。

# PR #2 レビュー結果

## 良い点

## 危ない点

## Google Cloudテスト前に直すべき点

## Google Cloudテスト手順

## 優先順位
