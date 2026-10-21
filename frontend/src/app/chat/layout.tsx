import { ConversationProvider } from "./conversation-context";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <ConversationProvider>{children}</ConversationProvider>
    </div>
  );
}
