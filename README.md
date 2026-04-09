# News Intelligence Graph

 A fully automated news intelligence pipeline that fetches articles from 57+ sources, uses parallel free LLMs to extract structured bullet-point summaries, deduplicates semantically similar stories, and visualizes the result as an interactive knowledge graph — styled after [MiroFish](https://github.com/nikmcfly/MiroFish-Offline).

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/KevinDo-Tuan/BETA.git
cd BETA
pip install feedparser requests trafilatura beautifulsoup4 scikit-learn numpy python-dotenv

# 2. Add your API keys (see Environment Setup below)
cp .env.example .env
# edit .env and fill in your keys

# 3. Run everything in one command
py run.py
```

`run.py` runs all four stages in order and opens the browser automatically.

---

## What it does

```
aggregator.py → summary.py → dedup.py → mindmap.py
   Fetch          Analyze      Dedupe     Visualize
```

| Step | Script | Input | Output | Description |
|------|--------|-------|--------|-------------|
| 1 | `aggregator.py` | RSS feeds | `news_results.json` | Fetches last 24h of articles from 57+ curated sources |
| 2 | `summary.py` | `news_results.json` | `news_stage1.json` | Parallel LLM agents filter and summarize into bullet-point JSON |
| 3 | `dedup.py` | `news_stage1.json` | `news_results_end.json` | TF-IDF cosine similarity removes semantic duplicates |
| 4 | `mindmap.py` | `news_results_end.json` | Browser at `localhost:8765` | Serves an interactive D3.js knowledge graph |

---

## Environment Setup

### API keys (all free, no credit card required)

Create a `.env` file in the project root:

```env
# Currents API — used by aggregator.py for additional news topics
# Get free key: https://currentsapi.services/en/register
CURRENTS_API_KEY=your_currents_api_key_here

# Groq — primary LLM provider (fastest, most reliable on free tier)
# Get free key: https://console.groq.com
GROQ_API_KEY=your_groq_api_key_here

# Google Gemini — secondary LLM provider (1M context window)
# Get free key: https://aistudio.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here

# OpenRouter — fallback LLM provider (access to many free models)
# Get free key: https://openrouter.ai/settings/keys
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Together AI — optional, not required for core pipeline
# Get free key: https://api.together.ai
TOGETHER_API_KEY=your_together_api_key_here
```

> **Minimum to run:** `GROQ_API_KEY` + `CURRENTS_API_KEY`. Gemini and OpenRouter are fallback providers — the pipeline still works without them, just with fewer parallel agents.

---

## Installation

### Requirements

- **Python 3.10** — use `py` on Windows (avoids Python 3.13/uv conflicts)
- Internet connection for RSS feeds and LLM API calls

### Dependencies

```bash
pip install feedparser requests trafilatura beautifulsoup4 scikit-learn numpy python-dotenv
```

---

## Usage

### Option A — Run everything at once (recommended)

```bash
py run.py
```

The browser opens automatically at `http://localhost:8765` when all steps complete.

### Option B — Skip the RSS fetch (reuse existing data)

```bash
py run.py --skip-fetch
```

Skips `aggregator.py` and starts from `summary.py` using your existing `news_results.json`.

### Option C — Jump straight to the map

```bash
py run.py --only-map
```

Opens the mindmap immediately using `news_results_end.json` from the last run.

### Option D — Run scripts individually

```bash
py aggregator.py   # ~2–5 min
py summary.py      # ~5–20 min (depends on rate limits)
py dedup.py        # <1 second
py mindmap.py      # opens browser
```

---

## Sources (~57 active)

| Category | Sources |
|----------|---------|
| **General** | Reuters, The Guardian, Washington Post, New York Times, CNBC, MarketWatch, Bloomberg |
| **Markets** | WSJ, The Economist, Financial Times, Yahoo Finance, Barron's, Business Insider, S&P Global, CBOE |
| **Macro** | Federal Reserve, FRED Blog, Zero Hedge, IMF, BIS, ECB, NY Fed, World Bank, OECD, FSB, Project Syndicate, VoxEU, Brookings |
| **Geopolitics** | CFR, Foreign Affairs, RAND, Atlantic Council, Stratfor, Crisis Group, Geopolitical Futures |
| **Sentiment** | Advisor Perspectives, Seeking Alpha |
| **Crypto** | CoinDesk, CoinTelegraph, The Block, Decrypt, Blockworks, BeInCrypto, CryptoSlate, Messari, Glassnode, The Defiant, Bankless, DL News, and more |
| **Aggregated** | Currents API, GDELT topic queries (65K+ underlying sources) |

---

## Mindmap UI

The graph is built with D3.js, styled after [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline).

**Layout:**

```
┌─────────────────────┬──────────────────────────────────────────┐
│  01 News Source     │  Graph Panel (white dot-grid)            │
│     entity tags     │                                          │
│                     │  [Source]──FROM──▶[Article]──COVERS──▶[Theme Hub]
│  02 Graph Build     │                                          │
│     stats grid      │  Click node → detail panel (right side) │
│                     │  Scroll = zoom  ·  Drag = pan           │
│  03 Refresh         │                                          │
│     pipeline btn    │  Legend (bottom-left)                    │
│  ─────────────────  │  Edge Labels toggle (top-right)          │
│  SYSTEM DASHBOARD   │                                          │
└─────────────────────┴──────────────────────────────────────────┘
```

**Node colors:**

| Color | Entity | Description |
|-------|--------|-------------|
| Orange `#FF5722` | Hub | Theme center node |
| Blue `#004E89` | Macro | Macro-economics articles |
| Red `#C5283D` | Geopolitics | Geopolitical articles |
| Purple `#7B2D8E` | Psychology | Market psychology articles |
| Green `#1A936F` | Markets | Market dynamics articles |
| Gray `#757575` | Source | News publishers |

**Interactions:**

| Action | Result |
|--------|--------|
| Click article node | Bullets, source, published date, link |
| Click theme or source node | All connected articles |
| Click edge | Relationship detail |
| Scroll | Zoom |
| Drag node | Pin position |
| Drag background | Pan |
| Edge Labels toggle | Show/hide COVERS / FROM labels |
| Entity tag (left panel) | Filter graph to one entity type |
| Refresh News button | Re-runs full pipeline with live log |

---

## Output format

### `news_results_end.json` — array of article objects

```json
[
  {
    "title": "Fed signals pause as inflation cools",
    "theme": "macro",
    "bullets": [
      "Federal Reserve holds rates steady at 5.25–5.5%",
      "Core PCE falls to 2.6%, approaching the 2% target",
      "Chair Powell signals no cuts until Q3 data confirms the trend"
    ],
    "source": "Reuters",
    "url": "https://reuters.com/article/...",
    "published": "2026-04-09T14:32:00"
  }
]
```

`theme` is always one of: `macro` · `geopolitical` · `psychology` · `market`

---

## How the LLM pipeline works (`summary.py`)

- Splits ~2,000 articles into **batches of 80**
- Sends batches in parallel to **Groq**, **Gemini**, and **OpenRouter** (all free)
- Each LLM filters for relevance and outputs 2–3 bullet points per qualifying article
- Wave-based execution: 8 concurrent calls → 62s pause → repeat (respects per-minute limits)
- Failed batches retry with exponential backoff: 5s → 10s → 20s

| Provider | Model | Context |
|----------|-------|---------|
| Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | 128K |
| Gemini | `gemini-2.5-flash` | 1M |
| OpenRouter | `google/gemma-3-27b-it:free` | 128K |

---

## How deduplication works (`dedup.py`)

Uses **TF-IDF cosine similarity** on full bullet text — not just title matching:

1. Build a text string per article: `title + bullets + source`
2. Vectorize with TF-IDF bigrams (`ngram_range=(1,2)`)
3. Compute pairwise cosine similarity
4. Pairs scoring ≥ **0.65** → keep the newer article, discard the older

Catches duplicates that title-matching misses:
> *"Fed raises rates 25bps"* and *"Federal Reserve hikes by a quarter point"* → correctly removed.

---

## Free-tier rate limits

| Provider | Requests/min | Daily limit | Resets |
|----------|-------------|-------------|--------|
| Groq | ~30 | ~1,000 | Midnight UTC |
| Gemini | ~15 | ~1,500 | Midnight UTC |
| OpenRouter | ~20 | ~200 | Daily |
| Currents API | — | 600 | Daily |

If limits are hit mid-run, those batches are skipped. Re-run after midnight UTC.

---

## Project structure

```
BETA/
├── run.py                 # One-command launcher for all 4 stages
├── aggregator.py          # Stage 1 — RSS fetcher (57+ sources, 24h lookback)
├── summary.py             # Stage 2 — Parallel LLM bullet-point extraction
├── dedup.py               # Stage 3 — TF-IDF semantic deduplication
├── mindmap.py             # Stage 4 — Local HTTP server (port 8765)
├── mindmap.html           # D3.js interactive knowledge graph frontend
├── .env                   # Your API keys (never commit this)
├── .env.example           # API key template
├── .gitignore
├── news_results.json      # Aggregator output (gitignored)
├── news_stage1.json       # LLM raw output before dedup (gitignored)
└── news_results_end.json  # Final graph data (gitignored)
```

---

## Troubleshooting

**`413 Payload Too Large` from Groq**
Batch too large for that model. The default 80-article batch works reliably with `llama-4-scout`. Do not switch models without testing.

**`429 Too Many Requests`**
Rate limit hit. The script retries 3 times with backoff. If all fail, the batch is skipped and the pipeline continues. Re-run after midnight UTC.

**`news_stage1.json` is empty or very small**
Daily quota exhausted. Check console for `429` errors. Wait until midnight UTC, then re-run with `py run.py --skip-fetch`.

**`py` not found on Windows**
Use the Python Launcher from the official [python.org](https://python.org) installer. Alternatively use `python run.py` — ensure Python 3.10 is active.

**Graph shows 0 articles**
`news_results_end.json` is missing or empty. Run: `py run.py --skip-fetch`

**Port 8765 already in use**
Kill the existing `mindmap.py` process, or change `PORT = 8765` in `mindmap.py`.

---

## License

MIT
