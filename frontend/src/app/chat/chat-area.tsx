"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Send } from "lucide-react";
import { Message, Conversation } from "@/types";
import QuoteComponent from "./quote";

interface ChatAreaProps {
  selectedConversationId: string;
  conversations: Conversation[];
  onUpdateConversation: (conversationId: string, messages: Message[]) => void;
}

export default function ChatArea({
  selectedConversationId,
  conversations,
  onUpdateConversation,
}: ChatAreaProps) {
  const [inputValue, setInputValue] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentConversation = conversations.find(
    (conv) => conv.id === selectedConversationId
  );

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [currentConversation?.messages]);

  const sendMessage = async () => {
    if (!inputValue.trim() || isStreaming || !currentConversation) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: [{ type: "text", message: inputValue.trim() }],
      role: "user",
      timestamp: new Date(),
    };

    // Add user message
    const updatedMessages = [...currentConversation.messages, userMessage];
    onUpdateConversation(selectedConversationId, updatedMessages);

    setInputValue("");
    setIsStreaming(true);

    // Simulate streaming response
    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      content: [],
      role: "assistant",
      timestamp: new Date(),
    };

    // Add empty assistant message
    const messagesWithAssistant = [...updatedMessages, assistantMessage];
    onUpdateConversation(selectedConversationId, messagesWithAssistant);

    // Simulate streaming
    const mockResponses: Array<
      Array<{ type: "text" | "source"; message: string }>
    > = [
      [
        {
          type: "text" as const,
          message:
            "I can definitely help you navigate UTD's systems and find the information you're looking for.",
        },
        {
          type: "source" as const,
          message:
            "UTD offers over 140 academic programs across eight schools.",
        },
        {
          type: "text" as const,
          message: "Let me know if you need help with any specific aspect!",
        },
        {
          type: "source" as const,
          message:
            "The university has a student population of over 30,000 students.",
        },
      ],
    ];

    const randomResponse =
      mockResponses[Math.floor(Math.random() * mockResponses.length)];

    // Stream each content item one by one
    for (
      let contentIndex = 0;
      contentIndex < randomResponse.length;
      contentIndex++
    ) {
      const contentItem = randomResponse[contentIndex];

      if (contentItem.type === "text") {
        // Stream text content character by character
        for (
          let charIndex = 0;
          charIndex <= contentItem.message.length;
          charIndex++
        ) {
          await new Promise((resolve) => setTimeout(resolve, 5));
          const streamingMessage = {
            ...assistantMessage,
            content: [
              ...randomResponse.slice(0, contentIndex),
              {
                ...contentItem,
                message: contentItem.message.slice(0, charIndex),
              },
            ],
          };
          const finalMessages = [...updatedMessages, streamingMessage];
          onUpdateConversation(selectedConversationId, finalMessages);
        }
      } else {
        // For source content, add it immediately
        const streamingMessage = {
          ...assistantMessage,
          content: randomResponse.slice(0, contentIndex + 1),
        };
        const finalMessages = [...updatedMessages, streamingMessage];
        onUpdateConversation(selectedConversationId, finalMessages);
        await new Promise((resolve) => setTimeout(resolve, 100)); // Small delay between items
      }
    }

    setIsStreaming(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  if (!currentConversation) {
    return (
      <div className="flex-1 flex flex-col">
        <div className="p-4 border-b border-utd-primary/20">
          <h1 className="text-lg font-semibold text-utd-primary">Ask Temoc</h1>
        </div>
        <div className="flex-1 p-4">
          <div className="text-center text-utd-primary/60">
            Select a conversation to start chatting
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col w-full">
      <div className="flex-1 overflow-y-auto p-4">
        <div className="w-full space-y-4">
          {currentConversation.messages.map((message) => (
            <div
              key={message.id}
              className={`flex ${
                message.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <Card
                className={`max-w-[80%] p-4 ${
                  message.role === "user"
                    ? "bg-utd-primary text-white"
                    : "bg-muted border-utd-primary/20"
                }`}
              >
                <div className="space-y-2">
                  {message.content.map((contentItem, index) => (
                    <div key={index}>
                      {contentItem.type === "text" ? (
                        <p className="whitespace-pre-wrap">
                          {contentItem.message}
                          {message.role === "assistant" &&
                            isStreaming &&
                            message.id ===
                              currentConversation.messages[
                                currentConversation.messages.length - 1
                              ]?.id &&
                            index === message.content.length - 1 && (
                              <span className="animate-pulse text-utd-primary">
                                |
                              </span>
                            )}
                        </p>
                      ) : (
                        <QuoteComponent message={contentItem.message} />
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="p-4 border-t border-utd-primary/20">
        <div className="w-full">
          <div className="flex gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Ask Temoc anything about UTD..."
              disabled={isStreaming}
              className="flex-1 border-utd-primary/30 focus:border-utd-primary focus:ring-utd-primary/20"
            />
            <Button
              onClick={sendMessage}
              disabled={!inputValue.trim() || isStreaming}
              size="icon"
              className="bg-utd-secondary hover:bg-utd-secondary/90 text-white"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
