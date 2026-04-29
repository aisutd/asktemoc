"use client";

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import {
  buildSourceIndex,
  siteLabelFromSource,
  type SourceMeta,
  splitInlineCitations,
} from "@/lib/citations";
import type { Message } from "@/types";

const pillClass =
  "mx-0.5 inline-flex max-w-[12rem] cursor-pointer items-center gap-1 truncate rounded-full border border-utd-primary/30 bg-background/80 px-2 py-0.5 align-baseline text-xs font-medium text-utd-primary underline-offset-2 transition-colors hover:bg-utd-primary/10 hover:underline";

function CitationPill({
  n,
  exactText,
  meta,
}: {
  n: number;
  exactText: string;
  meta?: SourceMeta;
}) {
  const label = meta ? siteLabelFromSource(meta) : `Source ${n}`;

  const trigger = meta?.url ? (
    <a
      href={meta.url}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(pillClass)}
      onClick={(e) => e.stopPropagation()}
    >
      {label}
    </a>
  ) : (
    <span className={cn(pillClass, "cursor-help no-underline hover:no-underline")}>
      {label}
    </span>
  );

  return (
    <Tooltip>
      <TooltipTrigger asChild>{trigger}</TooltipTrigger>
      <TooltipContent
        side="top"
        className="max-h-48 max-w-md overflow-y-auto text-left"
      >
        <p className="whitespace-pre-wrap text-xs leading-relaxed">{exactText}</p>
      </TooltipContent>
    </Tooltip>
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
          <span key={i}>{seg.text}</span>
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
