# note RSS → Slack / X 自動配信

noteに新しい記事が公開されると、Slackの指定チャンネルに通知し、あわせてXにも自動投稿します。
GitHub Actionsが15分ごとにnoteのRSSを確認し、新着記事だけを配信する仕組みです。
サーバーの用意は不要です。GitHub Actionsは無料枠内で動作しますが、
**X API は従量課金です**(月およそ540円。詳細は下記「費用」)。

**RSSのチェックは1回の実行でまとめて行うため、X投稿を足してもGitHub Actionsの消費は増えません。**
SlackとXは投稿済みの記録を別々に持つので(`seen_guids.json` と `seen_x.json`)、
片方だけをやり直しても、もう片方に再通知が飛ぶことはありません。

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

### 4. X(Twitter)への自動投稿を有効にする(任意)

Xへの投稿が不要なら、この手順を飛ばしてください。キーが未設定の場合、
X投稿のステップは失敗しますが、**Slackの通知は通常どおり動きます**。

#### 4-1. X Developer Portal でアプリを作る

1. https://console.x.com/ にアクセスし、投稿したいXアカウントでサインイン
   （旧 developer.x.com ではなく **console.x.com** です）
   - 無料プランは廃止され、従量課金(Pay-Per-Use)のみです。クレジットの事前購入が必要になります
   - **クレジットは返金・譲渡不可**で、Xは一方的に価格変更・停止・契約終了ができます(PPU Agreement)。
     使い切れる範囲の少額から購入してください
2. Developer Agreement を承認し、「New App」でアプリを作成
3. 左メニュー「アクセス」→「**アプリ**」→ 作成したアプリ →「**Keys & Tokens**」タブ
4. **先に権限を設定する**
   - 「OAuth 2.0 キー」セクションの「ユーザー認証設定」→「セットアップ」
   - **アプリの権限を「読み取りと書き込み」**にする（この設定が OAuth 1.0a にも適用される）
   - アプリの種類は「ウェブアプリ、自動化アプリまたはボット」
   - コールバックURI・ウェブサイトURLは必須項目だが、このフローでは使われないので
     `https://note.com/ユーザー名` などで可
   - 保存後、「アクセストークン」の表示が「読み取りと書き込み」になることを確認する
5. **「OAuth 1.0 キー」セクションから4つの値を取得する**
   - 「コンシューマーキー」の目のアイコン → **API Key と API Key Secret**
   - 「アクセストークン」の「生成する」→ **Access Token と Access Token Secret**
   - クレジットは左メニュー「請求書作成」→「クレジット」から購入する
2. Projects & Apps → アプリを作成(名前は何でも可)
3. **アプリの権限を書き込み可能にする**
   - アプリの Settings → **User authentication settings** → Set up
   - **App permissions** を **Read and write** に変更
   - Type of App: Web App / Automated App or Bot を選択
   - Callback URI と Website URL は必須項目なので、`https://example.com` など任意のURLで可
   - Save
4. **キーを発行する**(必ず手順3の後に行うこと)
   - Keys and tokens タブ → **API Key and Secret** を生成してコピー
   - 同じ画面の **Access Token and Secret** を **Generate**(または Regenerate)してコピー

> **実際に踏んだ罠**: 画面には「OAuth 1.0 キー」と「OAuth 2.0 キー」の2つのセクションがあり、
> **使うのは OAuth 1.0 の方だけ**です。OAuth 2.0 のクライアントID / クライアントシークレットを
> 登録すると、原因の分かりにくい 401 になります。
> 見分け方は長さです。**Access Token Secret は45文字、OAuth 2.0 のクライアントシークレットは50文字**。
>
> **もう1つの罠**: 権限を「読み取りと書き込み」に変える**前**に発行した Access Token は
> 読み取り専用のままです。投稿時に 403 が返る場合は Access Token を再生成してください。

#### 4-2. キーをリポジトリに登録する

Settings → Secrets and variables → Actions で:

**Secrets** タブ → New repository secret(4つ)

| Name | Value |
|---|---|
| `X_API_KEY` | 手順4-1の API Key |
| `X_API_SECRET` | 手順4-1の API Key Secret |
| `X_ACCESS_TOKEN` | 手順4-1の Access Token |
| `X_ACCESS_TOKEN_SECRET` | 手順4-1の Access Token Secret |

**Variables** タブ(任意)

| Name | Value |
|---|---|
| `X_POST_TEMPLATE` | 投稿文のテンプレート。未設定ならデフォルト文言 |

#### 4-3. 投稿される前に本文を確認する

Actions タブ → 「note RSS to Slack / X」→ Run workflow で、
**「X には投稿せず、投稿予定の本文をログに出すだけにする」にチェックを入れて実行**すると、
Xには投稿せずログで本文と文字数だけを確認できます。

初回の本番実行では、既存記事はすべて「投稿済み」として記録されるだけで、
過去記事がXに一斉投稿されることはありません。

