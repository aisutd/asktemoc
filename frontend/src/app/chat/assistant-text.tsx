"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  buildSourceIndex,
  resolveSourceHref,
  siteLabelFromSource,
  type SourceMeta,
  splitInlineCitations,
} from "@/lib/citations";
import { splitInlineMarkdown } from "@/lib/markdown";
import type { Message } from "@/types";

const PILL_LABEL_MAX = 80;

/** Prefer breaking at the last space within the first `maxLen` chars; otherwise cut at `maxLen`. */
function truncatePillLabel(label: string, maxLen = PILL_LABEL_MAX): string {
  const s = label.trim();
  if (s.length <= maxLen) return s;
  const window = s.slice(0, maxLen);
  const lastSpace = window.lastIndexOf(" ");
  const end = lastSpace > 0 ? lastSpace : maxLen;
  const head = s.slice(0, end).trimEnd();
  return head.length < s.length ? `${head}…` : head;
}

const pillBase =
  "mx-0.5 inline-flex items-center gap-1 rounded-full border border-utd-primary/30 bg-background/80 px-2 py-0.5 align-baseline text-xs font-medium text-utd-primary underline-offset-2 transition-colors";

const pillLink =
  "cursor-pointer hover:bg-utd-primary/10 hover:underline";

const pillNoLink =
  "cursor-default no-underline hover:bg-transparent";

function CitationPill({
  n,
  exactText,
  meta,
}: {
  n: number;
  exactText: string;
  meta?: SourceMeta;
}) {
  const fullLabel = meta ? siteLabelFromSource(meta) : `Source ${n}`;
  const label = truncatePillLabel(fullLabel);
  const href = resolveSourceHref(meta?.url);

  const trigger = href ? (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(pillBase, pillLink)}
      title={fullLabel !== label ? fullLabel : undefined}
      onClick={(e) => e.stopPropagation()}
    >
      {label}
    </a>
  ) : (
    <span
      className={cn(pillBase, pillNoLink)}
      title={fullLabel !== label ? fullLabel : undefined}
    >
      {label}
    </span>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{trigger}</TooltipTrigger>
      <TooltipContent
        side="top"
        className="max-w-md overflow-hidden p-0 text-left"
      >
        {/* Inner scroll keeps overflow off the animated surface so no scrollbar during zoom/fade */}
        <div className="max-h-48 overflow-x-hidden overflow-y-auto overscroll-contain px-3 py-1.5">
          <p className="whitespace-pre-wrap text-xs leading-relaxed">{exactText}</p>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  return (
    <>
      {splitInlineMarkdown(text).map((seg, i) => {
        switch (seg.type) {
          case "strong":
            return (
              <strong key={i} className="font-semibold">
                {seg.text}
              </strong>
            );
          case "em":
            return <em key={i}>{seg.text}</em>;
          case "code":
            return (
              <code
                key={i}
                className="rounded bg-utd-primary/10 px-1 py-0.5 font-mono text-[0.9em]"
              >
                {seg.text}
              </code>
            );
          default:
            return <span key={i}>{seg.text}</span>;
        }
      })}
    </>
  );
}

export function AssistantFormattedText({
  text,
  content,
}: {
  text: string;
  content: Message["content"];
}) {
  const sourceIndex = buildSourceIndex(content);
  const segments = splitInlineCitations(text);

  return (
    <>
      {segments.map((seg, i) =>
        seg.type === "text" ? (
          <InlineMarkdown key={i} text={seg.text} />
        ) : (
          <CitationPill
            key={i}
            n={seg.n}
            exactText={seg.exactText}
            meta={sourceIndex.get(seg.n)}
          />
        ),
      )}
    </>
  );
}
