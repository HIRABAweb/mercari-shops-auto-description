# EC出品効率化ツール

## 概要

リユース商品の出品準備業務を効率化するために開発した、Google Cloud上で動作するイベント駆動型のMVPです。
商品画像と採寸情報を基に生成AIでヤフオク向けの商品説明文を作成し、メルカリShopsに合わせた列データをGoogleスプレッドシートへ出力します。

## 開発背景

リユース事業では、商品画像の確認、採寸情報の整理、商品説明文の作成、出品プラットフォーム別のデータ入力に多くの作業時間が発生していました。
特に、販売数を増やすほど出品作業がボトルネックになるため、画像解析と文章生成、出品データ作成を自動化するMVPを開発しました。

## 主な機能

* 商品画像と採寸情報を利用した商品説明文の生成
* Google Cloud Storageへのファイル登録を起点とした自動処理
* 商品フォルダ名を利用した商品管理コードの設定
* 商品画像URLの取得と並び替え
* メルカリShops向け73列データの作成
* ヤフオク・オークタウン向け114列データの作成
* Googleスプレッドシートへの出品データ追記
* Secret Managerを利用したAPIキー管理
* 処理済みファイルへの変更による重複実行の抑止

## 処理フロー

```text
1. 商品ごとのフォルダに画像をアップロード
2. 採寸情報を記載した _SUCCESS.txt を作成
3. GCSイベントを検知
4. Vertex AI Geminiへ画像と採寸情報を送信
5. 商品説明文を _description.txt として保存
6. _description.txt の作成イベントを検知
7. メルカリ・ヤフオク向けの列データを作成
8. Googleスプレッドシートへ追記
9. 必要に応じて内容を修正し、CSVとして出力
```

## システム構成

### description-generator

商品画像と採寸情報から、商品説明文を生成するサービスです。

* `_SUCCESS.txt` の作成を検知
* 同一フォルダ内の商品画像を取得
* GCSに保存したプロンプトを読み込み
* Vertex AI Gemini 2.5 Flashで商品説明文を生成
* `_description.txt` としてGCSへ保存

### listing-data-exporter

生成された説明文を基に、各販売プラットフォーム用の出品データを作成するサービスです。

* `_description.txt` の作成を検知
* Gemini 2.5 Flash Liteでメルカリ用の文章を生成
* メルカリShops向け73列データを作成
* ヤフオク向け114列データを作成
* Googleスプレッドシートへ追記

## 使用技術

* Python
* Google Cloud Run functions / Functions Framework
* Google Cloud Storage
* Vertex AI
* Gemini API
* Google Secret Manager
* Google Sheets API
* gspread

## ディレクトリ構成

```text
services/
├─ description-generator/
│  ├─ main.py
│  └─ requirements.txt
└─ listing-data-exporter/
   ├─ main.py
   └─ requirements.txt
```

## 入力データ

商品ごとにCloud Storage上へフォルダを作成します。

```text
商品管理コード/
├─ 001.jpg
├─ 002.jpg
├─ 003.jpg
└─ _SUCCESS.txt
```

`_SUCCESS.txt` には、商品の採寸情報などを記載します。

## 出力データ

処理後、商品フォルダに以下のファイルが作成されます。

```text
商品管理コード/
├─ 001.jpg
├─ 002.jpg
├─ 003.jpg
├─ _SUCCESS.txt
└─ _processed.txt
```

また、Googleスプレッドシートの以下のシートへ出品データを追記します。

* `Mercari_List`
* `Yahoo_List`

## 手動確認が必要な項目

現在のMVPでは、以下の項目は自動確定せず、出力後に人が確認・修正する設計です。

* 商品名
* カテゴリID
* ブランドID
* 販売価格
* 商品状態
* 配送設定
* AIが生成した商品説明文

生成AIの出力をそのまま出品するのではなく、最終確認を行うHuman-in-the-loop方式を採用しています。

## 設定が必要な環境変数

実行環境では、以下の情報を設定する必要があります。

* Google CloudプロジェクトID
* 利用リージョン
* プロンプト保存用バケット名
* プロンプトファイル名
* Secret Managerのシークレット名
* GoogleスプレッドシートID
* 出力先シート名

認証情報、APIキー、実際のプロジェクトIDなどはリポジトリに含めていません。

## 現在のステータス

個人で運営していたリユース事業の実業務を基に開発したMVPです。

本番運用に必要な完全自動化ではなく、出品データの下書きを自動生成し、最終的に人が内容を確認することで、作業時間の削減と入力ミスの防止を目指しています。

## 今後の改善予定

* 設定値の環境変数化
* AI出力の構造化
* カテゴリ・ブランド・価格の自動推定
* エラー発生時の再実行機能
* 出力データのバリデーション
* CSVファイルの自動生成
* ログおよび処理状況の可視化
* テストコードの追加
