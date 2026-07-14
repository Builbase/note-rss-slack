"""note RSS -> Slack 自動配信スクリプト

標準ライブラリのみ使用(pip install 不要)。
環境変数:
  SLACK_WEBHOOK_URL : Slack Incoming Webhook の URL(必須・Secretsで渡す)
  NOTE_RSS_URL      : note の RSS URL(必須)例: https://note.com/ユーザー名/rss
状態ファイル:
  seen_guids.json   : 通知済み記事の GUID 一覧。初回実行時は現在の全記事を
                      既読として記録するだけで、Slack には投稿しない
                      (過去記事の一斉投稿を防ぐため)。
"""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET

STATE_FILE = "seen_guids.json"
MAX_STATE_SIZE = 500  # 既読GUIDの保持上限(古いものから削除)


def fetch_rss(url: str) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": "rss-to-slack/1.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return ET.fromstring(res.read())


def parse_items(root: ET.Element) -> list[dict]:
    """RSS 2.0 の item を新しい順のまま取り出す"""
    items = []
    for item in root.findall("./channel/item"):
        guid = item.findtext("guid") or item.findtext("link")
        items.append(
            {
                "guid": guid,
                "title": (item.findtext("title") or "(無題)").strip(),
                "link": (item.findtext("link") or "").strip(),
            }
        )
    return items


def load_state() -> list[str]:
    if not os.path.exists(STATE_FILE):
        return []
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_state(guids: list[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(guids[-MAX_STATE_SIZE:], f, ensure_ascii=False, indent=2)


def post_to_slack(webhook_url: str, item: dict) -> None:
    payload = {
        "text": f"📝 noteに新着記事が公開されました\n*<{item['link']}|{item['title']}>*"
    }
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        if res.status != 200:
            raise RuntimeError(f"Slack への投稿に失敗しました: HTTP {res.status}")


def main() -> None:
    rss_url = os.environ.get("NOTE_RSS_URL")
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not rss_url or not webhook_url:
        sys.exit("環境変数 NOTE_RSS_URL / SLACK_WEBHOOK_URL を設定してください")

    items = parse_items(fetch_rss(rss_url))
    if not items:
        print("フィードに記事がありません")
        return

    seen = load_state()

    # 初回実行: 全記事を既読登録のみ(投稿しない)
    if not seen:
        save_state([i["guid"] for i in reversed(items)])
        print(f"初回実行: {len(items)} 件を既読として登録しました(投稿なし)")
        return

    seen_set = set(seen)
    new_items = [i for i in items if i["guid"] not in seen_set]

    if not new_items:
        print("新着なし")
        return

    # 古い記事から順に投稿(時系列を保つ)
    for item in reversed(new_items):
        post_to_slack(webhook_url, item)
        seen.append(item["guid"])
        print(f"投稿: {item['title']}")

    save_state(seen)
    print(f"{len(new_items)} 件を投稿しました")


if __name__ == "__main__":
    main()
