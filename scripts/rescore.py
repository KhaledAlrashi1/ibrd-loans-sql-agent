"""Re-score saved eval runs against the current eval/questions.yaml. No model calls; result files are only read.

    uv run python scripts/rescore.py eval/results/20261101-173532_dev.json [more files...]

Uses the same scoring code as run_eval.py (src/agent/scoring.py). For each file, prints the outcomes
as saved and as re-scored, the caveat check before and after, and every question whose outcome changed.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.scoring import caveat_check, score  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.yaml"
OUTCOMES = ("correct", "abstained", "wrong")


def rescore_run(run: dict, spec: dict) -> dict:
    """Return {"saved", "now", "caveats_saved", "caveats_now", "changed", "warnings"} for one saved run."""
    questions = {q["id"]: q for q in spec["questions"]}
    saved, now = Counter(), Counter()
    caveats_saved, caveats_now = Counter(), Counter()
    changed, warnings = [], []
    for rec in run["results"]:
        q = questions.get(rec["id"])
        if q is None:
            warnings.append(f"{rec['id']}: not in questions.yaml, skipped")
            continue
        if q["question"] != rec["question"]:
            warnings.append(f"{rec['id']}: question text changed since this run")
        outcome, _ = score(q, rec["status"], rec["result"]["rows"], spec["scoring"])
        saved[rec["outcome"]] += 1
        now[outcome] += 1
        if outcome != rec["outcome"]:
            changed.append(f"{rec['id']}: {rec['outcome']} -> {outcome}")

        if rec["caveat"] is not None:
            caveats_saved["checked"] += 1
            caveats_saved["passed"] += rec["caveat"]["ok"]
        caveat = caveat_check(q, rec["message"], rec["assumptions"]) if rec["status"] == "answer" else None
        if caveat is not None:
            caveats_now["checked"] += 1
            caveats_now["passed"] += caveat[0]
    return {"saved": saved, "now": now, "caveats_saved": caveats_saved, "caveats_now": caveats_now,
            "changed": changed, "warnings": warnings}


def fmt(outcomes: Counter) -> str:
    return " / ".join(str(outcomes[o]) for o in OUTCOMES)


def fmt_caveats(c: Counter) -> str:
    return f"{c['passed']}/{c['checked']}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", nargs="+", type=Path, help="eval/results/<timestamp>_<split>.json files")
    args = parser.parse_args()

    spec = yaml.safe_load(QUESTIONS.read_text())
    print(f"{'file':34} {'saved (c/a/w)':>14} {'now (c/a/w)':>12} {'caveats':>14}")
    for path in args.results:
        r = rescore_run(json.loads(path.read_text()), spec)
        caveats = f"{fmt_caveats(r['caveats_saved'])} -> {fmt_caveats(r['caveats_now'])}"
        print(f"{path.name:34} {fmt(r['saved']):>14} {fmt(r['now']):>12} {caveats:>14}")
        for line in r["changed"] + r["warnings"]:
            print(f"    {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
