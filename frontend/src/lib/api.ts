export interface ChatResponse {
  /** "text" carries an answer delta; "done" ends the stream. Other types are ignored. */
  type: "text" | "source" | "done" | (string & {});
  message: string;
  /** Sent by older API builds alongside a cumulative `message`. */
  delta?: string;
  index?: number;
  n?: number;
  url?: string;
  href?: string;
  title?: string;
}

/** Same-origin proxy path on Vercel (see next.config rewrites). */
const PROXY_BASE = "/api/proxy";

function isProxyBase(base: string): boolean {
  const b = base.replace(/\/$/, "");
  return b === PROXY_BASE || b.endsWith(PROXY_BASE);
}

/**
 * API origin for chat + health.
 * - Default: same-origin /api/proxy, rewritten by next.config to ASKTEMOC_API_ORIGIN:
 *   the local API (http://localhost:8000) under `next dev`, Cloud Run in production
 *   builds (.env.production / vercel.json).
 * - Override: NEXT_PUBLIC_API_BASE_URL to call an API origin directly from the
 *   browser (requires CORS on that API).
 *
 * In production, a mis-set NEXT_PUBLIC_API_BASE_URL pointing at localhost is ignored
 * so Vercel deployments don’t try to call the developer’s laptop from the browser.
 */
export function getChatApiBaseUrl(): string {
  let explicit = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (explicit && process.env.NODE_ENV === "production") {
    try {
      const withProto = explicit.includes("://") ? explicit : `http://${explicit}`;
      const { hostname } = new URL(withProto);
      if (hostname === "localhost" || hostname === "127.0.0.1") {
        explicit = "";
      }
    } catch {
      /* keep explicit for values like /api/proxy */
    }
  }
  if (explicit) return explicit.replace(/\/$/, "");
  return PROXY_BASE;
}

function chatEndpoint(): string {
  const base = getChatApiBaseUrl();
  if (isProxyBase(base)) {
    return `${base.replace(/\/$/, "")}/chat`;
  }
  return `${base.replace(/\/$/, "")}/api/chat`;
}

/** Parse one SSE line. Returns null for comments, blank separators and bad JSON. */
function parseSseLine(line: string): ChatResponse | null {
  const trimmed = line.trimEnd();
  if (!trimmed.startsWith("data: ")) return null;
  try {
    return JSON.parse(trimmed.slice(6)) as ChatResponse;
  } catch (e) {
    console.error("Error parsing SSE data:", e);
    return null;
  }
}

function healthEndpoint(): string {
  const base = getChatApiBaseUrl();
  if (isProxyBase(base)) {
    return `${base.replace(/\/$/, "")}/health`;
  }
  return `${base.replace(/\/$/, "")}/api/health/`;
}

export class ChatAPI {
  async sendMessage(message: string): Promise<AsyncIterable<ChatResponse>> {
    const response = await fetch(chatEndpoint(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    });

    if (response.status === 401 || response.status === 403) {
      const loc = response.headers.get("Location");
      if (typeof window !== "undefined" && loc) {
        window.location.assign(loc);
      }
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    if (!response.body) {
      throw new Error("No response body");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    return {
      async *[Symbol.asyncIterator]() {
        // Network chunks split mid-line and mid-UTF-8, so hold the trailing partial
        // line until the next read instead of parsing (and dropping) it.
        let buffer = "";
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              const data = parseSseLine(line);
              if (data) yield data;
            }
          }

          buffer += decoder.decode();
          const tail = parseSseLine(buffer);
          if (tail) yield tail;
        } finally {
          reader.releaseLock();
        }
      },
    };
  }

  async isBackendAvailable(): Promise<boolean> {
    try {
      const response = await fetch(healthEndpoint(), {
        method: "GET",
        // Cloud Run cold starts have been measured over 20s; a short timeout here
        // reports a healthy backend as down.
        signal: AbortSignal.timeout(35000),
      });
      return response.ok;
    } catch (error) {
      console.error("Backend health check failed:", error);
      return false;
    }
  }
}

export const chatAPI = new ChatAPI();
