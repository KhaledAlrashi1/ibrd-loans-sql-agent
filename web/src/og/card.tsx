// The link-preview image (Open Graph and Twitter), drawn at build time from the page's own tokens and fonts:
// the title and the stat strip from web/src/data/stats.json, in the light palette of globals.css.
// Fonts: TTF copies of the page's Source Serif 4 / Source Sans 3 (SIL OFL 1.1, licences in ./fonts), because
// next/og cannot read the woff2 files next/font serves.

import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import statsJson from "@/data/stats.json";
import { compactUsd, longDate } from "@/lib/format";
import type { Stats } from "@/lib/types";

const stats = statsJson as Stats;

export const OG_SIZE = { width: 1200, height: 630 };
export const OG_ALT =
  `Ask the IBRD loan book: ${compactUsd(stats.outstanding_usd)} outstanding, ${compactUsd(stats.approved_usd)} approved ` +
  `since FY${stats.first_fy}, ${stats.countries} countries, ${stats.loans.toLocaleString("en-US")} loans.`;

// globals.css, light theme
const C = { page: "#f8f7f3", ink: "#1b1a17", ink2: "#55534c", muted: "#6f6c64", hairline: "#e4e2db", accent: "#007d61", surface: "#fdfcf9" };

/** Cached, so the image routes have no uncached I/O and are prerendered at build time. Base64, because the cache
 *  stores strings reliably and binary data not. */
async function loadFonts() {
  "use cache";
  const font = async (file: string) => (await readFile(join(process.cwd(), "src/og/fonts", file))).toString("base64");
  return Promise.all([font("SourceSerif4-SemiBold.ttf"), font("SourceSans3-Regular.ttf"), font("SourceSans3-SemiBold.ttf")]);
}

const arrayBuffer = (b64: string) => {
  const b = Buffer.from(b64, "base64");
  return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;
};

export async function renderCard() {
  const [serif, sans, sansBold] = (await loadFonts()).map(arrayBuffer);
  const items = [
    { label: "Outstanding", value: compactUsd(stats.outstanding_usd) },
    { label: `Approved since FY${stats.first_fy}`, value: compactUsd(stats.approved_usd) },
    { label: "Countries", value: stats.countries.toLocaleString("en-US") },
    { label: "Loans", value: stats.loans.toLocaleString("en-US") },
  ];

  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", background: C.page, padding: "64px 80px 56px", fontFamily: "Sans" }}>
        <div style={{ display: "flex", width: 56, height: 56, borderRadius: 12, background: C.accent, flexDirection: "column", justifyContent: "center", gap: 6, paddingLeft: 12 }}>
          {[32, 23, 14].map((w) => <div key={w} style={{ width: w, height: 5, borderRadius: 3, background: C.surface }} />)}
        </div>
        <div style={{ display: "flex", marginTop: 40, fontFamily: "Serif", fontSize: 84, lineHeight: 1.05, letterSpacing: "-0.015em", color: C.ink }}>
          Ask the IBRD loan book
        </div>
        <div style={{ display: "flex", marginTop: 18, fontSize: 32, lineHeight: 1.3, color: C.ink2 }}>
          Ask in plain English. See the answer, its SQL and every assumption.
        </div>
        <div style={{ display: "flex", marginTop: "auto", paddingTop: 32, borderTop: `2px solid ${C.hairline}` }}>
          {items.map((s) => (
            <div key={s.label} style={{ display: "flex", flexDirection: "column", width: "25%" }}>
              <div style={{ display: "flex", fontWeight: 600, fontSize: 56, lineHeight: 1.1, letterSpacing: "-0.02em", color: C.ink }}>{s.value}</div>
              <div style={{ display: "flex", marginTop: 4, fontSize: 24, color: C.ink2 }}>{s.label}</div>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", marginTop: 20, fontSize: 22, color: C.muted }}>
          Snapshot {longDate(stats.end_of_period)} · guarantees excluded
        </div>
      </div>
    ),
    {
      ...OG_SIZE,
      fonts: [
        { name: "Serif", data: serif, weight: 600, style: "normal" },
        { name: "Sans", data: sans, weight: 400, style: "normal" },
        { name: "Sans", data: sansBold, weight: 600, style: "normal" },
      ],
    },
  );
}
