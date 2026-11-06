// Keyword highlighting for the SQL panel. Returns text pieces; React escapes them, so no HTML is built.

const KEYWORDS = new Set(
  ("select from where and or not in is null as group by order having limit offset distinct case when then else end " +
    "with join left right inner outer full on union all asc desc between like ilike true false count sum avg min max " +
    "round coalesce cast over partition filter exists nullif qualify").split(" "),
);

export type Piece = { text: string; kw: boolean };

export function highlight(sql: string): Piece[] {
  // Strings and quoted identifiers stay whole, so a keyword inside 'text' is not highlighted.
  return sql.split(/('(?:[^']|'')*'|"(?:[^"]|"")*"|\b[A-Za-z_]+\b)/).filter(Boolean).map((text) => ({
    text,
    kw: KEYWORDS.has(text.toLowerCase()) && /^[A-Za-z_]+$/.test(text),
  }));
}
