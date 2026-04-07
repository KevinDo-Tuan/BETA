"""
agents.py — Multi-provider parallel LLM analysis of news_results.json.

Parallel threads across Groq / Gemini / OpenRouter.
Each thread reads 50 articles, filters for macro/geo/psychology/market
relevance, and returns structured bullet-point JSON.

Output: news_results_end.json

Run: py agents.py
Prerequisite: py aggregator.py  (produces news_results.json)
"""

import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Config ────────────────────────────────────────────────────────────────────
INPUT_FILE      = Path("news_results.json")
OUTPUT_FILE     = Path("news_results_end.json")
BATCH_SIZE      = 80        # 80 articles -> ~25 batches total; fits Groq payload limit
DEDUP_THRESHOLD = 0.72
MAX_RETRIES     = 3         # retries on 429

# Per-provider concurrency limits (semaphores cap simultaneous active calls)
# Groq free: ~30 RPM — cap at 4 concurrent
# OpenRouter free: ~20 RPM — cap at 2 concurrent
# Gemini free: ~10 RPM — cap at 2 concurrent
GROQ_CONCURRENCY       = 4
OPENROUTER_CONCURRENCY = 2
GEMINI_CONCURRENCY     = 2

# Total thread pool = sum of all slots (no idle threads piling up)
MAX_WORKERS = GROQ_CONCURRENCY + OPENROUTER_CONCURRENCY + GEMINI_CONCURRENCY  # 8

# API Keys
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ── Provider + model routing ──────────────────────────────────────────────────
# Verified working models only (April 2026 testing):
#   Groq:       llama-3.3-70b-versatile, llama-4-scout  (gpt-oss/qwen3 413 on free tier)
#   OpenRouter: gemma-3-27b-it:free, phi-4:free          (llama 429/402, deepseek 404)
#   Gemini:     gemini-2.5-flash                          (works perfectly, 1 per 10 slots)
#
# This 10-slot pattern cycles via modulo in main() to cover any number of batches.
THREAD_PROVIDERS = [
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("openrouter", "google/gemma-3-27b-it:free"),
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("gemini",     "gemini-2.5-flash"),
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
    ("openrouter", "google/gemma-3-27b-it:free"),
    ("groq",       "meta-llama/llama-4-scout-17b-16e-instruct"),
]

# ── Prompts ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a senior analyst covering global macro-economics, geopolitics, "
    "mass psychology, and financial markets. Your job is to extract signal from noise."
)

USER_PROMPT_TEMPLATE = """From the news articles below, select ONLY those relevant to:
- Macro-economics (Fed, rates, inflation, GDP, debt, trade wars, tariffs, recession)
- Geopolitics (wars, sanctions, elections, diplomacy, energy, alliances)
- Mass psychology (investor sentiment, fear/greed, social narratives, market behavior)
- Market dynamics (equities, crypto, commodities, bonds, volatility, flows)

For each relevant article output a JSON object with these exact keys:
  "title"     : original headline (string)
  "theme"     : one of ["macro", "geopolitical", "psychology", "market"] (string)
  "bullets"   : 2-3 concise bullet strings summarizing key facts and implications (array)
  "source"    : source name (string)
  "url"       : article URL (string)
  "published" : publication datetime (string)

Return ONLY a valid JSON array. No markdown fences, no explanation, no trailing text.
If zero articles qualify, return [].

Articles:
{articles}"""


