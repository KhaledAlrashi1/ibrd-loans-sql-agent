"use client";

import { useState } from "react";
import { highlight } from "@/lib/sql";
import { IconCheck, IconCopy } from "./icons";

export function SqlBlock({ sql }: { sql: string }) {
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
    <div className="sql-box">
      <button type="button" className="copy" onClick={copy}>
        {copied ? <IconCheck /> : <IconCopy />}
        <span aria-live="polite">{copied ? "Copied" : "Copy"}</span>
      </button>
      <pre className="sql" translate="no"><code>{highlight(sql).map((p, i) => (p.kw ? <span key={i} className="kw">{p.text}</span> : p.text))}</code></pre>
    </div>
  );
}
