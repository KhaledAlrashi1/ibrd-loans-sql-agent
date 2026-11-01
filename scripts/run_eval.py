"""Score the agent against eval/questions.yaml and save the run to eval/results/<timestamp>_<split>.json.

    python scripts/run_eval.py                                    # dev split (default)
    python scripts/run_eval.py --split heldout --confirm-heldout  # checkpoints only, when Khaled asks

Outcomes per question: correct | abstained | wrong (rules at the top of questions.yaml).
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent import config  # noqa: E402
from src.agent.agent import answer  # noqa: E402
from src.agent.scoring import plain, score  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.yaml"
RESULTS_DIR = ROOT / "eval" / "results"
OUTCOMES = ("correct", "abstained", "wrong")


def cost_usd(tokens: Counter) -> float:
    p = config.PRICE_PER_MTOK
    return (tokens["input_tokens"] * p["input"] + tokens["output_tokens"] * p["output"]
            + tokens["cache_read_input_tokens"] * p["cache_read"]
            + tokens["cache_creation_input_tokens"] * p["cache_write"]) / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "heldout"], default="dev")
    parser.add_argument("--confirm-heldout", action="store_true", help="required to run the heldout split")
    args = parser.parse_args()
    if args.split == "heldout" and not args.confirm_heldout:
        parser.error("the heldout split is scored only at checkpoints: add --confirm-heldout to run it")

    spec = yaml.safe_load(QUESTIONS.read_text())
    questions = [q for q in spec["questions"] if q["split"] == args.split]
    started = datetime.now()

    records, tokens = [], Counter()
    print(f"{'id':4} {'outcome':9} {'status':7} {'tries':5} {'secs':>5}  reason")
    for q in questions:
        r = answer(q["question"])
        outcome, reason = score(q, r.status, r.rows, spec["scoring"])
        usage = {k: getattr(r, k) for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        tokens.update(usage)
        if r.status == "error":
            reason = f"{reason}: {r.message}" if reason else r.message
        records.append({
            "id": q["id"], "category": q["category"], "question": q["question"],
            "expected_behavior": q["expected_behavior"], "outcome": outcome, "reason": reason,
            "status": r.status, "sql": r.sql, "assumptions": r.assumptions, "message": r.message,
            "result": {"columns": r.columns, "rows": [[plain(v) for v in row] for row in r.rows],
                       "truncated": r.truncated},
            "attempts": r.attempts, "latency_s": r.latency_s, "tokens": usage,
        })
        print(f"{q['id']:4} {outcome:9} {r.status:7} {r.attempts:5} {r.latency_s:5.1f}  {reason}", flush=True)

    totals = Counter(rec["outcome"] for rec in records)
    by_category = defaultdict(Counter)
    for rec in records:
        by_category[rec["category"]][rec["outcome"]] += 1
    summary = {
        "outcomes": {o: totals[o] for o in OUTCOMES},
        "by_category": {c: {o: n[o] for o in OUTCOMES} for c, n in sorted(by_category.items())},
        "tokens": dict(tokens),
        "estimated_cost_usd": round(cost_usd(tokens), 4),
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{started:%Y%m%d-%H%M%S}_{args.split}.json"
    out.write_text(json.dumps({
        "run_at": started.isoformat(timespec="seconds"), "split": args.split,
        "model": config.MODEL, "effort": config.EFFORT, "summary": summary, "results": records,
    }, indent=2, default=str) + "\n")

    n = len(records)
    print(f"\n{args.split}: {totals['correct']}/{n} correct, {totals['abstained']} abstained, {totals['wrong']} wrong")
    print(f"\n{'category':10} {'correct':>7} {'abstained':>9} {'wrong':>5}")
    for cat, c in summary["by_category"].items():
        print(f"{cat:10} {c['correct']:7} {c['abstained']:9} {c['wrong']:5}")
    print(f"\ntokens: input {tokens['input_tokens']:,}, output {tokens['output_tokens']:,}, "
          f"cache read {tokens['cache_read_input_tokens']:,}, cache write {tokens['cache_creation_input_tokens']:,}")
    print(f"estimated cost: ${summary['estimated_cost_usd']:.2f} ({config.MODEL}, prices in config.py)")
    print(f"saved: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
