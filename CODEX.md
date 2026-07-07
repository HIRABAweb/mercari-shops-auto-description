# CODEX.md

## プロジェクトの目的

このリポジトリは、リユースアパレル商品の出品業務を自動化するためのPython / Google Cloud Run Functions / Cloud Runプロジェクトです。

外注者は商品画像と `_SUCCESS.txt` をアップロードします。システムはYahoo向け説明文、メルカリShops用下書き、レビュー用情報、承認済みCSVを生成します。

## 現在の運用目標

- 入力は原則「商品画像 + `_SUCCESS.txt`」です。
- 商品情報は `_SUCCESS.txt` 本文に書きます。
- `product_info.txt` は通常運用では使いません。
- 商品情報不足は処理停止ではなくレビュー対象にします。
- GCS、Gemini API、ファイル破損、CSV書き込みなどの基盤エラーは停止対象です。
- Review UIで人間が確認・修正・承認し、承認済みCSVをメルカリShopsへアップロードします。

## エージェント運用

このリポジトリでは、開発担当とレビュー担当を分けます。

- `グラマー`: 実装担当
- `ラス`: レビュー担当

詳細は `.agents/README.md`、`.agents/glammer.agent.md`、`.agents/ras.agent.md` を参照してください。

### グラマーを使う場面

- 実装、修正、開発、テスト追加、ドキュメント更新
- レビュー指摘の修正
- PRへの反映、コミット、push

### ラスを使う場面

- コードレビュー、PRレビュー
- mainマージ前確認
- 本番デプロイ前確認
- 客観的なリスク確認

推奨フロー:

1. グラマーが実装する。
2. グラマーがテストを通す。
3. ラスがPR差分をレビューする。
4. グラマーが指摘を修正する。
5. ユーザー承認後にmainマージまたは本番デプロイへ進む。

## 重要なルール

- いきなり大きな作り替えをしない。
- 既存Cloud Functionsのentrypointを壊さない。
- GCSトリガーの動作を壊さない。
- メルカリShops用CSVの列順、列数、ヘッダーを勝手に変えない。
- Yahoo向け出力に不要な変更を入れない。
- APIキー、secret、認証情報をコードに直書きしない。
- 課金が発生し得るCloud操作は事前にユーザー確認する。
- 本番デプロイ、mainマージはユーザー承認なしに行わない。
- 未追跡の `portfolio/` は明示指示がない限り触らない。
- 変更したら必要に応じてREADME、PROJECT_STATUS、docsを更新する。

## 標準テスト

可能な限り次を実行します。

```powershell
python -m pytest -p no:cacheprovider tests
```

Review UIを触る場合は、Flask依存が必要です。

```powershell
python -m pip install -r review-ui/requirements.txt
python -m pytest -p no:cacheprovider tests/test_review_ui.py
```
