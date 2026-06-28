# PROJECT_STATUS.md

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

### まだ残っている課題

- メルカリShopsへのCSV投入では、画像ファイル名が存在しないという理由で失敗
- CSV内の画像名と、メルカリShopsに渡す画像ファイル名の一致確認が必要
- 出力CSVと画像ファイルをセットで扱う運用仕様を決める必要がある

### 次にやること

1. メルカリShops一括登録時の画像アップロード仕様を確認
2. CSVに書かれた画像名と実画像名を一致させる
3. 必要なら出力先に画像ファイルもコピーする処理を追加
4. 1商品で再度メルカリShops投入テストを行う


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
