"use client";

// Results with no agent output: rate-limited, unavailable, offline. Neutral, with a way forward.

import { useEffect, useState } from "react";
import type { Notice } from "@/lib/types";
import { waitText } from "@/lib/format";
import { IconAlert, IconClock, IconRetry } from "./icons";

export const OFFLINE = "Couldn’t reach the server. Check your connection and try again.";

export function NoticeCard({ notice, onRetry }: { notice: Notice | { status: "offline"; message: string }; onRetry: () => void }) {
  if (notice.status === "limited") return <Limited notice={notice as Notice} />;
  const title = notice.status === "offline" ? "Couldn’t reach the server" : "Demo is temporarily unavailable";
  const body = notice.status === "offline" ? OFFLINE : notice.message;
  return (
    <article className="card result" aria-labelledby="result-heading">
      <h2 id="result-heading" className="state-head neutral"><IconAlert /> {title}</h2>
      {body !== `${title}.` && <p className="state-help">{body}</p>}
      <button type="button" className="btn-quiet" onClick={onRetry}><IconRetry /> Try again</button>
    </article>
  );
}

function Limited({ notice }: { notice: Notice }) {
  const [left, setLeft] = useState(notice.retry_after_s ?? 0);
  useEffect(() => {
    if (notice.scope === "daily" || left <= 0) return;
    const id = setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [left, notice.scope]);

  return (
    <article className="card result" aria-labelledby="result-heading">
      <h2 id="result-heading" className="state-head neutral"><IconClock /> {notice.message}</h2>
      {notice.scope === "daily" ? (
        <p className="state-help">The limit resets at midnight UTC. Cached answers keep working.</p>
      ) : left > 0 ? (
        <p className="state-help">Try again in <span className="tabular">{waitText(left)}</span>. The examples and repeated questions still work.</p>
      ) : (
        <p className="state-help">You can ask again now.</p>
      )}
    </article>
  );
}
