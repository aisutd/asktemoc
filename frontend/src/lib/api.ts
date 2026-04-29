export interface ChatResponse {
  type: "text" | "source";
  message: string;
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
 * - Dev default: http://localhost:8000
 * - Production default: /api/proxy → Cloud Run (ASKTEMOC_API_ORIGIN in next.config)
 * - Override: NEXT_PUBLIC_API_BASE_URL (e.g. direct Cloud Run URL if CORS allows)
 */
export function getChatApiBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (explicit) return explicit.replace(/\/$/, "");
  if (process.env.NODE_ENV === "development") {
    return "http://localhost:8000";
  }
  return PROXY_BASE;
}

function chatEndpoint(): string {
  const base = getChatApiBaseUrl();
  if (isProxyBase(base)) {
    return `${base.replace(/\/$/, "")}/chat`;
  }
  return `${base.replace(/\/$/, "")}/api/chat`;
}

function healthEndpoint(): string {
  const base = getChatApiBaseUrl();
  if (isProxyBase(base)) {
    return `${base.replace(/\/$/, "")}/health`;
  }
  return `${base.replace(/\/$/, "")}/api/health`;
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
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split("\n");

            for (const line of lines) {
              if (line.startsWith("data: ")) {
                try {
                  const data = JSON.parse(line.slice(6));
                  yield data;
                } catch (e) {
                  console.error("Error parsing SSE data:", e);
                }
              }
            }
          }
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
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch (error) {
      console.error("Backend health check failed:", error);
      return false;
    }
  }
}

export const chatAPI = new ChatAPI();
