# YouTube トレンド自動要約 → スプレッドシート反映

毎日自動でYouTubeトレンドを取得し、Gemini API(無料枠)で要約、Googleスプレッドシートに追記するシステムです。

## 全体構成

```
GitHub Actions(毎朝トリガー)
    ↓
YouTube Data API v3(トレンド取得)
    ↓
Gemini API(要約 + 傾向分析、品質チェックのLoop付き)
    ↓
Google Sheets API(スプレッドシートに追記)
```

## セットアップ手順

### 1. YouTube Data API キーの取得
1. [Google Cloud Console](https://console.cloud.google.com/) で新規プロジェクトを作成(または既存のものを使用)
2. 「APIとサービス」→「ライブラリ」から **YouTube Data API v3** を有効化
3. 「認証情報」→「認証情報を作成」→「APIキー」でキーを発行

### 2. Google サービスアカウントの作成(スプレッドシート用)
1. 同じGCPプロジェクトの「認証情報」→「認証情報を作成」→「サービスアカウント」
2. 作成後、そのサービスアカウントの「鍵」タブから JSON形式の鍵をダウンロード
3. 「APIとサービス」→「ライブラリ」から **Google Sheets API** を有効化
4. 反映先にしたいGoogleスプレッドシートを開き、共有設定でサービスアカウントのメールアドレス(JSON内の`client_email`)を「編集者」として招待

### 3. スプレッドシートIDの確認
スプレッドシートのURLの `.../d/【ここがID】/edit` の部分をコピー

### 4. Gemini API キーの取得(無料)
1. [Google AI Studio](https://aistudio.google.com/apikey) にアクセス
2. 「Create API key」でキーを発行(無料枠で利用可能)

### 5. GitHubリポジトリの準備
1. このフォルダの中身を新規GitHubリポジトリにpush
2. リポジトリの Settings → Secrets and variables → Actions → New repository secret で以下4つを登録

| Secret名 | 値 |
|---|---|
| `YOUTUBE_API_KEY` | 手順1で取得したキー |
| `GEMINI_API_KEY` | 手順4で取得したキー |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 手順2でダウンロードしたJSONファイルの中身をそのまま貼り付け |
| `SPREADSHEET_ID` | 手順3で確認したID |

### 6. 動作確認
GitHubリポジトリの「Actions」タブ → 「Daily YouTube Trend Report」→「Run workflow」で手動実行し、
スプレッドシートに反映されるか確認してください。

以降は毎日 日本時間7:00(UTC 22:00)に自動実行されます。実行時刻を変えたい場合は
`.github/workflows/daily_trends.yml` 内の `cron` の値を編集してください。

## カスタマイズ

- `REGION_CODE`: トレンド取得地域(デフォルト`"JP"`)
- `MAX_RESULTS`: 取得件数(デフォルト10件)
- `SHEET_NAME`: 書き込み先のシート名(デフォルト`"trends"`、なければ自動作成)