#### 4-4. 投稿文をカスタマイズする

Variables の `X_POST_TEMPLATE` に、以下のプレースホルダを含む文章を設定します。

- `{title}` … 記事タイトル
- `{link}` … 記事URL

設定例:

```
📝 新しい記事を公開しました

{title}

▼続きはこちら
{link}

#建設DX #note
```

未設定のときのデフォルトは以下です。

```
📝 noteに新しい記事を公開しました

{title}
{link}
```

280文字(日本語は1文字を2として計算・URLは23文字扱い)を超える場合は、
**タイトルだけが自動で切り詰められます**。定型文が長すぎるとタイトルがほとんど残らないので注意してください。
定型文とURLだけで280文字に達している場合(日本語およそ128文字以上)は切り詰めようがないため、
ログに「X_POST_TEMPLATE が長すぎます」と警告が出ます。手順4-3のドライランで事前に確認できます。

#### 4-5. Xのルール上守るべきこと

**この用途の自動投稿は公式に許可されています。** Xの自動化ルールに明記があります。

> Provided you comply with all other rules, you may post automated posts for
> entertainment, informational, or novelty purposes.
> — [X's automation development rules](https://help.x.com/en/rules-and-policies/x-automation)

記事の新着告知は informational purposes に当たります。凍結の対象になるのは
`duplicative, spammy, or otherwise prohibited content` を投稿するアカウントであって、
投稿手段が自動かどうかではありません。

ただし**開発者ポリシー上の義務が1つ**あります。

> If you're operating an API-based bot account you must clearly indicate what the account is
> and who is responsible for it.
> — [X Developer Policy](https://docs.x.com/developer-terms/policy)

**bot として運用するなら、その旨をプロフィールに明記してください。** 人間の投稿に混ぜて
自動配信する運用でも、「一部の投稿を自動配信しています」等をプロフィールに書いておくのが安全です。

以下は禁止行為です。この仕組みはいずれにも該当しませんが、機能を足すときは注意してください。

- 未承諾の自動リプライ・自動メンション(キーワードに反応する返信など)
- 大量・攻撃的・無差別なリポスト、フォロー/アンフォロー、いいね
- 複数アカウントへの同一・類似コンテンツの投稿
- 同じ記事の繰り返し投稿(`seen_x.json` で防いでいます)

## 費用

| 項目 | 費用 |
|---|---|
| GitHub Actions | Privateリポジトリの無料枠は月2,000分。実測で月およそ1,400分のため**無料枠内**。X投稿を足しても実行回数は増えないので変わりません |
| X API | **従量課金。月およそ$3.6(約540円)** ↓ |

X API に無料枠はありません(2026-08時点)。公式の単価は以下のとおりで、
**URLを含む投稿だけが13倍**の単価です。この仕組みは記事URLを貼るため、常にこの単価が適用されます。

| 操作 | 単価 |
|---|---|
| Post: Create | $0.015 / 件 |
| **Post: Create (with URL)** | **$0.200 / 件** |
| Post: Create (summoned) | $0.010 / 件 |

`dx_madoguchi` のRSSを実測すると**42日で25件＝月およそ18件**。

> 18件 × $0.200 = **月 $3.6(約540円) / 年 約6,500円**

投稿頻度が上がれば比例して増えます。実際の消費はX Developer Consoleでリアルタイムに追跡できます。

Actionsの課金は1回の実行ごとに分単位で切り上げられるため、1回10秒で終わっても1分と数えられます。
`cron` の間隔を短くすると消費が増える点にだけ注意してください。

## 運用メモ

- **通知が来ないとき**: Actionsタブで直近の実行ログを確認。赤い×が付いていれば
  ログにエラー内容が出ています
- **通知文言を変えたい**: `rss_to_slack.py` の `post_to_slack` 内のテキストを編集
- **チャンネルを変えたい**: 手順1で新しいWebhookを作り、Secretを差し替え
- **止めたいとき**: Actionsタブ → ワークフロー右上の「…」→ Disable workflow
- `seen_guids.json` はSlack通知済み記事の記録です。手で編集する必要はありません

### X投稿まわり

- **Xにだけ投稿されないとき**: Actionsログの「RSSをチェックしてXに投稿」ステップを確認
  - `HTTP 401` … 4つのキーの値が違う、または権限変更前のトークンを使っている
  - `HTTP 403` … アプリ権限が Read only、または同一内容の重複投稿
  - `HTTP 429` … X APIの投稿上限に到達
- **X投稿の文言を変えたい**: Variables の `X_POST_TEMPLATE` を編集(コード変更は不要)
- **Xへの投稿だけ止めたい**: `X_API_KEY` などのSecretsを削除。Slack通知はそのまま続きます
- **特定の記事をXに投稿し直したい**: `seen_x.json` から該当記事のGUIDを削除して手動実行
  (`seen_guids.json` とは独立しているので、Slackに再通知は飛びません)