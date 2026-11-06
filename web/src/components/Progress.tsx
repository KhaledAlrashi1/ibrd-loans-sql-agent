// Loading state (docs/v2-plan.md 4): four honest steps plus a skeleton in the answer card's final shape.
// agent.answer() is one call, so "Writing SQL" covers the model call and the last two steps tick only
// when the server confirms it validated and ran the query. A question asked while the API instance is still
// starting gets an extra first step, and the others wait until /api/health has answered.

import { IconCheck } from "./icons";

export const STEPS = ["Understanding the question", "Writing SQL", "Checking the SQL", "Running it on the data"];
export const WAKE_STEP = "Waking up the server (~15 s)";

type Wake = "none" | "active" | "done";

export function Progress({ step, question, wake }: { step: number; question: string; wake: Wake }) {
  const steps = wake === "none" ? STEPS : [WAKE_STEP, ...STEPS];
  const current = wake === "none" ? step : wake === "active" ? 0 : step + 1;
  return (
    <div className="card loading" aria-busy="true">
      <p className="q">{question}</p>
      <ol className="steps" aria-label="Progress">
        {steps.map((s, i) => {
          const state = i < current ? "done" : i === current ? "active" : "todo";
          return (
            <li key={s} className={`step ${state}`} aria-current={state === "active" ? "step" : undefined}>
              <span className="step-mark" aria-hidden="true">{state === "done" ? <IconCheck size={12} /> : null}</span>
              {s}
              {state === "done" && <span className="sr-only"> (done)</span>}
            </li>
          );
        })}
      </ol>
      <div className="skeleton" aria-hidden="true">
        <span className="sk sk-line" style={{ width: "88%" }} />
        <span className="sk sk-line" style={{ width: "54%" }} />
        <div className="sk-bars">
          {[100, 86, 74, 42, 40, 28].map((w, i) => (
            <span key={i} className="sk-bar-row"><span className="sk sk-name" /><span className="sk sk-bar" style={{ width: `${w}%` }} /></span>
          ))}
        </div>
        <span className="sk sk-small" style={{ width: "70%" }} />
        <span className="sk sk-small" style={{ width: "62%" }} />
        <span className="sk sk-small" style={{ width: "45%" }} />
      </div>
    </div>
  );
}
