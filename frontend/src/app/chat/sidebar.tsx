"use client";

import React from "react";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
} from "@/components/ui/sidebar";
import { Button } from "@/components/ui/button";
import { Plus, MessageSquare, Trash2 } from "lucide-react";
import { Conversation } from "@/types";

interface SidebarProps {
  conversations: Conversation[];
  selectedConversationId: string;
  loading: boolean;
  creating: boolean;
  error: string | null;
  onSelectConversation: (id: string) => void;
  onCreateConversation: () => void;
  onDeleteConversation: (id: string) => void;
}

export default function ChatSidebar({
  conversations,
  selectedConversationId,
  loading,
  creating,
  error,
  onSelectConversation,
  onCreateConversation,
  onDeleteConversation,
}: SidebarProps) {
  return (
    <div className="flex h-full w-64 flex-col overflow-y-auto border-r border-utd-primary/20 bg-utd-secondary/10">
      <div className="p-4">
        <Button
          onClick={onCreateConversation}
          disabled={loading || creating}
          className="w-full bg-transparent hover:bg-utd-secondary/30 hover:text-black border-2 border-utd-secondary/30 text-black rounded-2xl justify-start p-4"
          size="sm"
          variant="ghost"
        >
          <Plus className="h-4 w-4 mr-2" />
          Add Chat
        </Button>
      </div>

      <SidebarGroup>
        <SidebarGroupLabel className="text-black font-semibold px-4 py-2">
          Conversations
        </SidebarGroupLabel>
        <SidebarGroupContent>
          {error && (
            <p className="px-4 pb-2 text-sm text-red-700">{error}</p>
          )}
          {loading && (
            <p className="px-4 pb-2 text-sm text-black/60">Loading conversations…</p>
          )}
          {!loading && conversations.length === 0 && !error && (
            <p className="px-4 pb-2 text-sm text-black/60">No conversations yet</p>
          )}
          <SidebarMenu>
            {conversations.map((conversation) => (
              <SidebarMenuItem key={conversation.id}>
                <div className="flex items-center gap-2 w-full px-0">
                  <SidebarMenuButton
                    onClick={() => onSelectConversation(conversation.id)}
                    className={`flex-1 justify-start text-left rounded-none transition-colors px-4 py-3 ${
                      selectedConversationId === conversation.id
                        ? "bg-utd-secondary text-white hover:text-white hover:bg-utd-secondary/80"
                        : "text-black hover:bg-utd-secondary/30"
                    }`}
                  >
                    <MessageSquare className="h-4 w-4" />
                    <span className="truncate text-sm">
                      {conversation.title}
                    </span>
                  </SidebarMenuButton>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDeleteConversation(conversation.id)}
                    className="h-8 w-8 p-0 hover:bg-utd-secondary/30 text-black"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </div>
  );
}
