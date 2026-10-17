export interface ChatResponse {
  type: "text" | "source";
  message: string;
  index?: number;
  n?: number;
  url?: string;
  href?: string;
  title?: string;
}

/**
 * The browser only talks to this app's own route handlers (src/app/api/*),
 * which check the Auth.js session and forward to FastAPI with a short-lived JWT.
 */
const CHAT_ENDPOINT = "/api/chat";
const HEALTH_ENDPOINT = "/api/health";

function redirectToSignIn(): void {
  if (typeof window === "undefined") return;
  const back = window.location.pathname + window.location.search;
  window.location.assign(`/signin?callbackUrl=${encodeURIComponent(back)}`);
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

    if (response.status === 401 || response.status === 403) {
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
      const response = await fetch(HEALTH_ENDPOINT, {
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
