# PROJECT_STATUS.md

## 2026-07-01 更新: PR #2最終確認と実機検証状況

### 到達点

- Cloud Functions Gen2へ `feature/title-description-separation` の最新コードをデプロイ済み。
- GCSトリガーでCSV生成が起動することを確認済み。
- メルカリShops用 `mercari.csv` の `商品画像名_1` 〜 `商品画像名_20` は、GCS公開画像URLをそのまま出力する方式へ変更済み。
- メルカリShopsへのCSVアップロードと下書き保存まで実機検証済み。
- ローカルテストとCloud Shellテストはいずれも `45 passed`。
- PR #2はopenで、mergeable true。

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
