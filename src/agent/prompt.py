"""Build the system prompt and the response tool from data_dictionary.yaml.

The prompt is deterministic (no dates, no random order) so the API can cache it.
None of the worked examples is a question from eval/questions.yaml or a paraphrase of one.
"""

import json
from functools import cache
from pathlib import Path

import yaml

from src.agent import config

TOOL_NAME = "submit_response"

RESPONSE_TOOL = {
    "name": TOOL_NAME,
    "description": (
        "Submit your response to the user's question. Call this exactly once per turn. "
        "status=answer: sql holds one DuckDB SELECT on ibrd_loans. "
        "status=clarify: message holds one clarifying question; sql is empty. "
        "status=refuse: message says why the question cannot be answered from this dataset; sql is empty."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["answer", "clarify", "refuse"]},
            "sql": {"type": "string", "description": "One DuckDB SELECT statement, or an empty string."},
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Every default or interpretation the SQL relies on, in plain English.",
            },
            "message": {
                "type": "string",
                "description": "answer: one short sentence on what the result shows. "
                "clarify: the clarifying question. refuse: the reason.",
            },
        },
        "required": ["status", "sql", "assumptions", "message"],
        "additionalProperties": False,
    },
}

INSTRUCTIONS = f"""\
You answer questions about IBRD loans by writing one DuckDB SQL query against a single table, {config.TABLE}.
Your SQL is checked and run by the application, and the user sees the result table, your SQL and your assumptions.
Correct answers matter more than anything else: saying you are not sure is better than returning a wrong number.

Always respond by calling the {TOOL_NAME} tool exactly once. Do not answer in plain text.

# How to decide the status

Use status "answer" only when the question can be answered from this table with the rules below.

Do not write SQL. Use status "clarify" (ask one short question) only when two readings are about equally
likely AND would give materially different answers, or when the dictionary says to ask (e.g. 'active').
Otherwise use the dominant reading and state it as an assumption.
Default: "most/largest/biggest <money term> loans" (undisbursed, cancelled, disbursed, owed, approved) ranks by
total amount, not number of loans.

Do not write SQL. Use status "refuse" (say why, and say what this dataset can answer instead) when:
- the data needed is not in this table. It covers IBRD loans and guarantees only: no other World Bank Group
  institution or other lender, no economic indicators (GDP, population), no sectors or project results,
  nothing after the snapshot date ({{end_of_period}});
- the question asks for a forecast or prediction;
- the question asks to change data (insert, update, delete, create, drop, or anything other than reading).

# SQL rules

- Exactly one SELECT statement (CTEs, subqueries, UNION and window functions are fine). Only the table {config.TABLE}.
- Use the exact strings from the allowed values below. Map common names to them (for example a user's
  "Ivory Coast" is 'Cote d'Ivoire').
- Return raw, unrounded values in the units stored. No ROUND, no division into millions or billions, no
  formatting or casting numbers to text. The UI formats numbers.
- Return shares and ratios as fractions between 0 and 1. The UI formats percentages.
- Use stored amount columns directly; never derive an amount by adding or subtracting other amount columns.
- For "top N" questions, ORDER BY the measure DESC and LIMIT N; include the name and the measure as columns.
- Give result columns short snake_case aliases.

# Defaults (apply unless the question says otherwise, and list each one you used in assumptions)

- Loans exclude guarantees: is_guarantee = FALSE. Questions about guarantees use is_guarantee = TRUE.
- Country rankings and country-by-country comparisons exclude regional entries: is_regional_entry = FALSE.
  Overall totals and counts do not exclude them.
- "Year" means the World Bank fiscal year, board_approval_fy (Jul-Jun; FY2024 = Jul 2023-Jun 2024).
  Use board_approval_cy only when the question says calendar year.
- Amounts are US$ at historical exchange rates (undisbursed_amount_usd: End of Period rates).
- State every assumption: which amount column you used and why, guarantees excluded, regional entries
  excluded, fiscal year, name mappings, exclusions of zero or NULL values, partial periods.
- Assumptions describe what the SQL does. Don't predict how the result compares to a number:
  you write them before you see the result.
"""

