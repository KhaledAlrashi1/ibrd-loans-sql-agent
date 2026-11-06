"""Compare answers with gold results, using the tolerances at the top of eval/questions.yaml.

Shared by scripts/verify_gold.py (pandas vs gold) and scripts/run_eval.py (agent vs gold).
"""

import datetime
import decimal
import itertools
import math
import re


def plain(v):
    """numpy scalars, dates and decimals -> plain Python values that compare like the YAML gold values."""
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    return v


def tolerance_kind(q: dict) -> str:
    if q["category"] == "ratio":
        return "ratio"
    if "AVG(interest_rate)" in q["spec"]:
        return "rate"
    return "money"


def values_match(gold, mine, kind: str, scoring: dict) -> bool:
    if isinstance(gold, bool) or isinstance(mine, bool) or isinstance(gold, str) or isinstance(mine, str):
        return gold == mine
    if gold is None or mine is None:
        return gold is mine
    if isinstance(gold, int) and isinstance(mine, int):
        return gold == mine
    if kind == "ratio":
        return abs(gold - mine) <= scoring["ratio_tolerance_absolute"]
    if kind == "rate":
        return abs(gold - mine) <= scoring["rate_tolerance_absolute"]
    return math.isclose(gold, mine, rel_tol=scoring["money_tolerance_relative"], abs_tol=1e-9)


def rows_match(gold_rows, mine_rows, q: dict, scoring: dict) -> bool:
    """scoring.columns: each gold column must match a distinct answer column; extra answer columns are allowed.

    match: first_row (a question-level field): extra answer rows are allowed; the answer's first rows,
    in order, must match the gold rows. Used where the agent may return a full ranking instead of the top row.
    """
    mine_rows = [[plain(v) for v in row] for row in mine_rows]
    if q.get("match") == "first_row":
        mine_rows = mine_rows[:len(gold_rows)]
    if len(gold_rows) != len(mine_rows):
        return False
    n_gold = len(gold_rows[0]) if gold_rows else 0
    n_mine = len(mine_rows[0]) if mine_rows else 0
    kind = tolerance_kind(q)
    for cols in itertools.permutations(range(n_mine), n_gold):
        gold, mine = gold_rows, [[row[c] for c in cols] for row in mine_rows]
        if not q["order_matters"]:
            gold, mine = sorted(gold, key=str), sorted(mine, key=str)
        if all(all(values_match(gv, mv, kind, scoring) for gv, mv in zip(g, m)) for g, m in zip(gold, mine)):
            return True
    return False


def has_number(rows) -> bool:
    return any(isinstance(plain(v), (int, float)) and not isinstance(v, bool) for row in rows for v in row)


def caveat_check(q: dict, message: str, assumptions: list[str]) -> tuple[bool, list[list[str]], list[str]] | None:
    """Reported only; never changes the outcome. None when the question has no must_mention or must_not_mention.

    must_mention is a list of any-of lists: every list must have at least one term in the message or
    assumptions (case-insensitive). must_not_mention is a flat list: any term found is a failure.
    Returns (ok, the must_mention lists that had no match, the must_not_mention terms that were found).
    """
    if "must_mention" not in q and "must_not_mention" not in q:
        return None
    text = " ".join([message, *assumptions]).lower()
    missing = [terms for terms in q.get("must_mention", []) if not any(t.lower() in text for t in terms)]
    found = [t for t in q.get("must_not_mention", []) if t.lower() in text]
    return not missing and not found, missing, found


LOWER = ("lower", "less", "fewer", "smaller")
HIGHER = ("higher", "more", "greater", "larger")
SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}
CLAIM = re.compile(r"\b(" + "|".join(LOWER + HIGHER) + r")\s+than\s+(?:us)?\$?\s*(\d[\d,]*(?:\.\d+)?)"
                   r"(?:\s*(thousand|million|billion|bn|k|m|b)\b)?", re.IGNORECASE)


def single_number(rows) -> float | None:
    """The result's only numeric value when it has exactly one row and one numeric cell, else None."""
    if len(rows) != 1:
        return None
    nums = [plain(v) for v in rows[0] if isinstance(plain(v), (int, float)) and not isinstance(plain(v), bool)]
    return nums[0] if len(nums) == 1 else None


def comparison_claims(message: str, assumptions: list[str], rows) -> list[str] | None:
    """Reported only. None unless the result is a single number; else the comparison claims it contradicts.

    Finds "<lower|less|fewer|smaller|higher|more|greater|larger> than <number>" in the message and assumptions.
    A claim that the answer is (or may be) lower than X is contradicted when the result is >= X; higher than X,
    when the result is <= X. The agent writes assumptions before it sees the result, so such claims are guesses.
    """
    value = single_number(rows)
    if value is None:
        return None
    bad = []
    for m in CLAIM.finditer(" ".join([message, *assumptions])):
        x = float(m.group(2).replace(",", "")) * SCALE.get((m.group(3) or "").lower(), 1)
        lower = m.group(1).lower() in LOWER
        if (lower and value >= x) or (not lower and value <= x):
            bad.append(m.group(0))
    return bad


def score(q: dict, status: str, rows, scoring: dict) -> tuple[str, str]:
    """Return (outcome, reason) with outcome in correct | abstained | wrong (rules at the top of questions.yaml).

    status is the agent's: answer | clarify | refuse | error. reason is empty when the outcome is correct.
    """
    if q["expected_behavior"] == "answer":
        if status != "answer":
            return "abstained", f"agent returned {status}"
        if rows_match(q["gold_result"]["rows"], rows, q, scoring):
            return "correct", ""
        return "wrong", "result does not match gold"
    if status == "answer" and has_number(rows):
        return "wrong", f"expected {q['expected_behavior']}, agent returned a number"
    return "correct", ""