# ── Format batch ──────────────────────────────────────────────────────────────
def _format_articles(articles: list[dict]) -> str:
    """Compact format — no URL in body (model doesn't need it for relevance filtering)."""
    lines = []
    for i, a in enumerate(articles, 1):
        title   = a.get("title", "").strip()[:100]
        source  = a.get("source", "").strip()
        pub     = a.get("published", "").strip()[:19]  # trim to date+time only
        summary = (a.get("summary") or a.get("content") or "").strip()
        summary = re.sub(r"<[^>]+>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()[:150]
        lines.append(f"{i}. [{source}] {title} ({pub})\n   {summary}")
    return "\n\n".join(lines)


# ── JSON parser (shared) ──────────────────────────────────────────────────────
def _parse_json(text: str, label: str) -> list[dict]:
    """Strip markdown fences, parse JSON array, validate required keys."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE).strip()
    # If multiple JSON arrays exist (model output two blocks), take only the first
    # Also recover truncated JSON by closing at last complete object
    bracket = text.find("[")
    if bracket != -1:
        # Find matching close bracket by scanning
        depth = 0
        end = -1
        for k, ch in enumerate(text[bracket:], bracket):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = k
                    break
        if end != -1:
            text = text[bracket:end + 1]
        else:
            # truncated — close at last complete object
            last_close = text.rfind("}")
            if last_close != -1:
                text = text[bracket:last_close + 1] + "]"
    try:
        data = json.loads(text)
        if not isinstance(data, list):
            print(f"  [{label}] Response not a list — skipping")
            return []
        valid = [x for x in data if all(k in x for k in ("title", "theme", "bullets", "source", "url"))]
        return valid
    except json.JSONDecodeError as e:
        print(f"  [{label}] JSON parse error: {e}")
        return []


# ── Retry helper ──────────────────────────────────────────────────────────────
def _post_with_retry(url: str, label: str, provider: str, **kwargs) -> requests.Response:
    """POST with exponential backoff on 429. Releases semaphore slot during sleep."""
    import socket
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(url, **kwargs)
        except (requests.exceptions.ConnectionError, socket.gaierror) as e:
            # DNS / connection failure — don't retry, fail fast
            raise requests.exceptions.ConnectionError(f"DNS/connection failure: {e}") from e
        if r.status_code == 429 and attempt < MAX_RETRIES - 1:
            wait = 2 ** attempt * 5  # 5s, 10s, 20s
            print(f"  [{label}] 429 rate-limit — retrying in {wait}s...")
            # Release semaphore slot during sleep so other threads can proceed
            _PROVIDER_SEMS[provider].release()
            time.sleep(wait)
            _PROVIDER_SEMS[provider].acquire()
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


# ── Provider callers ──────────────────────────────────────────────────────────
def _call_groq(model: str, prompt_user: str, label: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt_user},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }
    r = _post_with_retry(
        "https://api.groq.com/openai/v1/chat/completions",
        label, "groq", headers=headers, json=payload, timeout=(5, 30)
    )
    return _parse_json(r.json()["choices"][0]["message"]["content"], label)


def _call_gemini(model: str, prompt_user: str, label: str) -> list[dict]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": SYSTEM_PROMPT + "\n\n" + prompt_user}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 65536},
    }
    r = _post_with_retry(url, label, "gemini", json=payload, timeout=(5, 180))
    return _parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"], label)


def _call_openrouter(model: str, prompt_user: str, label: str) -> list[dict]:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/KevinDo-Tuan/BETA",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt_user},
        ],
        "temperature": 0.1,
        "max_tokens": 8192,
    }
    r = _post_with_retry(
        "https://openrouter.ai/api/v1/chat/completions",
        label, "openrouter", headers=headers, json=payload, timeout=(5, 120)
    )
    return _parse_json(r.json()["choices"][0]["message"]["content"], label)


# ── Key + caller maps ─────────────────────────────────────────────────────────
PROVIDER_KEYS = {
    "groq":       GROQ_API_KEY,
    "gemini":     GEMINI_API_KEY,
    "openrouter": OPENROUTER_API_KEY,
}

PROVIDER_CALLERS = {
    "groq":       _call_groq,
    "gemini":     _call_gemini,
    "openrouter": _call_openrouter,
}

# Per-provider semaphores — cap concurrent active calls per provider
import threading as _threading
_PROVIDER_SEMS = {
    "groq":       _threading.Semaphore(GROQ_CONCURRENCY),
    "openrouter": _threading.Semaphore(OPENROUTER_CONCURRENCY),
    "gemini":     _threading.Semaphore(GEMINI_CONCURRENCY),
}


# ── Agent runner ──────────────────────────────────────────────────────────────
def run_agent(batch: list[dict], batch_idx: int, provider: str, model: str) -> list[dict]:
    short_model = model.split("/")[-1][:22]
    label = f"Agent {batch_idx:02d} | {provider}/{short_model}"

    t0 = time.time()
    print(f"[{label}] Starting ({len(batch)} articles)...")

    if not PROVIDER_KEYS.get(provider):
        print(f"[{label}] API key missing — skipping")
        return []

    prompt_user = USER_PROMPT_TEMPLATE.format(articles=_format_articles(batch))

    with _PROVIDER_SEMS[provider]:  # blocks until a slot is free for this provider
        try:
            results = PROVIDER_CALLERS[provider](model, prompt_user, label)
            elapsed = time.time() - t0
            print(f"[{label}] Done — {len(results)} relevant | {elapsed:.1f}s")
            return results
        except Exception as e:
            elapsed = time.time() - t0
            print(f"[{label}] Error after {elapsed:.1f}s: {e}")
            return []


# ── Dedup ─────────────────────────────────────────────────────────────────────
def _norm(t: str) -> set:
    t = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", t.lower())).strip()
    return {t[i:i+3] for i in range(max(0, len(t) - 2))}


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def dedup(items: list[dict]) -> list[dict]:
    ng = [_norm(x.get("title", "")) for x in items]
    removed: set = set()
    for i in range(len(items)):
        if i in removed:
            continue
        for j in range(i + 1, len(items)):
            if j in removed:
                continue
            if _jac(ng[i], ng[j]) >= DEDUP_THRESHOLD:
                removed.add(j)
    kept = [x for i, x in enumerate(items) if i not in removed]
    print(f"[Dedup] {len(items)} -> {len(kept)} ({len(removed)} removed)")
    return kept


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not INPUT_FILE.exists():
        print(f"[Error] {INPUT_FILE} not found — run: py aggregator.py")
        sys.exit(1)

    articles = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"[agents] Loaded {len(articles)} articles from {INPUT_FILE}")

    for provider, key in PROVIDER_KEYS.items():
        if not key:
            print(f"[agents] Warning: {provider.upper()}_API_KEY not set — those threads will be skipped")

    batches     = [articles[i:i + BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    n           = len(batches)
    assignments = [THREAD_PROVIDERS[i % len(THREAD_PROVIDERS)] for i in range(n)]

    print(f"[agents] {n} batches x {BATCH_SIZE} articles -> {MAX_WORKERS} per wave")
    for i, (prov, mdl) in enumerate(assignments):
        print(f"  Batch {i+1:02d} -> {prov}/{mdl}")

    t0          = time.time()
    all_results: list[dict] = []

    # Run in waves of MAX_WORKERS. Wait 62s between waves so Groq's 1-min RPM window resets.
    WAVE_PAUSE = 62
    for wave_start in range(0, n, MAX_WORKERS):
        wave = list(range(wave_start, min(wave_start + MAX_WORKERS, n)))
        wave_num = wave_start // MAX_WORKERS + 1
        total_waves = (n + MAX_WORKERS - 1) // MAX_WORKERS
        print(f"\n[agents] Wave {wave_num}/{total_waves} — batches {wave[0]+1}-{wave[-1]+1}")

        with ThreadPoolExecutor(max_workers=len(wave)) as pool:
            futures = {
                pool.submit(run_agent, batches[i], i + 1, assignments[i][0], assignments[i][1]): i
                for i in wave
            }
            for future in as_completed(futures):
                try:
                    all_results.extend(future.result())
                except Exception as e:
                    print(f"[agents] Unhandled future error: {e}")

        if wave_start + MAX_WORKERS < n:
            print(f"[agents] Wave done — waiting {WAVE_PAUSE}s for rate limits to reset...")
            time.sleep(WAVE_PAUSE)

    elapsed = time.time() - t0
    print(f"\n[agents] All agents done in {elapsed:.1f}s — {len(all_results)} items before dedup")

    final = dedup(all_results)
    final.sort(key=lambda x: x.get("published", "") or "", reverse=True)

    OUTPUT_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[agents] Saved {len(final)} items -> {OUTPUT_FILE}")

    print("\n── First 5 results ──")
    for item in final[:5]:
        print(f"  [{item.get('theme', '?').upper()}] {item.get('title', '')[:80]}")
        for b in item.get("bullets", []):
            print(f"    • {b}")


if __name__ == "__main__":
    main()
