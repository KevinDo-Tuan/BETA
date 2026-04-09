"""
run.py — Run the full News Intelligence pipeline in one command.

Usage:
    py run.py              # full pipeline: fetch → analyze → dedup → visualize
    py run.py --skip-fetch # skip aggregator (reuse existing news_results.json)
    py run.py --only-map   # skip directly to the mindmap (reuse existing data)
"""

import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).parent
PY   = sys.executable   # same Python that is running this script


def run_step(label: str, script: str, *args) -> bool:
    """Run a script and return True on success, False on failure."""
    cmd = [PY, str(BASE / script), *args]
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    t0 = time.time()
    result = subprocess.run(cmd, cwd=str(BASE))
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"\n[run] ERROR: {script} failed (exit {result.returncode})")
        return False
    print(f"\n[run] {script} done in {elapsed:.1f}s")
    return True


def main():
    args = sys.argv[1:]
    skip_fetch = "--skip-fetch" in args
    only_map   = "--only-map"   in args

    if only_map:
        # Jump straight to the mindmap server
        run_step("STEP 4 — Mindmap  (http://localhost:8765)", "mindmap.py")
        return

    steps_ok = True

    if not skip_fetch:
        steps_ok = run_step("STEP 1 — Aggregator  (fetching 57+ prestigious and well-known sources, 2000+ news ~2-5 min)", "aggregator.py")
        if not steps_ok:
            print("[run] Aggregator failed — aborting.")
            sys.exit(1)
    else:
        print("\n[run] --skip-fetch: reusing existing news_results.json")

    steps_ok = run_step("STEP 2 — LLM Analysis  (parallel agents, ~5-20 min)", "summary.py")
    if not steps_ok:
        print("[run] LLM analysis failed — continuing to dedup with whatever was collected...")

    steps_ok = run_step("STEP 3 — Deduplication  (TF-IDF cosine, <1s)", "dedup.py")
    if not steps_ok:
        print("[run] Dedup failed — check that news_stage1.json exists.")
        sys.exit(1)

    run_step("STEP 4 — Mindmap  (opening http://localhost:8765)", "mindmap.py")


if __name__ == "__main__":
    main()
