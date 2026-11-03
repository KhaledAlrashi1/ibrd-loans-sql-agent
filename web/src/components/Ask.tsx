"use client";

// The question box, the examples and the result area. All rules live in the API; this only renders.

import { useEffect, useRef, useState } from "react";
import type { Answer, AskResponse, ExamplesFile, Notice } from "@/lib/types";
import { isAnswer } from "@/lib/types";
import { MAX_QUESTION_CHARS, validateQuestion } from "@/lib/format";
import { AnswerCard } from "./AnswerCard";
import { NoticeCard, OFFLINE } from "./NoticeCard";
import { Progress } from "./Progress";

const WRITING_AFTER_MS = 700;   // "Writing SQL" once the request has clearly reached the model
const TICK_MS = 150;            // each confirmed step, once the response is in
const TIMEOUT_MS = 70_000;      // above the API's 60 s maximum duration
const WAKING_AFTER_MS = 800;    // a warm /api/health answers well within this, so a warm page never shows "waking"

/** "checking" until /api/health answers or is slow, "waking" while a cold instance starts, then "ready". */
type Server = "checking" | "waking" | "ready";

type View =
  | { kind: "idle" }
  | { kind: "loading"; question: string; step: number; woke: boolean }
  | { kind: "answer"; data: Answer }
  | { kind: "notice"; notice: Notice | { status: "offline"; message: string }; question: string };

const ANNOUNCE: Record<string, string> = {
  answer: "Answer ready.", empty: "No matching rows.", clarify: "The agent needs more detail.",
  refuse: "The agent can't answer that from this data.", error: "The agent couldn't answer that reliably.",
  limited: "Rate limit reached.", unavailable: "The demo is unavailable.", offline: "Couldn't reach the server.",
};

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function post(question: string, signal: AbortSignal): Promise<AskResponse | null> {
  try {
    const res = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }), signal,
    });
    try {
      return (await res.json()) as AskResponse;
    } catch {  // a platform error page (e.g. a gateway timeout) instead of the API's JSON
      return { status: "unavailable", message: "Demo is temporarily unavailable.", retry_after_s: null };
    }
  } catch {
    return null;  // network failure or timeout
  }
}

export function Ask({ examples }: { examples: ExamplesFile }) {
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [view, setView] = useState<View>({ kind: "idle" });
  const [announce, setAnnounce] = useState("");
  const [server, setServer] = useState<Server>("checking");
  const run = useRef(0);
  const input = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const loading = view.kind === "loading";

  // Wake the API instance while the visitor reads or types, so the first live question skips the cold start.
  // A cold instance takes about 10 s; say so instead of leaving a silent spinner. Any reply (even a 503) or a
  // network failure ends the wait: /api/ask then reports the problem itself.
  useEffect(() => {
    let answered = false;
    const slow = setTimeout(() => !answered && setServer("waking"), WAKING_AFTER_MS);
    // Read the (tiny) body so the request completes instead of staying open.
    fetch("/api/health", { cache: "no-store" }).then((r) => r.text()).catch(() => {}).finally(() => {
      answered = true;
      clearTimeout(slow);
      setServer("ready");
    });
    if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) input.current?.focus();
    return () => clearTimeout(slow);
  }, []);

  function show(next: View, status: string) {
    setView(next);
    setAnnounce(ANNOUNCE[status] ?? "");
  }

  async function ask(raw: string) {
    const question = raw.trim();
    const invalid = validateQuestion(question);
    setProblem(invalid);
    if (invalid) return input.current?.focus();

    const id = ++run.current;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
    const woke = server !== "ready";
    setView({ kind: "loading", question, step: 0, woke });
    setAnnounce("Asking…");
    reveal();
    const writing = setTimeout(() => run.current === id && setView({ kind: "loading", question, step: 1, woke }), WRITING_AFTER_MS);

    const res = await post(question, controller.signal);
    clearTimeout(timeout);
    clearTimeout(writing);
    if (run.current !== id) return;

    if (!res) return show({ kind: "notice", notice: { status: "offline", message: OFFLINE }, question }, "offline");
    if (res.status === "invalid") {
      setView({ kind: "idle" });
      setProblem(res.message);
      return input.current?.focus();
    }
    if (!isAnswer(res)) return show({ kind: "notice", notice: res, question }, res.status);

    if (res.status === "answer" || res.status === "empty") {
      // The server validated and ran the SQL: tick the last two steps before showing the answer.
      setView({ kind: "loading", question, step: 3, woke });
      await wait(TICK_MS);
      if (run.current !== id) return;
      setView({ kind: "loading", question, step: 4, woke });
      await wait(TICK_MS);
      if (run.current !== id) return;
    }
    show({ kind: "answer", data: res }, res.status);
  }

  function showExample(e: Answer) {
    run.current++;  // cancels a live question still in flight
    setText(e.question);
    setProblem(null);
    show({ kind: "answer", data: e }, "answer");
    reveal();
  }

  /** On a phone the result area is below the examples: bring it into view (no jump if already visible). */
  function reveal() {
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => resultRef.current?.scrollIntoView({ block: "nearest", behavior: smooth ? "smooth" : "auto" }));
  }

  const count = text.trim().length;
  const over = count > MAX_QUESTION_CHARS;

  return (
    <>
      <form className="ask" onSubmit={(e) => { e.preventDefault(); ask(text); }} noValidate>
        <label htmlFor="q" className="sr-only">Your question about IBRD loans</label>
        <div className="ask-row">
          <input ref={input} id="q" name="q" type="text" autoComplete="off" spellCheck enterKeyHint="send"
            placeholder="e.g. How much does Chile owe the IBRD?" value={text}
            aria-invalid={problem ? true : undefined} aria-describedby="q-hint q-problem"
            onChange={(e) => { setText(e.target.value); if (problem) setProblem(null); }} />
          <button className="btn" type="submit" disabled={loading} aria-disabled={loading}>
            {loading ? "Asking…" : "Ask"}
          </button>
        </div>
        <div className="hint" id="q-hint">
          <span className="hint-enter">Press Enter to ask</span>
          <span className={over ? "count over" : "count"} aria-live={over ? "polite" : "off"}>
            {count} / {MAX_QUESTION_CHARS}
          </span>
        </div>
        <p id="q-problem" className="problem" role="alert">{problem}</p>
        <p className="wake" role="status">
          {server === "waking" && <><span className="wake-dot" aria-hidden="true" />Waking up the server (~10 s). The examples below work now.</>}
        </p>
      </form>

      <section aria-labelledby="examples-heading" className="examples-block">
        <h2 id="examples-heading" className="section-head">Try an example</h2>
        <ul className="examples">
          {examples.examples.map((e) => (
            <li key={e.question}>
              <button type="button" onClick={() => showExample(e)}>
                <span>{e.question}</span>
                <span className="tag">Instant</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div ref={resultRef} className="result-area">
        {view.kind === "loading" && <Progress step={view.step} question={view.question} wake={!view.woke ? "none" : server === "ready" ? "done" : "active"} />}
        {view.kind === "answer" && <AnswerCard key={`${view.data.question}-${view.data.source}`} data={view.data} computedAt={examples.computed_at} />}
        {view.kind === "notice" && <NoticeCard notice={view.notice} onRetry={() => ask(view.question)} />}
      </div>
      <p className="sr-only" aria-live="polite">{announce}</p>
    </>
  );
}
