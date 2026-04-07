## Reusable Code from Sibling Projects

### `d:/Coding/MiroFish/backend/app/utils/`
- **`llm_client.py`** — `LLMClient` class: OpenAI-compatible `chat()` + `chat_json()`. Strips `<think>` tags from reasoning models, auto-cleans markdown fences before JSON parse. Best for adding LLM signal extraction to news articles.
- **`retry.py`** — `retry_with_backoff` decorator (sync + async). Exponential backoff with jitter, configurable exception types. Wrap RSS fetchers to handle transient HTTP failures.
- **`file_parser.py`** — `FileParser.extract_text()` for PDF/MD/TXT. Multi-level encoding fallback (UTF-8 → charset_normalizer → chardet → UTF-8+replace).

### `d:/Coding/news/last30days-skill/scripts/lib/`
- **`dedupe.py`** — Near-duplicate detection via hybrid trigram + token Jaccard similarity.
- **`dates.py`** — `parse_date()` handles Unix timestamps + ISO 8601 multi-format.
- **`score.py`** — Composite scoring: `relevance * 0.45 + recency * 0.25 + engagement * 0.30`.
- **`relevance.py`** + **`entity_extract.py`** — NLP-based relevance scoring and entity extraction.

---

## Aggregator Project Context

**Main file:** `d:/Coding/news/aggregator.py`
**Output:** `news_results.json` (JSON array, sorted by published desc)
**Run command:** `py aggregator.py` (NOT `python` — Windows Git Bash uses `py` launcher)
**Python env:** `py` = Python 3.10. Do NOT use uv Python 3.13 (feedparser not installed there).
**Lookback window:** `HOURS = 24`
**Current source count:** ~65 sources across 7 categories (see docstring at top of aggregator.py)
**GitHub remote:** `https://github.com/KevinDo-Tuan/BETA.git` (branch: master)

### Article dict fields
```python
{"source": str, "title": str, "url": str, "published": str, "summary": str, "content": str}
```
- `summary`: capped at 300 chars from RSS feed
- `content`: filled by `enrich_articles()` via 6-layer pipeline, often empty for paywalled sites

### Feed Patterns Used
- **Direct RSS:** `feedparser.parse(URL)` → iterate `feed.entries`
- **Google News RSS (site-specific):** `https://news.google.com/rss/search?q=site:domain.com&hl=en-US&gl=US&ceid=US:en` — use two feeds (regular + `when:24h+site:...`) and dedup by URL then title
- **Google News RSS (topic):** `https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q=when:24h+{keywords}` — used by `fetch_gnews_topics()`

### Source Categories
- **Crypto (21 sources):** CoinTelegraph, BeInCrypto, CryptoSlate, Decrypt, The Block, CoinDesk, Blockworks, Bitcoin Magazine, CryptoNews, crypto.news, Protos, Unchained, Messari, Glassnode, The Defiant, Bankless, Crypto Briefing, DL News, AInvest, SoSoValue, TradingView
- **Market/Finance:** WSJ, Bloomberg, FT, Yahoo Finance, Barron's, Business Insider, S&P Global, CBOE, MarketWatch, The Economist, Seeking Alpha, Advisor Perspectives
- **Macro/Economics:** Federal Reserve, FRED Blog, IMF, BIS, ECB, NY Fed, World Bank, OECD, FSB, Project Syndicate, VoxEU, Brookings, Zero Hedge
- **Geopolitical:** CFR, Foreign Affairs, RAND, Atlantic Council, Stratfor, Crisis Group
- **General News:** Reuters, The Guardian, Washington Post, New York Times, CNBC
- **Broad Aggregators:** Currents API (`Currents/Business` etc.), GNews Topics (`GNews/Market`, `GNews/Fed`, `GNews/Macro`, `GNews/Geopolitical`)

### Dedup Pattern (Pattern B — list comprehension)
```python
seen_titles: set = set()
unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
```

### Key Internals
- **`_dedupe_articles(threshold=0.72)`** — near-dedup via trigram + token Jaccard on titles. Runs after fetch, before enrich. Collapses ~10% duplicates.
- **`enrich_articles(workers=50)`** — 6-layer content extraction pipeline, 50 threads. Layers: WSJ AMP → AMP builders → trafilatura → Googlebot UA → nodriver (capped at 4 via `_NODRIVER_SEM`) → Wayback Machine.
- **Google News URL resolution** — at start of `_fetch_content_layered`, resolves `news.google.com/rss/articles/...` redirect URLs to real article URLs using `requests.get(stream=True)`. Fixes WSJ AMP bypass and Wayback lookup.
- **`_PAYWALL_SOURCES`** — WSJ, The Economist, FT, Bloomberg, WaPo, NYT, Barron's, Business Insider. 12ft.io layer fires for these (NOTE: 12ft.io shut down Jul 2025 — layer is dead, should be removed).
- **`_NO_WAYBACK_SOURCES`** — crypto/social sources that are never archived. Wayback skipped for these.
- All timeouts use `(connect, read)` tuple: `timeout=(3, N)` for fast fail on dead links.

### .env Keys Required
```
CURRENTS_API_KEY=...   # free at currentsapi.services/en/register
GROQ_API_KEY=...       # free at console.groq.com (for summarize.py — not yet built)
MEDIACLOUD_API_KEY=... # optional — only for dump_mediacloud_feeds.py one-time script
```

---

## Scripts

### `dump_mediacloud_feeds.py` (one-time utility)
Downloads Media Cloud's curated English RSS feed list (~5K-20K feeds) via their free API.
Saves to `mediacloud_feeds.json` (gitignored). Run once:
```
py dump_mediacloud_feeds.py
```
Requires `MEDIACLOUD_API_KEY` in `.env`. Get free key at search.mediacloud.org.
The aggregator does NOT use this file currently (fetch_mediacloud_feeds was removed from aggregator).

### `summarize.py` (PLANNED — not yet implemented)
Reads `news_results.json`, groups articles into 5 categories (Crypto/Market/Macro/Geopolitical/General),
makes 1 Groq LLM call per category (top 40 articles × title + 100-char summary), outputs:
- `news_summary.json` — structured briefing
- Terminal — formatted bullet-point briefing

**Implementation plan is in:** `C:/Users/Do Pham Tuan/.claude/plans/woolly-jumping-newell.md` (top section)

Key design decisions already made:
- Model: `llama-3.3-70b-versatile` on Groq (free, 128K context, OpenAI-compatible)
- Uses `requests` directly (no `openai` package needed)
- Sequential API calls (5 calls, ~15-30s total) — avoids Groq rate limits
- Source→category mapping already designed (see plan file)

Run order: `py aggregator.py` → `py summarize.py`

---

## Known Issues / Tech Debt
- **`_try_12ft()`** in `aggregator.py` is dead code — 12ft.io shut down July 2025. Should be removed.
- **`_PAYWALL_SOURCES`** set and `_try_12ft()` function can both be deleted.
- **WSJ/WaPo/FT/Bloomberg content always empty** — hard paywalls, no reliable free bypass exists. Archive.ph unreliable (CAPTCHA + Jan 2026 DDoS incident). Wayback Machine too slow for same-day articles.

---

## Rules
+ You are allowed to search Google to help with tasks
+ After making changes, update this CLAUDE.md to reflect the new state
+ Users use OpenClaw for this project (tools: exec, browser, web_search, read/write/edit, apply_patch, message, canvas, nodes, cron/gateway, image_generate, sessions/agents)
