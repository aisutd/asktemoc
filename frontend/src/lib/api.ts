export interface ChatResponse {
  /** "text" carries an answer delta; "done" ends the stream. Other types are ignored. */
  type: "text" | "source" | "done" | (string & {});
  message: string;
  index?: number;
  n?: number;
  url?: string;
  href?: string;
  title?: string;
}

/**
 * The browser only talks to this app's own route handlers (src/app/api/*), which
 * check the Auth.js session and forward to the FastAPI backend with a
 * short-lived token. There is deliberately no way to point the browser at the
 * API directly: that would bypass sign-in.
 */
const CHAT_ENDPOINT = "/api/chat";
const HEALTH_ENDPOINT = "/api/health";

/** Send the user to sign in, returning to the current page afterwards. */
function redirectToSignIn(): void {
  if (typeof window === "undefined") return;
  const back = window.location.pathname + window.location.search;
  window.location.assign(`/signin?callbackUrl=${encodeURIComponent(back)}`);
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

export class ChatAPI {
  async sendMessage(message: string): Promise<AsyncIterable<ChatResponse>> {
    const response = await fetch(CHAT_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    });

    if (response.status === 401) {
      redirectToSignIn();
      throw new Error("Your session has expired. Redirecting to sign in…");
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
      const response = await fetch(HEALTH_ENDPOINT, {
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
