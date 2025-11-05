"use client";

import { useState } from "react";
import { SidebarProvider } from "@/components/ui/sidebar";
import ChatSidebar from "./sidebar";
import ChatArea from "./chat-area";
import { Message, Conversation } from "@/types";

export default function Chat() {
  const [conversations, setConversations] = useState<Conversation[]>([
    {
      id: "1",
      title: "How to register for classes?",
      messages: [],
      lastMessage: new Date(),
    },
    {
      id: "2",
      title: "UTD parking information",
      messages: [],
      lastMessage: new Date(),
    },
    {
      id: "3",
      title: "Campus dining options",
      messages: [],
      lastMessage: new Date(),
    },
  ]);
  const [selectedConversationId, setSelectedConversationId] =
    useState<string>("1");

  const createNewConversation = () => {
    const newConversation: Conversation = {
      id: Date.now().toString(),
      title: "New Chat",
      messages: [],
      lastMessage: new Date(),
    };
    setConversations((prev) => [newConversation, ...prev]);
    setSelectedConversationId(newConversation.id);
  };

  const updateConversation = (conversationId: string, messages: Message[]) => {
    setConversations((prev) =>
      prev.map((conv) =>
        conv.id === conversationId
          ? {
              ...conv,
              messages,
              title:
                messages.length > 0 && conv.title === "New Chat"
                  ? messages[0].content
                      .find((item) => item.type === "text")
                      ?.message.slice(0, 30) + "..." || "New Chat"
                  : conv.title,
              lastMessage: new Date(),
            }
          : conv
      )
    );
  };

  const deleteConversation = (conversationId: string) => {
    setConversations((prev) =>
      prev.filter((conv) => conv.id !== conversationId)
    );
    if (selectedConversationId === conversationId) {
      setSelectedConversationId(
        conversations.length > 1 ? conversations[1].id : ""
      );
    }
  };

  return (
    <SidebarProvider>
      <div className="h-screen flex w-full">
        {/* Sidebar */}
        <ChatSidebar
          conversations={conversations}
          selectedConversationId={selectedConversationId}
          onSelectConversation={setSelectedConversationId}
          onCreateConversation={createNewConversation}
          onDeleteConversation={deleteConversation}
        />

        {/* Main Chat Area */}
        <ChatArea
          selectedConversationId={selectedConversationId}
          conversations={conversations}
          onUpdateConversation={updateConversation}
        />
      </div>
    </SidebarProvider>
  );
}
