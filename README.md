# note RSS → Slack 自動配信

noteに新しい記事が公開されると、Slackの指定チャンネルに自動で通知します。
GitHub Actionsが15分ごとにnoteのRSSを確認し、新着記事だけを投稿する仕組みです。
サーバーの用意・費用は不要です(GitHub無料枠内で動作)。

## 初期セットアップ(所要10分)

### 1. Slack Incoming Webhookを作成
1. https://api.slack.com/apps → Create New App → From scratch
2. アプリ名(例: `note通知`)とワークスペースを選択
3. 左メニュー Incoming Webhooks → On にする
4. Add New Webhook to Workspace → 通知先チャンネルを選択
5. 発行された `https://hooks.slack.com/services/...` のURLをコピー

### 2. リポジトリに設定を登録
リポジトリの Settings → Secrets and variables → Actions で:

- **Secrets** タブ → New repository secret
  - Name: `SLACK_WEBHOOK_URL` / Value: 手順1でコピーしたURL
- **Variables** タブ → New repository variable
  - Name: `NOTE_RSS_URL` / Value: `https://note.com/ユーザー名/rss`

### 3. 動作確認
1. Actions タブ → 「note RSS to Slack」→ Run workflow で手動実行
2. 初回は既存記事を「通知済み」として記録するだけです(Slackには何も届きません)
3. 以後、新しい記事が公開されると15分〜30分以内にSlackへ通知されます

## 運用メモ

- **通知が来ないとき**: Actionsタブで直近の実行ログを確認。赤い×が付いていれば
  ログにエラー内容が出ています
- **通知文言を変えたい**: `rss_to_slack.py` の `post_to_slack` 内のテキストを編集
- **チャンネルを変えたい**: 手順1で新しいWebhookを作り、Secretを差し替え
- **止めたいとき**: Actionsタブ → ワークフロー右上の「…」→ Disable workflow
- `seen_guids.json` は通知済み記事の記録です。手で編集する必要はありません