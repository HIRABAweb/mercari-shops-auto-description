# Review UI deployment

Review UIは`review-ui/Dockerfile`からCloud Runへデプロイします。本番デプロイ、IAM変更、新しい有料リソースの作成はユーザー承認後に行います。

実際のプロジェクトID、bucket名、Spreadsheet ID、許可ユーザー、OAuth secretはGitへ記録しません。

## 構成

- Cloud Run service: `mercari-review-ui`
- Authentication: Cloud Run direct IAP
- Runtime service account: 専用service account
- Minimum instances: `0`
- Maximum instances: `1`
- Public access: disabled
- Approved CSV: `exports/{batch_id}/approved/mercari_shops.csv`
- Image access: 7日間有効のV4署名付きURL

## 必要な値

デプロイ前に、ローカルで次を用意します。

```text
YOUR_PROJECT_ID
YOUR_PRODUCT_BUCKET
YOUR_SPREADSHEET_ID
operator@example.com
```

これらはコマンド引数またはCloud Run環境変数として渡し、ソースコードへ書きません。

## Runtime service account

専用service accountには次の権限が必要です。

- 商品画像のGCS read
- 承認済みCSVのGCS create / update / delete
- 自分自身で短期間の署名付きURLを作る権限
- 対象Spreadsheetの編集者権限

Review UI専用bucketを使う場合はbucket単位のobject権限を利用できます。商品bucketを他用途と共有する場合は、IAM Conditionまたは別bucketで権限範囲を限定してください。

署名用にruntime service account自身へ次を付与します。

```text
roles/iam.serviceAccountTokenCreator
```

## デプロイスクリプト

リポジトリルートから実行します。実際の値はローカルで指定してください。

```powershell
.\scripts\deploy_review_ui.ps1 `
  -ProjectId "YOUR_PROJECT_ID" `
  -ProductBucketName "YOUR_PRODUCT_BUCKET" `
  -SpreadsheetId "YOUR_SPREADSHEET_ID" `
  -AllowedUser "operator@example.com"
```

スクリプトは次を行います。

1. 必要なGoogle Cloud APIを有効化する
2. bucket、Artifact Registry、service accountがなければ作成する
3. runtime service accountへGCS・署名権限を設定する
4. Cloud Buildでimageを作成する
5. Cloud RunをIAP・`min-instances=0`・`max-instances=1`でデプロイする
6. 指定ユーザーへIAPアクセスを付与する

実行前に課金アラートと予算を確認してください。

## Spreadsheet

Cloud Runのruntime service accountを、対象Spreadsheetの編集者へ追加します。人間のログインユーザーだけを編集者にしても、Cloud Runからはアクセスできません。

商品処理FunctionsからSheetsへ下書きを書く場合は、そのFunctionsのruntime service accountにもSpreadsheet編集権限が必要です。

## IAP OAuth

初回アクセスで次が表示される場合、IAP OAuth設定が未完了です。

```text
Empty Google Account OAuth client ID(s)/secret(s).
```

Google Cloud Consoleで対象Cloud Run serviceのIAP / Google Auth Platformを設定します。公開ユーザーを増やさず、必要な運用者だけへ`roles/iap.httpsResourceAccessor`を付与します。

カスタムOAuth clientを使う場合は、secretをチャットやGitへ貼らず、ローカルで次を実行します。

```powershell
.\scripts\apply_iap_oauth_settings.ps1 -ProjectId "YOUR_PROJECT_ID"
```

このスクリプトはclient IDとsecretを対話入力し、一時ファイルを処理後に削除します。

## Cloud Run環境変数

| 変数 | 用途 |
|---|---|
| `SPREADSHEET_ID` | Review UIが参照するSpreadsheet |
| `PRODUCT_BUCKET_NAME` | 商品画像と承認済みCSVを保持するbucket |
| `APPROVED_CSV_OBJECT_TEMPLATE` | 承認済みCSVのobject path |
| `MERCARI_SIGNING_SERVICE_ACCOUNT_EMAIL` | 画像URLへ署名するservice account |
| `MERCARI_IMAGE_SIGNED_URL_TTL_HOURS` | URL有効時間。1〜168時間 |
| `FLASK_SECRET_KEY` | session / CSRF署名用secret |

`FLASK_SECRET_KEY`はCloud Runで必須です。デプロイスクリプトは未指定時にランダム生成します。

## デプロイ後確認

1. `/healthz`が`ok`を返す
2. 許可ユーザーだけがGoogleログインできる
3. private GCS画像がReview UIへ表示される
4. Save / Save & Approveが動く
5. 承認済みCSVを生成・ダウンロードできる
6. CSV画像URLを未ログイン状態で取得できる
7. CSVを7日以内にメルカリShopsへアップロードできる

## 代替HTTP entrypoint

`export_approved_mercari_csv`はReview UIを使えない場合の代替です。Sheetsを変更するためPOSTだけを受け付けます。

```powershell
curl -X POST "$FunctionUrl?batch_prefix=exports/YOUR_BATCH_ID"
```
