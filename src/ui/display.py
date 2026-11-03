"""How a result table is shown: units per column, display formatting, and which chart (if any) fits.

Formatting is for display only: the DataFrame keeps the agent's raw values, and the formatters are
applied through a pandas Styler, so sorting a column in the UI still sorts by the real number.

Unit rule, per result column (first match wins):
  1. A unit passed in explicitly (the agent output carries none today).
  2. A column name from data_dictionary.yaml: "usd" if its original name is marked (US$), else "plain".
     interest_rate is "plain": its units are not documented.
  3. A computed alias: "_usd" suffix -> "usd", "_share" suffix -> "share" (a 0-1 fraction, per the prompt).
  4. Anything else -> "plain", shown as stored.

Chart rule (a pure function of the result shape, see choose_chart):
  line: exactly two columns, a fiscal-year column of integers + one numeric column, 2+ distinct years.
  bar:  exactly two columns, one text column + one numeric column, 2-25 rows, distinct labels; row order kept.
  else: no chart.
"""

import math
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import altair as alt
import pandas as pd
import yaml

from src.agent import config

USD, SHARE, PLAIN = "usd", "share", "plain"
BAR_MIN_ROWS, BAR_MAX_ROWS = 2, 25
FISCAL_YEAR_NAME = re.compile(r"(^|_)(fy|fiscal_year)$")
YEAR_NAME = re.compile(r"(^|_)(fy|cy|year|fiscal_year|calendar_year)$")


@cache
def dictionary_units(dictionary_path: Path = config.DICTIONARY_PATH) -> dict[str, str]:
    columns = yaml.safe_load(Path(dictionary_path).read_text())["columns"]
    return {c["column"]: USD if "(US$)" in (c["original_name"] or "") else PLAIN for c in columns}


def column_unit(name: str, units: dict[str, str] | None = None) -> str:
    if units and name in units:
        return units[name]
    key = name.lower()
    known = dictionary_units()
    if key in known:
        return known[key]
    if key.endswith("_usd"):
        return USD
    if key.endswith("_share"):
        return SHARE
    return PLAIN


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and math.isnan(v))


def format_usd(v: float) -> str:
    """$1.23B / $456.7M / $12.3K / $512.40. Picks the largest unit the rounded value reaches."""
    sign, a = ("-" if v < 0 else ""), abs(v)
    for divisor, suffix, decimals in ((1e9, "B", 2), (1e6, "M", 1), (1e3, "K", 1)):
        if round(a / divisor, decimals) >= 1:
            return f"{sign}${a / divisor:,.{decimals}f}{suffix}"
    if round(a, 2) == 0:
        return "$0.00"
    return f"{sign}${a:,.2f}"


def format_share(v: float) -> str:
    """A 0-1 fraction as a percentage with one decimal."""
    pct = v * 100
    if pct != 0 and abs(pct) < 0.05:
        return "<0.1%" if pct > 0 else ">-0.1%"
    return f"{pct:.1f}%"


def format_value(v, unit: str) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if is_number(v):
        if unit == USD:
            return format_usd(v)
        if unit == SHARE:
            return format_share(v)
    return str(v)


def unique_names(columns: list[str]) -> list[str]:
    """Duplicate result column names (legal in SQL) would break the table; number the repeats."""
    seen: dict[str, int] = {}
    out = []
    for name in columns:
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name} ({seen[name]})")
    return out


def result_frame(columns: list[str], rows: list[list]) -> pd.DataFrame:
    """The raw values as a DataFrame. Integer columns with NULLs stay integers (Int64), not floats."""
    names = unique_names(columns)
    data = {}
    for i, name in enumerate(names):
        values = [row[i] for row in rows]
        present = [v for v in values if v is not None]
        if present and all(isinstance(v, int) and not isinstance(v, bool) for v in present):
            data[name] = pd.Series(values, dtype="Int64")
        else:
            data[name] = pd.Series(values, dtype=object if not present else None)
    return pd.DataFrame(data)


def styled_table(columns: list[str], rows: list[list], units: dict[str, str] | None = None):
    """A Styler whose display text follows the unit rule; the underlying values are unchanged."""
    df = result_frame(columns, rows)
    formatters = {name: (lambda v, u=column_unit(orig, units): format_value(v, u))
                  for name, orig in zip(df.columns, columns)}
    return df.style.format(formatters, na_rep="")


@dataclass(frozen=True)
class ChartSpec:
    kind: str  # "bar" | "line"
    x: str     # category or fiscal-year column
    y: str     # numeric column


def is_fiscal_year_column(name: str, values: list) -> bool:
    return bool(FISCAL_YEAR_NAME.search(name.lower())) and all(
        isinstance(v, int) and not isinstance(v, bool) for v in values)


def choose_chart(columns: list[str], rows: list[list]) -> ChartSpec | None:
    if len(columns) != 2 or len(set(columns)) != 2 or not rows:
        return None
    cols = [[row[i] for row in rows] for i in range(2)]
    numeric = [all(is_number(v) for v in c) for c in cols]

    for x, y in ((0, 1), (1, 0)):
        if is_fiscal_year_column(columns[x], cols[x]) and numeric[y]:
            if len(set(cols[x])) == len(rows) >= 2:
                return ChartSpec("line", columns[x], columns[y])
            return None

    text = [all(isinstance(v, str) for v in c) for c in cols]
    for x, y in ((0, 1), (1, 0)):
        if YEAR_NAME.search(columns[y].lower()):
            continue  # a bar of years (e.g. country, first_fy) is not a measure
        if text[x] and numeric[y] and BAR_MIN_ROWS <= len(rows) <= BAR_MAX_ROWS and len(set(cols[x])) == len(rows):
            return ChartSpec("bar", columns[x], columns[y])
    return None


# Vega-Lite axis labels: SI prefixes, with G (giga) shown as B (billion) to match the table.
USD_AXIS = "replace(replace(format(datum.value, '$.3~s'), 'G', 'B'), 'k', 'K')"


def build_chart(spec: ChartSpec, columns: list[str], rows: list[list],
                units: dict[str, str] | None = None) -> alt.Chart:
    unit = column_unit(spec.y, units)
    df = pd.DataFrame({spec.x: [row[columns.index(spec.x)] for row in rows],
                       spec.y: [row[columns.index(spec.y)] for row in rows]})
    df["label"] = [format_value(v, unit) for v in df[spec.y]]
    axis = (alt.Axis(labelExpr=USD_AXIS) if unit == USD
            else alt.Axis(format=".0%") if unit == SHARE else alt.Axis())
    tooltip = [alt.Tooltip(spec.x), alt.Tooltip("label", title=spec.y)]

    if spec.kind == "bar":
        return alt.Chart(df).mark_bar().encode(
            y=alt.Y(spec.x, type="nominal", sort=None, title=None),
            x=alt.X(spec.y, type="quantitative", axis=axis),
            tooltip=tooltip,
        ).properties(height=28 * len(df) + 40)
    return alt.Chart(df).mark_line(point=True).encode(
        x=alt.X(spec.x, type="quantitative", axis=alt.Axis(format="d", tickMinStep=1), scale=alt.Scale(zero=False)),
        y=alt.Y(spec.y, type="quantitative", axis=axis),
        tooltip=tooltip,
    )


def md_text(s: str) -> str:
    """Escape $ so Streamlit markdown does not render "US$ ... US$" as LaTeX."""
    return s.replace("$", "\\$")
