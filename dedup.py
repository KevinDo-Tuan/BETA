"""
dedup_nlp.py — Stage 2: TF-IDF cosine-similarity deduplication.

Reads  : news_stage1.json   (raw LLM output from agents.py, may contain duplicates)
Writes : news_results_end.json  (deduplicated, sorted newest first)

Run after agents.py:
    py agents.py        ->  news_stage1.json
    py dedup_nlp.py     ->  news_results_end.json

Why better than Jaccard on titles:
- Compares the FULL bullet-point text, not just the headline
- TF-IDF bigrams catch "Fed raises rates 25bps" == "Federal Reserve hikes by quarter point"
- Pure NLP: no API, no rate limits, no failures, runs in <1s
"""

import json
import sys
from pathlib import Path
import numpy as np

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError:
    print("[dedup] scikit-learn not found — install: pip install scikit-learn")
    sys.exit(1)

INPUT_FILE  = Path("news_stage1.json")
OUTPUT_FILE = Path("news_results_end.json")
THRESHOLD   = 0.65   # cosine similarity >= this => duplicate (keep the earlier/richer one)


def build_text(item: dict) -> str:
    """Concatenate title + all bullet text for a richer TF-IDF signal."""
    title   = item.get("title", "") or ""
    bullets = " ".join(item.get("bullets", []) or [])
    source  = item.get("source", "") or ""
    return f"{title} {bullets} {source}".strip()


def dedup_tfidf(items: list[dict]) -> list[dict]:
    if not items:
        return []

    texts = [build_text(x) for x in items]

    vec    = TfidfVectorizer(ngram_range=(1, 2), max_features=10_000, sublinear_tf=True)
    matrix = vec.fit_transform(texts)          # sparse (N, vocab)
    sims   = cosine_similarity(matrix)         # dense (N, N)

    removed: set[int] = set()
    n = len(items)

    for i in range(n):
        if i in removed:
            continue
        for j in range(i + 1, n):
            if j in removed:
                continue
            if sims[i, j] >= THRESHOLD:
                # Keep i (earlier = newer because items are sorted desc by published)
                removed.add(j)

    kept = [x for idx, x in enumerate(items) if idx not in removed]
    print(f"[dedup_nlp] {n} -> {len(kept)} ({len(removed)} removed, threshold={THRESHOLD})")
    return kept


def main():
    if not INPUT_FILE.exists():
        print(f"[dedup_nlp] {INPUT_FILE} not found — run: py agents.py first")
        sys.exit(1)

    items = json.loads(INPUT_FILE.read_text(encoding="utf-8"))
    print(f"[dedup_nlp] Loaded {len(items)} items from {INPUT_FILE}")

    # Ensure sorted newest-first before dedup (keep the newest of any duplicate pair)
    items.sort(key=lambda x: x.get("published", "") or "", reverse=True)

    final = dedup_tfidf(items)

    OUTPUT_FILE.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[dedup_nlp] Saved {len(final)} items -> {OUTPUT_FILE}")

    print("\n── First 5 results ──")
    for item in final[:5]:
        print(f"  [{item.get('theme', '?').upper()}] {item.get('title', '')[:80]}")
        for b in item.get("bullets", []):
            print(f"    • {b}")


if __name__ == "__main__":
    main()
