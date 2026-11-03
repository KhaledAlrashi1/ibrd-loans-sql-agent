"""Settings for the IBRD loans SQL agent. Change values here, not in the modules that use them."""

import hashlib
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Built from the frozen CSV by scripts/build_db.py, always in the temp directory (the same path locally
# and on Streamlit Community Cloud). One folder per checkout, so two clones never share a database.
DB_PATH = (Path(tempfile.gettempdir()) / f"ibrd-loans-sql-agent-{hashlib.sha1(str(ROOT).encode()).hexdigest()[:8]}"
           / "ibrd.duckdb")
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
