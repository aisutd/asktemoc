"use client";

import { SidebarProvider } from "@/components/ui/sidebar";
import ChatSidebar from "./sidebar";
import ChatArea from "./chat-area";
import { useConversations } from "./conversation-context";

export default function Chat() {
  const {
    conversations,
    selectedConversationId,
    loading,
    creating,
    error,
    selectConversation,
    createConversation,
    updateConversation,
    deleteConversation,
  } = useConversations();

  return (
    <SidebarProvider className="min-h-0 flex-1">
      <div className="flex h-full min-h-0 w-full">
        <ChatSidebar
          conversations={conversations}
          selectedConversationId={selectedConversationId}
          loading={loading}
          creating={creating}
          error={error}
          onSelectConversation={selectConversation}
          onCreateConversation={() => {
            void createConversation();
          }}
          onDeleteConversation={deleteConversation}
        />

        <ChatArea
          selectedConversationId={selectedConversationId}
          conversations={conversations}
          onUpdateConversation={updateConversation}
        />
      </div>
    </SidebarProvider>
  );
}
