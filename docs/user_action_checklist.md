# あなたがやることチェックリスト

このファイルは、Phase 1 Review UIを本番で使い始める前に、あなたが確認・判断することだけをまとめたものです。

## まず知っておくこと

開発側でできるコード修正、テスト、PR反映は進めています。

ただし、次の作業は本番のGoogle CloudやメルカリShopsに関わるため、あなたの確認なしには進めません。

- お金が発生する可能性がある設定
- 本番の権限設定
- 本番デプロイ
- メルカリShopsへの実アップロード
- mainへのマージ

## あなたが決めること

### 1. 本番デプロイしてよいか

Review UIは新しいCloud Runサービスとして動かします。

デプロイすると、少額でもGoogle Cloudの料金が発生する可能性があります。
そのため、デプロイしてよいかをあなたが決める必要があります。

確認すること:

- Cloud Runを作ってよい
- Artifact RegistryにDocker imageを置いてよい
- 課金アラートや予算をGoogle Cloudで設定・確認した

補足:

課金アラートや予算は、Google CloudのBilling画面で設定します。
この設定はお金に関わるため、基本的にはあなたがGoogle Cloud上で確認してください。
こちらでは手順書の整備や、設定後のデプロイ手順の準備を進めます。

現在の状態:

- 課金アラート/予算は設定済み
- Project IDは `gen-lang-client-0122735738`
- Google Cloud CLIはこのPCにインストール済み
- ただし、Googleログインはまだ必要

### 2. 本番のbucket名

Review UIは、商品画像を読むためにGCS bucketへアクセスします。
また、承認済みCSVも同じbucketに保存します。

確認すること:

- bucket名は `test-review-ui`
- `PRODUCT_BUCKET_NAME` に `test-review-ui` を設定してよい

### 3. 権限を付けてよいか

Review UIのCloud Run service accountには、次の権限が必要です。

- Google Spreadsheetを編集する権限
- 商品画像をGCSから読む権限
- 承認済みCSVをGCSへ書く権限

確認すること:

- Cloud Run用のservice accountを作ってよい
- Spreadsheetに編集者として追加してよいか
- GCS bucketの読み書き権限を付けてよいか

注意:

`hirabaaiwork@gmail.com` は、人間がReview UIへログインするためのアカウントです。
Cloud RunのプログラムがGoogle SheetsやGCSへアクセスするには、別のservice accountが必要です。

おすすめのservice account名:

```text
mercari-review-ui-sa
```

このservice accountをSpreadsheetの編集者に追加し、`test-review-ui` bucketを読み書きできるようにします。

あなたが手動でやること:

1. Google Cloud CLIで `hirabaaiwork@gmail.com` にログインする
2. デプロイ後に表示されるservice accountメールアドレスをSpreadsheetの編集者に追加する

service accountメールアドレスの形:

```text
mercari-review-ui-sa@gen-lang-client-0122735738.iam.gserviceaccount.com
```

### 4. 誰がReview UIに入れるか

今の予定では、Review UIはIAPで守ります。
アクセスできる人は `hirabaaiwork@gmail.com` に限定します。

確認すること:

- `hirabaaiwork@gmail.com` でログインできる
- それ以外の人を入れない運用でよい

ここはあなたの希望どおり、`hirabaaiwork@gmail.com` だけを許可する方針です。

現在の追加確認:

- Review UI URLで `Empty Google Account OAuth client ID(s)/secret(s).` が出る場合、アプリではなくIAPのOAuth設定が未完了です。
- Project `gen-lang-client-0122735738` は組織なしプロジェクトのため、初回のIAP OAuth設定はGoogle Cloud Consoleで行う必要があります。
- Cloud Runの `mercari-review-ui` でIAP OAuth/Google Auth Platformを設定してください。
- Audienceは `External` を選び、`hirabaaiwork@gmail.com` でログインできるようにしてください。
- Consoleに「auto-generate credentials」の選択肢があれば、それを使うのが一番簡単です。
- 手動でOAuth client ID/secretを作る場合、secretはチャットに貼らず、Console上で設定するか `scripts/apply_iap_oauth_settings.ps1` を手元で実行してください。

### 5. 実データで確認する

デプロイ後、実際の商品で動作確認が必要です。

確認すること:

- `/healthz` が `ok` を返す
- Review UIに商品一覧が出る
- 商品画像が表示される
- 商品名や説明文を編集できる
- `Save` だけ押すと未承認に戻る
- `Save & Approve` で承認できる
- 承認済みCSVを生成できる
- CSVをダウンロードできる

### 6. メルカリShopsへCSVをアップロードする

最後は、ダウンロードしたCSVをメルカリShopsに入れて確認します。

確認すること:

- CSVがメルカリShopsに読み込まれる
- 商品画像が正しく取り込まれる
- 商品名、説明文、価格、カテゴリ、状態が正しい
- 下書き保存または出品まで問題なく進める

## あなたがやらなくてよいこと

次の作業はこちらで進められます。

- コード修正
- テスト追加
- READMEや手順書の更新
- PRブランチへのcommit / push
- PR上の説明コメント更新
- コードレビュー
- 本番前チェックリストの整備

## いま止まる場所

コード開発は進められます。

ただし、本当に本番で使えるかは、次の確認が終わらないと判断できません。

1. Google Cloudへデプロイしてよいか
2. IAPとIAMを設定してよいか
3. 実データでReview UIを開けるか
4. CSVをメルカリShopsへアップロードできるか

この4つは、あなたの確認が必要です。
