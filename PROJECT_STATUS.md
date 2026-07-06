# PROJECT_STATUS.md

## 2026-07-06 更新: _SUCCESS.txt正式運用への統一

### やったこと

- 通常運用の入力を、商品画像と `_SUCCESS.txt` のみに統一。
- `_SUCCESS.txt` を処理開始トリガー兼、採寸情報・状態メモの入力ファイルとして扱う方針に変更。
- 通常運用から `product_info.txt` を除外。
- `image-to-description` では `_SUCCESS.txt` 本文のみを読み、本文が空の場合は `_description.txt` を生成せずに明確なエラーで停止するように変更。
- `_description.txt` の先頭に `【要確認：採寸情報なし】` を付ける通常経路を廃止。
- READMEを、外注者がアップロードするものは「商品画像」と「採寸・状態メモを書いた `_SUCCESS.txt`」だけである内容に更新。

### 確認済み

- `image-to-description/main.py` の通常経路で `product_info.txt` を読まない構成に変更済み。
- `_SUCCESS.txt` 本文が空の場合はエラー停止し、AI生成・`_description.txt` 作成へ進まない構成に変更済み。
- README上の外注者向け手順を `_SUCCESS.txt` 正式運用へ更新済み。

### まだ人間が確認すべき事項

- GCS上の `prompt.txt` が `タイトル:` / `説明文（HTML）:` 形式を安定して出すか確認。
- GCS上の `mercari_prompt.txt` が `[TITLE]` / `[BODY]` 形式を安定して出すか確認。
- Cloud Functionsの環境変数 `PROMPT_FILE_NAME=prompts/prompt.txt` を確認。
- Cloud Functionsの環境変数 `MERCARI_PROMPT_FILE_NAME=prompts/mercari_prompt.txt` を確認。
- 1商品でCloud Functions実行確認。
- 3〜5商品で再現性確認。
- メルカリShops CSV画像URL方式の再実機確認。
- Yahooオークション向け `yahoo.csv` の実際の出品画面または一括出品ツールへの投入検証。

---

## 2026-07-03 更新: _description.txt正本化とMercari変換フロー整理

### やったこと

- `_description.txt` をヤフオク用タイトル・HTML説明文の正本として扱う方針に変更。
- Yahoo CSVでは `_description.txt` から抽出したタイトルと説明文HTMLを原則そのまま使うように変更。
- Mercari CSVでは `mercari_prompt.txt` による `[TITLE]` / `[BODY]` 変換結果を `商品名` / `商品説明` に使うように変更。
- Python側ではタイトル・商品説明文を再生成しない方針に整理。
- 通常経路から `build_title()` と `ensure_size_in_description()` を外した。
- Python側の担当を、CSV列マッピング、画像URL、価格、配送、ブランドID、カテゴリID、SKU、review判定などに限定。
- `_description.txt` 用の `yahoo_description_parser.py` と、Mercari変換応答用の `mercari_response_parser.py` を追加。
- メルカリ変換用プロンプトを読む環境変数 `MERCARI_PROMPT_FILE_NAME` を追加。`MERCARI_PROMPT_BUCKET_NAME` は任意で、未設定時は `PROMPT_BUCKET_NAME` を使う。

### 確認済み

- ローカルテスト: `python -m pytest -p no:cacheprovider tests`
- 結果: `69 passed`

### まだ人間が確認すべき事項

- GCS上の `prompt.txt` が `タイトル:` / `説明文（HTML）:` 形式を安定して出すか確認。
- GCS上の `mercari_prompt.txt` が `[TITLE]` / `[BODY]` 形式を安定して出すか確認。
- Mercari変換後のタイトル・本文が実運用品質として十分か、複数商品で確認。
- Yahooオークション向け `yahoo.csv` の実際の出品画面または一括出品ツールへの投入検証。
- メルカリShops CSVの画像URL方式が今回の変更後も実機で問題ないか再確認。

---

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
- 実際の出品画面または一括出品ツールへの投入検証は未実施。
