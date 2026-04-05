## Reusable Code from Sibling Projects

### `d:/Coding/MiroFish/backend/app/utils/`
- **`llm_client.py`** — `LLMClient` class: OpenAI-compatible `chat()` + `chat_json()`. Strips `<think>` tags from reasoning models, auto-cleans markdown fences before JSON parse. Best for adding LLM signal extraction to news articles.
- **`retry.py`** — `retry_with_backoff` decorator (sync + async). Exponential backoff with jitter, configurable exception types. Wrap RSS fetchers to handle transient HTTP failures.
- **`file_parser.py`** — `FileParser.extract_text()` for PDF/MD/TXT. Multi-level encoding fallback (UTF-8 → charset_normalizer → chardet → UTF-8+replace).

### `d:/Coding/news/last30days-skill/scripts/lib/`
- **`dedupe.py`** — Near-duplicate detection via hybrid trigram + token Jaccard similarity. `dedupe_items(items, threshold=0.7)` keeps highest-scored item from near-duplicate pairs. `cross_source_link()` adds bidirectional cross-refs across sources at threshold=0.40. Replace aggregator's exact title/URL dedup with this for ~1,080 daily articles.
- **`dates.py`** — `parse_date()` handles Unix timestamps + ISO 8601 multi-format. `recency_score(date_str, max_days=30)` returns 0-100 decay score. Enhances `to_utc()` in aggregator.
- **`score.py`** — Composite scoring: `relevance * 0.45 + recency * 0.25 + engagement * 0.30`. `log1p_safe()`, `normalize_to_100()` for engagement normalization. `relevance_filter()` with minimum-result guarantee (always keeps top 3). Adaptable for ranking news articles.
- **`cache.py`** — Disk-based caching to avoid re-fetching RSS feeds on repeated runs.
- **`parallel_search.py`** — Parallel execution pattern. Adaptable to parallelize the 29 RSS fetchers (currently sequential, takes ~30s).
- **`relevance.py`** + **`entity_extract.py`** — NLP-based relevance scoring and entity extraction. Useful for options signal extraction (tickers, events, sentiment).

---

## Aggregator Project Context

**Main file:** `d:/Coding/news/aggregator.py`
**Output:** `news_results.json` in the working directory (JSON array, sorted by published desc)
**Run command:** `py aggregator.py` (NOT `python` — Windows Git Bash has no `python` in PATH; use the `py` launcher)
**Python env:** Use `py` (Python 3.10, packages pre-installed). Do NOT use uv's Python 3.13 (feedparser not installed there; uv Python is externally managed).
**Lookback window:** `HOURS = 24` — fetches articles from last 24 hours
**Current source count:** 29 sources (see docstring at top of aggregator.py)
**Known bug:** `fetch_blockworks()` is called in `run()` but the function is not defined → NameError at runtime. Needs to be added.

### Feed Patterns Used
- **Direct RSS:** `feedparser.parse(URL)` → iterate `feed.entries`, check `entry.get("link")` and `entry.get("published_parsed")`
- **Google News RSS:** `https://news.google.com/rss/search?q=site:domain.com&hl=en-US&gl=US&ceid=US:en` — use two feeds (regular + `when:24h+site:...`) and dedup by URL then title

### Dedup Pattern (use Pattern B — list comprehension)
```python
seen_titles: set = set()
unique = [r for r in results if not (r["title"] in seen_titles or seen_titles.add(r["title"]))]
```

### Windows Terminal Encoding Fix (already at top of aggregator.py)
```python
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
```

---
+ You are allowed to search google in order to help users with your best capabilities
+ Also after make changes, fix Claude.md to clear with the new changes.
The users will use OpenClaw for this project. Here is the tools of OpenClaw that the LLMs will use to help users, which the users have fetched on official website:
Tool	What it does	Page
exec / process	Run shell commands, manage background processes	Exec
code_execution	Run sandboxed remote Python analysis	Code Execution
browser	Control a Chromium browser (navigate, click, screenshot)	Browser
web_search / x_search / web_fetch	Search the web, search X posts, fetch page content	Web
read / write / edit	File I/O in the workspace	
apply_patch	Multi-hunk file patches	Apply Patch
message	Send messages across all channels	Agent Send
canvas	Drive node Canvas (present, eval, snapshot)	
nodes	Discover and target paired devices	
cron / gateway	Manage scheduled jobs, restart gateway	
image / image_generate	Analyze or generate images	
sessions_* / agents_list	Session management, sub-agents	Sub-agents
