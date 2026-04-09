<div align="center">

# News Intelligence Graph

**Turn 57+ news sources into a live, interactive knowledge graph — powered by free LLMs.**

[![Python 3.10](https://img.shields.io/badge/Python-3.10-black?style=flat-square&logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-black?style=flat-square)](LICENSE)
[![Free LLMs](https://img.shields.io/badge/LLMs-100%25%20Free%20Tier-black?style=flat-square)](https://console.groq.com)
[![No credit card](https://img.shields.io/badge/API%20Keys-No%20Credit%20Card-black?style=flat-square)](.env.example)

<br/>

<img width="1213" alt="News Intelligence Graph — interactive D3.js knowledge graph" src="https://github.com/user-attachments/assets/8504d397-aa72-4db8-89c6-a681ace06905" />

<br/><br/>

*Every morning, one command fetches the day's macro, geopolitical, market, and crypto news — filters it with parallel LLM agents — deduplicates semantically — and maps it as an interactive force graph you can explore.*

</div>

---

## How it works

```
aggregator.py → summary.py → dedup.py → mindmap.py
   57+ RSS        Parallel     TF-IDF      D3.js
   sources        LLM agents   cosine      graph
   ~2,000 art.    filter+sum.  dedup       localhost:8765
```

| # | Script | What happens | Time |
|---|--------|-------------|------|
| 1 | `aggregator.py` | Fetches last 24h from 57+ curated RSS sources | 2–5 min |
| 2 | `summary.py` | 8 parallel LLM agents filter for relevance, write 2–3 bullet points per article | 5–20 min |
| 3 | `dedup.py` | TF-IDF cosine similarity removes stories that say the same thing | < 1 sec |
| 4 | `mindmap.py` | Serves an interactive knowledge graph at `localhost:8765` | instant |

---

## Quickstart

### 1. Clone & install

```bash
git clone https://github.com/KevinDo-Tuan/BETA.git
cd BETA
pip install feedparser requests trafilatura beautifulsoup4 scikit-learn numpy python-dotenv
```

### 2. Add your API keys

All keys are **free** — no credit card required.

```bash
cp .env.example .env
# open .env and paste your keys
```

```env
# Required
CURRENTS_API_KEY=your_key_here    # https://currentsapi.services/en/register
GROQ_API_KEY=your_key_here        # https://console.groq.com

# Recommended (fallback LLM providers)
GEMINI_API_KEY=your_key_here      # https://aistudio.google.com/app/apikey
OPENROUTER_API_KEY=your_key_here  # https://openrouter.ai/settings/keys
```

> Minimum: `GROQ_API_KEY` + `CURRENTS_API_KEY`. The pipeline works without Gemini/OpenRouter — just fewer parallel agents.

### 3. Run

```bash
py run.py
```

Browser opens automatically at `http://localhost:8765`.

---

## Run options

| Command | What it does |
|---------|-------------|
| `py run.py` | Full pipeline — fetch → analyze → dedup → visualize |
| `py run.py --skip-fetch` | Skip RSS fetch, reuse today's `news_results.json` |
| `py run.py --only-map` | Jump straight to the map with existing data |

---

## The Graph

The mindmap UI is styled after [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) — same white dot-grid canvas, curved D3.js force graph, step cards, and detail panels.

**Node types**

| Color | Type | What it represents |
|-------|------|--------------------|
| `#FF5722` | Hub | Theme center (Macro / Geopolitics / Markets / Psychology) |
| `#004E89` | Macro | Macro-economics article |
| `#C5283D` | Geopolitics | Geopolitical article |
| `#7B2D8E` | Psychology | Market sentiment article |
| `#1A936F` | Markets | Market dynamics article |
| `#757575` | Source | News publisher |

**Controls**

| Input | Action |
|-------|--------|
| Click node | Open detail panel — bullets, source, date, link |
| Click theme node | See all articles in that theme |
| Click edge | See relationship detail |
| Scroll | Zoom in / out |
| Drag node | Pin it in place |
| Drag canvas | Pan |
| Entity tag (left panel) | Filter graph to one type |
| Refresh News | Re-run full pipeline with live log stream |

---

## Sources (~57 active)

<details>
<summary>Click to expand full source list</summary>

| Category | Sources |
|----------|---------|
| **General** | Reuters, The Guardian, Washington Post, New York Times, CNBC, MarketWatch, Bloomberg |
| **Markets** | WSJ, The Economist, Financial Times, Yahoo Finance, Barron's, Business Insider, S&P Global, CBOE |
| **Macro** | Federal Reserve, FRED Blog, Zero Hedge, IMF, BIS, ECB, NY Fed, World Bank, OECD, FSB, Project Syndicate, VoxEU, Brookings |
| **Geopolitics** | CFR, Foreign Affairs, RAND, Atlantic Council, Stratfor, Crisis Group, Geopolitical Futures |
| **Sentiment** | Advisor Perspectives, Seeking Alpha |
| **Crypto** | CoinDesk, CoinTelegraph, The Block, Decrypt, Blockworks, BeInCrypto, CryptoSlate, Messari, Glassnode, The Defiant, Bankless, DL News, and more |
| **Aggregated** | Currents API, GDELT topic queries (65K+ underlying sources) |

</details>

---

## Output schema

```json
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
```

`theme` → `macro` · `geopolitical` · `psychology` · `market`

---

## LLM providers (all free tier)

| Provider | Model | Context | RPM | Daily |
|----------|-------|---------|-----|-------|
| Groq | `llama-4-scout-17b-16e-instruct` | 128K | 30 | 1,000 |
| Gemini | `gemini-2.5-flash` | 1M | 15 | 1,500 |
| OpenRouter | `gemma-3-27b-it:free` | 128K | 20 | 200 |

8 agents run in parallel, with 62s pauses between waves to respect per-minute limits. Failed batches retry with 5s → 10s → 20s backoff.

---

## Deduplication

`dedup.py` uses **TF-IDF cosine similarity** on the full bullet text — not just headline matching.

- Vectorizes `title + bullets + source` with TF-IDF bigrams
- Any two articles with cosine similarity ≥ 0.65 → keep the newer one
- Catches semantically identical stories with different headlines:

> *"Fed raises rates 25bps"* and *"Federal Reserve hikes by a quarter point"* → one removed.

---

## Project structure

```
BETA/
├── run.py              ← start here
├── aggregator.py       Stage 1 — RSS fetch
├── summary.py          Stage 2 — LLM analysis
├── dedup.py            Stage 3 — semantic dedup
├── mindmap.py          Stage 4 — web server
├── mindmap.html        D3.js graph frontend
├── .env.example        API key template
└── .gitignore
```

---

## Troubleshooting

<details>
<summary>429 Too Many Requests</summary>

Free-tier daily quota hit. The script retries 3 times then skips the batch and continues. Re-run after midnight UTC, or use `py run.py --skip-fetch` to skip re-fetching.

</details>

<details>
<summary>413 Payload Too Large from Groq</summary>

Only affects non-scout models. The default `llama-4-scout` handles 80-article batches reliably. Do not change the model without testing.

</details>

<details>
<summary>Graph shows 0 articles</summary>

`news_results_end.json` is missing. Run:
```bash
py run.py --skip-fetch
```

</details>

<details>
<summary>Port 8765 already in use</summary>

Kill the existing `mindmap.py` process (`Ctrl+C` in its terminal), or change `PORT = 8765` in `mindmap.py`.

</details>

<details>
<summary>py command not found on Windows</summary>

Install Python from [python.org](https://python.org) (includes the `py` launcher). Alternatively use `python run.py` — ensure Python 3.10 is active, not 3.13.

</details>

---

<div align="center">

MIT License · Built with [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) inspiration

</div>
