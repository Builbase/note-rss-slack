"""X API 認証の診断用スクリプト(一時的なもの。原因特定後に削除する)

秘密の値そのものは一切出力しない。長さ・文字種・空白混入の有無だけを出し、
認証のみを検証する読み取りエンドポイントを2つのホストで叩く。
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rss_to_x import oauth_header  # noqa: E402


def describe(name: str, value: str) -> None:
    if not value:
        print(f"  {name}: 未設定")
        return
    stripped = value.strip()
    flags = []
    if value != stripped:
        flags.append("!!前後に空白/改行あり!!")
    if "\n" in value or "\r" in value:
        flags.append("!!改行を含む!!")
    if " " in stripped:
        flags.append("!!途中に空白あり!!")
    shape = "数字始まり+ハイフン有" if ("-" in stripped and stripped[0].isdigit()) else "ハイフン無し or 英字始まり"
    print(f"  {name}: 長さ{len(value)} (trim後{len(stripped)}) / {shape} / {' '.join(flags) or 'OK'}")


def probe(host: str, creds: dict) -> None:
    url = f"https://{host}/2/users/me"
    req = urllib.request.Request(
        url, headers={"Authorization": oauth_header("GET", url, creds)}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            body = json.loads(res.read())
            print(f"  {host}: HTTP {res.status} OK -> @{body.get('data', {}).get('username', '?')}")
    except urllib.error.HTTPError as e:
        print(f"  {host}: HTTP {e.code} -> {e.read().decode('utf-8', 'replace')[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"  {host}: 例外 {type(e).__name__}: {e}")


def main() -> None:
    raw = {
        "X_API_KEY": os.environ.get("X_API_KEY", ""),
        "X_API_SECRET": os.environ.get("X_API_SECRET", ""),
        "X_ACCESS_TOKEN": os.environ.get("X_ACCESS_TOKEN", ""),
        "X_ACCESS_TOKEN_SECRET": os.environ.get("X_ACCESS_TOKEN_SECRET", ""),
    }
    print("=== キーの形式(値は出力しない) ===")
    for k, v in raw.items():
        describe(k, v)

    print("\n=== 参考: 正しい場合のおおよその長さ ===")
    print("  API Key(Consumer Key)      : 25文字前後 / 英数字")
    print("  API Secret(Consumer Secret): 50文字前後 / 英数字")
    print("  Access Token               : 50文字前後 / 数字始まり + ハイフン")
    print("  Access Token Secret        : 45文字前後 / 英数字")
    print("  ※OAuth 2.0 の Client ID は約35文字でハイフン無し(取り違えの目印)")

    creds = {
        "api_key": raw["X_API_KEY"].strip(),
        "api_secret": raw["X_API_SECRET"].strip(),
        "access_token": raw["X_ACCESS_TOKEN"].strip(),
        "access_token_secret": raw["X_ACCESS_TOKEN_SECRET"].strip(),
    }
    print("\n=== 認証のみの検証(GET /2/users/me・書き込み権限は不要) ===")
    for host in ("api.x.com", "api.twitter.com"):
        probe(host, creds)

    # Consumer Key/Secret だけで Bearer Token を取得できるか。
    # これが通れば Consumer 側は有効で、問題は Access Token 側に絞られる
    print("\n=== Consumer Key/Secret 単独の検証(App-only 認証) ===")
    import base64 as _b64
    basic = _b64.b64encode(
        f"{urllib.parse.quote(creds['api_key'], safe='')}:"
        f"{urllib.parse.quote(creds['api_secret'], safe='')}".encode()
    ).decode()
    req = urllib.request.Request(
        "https://api.x.com/oauth2/token",
        data=b"grant_type=client_credentials",
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            got = json.loads(res.read())
            print(f"  HTTP {res.status} OK -> Bearer Token 取得成功"
                  f"(長さ{len(got.get('access_token',''))}) = Consumer Key/Secret は有効")
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} -> {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:  # noqa: BLE001
        print(f"  例外 {type(e).__name__}: {e}")

    # 外部ライブラリでも同じ結果になるか。自作署名の不具合かを切り分ける
    print("\n=== 外部ライブラリ(requests-oauthlib)での検証 ===")
    try:
        import requests
        from requests_oauthlib import OAuth1
        auth = OAuth1(
            creds["api_key"], creds["api_secret"],
            creds["access_token"], creds["access_token_secret"],
            signature_type="auth_header",
        )
        r = requests.get("https://api.x.com/2/users/me", auth=auth, timeout=30)
        print(f"  HTTP {r.status_code} -> {r.text[:200]}")
        if r.status_code == 200:
            print("  ※ライブラリでは通った = 自作の署名処理に不具合がある")
        else:
            print("  ※ライブラリでも同じ = キーまたはアプリ設定側の問題")
    except ImportError:
        print("  requests-oauthlib が未インストールのためスキップ")


if __name__ == "__main__":
    main()
