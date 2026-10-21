"""
Tell Bing, Yandex, Seznam and Naver which pages of holibase.org are new or changed (IndexNow).

    python scripts/indexnow.py --previous old-hashes.json --current web/public/assets/page-hashes.json [--dry-run]

web/build.py writes a hash of every page's title, description and content to assets/page-hashes.json.
The deploy workflow downloads the live copy before deploying; after the deploy this script compares
the two and sends the paths that are new or changed. Without a previous copy (first run) it sends all.
Google does not take part in IndexNow; it reads the sitemap.

The key is not a secret: it only proves that the site itself sends the list, by being served at
https://holibase.org/<key>.txt (web/public/<key>.txt).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

SITE = "holibase.org"
KEY = "4ade8d2722f02abcbb5f5bccf8b3d33b"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10000  # the protocol's limit per request


def load(path: str | None) -> dict:
    try:
        return json.loads(pathlib.Path(path).read_text()) if path else {}
    except (OSError, ValueError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--previous")
    ap.add_argument("--current", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    old, new = load(args.previous), load(args.current)
    if not new:
        print("no page hashes in this build, nothing to send")
        return 0
    changed = sorted(p for p, h in new.items() if old.get(p) != h)
    print(f"{len(new)} pages, {len(changed)} new or changed" + ("" if old else " (no previous list: sending all)"))
    for p in changed[:20]:
        print("  " + p)
    if not changed or args.dry_run:
        return 0
    for i in range(0, len(changed), BATCH):
        body = json.dumps({"host": SITE, "key": KEY, "keyLocation": f"https://{SITE}/{KEY}.txt",
                           "urlList": [f"https://{SITE}{p}" for p in changed[i:i + BATCH]]}).encode()
        req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"IndexNow: HTTP {r.status}")
        except urllib.error.HTTPError as e:
            # 202 = accepted, key not yet checked; 403/422 = key file or URLs not accepted; 429 = too often
            print(f"::warning::IndexNow answered HTTP {e.code}: {e.read()[:300]!r}")
        except OSError as e:
            print(f"::warning::IndexNow not reachable: {e}")
    return 0  # a failed ping must never fail the deploy


if __name__ == "__main__":
    sys.exit(main())
