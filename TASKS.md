# TASKS.md

## 今やること

### 1. PR #2をCodexにレビューしてもらう

目的:
Google Cloudでテストする前に、コード上の危ない部分を見つける。

やること:
- CodexにPR #2を読ませる
- Cloud Run Functionsで失敗しそうな点を確認する
- GCSトリガーで失敗しそうな点を確認する
- 環境変数の不足がないか確認する
- 出力CSVに問題がないか確認する

完了条件:
- Codexからレビュー結果が出る
- 修正すべき点がリスト化される

---

### 2. Google Cloudテストの準備

目的:
実際にCloud Run Functionsで動くか確認する。

やること:
- 必要な環境変数を確認する
- テスト用GCSバケットを確認する
- テスト用の商品画像を1件用意する
- 採寸情報ファイルを用意する
- `_SUCCESS.txt` を用意する

完了条件:
- GCSにアップロードできるテスト用フォルダが用意できている

---

### 3. Google Cloudで実行テスト

目的:
ローカルではなく、クラウド上で実際に動くか確認する。

やること:
- Cloud Run Functionsにデプロイする
- GCSにテスト商品をアップロードする
- Cloud Run Functionsが起動するか確認する
- Cloud Loggingを見る
- 出力ファイルが作られるか確認する

期待する出力:
- `mercari.csv`
- `yahoo.csv`
- `review_required.csv`
- `result.json`
- `_DONE.txt`

完了条件:
- エラーなく出力ファイルが作られる

---

### 4. メルカリShops CSV確認

目的:
生成したCSVが実際に使えるか確認する。

やること:
- `mercari.csv` をダウンロードする
- Excelまたはスプレッドシートで開く
- 文字化けがないか見る
- 列数が合っているか見る
- 必須項目が入っているか見る
- メルカリShopsでテスト投入する

完了条件:
- メルカリShops側でCSVが読み込める
