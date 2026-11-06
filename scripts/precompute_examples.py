"""Run the real agent once on the app's example questions and save the answers for the v2 page.

    python scripts/precompute_examples.py                     # all examples -> web/src/data/examples.json
    python scripts/precompute_examples.py --replace 4 "What is the average interest rate on IBRD loans?"

The output is committed as-is and shown as "Cached example": never hand-edit it and never re-run a question
to get a nicer answer (Khaled, Nov 3). --replace swaps exactly one example (1-based) and keeps the others.
The questions come from EXAMPLES in app.py, read without importing Streamlit.
"""

import argparse
import ast
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_db import ensure_database  # noqa: E402
from src.agent import agent, config  # noqa: E402
from src.ui import service  # noqa: E402

from server import contract  # noqa: E402

OUT = ROOT / "web" / "src" / "data" / "examples.json"


def app_examples() -> list[str]:
    tree = ast.parse((ROOT / "app.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "EXAMPLES" for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("EXAMPLES not found in app.py")


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def run(question: str) -> dict:
    result = agent.answer(question)
    payload = contract.respond(contract.build_payload(result), "example", round(result.latency_s * 1000))
    print(f"\n[{payload['status']}] {question}\n  {payload['summary']}")
    for row in payload["display_rows"][:3]:
        print("   ", row)
    for a in payload["assumptions"]:
        print("  -", a)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", nargs=2, metavar=("N", "QUESTION"), help="replace example N (1-based) only")
    args = parser.parse_args()
    ensure_database()

    if args.replace:
        data = json.loads(OUT.read_text())
        n, question = int(args.replace[0]), args.replace[1]
        if data["cache_version"] != contract.cache_version():
            raise SystemExit("examples.json is from another prompt version; regenerate all examples instead")
        data["examples"][n - 1] = run(question)
        data["replaced"] = {"example": n, "question": question, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            "git_commit": git_commit()}
    else:
        info = service.dataset_info()
        rows = yaml.safe_load(config.DICTIONARY_PATH.read_text())["dataset"]["rows"]
        data = {
            "computed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "git_commit": git_commit(),
            "model": config.MODEL,
            "effort": config.EFFORT,
            "cache_version": contract.cache_version(),
            "dataset": {"name": info.name, "id": info.id, "source_url": info.source_url,
                        "end_of_period": info.end_of_period.isoformat(), "rows": rows},
            "examples": [run(q) for q in app_examples()],
        }
    failed = [e["question"] for e in data["examples"] if e["status"] != "answer"]
    if failed:
        raise SystemExit(f"not saved: an example did not return an answer: {failed}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    print(f"\nOK: wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
