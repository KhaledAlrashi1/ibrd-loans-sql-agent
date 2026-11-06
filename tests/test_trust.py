"""web/src/data/trust.json (the page's "Why you can trust the answers" numbers) checked against the repo.

The page builds its sentences from trust.json only (web/src/components/Trust.tsx; the smoke test checks that
every number on the section comes from this file), so these tests cover every number it shows.
Heldout numbers are checked against RESULTS.md and the README only: the heldout result file is not read.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

from src.agent import config

ROOT = config.ROOT
TRUST = ROOT / "web" / "src" / "data" / "trust.json"
RESULTS_MD = ROOT / "eval" / "RESULTS.md"


@pytest.fixture(scope="module")
def trust() -> dict:
    return json.loads(TRUST.read_text())


def results_rows(file_name: str) -> list[list[str]]:
    """Cells of every RESULTS.md table row that names this run file, with bold markers removed."""
    rows = []
    for line in RESULTS_MD.read_text().splitlines():
        if line.startswith("|") and f"results/{file_name}" in line:
            rows.append([c.strip().replace("**", "") for c in line.strip("|").split("|")])
    return rows


def test_linked_files_exist(trust):
    for rel in (trust["dev"]["run_file"], trust["results_doc"], trust["security_doc"], trust["clarify_case"]["file"]):
        assert (ROOT / rel).is_file(), rel


def test_dev_numbers_match_the_latest_dev_run(trust):
    run = ROOT / trust["dev"]["run_file"]
    latest = sorted((ROOT / "eval" / "results").glob("*_dev.json"))[-1]
    assert run == latest, "a newer dev run exists: update trust.json (and RESULTS.md) first"

    outcomes = json.loads(run.read_text())["summary"]["outcomes"]
    assert outcomes["correct"] == trust["dev"]["correct"]
    assert sum(outcomes.values()) == trust["dev"]["questions"]

    rows = results_rows(run.name)
    assert rows, "the run file must be reported in RESULTS.md"
    correct, abstained, wrong = rows[0][2:5]  # | Run | File | Correct | Abstained | Wrong | ...
    assert int(correct) == trust["dev"]["correct"]
    assert int(correct) + int(abstained) + int(wrong) == trust["dev"]["questions"]


def test_heldout_numbers_match_results_md_as_first_scored(trust):
    rows = [r for r in results_rows("20261101-173903_heldout.json") if r[0] == "heldout"]
    correct, abstained, wrong = rows[0][2:5]  # "Runs as first scored", the first heldout row in the file
    assert int(correct) == trust["heldout"]["correct_first_scored"]
    assert int(correct) + int(abstained) + int(wrong) == trust["heldout"]["questions"]
    assert "the heldout score was **9/10 as first scored**" in RESULTS_MD.read_text()
    assert "**9/10** as first scored" in (ROOT / "README.md").read_text()


def test_heldout_size_matches_the_eval_file(trust):
    questions = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text())["questions"]
    assert sum(q["split"] == "heldout" for q in questions) == trust["heldout"]["questions"]
    assert sum(q["split"] == "dev" for q in questions) == trust["dev"]["questions"]


def test_limits_match_config(trust):
    assert trust["row_limit"] == config.ROW_LIMIT
    assert trust["timeout_s"] == config.TIMEOUT_S


def test_clarify_link_points_at_a_clarify_case(trust):
    case = trust["clarify_case"]
    lines = (ROOT / case["file"]).read_text().splitlines()[case["first_line"] - 1:case["last_line"]]
    assert re.fullmatch(rf"\s*- id: {case['id']}", lines[0])
    assert any(re.fullmatch(r"\s*expected_behavior: clarify", ln) for ln in lines)
    assert lines[-1].strip() == "gold_result: null"