EXAMPLES = [
    {
        "question": "How much has been disbursed to Vietnam so far, and how much of it has been repaid?",
        "response": {
            "status": "answer",
            "sql": (
                "SELECT SUM(disbursed_amount_usd) AS disbursed_usd, SUM(repaid_to_ibrd_usd) AS repaid_to_ibrd_usd\n"
                "FROM ibrd_loans\n"
                "WHERE country = 'Viet Nam' AND is_guarantee = FALSE"
            ),
            "assumptions": [
                "Vietnam is listed as 'Viet Nam'.",
                "Guarantees excluded (is_guarantee = FALSE).",
                "Disbursed = disbursed_amount_usd; repaid = repaid_to_ibrd_usd (principal repaid to IBRD).",
                "US$ at historical exchange rates.",
            ],
            "message": "Total disbursed and total principal repaid to IBRD on loans to Viet Nam.",
        },
    },
    {
        "question": "List the IBRD loans approved for Chile in calendar year 2005 with their projects.",
        "response": {
            "status": "answer",
            "sql": (
                "SELECT loan_number, project_id, project_name, board_approval_date, original_principal_amount_usd\n"
                "FROM ibrd_loans\n"
                "WHERE country = 'Chile' AND board_approval_cy = 2005 AND is_guarantee = FALSE\n"
                "ORDER BY board_approval_date, loan_number"
            ),
            "assumptions": [
                "Calendar year 2005 as asked (board_approval_cy), not fiscal year.",
                "Guarantees excluded (is_guarantee = FALSE).",
                "Loan amount = original_principal_amount_usd (amount approved).",
            ],
            "message": "Loans to Chile approved in calendar year 2005, with project and approved amount.",
        },
    },
    {
        "question": "Who is the biggest borrower in Asia?",
        "response": {
            "status": "clarify",
            "sql": "",
            "assumptions": [],
            "message": (
                "Asia is not one region in this data: it spans EAST ASIA AND PACIFIC, SOUTH ASIA and parts of other "
                "regions. Which region(s) do you mean, and should 'biggest' be by total amount approved or by "
                "amount still owed?"
            ),
        },
    },
    {
        "question": "How does Ghana's IBRD debt compare with its GDP?",
        "response": {
            "status": "refuse",
            "sql": "",
            "assumptions": [],
            "message": (
                "GDP is not in this dataset, which only covers IBRD loans and guarantees. "
                "I can show how much Ghana owes the IBRD (borrowers_obligation_usd) on its own."
            ),
        },
    },
]


def render_allowed_value(v) -> str:
    if isinstance(v, dict):
        extra = ", ".join(f"{k}: {val}" for k, val in v.items() if k != "value")
        return f"{v['value']} ({extra})"
    return json.dumps(v) if isinstance(v, bool) else str(v)


def render_column(c: dict) -> str:
    lines = [f"## {c['column']} ({c['type']})", f"Description: {c['description']}"]
    if c.get("original_name"):
        lines.append(f"Original name: {c['original_name']}")
    lines.append(f"NULL rows: {c['nulls']}")
    if "allowed_values" in c:
        values = c["allowed_values"]
        lines.append("Allowed values (exact): " + ("none (always NULL)" if not values else
                                                    "; ".join(render_allowed_value(v) for v in values)))
    if c.get("example_values"):
        lines.append("Example values: " + ", ".join(str(v) for v in c["example_values"]))
    if c.get("data_check"):
        lines.append(f"Data check: {c['data_check']}")
    for quirk in c.get("known_quirks", []):
        lines.append(f"- {quirk}")
    return "\n".join(lines)


def render_example(ex: dict) -> str:
    """Plain labelled fields, not JSON text: JSON-encoded examples ending in `."` made the model
    occasionally copy the closing quote into its own message (seen on D15, about 1 in 40 calls)."""
    r = ex["response"]
    sql = "\n".join("    " + line for line in r["sql"].splitlines()) if r["sql"] else "    (empty)"
    assumptions = "\n".join(f"    - {a}" for a in r["assumptions"]) or "    (none)"
    return (f"User: {ex['question']}\n{TOOL_NAME} fields:\n  status: {r['status']}\n  sql:\n{sql}\n"
            f"  assumptions:\n{assumptions}\n  message: {r['message']}")


@cache
def build_system_prompt(dictionary_path: Path = config.DICTIONARY_PATH) -> str:
    d = yaml.safe_load(Path(dictionary_path).read_text())
    ds = d["dataset"]
    sections = [
        INSTRUCTIONS.replace("{end_of_period}", ds["end_of_period"]),
        "# Dataset\n"
        f"{ds['name']} ({ds['id']}). Snapshot: End of Period {ds['end_of_period']}, {ds['rows']} rows, "
        f"one row per loan_number. License: {ds['license']}.\n"
        f"Official description: {ds['description']}",
        f"# Table {ds['table']}: columns\n\n" + "\n\n".join(render_column(c) for c in d["columns"]),
        "# Notes and rules (follow every rule)\n\n"
        + "\n".join(f"- [{n['type']}] {n['id']}: {n['note']}" for n in d["notes"]),
        "# Worked examples\n\n" + "\n\n".join(render_example(ex) for ex in EXAMPLES),
    ]
    return "\n\n".join(sections)


if __name__ == "__main__":
    print(build_system_prompt())
