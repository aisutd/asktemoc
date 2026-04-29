/** Optional fields on source items come from SSE (index/url) or `Source n: URL` in message. */
export type MessageContentItem =
  | { type: "text"; message: string }
  | {
      type: "source";
      message: string;
      index?: number;
      n?: number;
      url?: string;
      href?: string;
      title?: string;
    };

export interface Message {
  id: string;
  content: MessageContentItem[];
  role: "user" | "assistant";
  timestamp: Date;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  lastMessage: Date;
}
