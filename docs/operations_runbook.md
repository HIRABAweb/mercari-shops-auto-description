# 運用・復旧手順

## 通常処理

1. `exports/{batch_id}/{item_id}/` に商品画像を配置する
2. 商品情報を書いた `_SUCCESS.txt` を最後に配置する
3. `_description.txt` と商品単位の成果物が生成されるまで待つ
4. Review UIで商品を修正・承認する
5. `Generate CSV` で承認済みCSVを作る
6. 7日以内にメルカリShopsへアップロードする

## 商品情報不足とシステム障害の違い

| 状況 | 動作 | 対応 |
|---|---|---|
| `_SUCCESS.txt`は読めたが本文が空 | 処理を続け、採寸・状態メモをレビュー対象にする | Review UIで追記する |
| 採寸ラベルや採寸値がない | 処理を続ける | Review UIで採寸を確認する |
| 状態・特記事項等の明示ラベルに内容がない | 処理を続ける | Review UIで状態を確認する |
| `_SUCCESS.txt`のGCS読込・権限・UTF-8 decode失敗 | 例外停止する | Cloud Loggingと元ファイルを確認する |
| 商品画像がない、または取得できない | 例外停止する | GCS上の画像と権限を確認する |
| Gemini API失敗 | 例外停止する | API状態・quota・認証を確認し再実行する |
| Sheets同期失敗 | `_DONE.txt`を作らず停止する | Sheets権限を直して再実行する |

## 一覧から商品が欠けている場合

Review UIの `欠けた商品を復元` は、GCSに残っている処理済み `result.json`、`mercari.csv`、`review_required.csv` から、欠けたDraft / Review行を復元します。

- 通常の編集・承認後には押さない
- 商品がReview UIに出ないときだけ実行する
- 同じ商品キーが存在する場合は追加しない
- 復元後は内容を再確認して承認する

## リトライ

- `_description.txt`生成済みの商品は再生成しない
- CSV変換中はGCSの処理ロックで同時実行を抑止する
- 処理成功後は元の`_description.txt`を`_processed.txt`へ移す
- Review / Draftは`batch_prefix/product_code`で同じ商品を識別する
- batchを指定してCSVを生成するため、別日batchを混ぜない

同じエラーが繰り返される場合は、入力を何度もアップロードせずCloud Loggingで原因を確認します。

## CSVを作り直す場合

- 商品を編集した場合は再承認する
- `Generate CSV`を押すと、その時点の承認済み商品だけで上書き生成する
- 署名付き画像URLの期限は7日間
- 期限切れの場合は`Generate CSV`を再実行する

## デプロイ後の確認

1. `/healthz`が`ok`を返す
2. Googleログインできる
3. batchと商品画像が表示できる
4. Save / Save & Approveが動く
5. 承認済みCSVを生成・ダウンロードできる
6. メルカリShopsでCSVを読み込める

本番デプロイ、IAM変更、mainマージはユーザー承認後に行います。
