/**
 * Inline citations: [n, "EXACT_TEXT"] per assistant protocol (machine-parseable).
 */

export type SourceMeta = {
  index: number;
  url: string;
  title?: string;
};

export type CiteSegment =
  | { type: "text"; text: string }
  | { type: "cite"; n: number; exactText: string };

/** Match complete citations only; incomplete trailing fragments stay in text segments. */
const CITATION_RE = /\[(\d+)\s*,\s*"((?:[^"\\]|\\.)*)"\s*\]/g;

function unescapeCiteExact(s: string): string {
  return s.replace(/\\(.)/g, (_, ch: string) => {
    switch (ch) {
      case "n":
        return "\n";
      case "r":
        return "\r";
      case "t":
        return "\t";
      case '"':
        return '"';
      case "\\":
        return "\\";
      default:
        return ch;
    }
  });
}

export function splitInlineCitations(text: string): CiteSegment[] {
  const out: CiteSegment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(CITATION_RE.source, "g");
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push({ type: "text", text: text.slice(last, m.index) });
    }
    out.push({
      type: "cite",
      n: Number(m[1]),
      exactText: unescapeCiteExact(m[2]),
    });
    last = re.lastIndex;
  }
  if (last < text.length) {
    out.push({ type: "text", text: text.slice(last) });
  }
  return out;
}

export function siteLabelFromSource(meta: SourceMeta): string {
  const t = meta.title?.trim();
  if (t) return t;
  try {
    return new URL(meta.url).hostname.replace(/^www\./i, "");
  } catch {
    return `Source ${meta.index}`;
  }
}

/** Parse SSE source chunk body. Expects JSON: { n | index, url | href, title? }. */
export function parseSourceMessage(raw: string): SourceMeta | null {
  try {
    const o = JSON.parse(raw) as Record<string, unknown>;
    const index =
      typeof o.n === "number"
        ? o.n
        : typeof o.index === "number"
          ? o.index
          : typeof o.source === "number"
            ? o.source
            : null;
    const url =
      typeof o.url === "string"
        ? o.url
        : typeof o.href === "string"
          ? o.href
          : null;
    if (index != null && url) {
      return {
        index,
        url,
        title: typeof o.title === "string" ? o.title : undefined,
      };
    }
  } catch {
    /* not JSON */
  }
  return null;
}

export function buildSourceIndex(
  content: Array<{ type: string; message: string }>,
): Map<number, SourceMeta> {
  const m = new Map<number, SourceMeta>();
  for (const item of content) {
    if (item.type !== "source") continue;
    const meta = parseSourceMessage(item.message);
    if (meta) m.set(meta.index, meta);
  }
  return m;
}
