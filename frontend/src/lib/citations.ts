/**
 * Inline citations: [n, "EXACT_TEXT"] per assistant protocol (machine-parseable).
 */

import type { MessageContentItem } from "@/types";

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
  const href = resolveSourceHref(meta.url);
  if (href) {
    try {
      return new URL(href).hostname.replace(/^www\./i, "");
    } catch {
      /* fall through */
    }
  }
  return `Source ${meta.index}`;
}

/**
 * Normalizes stored source URLs into a safe absolute href for <a>.
 * Relative paths resolve against the current origin in the browser.
 */
export function resolveSourceHref(raw: string | undefined): string | undefined {
  if (!raw?.trim()) return undefined;
  const t = raw.trim();
  try {
    return new URL(t).href;
  } catch {
    /* missing scheme or invalid absolute */
  }
  try {
    if (t.startsWith("//")) return new URL(`https:${t}`).href;
    if (t.startsWith("/")) {
      if (typeof window !== "undefined") {
        return new URL(t, window.location.origin).href;
      }
      return undefined;
    }
    return new URL(`https://${t}`).href;
  } catch {
    return undefined;
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

/** `Source 1: https://example.com/...` (catalog-style) */
const SOURCE_LINE_RE = /^Source\s*(\d+)\s*:\s*(.+)$/i;

/**
 * Resolve one assistant content item of type "source" into metadata.
 * Handles: top-level index/url from SSE, JSON in message, or "Source n: URL" text.
 */
export function parseSourceContentItem(
  item: {
    type: string;
    message?: string;
    index?: number;
    n?: number;
    url?: string;
    href?: string;
    title?: string;
  },
): SourceMeta | null {
  if (item.type !== "source") return null;

  const idx =
    typeof item.index === "number"
      ? item.index
      : typeof item.n === "number"
        ? item.n
        : null;
  const topUrl =
    typeof item.url === "string"
      ? item.url.trim()
      : typeof item.href === "string"
        ? item.href.trim()
        : undefined;
  if (idx != null && topUrl) {
    return {
      index: idx,
      url: topUrl,
      title: typeof item.title === "string" ? item.title : undefined,
    };
  }

  if (typeof item.message === "string") {
    const fromJson = parseSourceMessage(item.message);
    if (fromJson) return fromJson;
    const m = item.message.trim().match(SOURCE_LINE_RE);
    if (m) {
      const n = Number(m[1]);
      const url = m[2].trim();
      if (Number.isFinite(n) && url) {
        return {
          index: n,
          url,
          title: typeof item.title === "string" ? item.title : undefined,
        };
      }
    }
  }

  return null;
}

export function buildSourceIndex(
  content: MessageContentItem[],
): Map<number, SourceMeta> {
  const m = new Map<number, SourceMeta>();
  for (const item of content) {
    if (item.type !== "source") continue;
    const meta = parseSourceContentItem(item);
    if (meta) m.set(meta.index, meta);
  }
  return m;
}
