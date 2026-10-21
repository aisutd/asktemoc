/**
 * Minimal inline markdown for assistant text: **bold**, *italic*, `code`.
 * Block structure (lists, numbering) already reads correctly under
 * `whitespace-pre-wrap`, so only inline spans are parsed here.
 */

export type MarkdownSegment =
  | { type: "text"; text: string }
  | { type: "strong"; text: string }
  | { type: "em"; text: string }
  | { type: "code"; text: string };

/**
 * Delimiters must hug non-space, non-delimiter characters so arithmetic (`2 * 3`)
 * and course codes stay literal. Underscore emphasis is deliberately unsupported —
 * catalog text and URLs contain bare underscores.
 */
const INLINE_MD_RE =
  /`([^`\n]+)`|\*\*([^\s*](?:[^*]*[^\s*])?)\*\*|\*([^\s*](?:[^*\n]*[^\s*])?)\*/g;

export function splitInlineMarkdown(text: string): MarkdownSegment[] {
  const out: MarkdownSegment[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(INLINE_MD_RE.source, "g");
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      out.push({ type: "text", text: text.slice(last, m.index) });
    }
    if (m[1] !== undefined) {
      out.push({ type: "code", text: m[1] });
    } else if (m[2] !== undefined) {
      out.push({ type: "strong", text: m[2] });
    } else {
      out.push({ type: "em", text: m[3] });
    }
    last = re.lastIndex;
  }
  if (last < text.length) {
    out.push({ type: "text", text: text.slice(last) });
  }
  return out;
}
