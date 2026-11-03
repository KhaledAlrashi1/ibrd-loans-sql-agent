"""Plain-English labels for result columns, shown as table headers, chart captions, axis titles and tooltips.

  1. A dictionary column uses its official original name in sentence case, with "(US$)" -> "(USD)" and
     " - " -> " ": borrowers_obligation_usd -> "Borrower's obligation (USD)",
     board_approval_fy -> "Board approval fiscal year". All-caps words (IBRD, ID) keep their case.
  2. Any other name (a SQL alias) is split on "_": a trailing "usd" -> "(USD)", a trailing "share" -> "(%)",
     "fy" -> "fiscal year", "cy" -> "calendar year", "avg" -> "average"; the first letter is capitalised:
     total_owed_usd -> "Total owed (USD)", loan_count -> "Loan count".
  3. A repeated name numbered by display.unique_names ("x (2)") keeps its number: "X (2)".
"""

import re
from functools import cache
from pathlib import Path

import yaml

from src.agent import config

WORDS = {"fy": "fiscal year", "cy": "calendar year", "avg": "average"}
SUFFIXES = {"usd": "(USD)", "share": "(%)"}
REPEAT = re.compile(r"^(.*) \((\d+)\)$")


def sentence_case(name: str) -> str:
    words = name.replace(" - ", " ").replace("(US$)", "(USD)").split(" ")
    return " ".join([words[0]] + [lower_if_capitalised(w) for w in words[1:]])


def lower_if_capitalised(word: str) -> str:
    """"Obligation" -> "obligation", "(Most" -> "(most"; "IBRD", "ID" and "3rd" are unchanged."""
    letters = word.lstrip("(")
    return word.lower() if letters[:1].isupper() and letters[1:].islower() else word


@cache
def dictionary_labels(dictionary_path: Path = config.DICTIONARY_PATH) -> dict[str, str]:
    columns = yaml.safe_load(Path(dictionary_path).read_text())["columns"]
    return {c["column"]: sentence_case(c["original_name"]) for c in columns if c.get("original_name")}


def alias_label(name: str) -> str:
    parts = [p for p in name.lower().split("_") if p]
    if not parts:
        return name
    suffix = SUFFIXES.get(parts[-1]) if len(parts) > 1 else None
    if suffix:
        parts = parts[:-1]
    words = [WORDS.get(p, p) for p in parts] + ([suffix] if suffix else [])
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def column_label(name: str) -> str:
    repeat = REPEAT.match(name)
    if repeat:
        return f"{column_label(repeat.group(1))} ({repeat.group(2)})"
    return dictionary_labels().get(name.lower()) or alias_label(name)
