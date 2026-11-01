"""The agent: question -> LLM -> guardrails -> DuckDB -> one AgentResult.

    from src.agent.agent import answer
    result = answer("How many loans has Chile received?")

On a guardrail rejection, a SQL error or a missing tool call, the model gets one retry with the
error message. If that also fails, the result has status "error" and says why.
"""

import time
from dataclasses import asdict, dataclass, field

import anthropic

from src.agent import config, llm
from src.agent.executor import ExecutionError, run_query
from src.agent.guardrails import check_sql
from src.agent.prompt import TOOL_NAME

NO_ROWS = "No matching rows"
UNRELIABLE = "I couldn't answer that reliably."


@dataclass
class AgentResult:
    question: str
    status: str                      # answer | clarify | refuse | error
    sql: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    truncated: bool = False
    assumptions: list[str] = field(default_factory=list)
    message: str = ""
    attempts: int = 0
    latency_s: float = 0.0
    input_tokens: int = 0            # uncached input tokens
    output_tokens: int = 0           # includes thinking tokens
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def add_usage(result: AgentResult, usage) -> None:
    result.input_tokens += usage.input_tokens
    result.output_tokens += usage.output_tokens
    result.cache_read_input_tokens += usage.cache_read_input_tokens or 0
    result.cache_creation_input_tokens += usage.cache_creation_input_tokens or 0


def answer(question: str) -> AgentResult:
    start = time.perf_counter()
    result = AgentResult(question=question, status="error")
    messages = [{"role": "user", "content": question}]
    reason = ""

    for attempt in range(1, config.MAX_ATTEMPTS + 1):
        result.attempts = attempt
        try:
            response = llm.call_model(messages)
        except anthropic.APIError as e:
            reason = f"The language model request failed ({type(e).__name__})."
            break
        add_usage(result, response.usage)

        if response.stop_reason == "refusal":
            reason = "The language model declined the request."
            break

        call = llm.find_tool_call(response)
        if call is None:
            reason = f"The model did not call {TOOL_NAME}."
            feedback = f"{reason} Respond by calling {TOOL_NAME} exactly once."
        else:
            out = call.input
            result.sql, result.assumptions = out["sql"].strip(), out["assumptions"]
            if out["status"] in ("clarify", "refuse"):
                result.status, result.message, result.sql = out["status"], out["message"], ""
                break
            ok, why = check_sql(result.sql)
            if ok:
                try:
                    q = run_query(result.sql)
                except ExecutionError as e:
                    reason = f"The query failed: {e}"
                else:
                    result.status = "answer"
                    result.columns, result.rows, result.truncated = q.columns, [list(r) for r in q.rows], q.truncated
                    result.message = out["message"] if q.rows else NO_ROWS
                    break
            else:
                reason = f"The SQL was rejected: {why}"
            feedback = [{
                "type": "tool_result",
                "tool_use_id": call.id,
                "is_error": True,
                "content": f"{reason}\nFix the query, or use status clarify or refuse if the question "
                           "cannot be answered reliably from this table.",
            }]
        messages += [{"role": "assistant", "content": response.content}, {"role": "user", "content": feedback}]

    if result.status == "error":
        result.message = f"{UNRELIABLE} {reason}"
    result.latency_s = round(time.perf_counter() - start, 2)
    return result
