# Google Sheets並行書き込み設計

## 現在の対策

新規行は、既存行数から書き込み先を計算せず、Google Sheets APIの
`spreadsheets.values.append`に相当する`append_row`で追加します。
`INSERT_ROWS`を指定するため、同時実行が同じ行番号を計算して互いを
上書きする経路を避けられます。値は`RAW`として送り、文字列を数式として
評価させません。

Googleの公式仕様では、appendは対象テーブルの最終行をAPI側で検出し、
その次の行へ値を追加します。

- https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append
- https://developers.google.com/workspace/sheets/api/guides/values

## 残る競合

既存実装の一意性確認は「キーを検索してから、見つからなければ追加する」
という2リクエストです。異なるCloud Run Functionsインスタンスが同時に
同じ商品を処理した場合、両方が未登録と判断して同じキーを2行追加する
可能性は残ります。

Sheetsのbatch updateは単一リクエスト内の更新をまとめて適用できますが、
既存値に対する一意制約やcompare-and-setを提供するものではありません。

- https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate

したがって、appendへの変更だけで「重複も含めて完全に解決」とは扱いません。

## 推奨する次段階

全インスタンスで共有できる期限付きロックを取得した処理だけが、Sheetsの
検索・追加・更新を行う設計にします。候補はGCSオブジェクトの世代番号条件を
利用するロックです。

実装前に、次を人間が確定する必要があります。

1. ロックを保存する既存バケット
2. ロックオブジェクト名と対象範囲（Spreadsheet全体、batch単位、商品単位）
3. ロック期限と待機時間
4. 異常終了時の期限切れ回収方法
5. Review UIと変換Functionの両方が同じロック規則を使うこと

ロックオブジェクト名はGCS命名契約に該当するため、承認なしでは実装しません。

## 完了条件

- 同じ商品を複数インスタンスから同時実行しても各Sheetに1行だけ残る
- 異なる商品を同時実行しても欠落や上書きがない
- タイムアウトや強制終了後にロックを安全に回収できる
- batch間で行や承認状態が混ざらない
- 外部I/Oをfakeに置き換えた競合テストが成功する
