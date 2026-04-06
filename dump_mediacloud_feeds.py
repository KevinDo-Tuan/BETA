"""
One-time script: download Media Cloud's curated RSS feed list.

Strategy:
  1. Get all online_news collections → filter to English-language ones
  2. Get all sources from those collections
  3. Page through ALL feeds globally, keep only ones from English sources
  4. Save to mediacloud_feeds.json

Run once:  py dump_mediacloud_feeds.py
Output:    mediacloud_feeds.json  (~5K-20K feeds depending on filter)
Requires:  MEDIACLOUD_API_KEY in .env  (free at search.mediacloud.org)

API budget: ~200-400 calls total — well within 4K/week free tier.
"""

import os
import sys
import json
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
_env = Path(__file__).parent / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, v = _line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.getenv("MEDIACLOUD_API_KEY", "")
if not API_KEY:
    print("ERROR: MEDIACLOUD_API_KEY not set in .env")
    print("       Get a free key at: https://search.mediacloud.org")
    sys.exit(1)

try:
    import mediacloud.api as mc_api
except ImportError:
    print("ERROR: Run: pip install mediacloud")
    sys.exit(1)

mc = mc_api.DirectoryApi(API_KEY)

# ── Collections with English-language news ────────────────────────────────────
ENGLISH_TERMS = [
    "United States", "United Kingdom", "Canada", "Australia", "New Zealand",
    "Ireland", "South Africa", "India", "Singapore", "Nigeria", "Kenya",
    "Philippines", "Jamaica", "Trinidad", "Ghana", "Pakistan",
    "National", "Financial", "Business", "Top Online", "English",
    "International",
]


def paginate(fn, **kwargs):
    """Generic paginator for Media Cloud list methods."""
    results = []
    offset = 0
    limit = kwargs.pop("limit", 100)
    while True:
        resp = fn(limit=limit, offset=offset, **kwargs)
        batch = resp.get("results", [])
        if not batch:
            break
        results.extend(batch)
        offset += len(batch)
        if resp.get("next") is None:
            break
    return results


# ── Step 1: All online_news collections ───────────────────────────────────────
print("Step 1/3  Fetching all online_news collections...")
all_collections = paginate(mc.collection_list, platform="online_news", limit=100)
print(f"          {len(all_collections)} total collections")

english_collections = [
    c for c in all_collections
    if any(t in c.get("name", "") for t in ENGLISH_TERMS)
]
print(f"          {len(english_collections)} English-language collections kept")
for c in english_collections[:10]:
    print(f"            • {c['name']}")
if len(english_collections) > 10:
    print(f"            ... and {len(english_collections) - 10} more")

# ── Step 2: Sources from filtered collections ─────────────────────────────────
print("\nStep 2/3  Fetching sources from English collections...")
english_source_ids: set = set()
for i, coll in enumerate(english_collections):
    print(f"          [{i+1}/{len(english_collections)}] {coll['name']}        ", end="\r")
    sources = paginate(mc.source_list, collection_id=coll["id"], limit=1000)
    for s in sources:
        english_source_ids.add(s["id"])

print(f"\n          {len(english_source_ids)} unique sources from English collections")

# ── Step 3: Page through ALL feeds, keep English-source ones ──────────────────
print("\nStep 3/3  Fetching all feeds (filtered to English sources)...")
all_feeds: list[dict] = []
seen_urls: set = set()
offset = 0
limit = 1000
processed = 0

while True:
    resp = mc.feed_list(limit=limit, offset=offset)
    batch = resp.get("results", [])
    if not batch:
        break
    processed += len(batch)
    for feed in batch:
        if feed.get("sources_id") not in english_source_ids:
            continue
        url = feed.get("url", "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        all_feeds.append({
            "name": feed.get("name") or feed.get("rss_title") or "",
            "url": url,
            "source_id": feed.get("sources_id"),
        })
    offset += len(batch)
    print(f"          Processed {processed:,} feeds — kept {len(all_feeds):,} English ones...", end="\r")
    if resp.get("next") is None:
        break

print(f"\n          Done. {len(all_feeds):,} unique English feeds saved.")

# ── Save ───────────────────────────────────────────────────────────────────────
out_path = Path(__file__).parent / "mediacloud_feeds.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(all_feeds, f, indent=2, ensure_ascii=False)

print(f"\nSaved → {out_path}  ({out_path.stat().st_size / 1024:.0f} KB)")
print("\nNext step: run py aggregator.py — fetch_mediacloud_feeds() will use this file.")
