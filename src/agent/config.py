"""Settings for the IBRD loans SQL agent. Change values here, not in the modules that use them."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "ibrd.duckdb"
DICTIONARY_PATH = ROOT / "src" / "agent" / "data_dictionary.yaml"
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"
TABLE = "ibrd_loans"

# Model. claude-sonnet-5-5 accepts no temperature and no forced tool_choice (both return a 400);
# see llm.py for how structured output is enforced instead.
MODEL = "claude-sonnet-5-5"
EFFORT = "high"           # the model's default, stated explicitly
MAX_TOKENS = 16000

# Guardrails
ROW_LIMIT = 1000
TIMEOUT_S = 10
MAX_ATTEMPTS = 2          # first try + one retry with the error message

# US$ per million tokens for MODEL, used only for the cost estimate in run_eval.py.
# Cache writes use the 5-minute TTL (1.25x input).
PRICE_PER_MTOK = {
    "input": 2.00,
    "output": 10.00,
    "cache_read": 0.20,
    "cache_write": 2.50,
}
