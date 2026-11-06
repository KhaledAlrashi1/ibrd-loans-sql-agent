// "Why you can trust the answers": every number comes from web/src/data/trust.json, which tests/test_trust.py
// checks against eval/RESULTS.md, the dev run file and src/agent/config.py. Plain statements, no adjectives.

import trustJson from "@/data/trust.json";

const t = trustJson;
const blob = (repo: string, path: string) => `${repo}/blob/main/${path}`;

export function Trust({ repoUrl }: { repoUrl: string }) {
  const c = t.clarify_case;
  const items = [
    {
      label: "Test results",
      text: `Dev set ${t.dev.correct}/${t.dev.questions} correct; held-out set ${t.heldout.correct_first_scored}/${t.heldout.questions} as first scored.`,
      href: blob(repoUrl, t.results_doc), link: "RESULTS.md",
    },
    {
      label: "Guardrails",
      text: `Read-only database; SQL checked before it runs; ${t.row_limit.toLocaleString("en-US")} rows, ${t.timeout_s} s max.`,
      href: blob(repoUrl, t.security_doc), link: "security.md",
    },
    {
      label: "Ambiguity",
      text: "Asks instead of guessing when a question is ambiguous.",
      href: `${blob(repoUrl, c.file)}#L${c.first_line}-L${c.last_line}`, link: `Eval case ${c.id}`,
    },
  ];
  return (
    <section aria-labelledby="trust-heading" className="trust">
      <h2 id="trust-heading" className="section-head">Why you can trust the answers</h2>
      <dl>
        {items.map((i) => (
          <div key={i.label} className="trust-row">
            <dt>{i.label}</dt>
            <dd>{i.text} <a href={i.href}>{i.link}</a></dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
