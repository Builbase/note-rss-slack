"""note RSS -> X(Twitter) 自動投稿スクリプト

標準ライブラリのみ使用(pip install 不要)。
環境変数:
  NOTE_RSS_URL          : note の RSS URL(必須)例: https://note.com/ユーザー名/rss
  X_API_KEY             : X アプリの API Key(必須・Secret)
  X_API_SECRET          : X アプリの API Key Secret(必須・Secret)
  X_ACCESS_TOKEN        : 投稿先アカウントの Access Token(必須・Secret)
  X_ACCESS_TOKEN_SECRET : 同 Access Token Secret(必須・Secret)
  X_POST_TEMPLATE       : 投稿文のテンプレート(任意)。{title} {link} を差し込む
  X_DRY_RUN             : 1 を指定すると投稿せず本文を表示するだけ(状態も更新しない)
状態ファイル:
  seen_x.json           : X に投稿済みの記事 GUID 一覧。Slack 側の seen_guids.json とは
                          独立しており、片方をやり直しても他方に影響しない。初回実行時は現在の全記事を
                          既読として記録するだけで、X には投稿しない
                          (過去記事の一斉投稿を防ぐため)。
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

STATE_FILE = "seen_x.json"
MAX_STATE_SIZE = 500  # 既読GUIDの保持上限(古いものから削除)

TWEETS_ENDPOINT = "https://api.x.com/2/tweets"


class AlreadyPosted(Exception):
    """同一内容が既に投稿済みだと X に拒否された(記録漏れからの復帰用)"""

DEFAULT_TEMPLATE = "📝 noteに新しい記事を公開しました\n\n{title}\n{link}"

# X の文字数カウント仕様(twitter-text v3)
MAX_WEIGHTED_LENGTH = 280
URL_WEIGHTED_LENGTH = 23  # URL は実際の長さに関係なくこの重みで数えられる
# 重み1(半角相当)になるコードポイント範囲。ここ以外は重み2(全角相当)。
# twitter-text v3 の config/v3.json をそのまま写したもの。範囲を広く取ると
# 「…」(U+2026)などを過小に数え、280文字を超える本文を作ってしまう
LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


# ---------------------------------------------------------------- RSS

def fetch_rss(url: str) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": "rss-to-x/1.0"})
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


# ---------------------------------------------------------------- 状態

def load_state() -> list[str]:
    if not os.path.exists(STATE_FILE):
        return []
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_state(guids: list[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(guids[-MAX_STATE_SIZE:], f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 文字数

def weighted_length(text: str) -> int:
    """X の重み付き文字数を返す(日本語は1文字=2)"""
    total = 0
    for ch in text:
        cp = ord(ch)
        total += 1 if any(lo <= cp <= hi for lo, hi in LIGHT_RANGES) else 2
    return total


# SHORTCUT: 絵文字の ZWJ 連結(👨‍👩‍👧 等)を1文字にまとめる処理は入れていない。
# 実際より多く数えるため上限を超えることはないが、定型文に連結絵文字を多用すると
# タイトルが必要以上に切り詰められる。踏んだら grapheme 分割に置き換える。
def build_text(template: str, title: str, link: str) -> str:
    """テンプレートに差し込み、280文字に収まるようタイトルだけを切り詰める"""
    # str.format は本文中の { } でも落ちるため、単純置換で差し込む
    fixed = template.replace("{title}", "").replace("{link}", "")
    # プレースホルダは複数回書けるので、出現回数の分だけ予算を引く
    title_count = template.count("{title}")
    link_count = template.count("{link}")
    # link が空(RSSにlinkが無い記事)なら URL 分の枠は要らない
    url_cost = URL_WEIGHTED_LENGTH * link_count if link else 0
    budget = MAX_WEIGHTED_LENGTH - weighted_length(fixed) - url_cost
    # タイトルが複数回入るなら、1回あたりに使える枠はその分だけ小さくなる
    if title_count > 1:
        budget //= title_count

    if title_count and weighted_length(title) > budget:
        ellipsis = "…"
        # 省略記号自体にも重み2がある。これを引いて余りが無ければ、
        # 省略記号を足すと逆に上限を超えるのでタイトルごと落とす
        room = budget - weighted_length(ellipsis)
        if room <= 0:
            title = ""
        else:
            truncated = ""
            used = 0
            for ch in title:
                w = weighted_length(ch)
                if used + w > room:
                    break
                truncated += ch
                used += w
            title = truncated + ellipsis

    # 切り詰めた後の実効の重みで判定する。予算だけを見ると、{title} を含まない
    # テンプレートが単独で上限を超えている場合を見落とす
    effective = (
        weighted_length(fixed)
        + weighted_length(title) * title_count
        + url_cost
    )
    if effective > MAX_WEIGHTED_LENGTH:
        print(
            f"警告: X_POST_TEMPLATE が長すぎます"
            f"(この本文は {effective}/{MAX_WEIGHTED_LENGTH} 文字で、Xに拒否されます)",
            file=sys.stderr,
        )

    return template.replace("{title}", title).replace("{link}", link)


# ---------------------------------------------------------------- OAuth 1.0a

def _percent(value: str) -> str:
    """RFC 3986 のパーセントエンコード(OAuth 署名で必須)"""
    return urllib.parse.quote(str(value), safe="-._~")


def oauth_header(method: str, url: str, creds: dict) -> str:
    params = {
        "oauth_consumer_key": creds["api_key"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": creds["access_token"],
        "oauth_version": "1.0",
    }
    # JSON ボディの POST では、ボディは署名対象に含めない
    param_string = "&".join(
        f"{_percent(k)}={_percent(v)}" for k, v in sorted(params.items())
    )
    base_string = f"{method}&{_percent(url)}&{_percent(param_string)}"
    signing_key = f"{_percent(creds['api_secret'])}&{_percent(creds['access_token_secret'])}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    params["oauth_signature"] = signature
    return "OAuth " + ", ".join(
        f'{_percent(k)}="{_percent(v)}"' for k, v in sorted(params.items())
    )


def post_to_x(creds: dict, text: str) -> str:
    """ツイートを投稿し、投稿IDを返す"""
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        TWEETS_ENDPOINT,
        data=body,
        headers={
            "Authorization": oauth_header("POST", TWEETS_ENDPOINT, creds),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read()).get("data", {}).get("id", "?")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        # 原因の切り分けに必要なので、ステータスと本文をそのまま出す
        if e.code == 401:
            hint = "認証エラー。4つのキーの値と、アプリ権限を Read and write にした後に Access Token を再生成したかを確認してください"
        elif e.code == 403:
            # 投稿成功後に記録を残せずプロセスが落ちると、次回この経路に入る。
            # 停止すると以後の記事も投稿できなくなるため、投稿済みとして扱い先へ進む
            if "duplicate" in detail.lower():
                raise AlreadyPosted(detail) from None
            hint = "投稿が拒否されました。アプリ権限が Read only の可能性があります"
        elif e.code == 429:
            hint = "レート上限に達しました。X の Free プランは投稿数に上限があります"
        else:
            hint = "X API がエラーを返しました"
        raise RuntimeError(f"{hint} (HTTP {e.code}): {detail}") from None


# ---------------------------------------------------------------- main

def main() -> None:
    rss_url = os.environ.get("NOTE_RSS_URL")
    creds = {
        "api_key": os.environ.get("X_API_KEY"),
        "api_secret": os.environ.get("X_API_SECRET"),
        "access_token": os.environ.get("X_ACCESS_TOKEN"),
        "access_token_secret": os.environ.get("X_ACCESS_TOKEN_SECRET"),
    }
    dry_run = os.environ.get("X_DRY_RUN") == "1"
    template = os.environ.get("X_POST_TEMPLATE") or DEFAULT_TEMPLATE

    if not rss_url:
        sys.exit("環境変数 NOTE_RSS_URL を設定してください")
    missing = [k for k, v in creds.items() if not v]
    if missing and not dry_run:
        sys.exit(f"X の認証情報が未設定です: {', '.join(missing)}")

    items = parse_items(fetch_rss(rss_url))
    if not items:
        print("フィードに記事がありません")
        return

    seen = load_state()

    # 初回実行: 全記事を既読登録のみ(投稿しない)
    if not seen:
        if dry_run:
            print(f"[DRY RUN] 初回実行: {len(items)} 件を既読登録する状態です(状態は書き換えません)")
            return
        save_state([i["guid"] for i in reversed(items)])
        print(f"初回実行: {len(items)} 件を既読として登録しました(投稿なし)")
        return

    seen_set = set(seen)
    new_items = [i for i in items if i["guid"] not in seen_set]

    if not new_items:
        print("新着なし")
        return

    # 古い記事から順に投稿(時系列を保つ)
    posted = 0
    for item in reversed(new_items):
        text = build_text(template, item["title"], item["link"])
        if dry_run:
            print(f"[DRY RUN] 投稿予定 ({weighted_length(text)}/{MAX_WEIGHTED_LENGTH}):\n{text}\n---")
            continue
        try:
            tweet_id = post_to_x(creds, text)
            posted += 1
            print(f"投稿: {item['title']} (id={tweet_id})")
        except AlreadyPosted:
            print(f"投稿済みのため記録のみ更新: {item['title']}")
        # 途中で失敗しても既投稿分を再投稿しないよう、1件ごとに記録する
        seen.append(item["guid"])
        save_state(seen)

    if dry_run:
        print(f"[DRY RUN] {len(new_items)} 件が投稿対象です(実際には投稿していません)")
    else:
        print(f"{posted} 件を投稿しました")


if __name__ == "__main__":
    main()
