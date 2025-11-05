"use client";

import { Quote } from "lucide-react";

interface QuoteComponentProps {
  message: string;
  className?: string;
}

export default function QuoteComponent({
  message,
  className = "",
}: QuoteComponentProps) {
  return (
    <div
      className={`flex items-start gap-2 p-3 bg-muted/50 rounded-lg border border-utd-primary/20 ${className}`}
    >
      <Quote className="h-4 w-4 text-utd-primary mt-0.5 flex-shrink-0" />
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
