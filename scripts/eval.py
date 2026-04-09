"""Eval-driven harness for the P-line classifier.

Philosophy: ground_truth.jsonl is the spec. We run the live API over every
row, score with two layers (deterministic exact-match + RAGAS AspectCritic
on reasoning quality), print a confusion matrix, and exit non-zero if we
fall below the accuracy threshold. This is the inner loop for prompt work.

Run AGAINST a running API:

    docker compose up -d
    python scripts/eval.py                    # default: localhost:8000
    python scripts/eval.py --threshold 0.7
    python scripts/eval.py --no-ragas         # skip the LLM-graded layer
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

DEFAULT_GT = REPO_ROOT / "data" / "ground_truth.jsonl"
BUCKETS = ["likely_owned", "likely_available", "unclear"]


def load_ground_truth(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def classify_via_api(base_url: str, isrc: str) -> dict:
    r = httpx.post(f"{base_url}/tracks/{isrc}/classify", timeout=60)
    r.raise_for_status()
    return r.json()


def confusion_matrix(rows: list[dict]) -> dict:
    matrix = {a: Counter() for a in BUCKETS}
    for row in rows:
        matrix[row["expected"]][row["got"]] += 1
    return matrix


def print_matrix(matrix: dict) -> None:
    print("\nConfusion matrix (rows = expected, cols = predicted):")
    header = f"{'':22}" + "".join(f"{b:20}" for b in BUCKETS)
    print(header)
    for expected in BUCKETS:
        line = f"{expected:22}" + "".join(f"{matrix[expected][p]:<20}" for p in BUCKETS)
        print(line)


def run_ragas(rows: list[dict]) -> float | None:
    """Optional RAGAS layer: AspectCritic graded by an LLM judge.

    Scores whether the model's `reasoning` justifies the `expected_bucket`
    using the same evidence. This catches 'right answer, wrong reason'
    failures that exact-match misses.
    """
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import AspectCritic
    except ImportError:
        print("\n[ragas] Not installed — skipping. Install with: pip install ragas datasets")
        return None

    ds = Dataset.from_list(
        [
            {
                "user_input": f"Classify ownership for ISRC {r['isrc']}",
                "response": json.dumps(
                    {"bucket": r["got"], "reasoning": r["reasoning"]}
                ),
                "retrieved_contexts": [json.dumps(r["evidence"])],
                "reference": r["expected"],
            }
            for r in rows
        ]
    )

    critic = AspectCritic(
        name="bucket_reasoning_quality",
        definition=(
            "Return 1 if the response.bucket equals the reference AND the "
            "response.reasoning correctly identifies the controlling entities "
            "(label / owner / distributor) from retrieved_contexts and applies "
            "the right rule (major-owned vs artist-services exception vs "
            "middle-tier ambiguity vs pure indie). Return 0 otherwise."
        ),
    )

    print("\n[ragas] Running AspectCritic...")
    result = evaluate(ds, metrics=[critic])
    score = float(result["bucket_reasoning_quality"])
    print(f"[ragas] bucket_reasoning_quality = {score:.3f}")
    return score


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT_GT), help="Ground truth jsonl path")
    parser.add_argument("--base-url", default=os.getenv("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--no-ragas", action="store_true")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    gt = load_ground_truth(Path(args.file))
    rows: list[dict] = []
    print(f"Running {len(gt)} examples from {args.file} against {args.base_url}\n")

    for entry in gt:
        try:
            result = classify_via_api(args.base_url, entry["isrc"])
            rows.append(
                {
                    "isrc": entry["isrc"],
                    "expected": entry["expected_bucket"],
                    "got": result["bucket"],
                    "confidence": result.get("confidence", 0.0),
                    "reasoning": result.get("reasoning", ""),
                    "evidence": result.get("evidence", {}),
                    "model": result.get("model", ""),
                    "correct": result["bucket"] == entry["expected_bucket"],
                }
            )
        except Exception as e:
            print(f"  ERROR  {entry['isrc']}: {e}")
            rows.append(
                {
                    "isrc": entry["isrc"],
                    "expected": entry["expected_bucket"],
                    "got": "ERROR",
                    "confidence": 0.0,
                    "reasoning": str(e),
                    "evidence": {},
                    "model": "",
                    "correct": False,
                }
            )

    correct = sum(1 for r in rows if r["correct"])
    accuracy = correct / len(rows) if rows else 0.0

    print(f"{'ISRC':16} {'expected':18} {'got':18} {'conf':6} ok  reasoning")
    print("-" * 110)
    for r in rows:
        mark = "✓" if r["correct"] else "✗"
        print(
            f"{r['isrc']:16} {r['expected']:18} {r['got']:18} {r['confidence']:<6.2f} {mark}   "
            f"{r['reasoning'][:60]}"
        )

    print(f"\nAccuracy: {correct}/{len(rows)} = {accuracy:.1%}")
    print_matrix(confusion_matrix([r for r in rows if r["got"] != "ERROR"]))

    misses = [r for r in rows if not r["correct"]]
    if misses:
        print("\nMisses (full evidence + reasoning):")
        for r in misses:
            print(f"\n  {r['isrc']}  expected={r['expected']}  got={r['got']}")
            print(f"    evidence: {json.dumps(r['evidence'])}")
            print(f"    reasoning: {r['reasoning']}")

    ragas_score = None
    if not args.no_ragas:
        ragas_score = run_ragas([r for r in rows if r["got"] != "ERROR"])

    if args.json:
        print(json.dumps(
            {"accuracy": accuracy, "ragas_score": ragas_score, "rows": rows},
            indent=2,
        ))

    if accuracy < args.threshold:
        print(f"\nFAIL: accuracy {accuracy:.1%} below threshold {args.threshold:.1%}")
        return 1
    print(f"\nPASS: accuracy {accuracy:.1%} >= threshold {args.threshold:.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
