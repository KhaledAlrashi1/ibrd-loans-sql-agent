"use client";

import { useState } from "react";
import { highlight } from "@/lib/sql";
import { IconCheck, IconChevron, IconCopy } from "./icons";

export function SqlBlock({ sql, title }: { sql: string; title: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked: the text is still selectable */
    }
  }

  return (
    <details className="sql-details">
      <summary>
        <span className="chev" aria-hidden="true"><IconChevron /></span>
        {title}
      </summary>
      <div className="sql-box">
        <button type="button" className="copy" onClick={copy}>
          {copied ? <IconCheck /> : <IconCopy />}
          <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
        </button>
        <pre className="sql" translate="no"><code>{highlight(sql).map((p, i) => (p.kw ? <span key={i} className="kw">{p.text}</span> : p.text))}</code></pre>
      </div>
    </details>
  );
}
