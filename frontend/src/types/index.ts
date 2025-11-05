export interface Message {
  id: string;
  content: Array<{
    type: "text" | "source";
    message: string;
  }>;
  role: "user" | "assistant";
  timestamp: Date;
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  lastMessage: Date;
}
