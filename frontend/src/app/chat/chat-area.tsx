"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Send } from "lucide-react";
import { Message, Conversation } from "@/types";
import QuoteComponent from "./quote";
import { AssistantFormattedText } from "./assistant-text";
import { chatAPI, type ChatResponse } from "@/lib/api";

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
  const [isBackendAvailable, setIsBackendAvailable] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  // Check backend availability on mount
  useEffect(() => {
    const checkBackend = async () => {
      try {
        const available = await chatAPI.isBackendAvailable();
        setIsBackendAvailable(available);
      } catch (error) {
        console.error("Backend check failed:", error);
        setIsBackendAvailable(false);
      }
    };

    checkBackend();
  }, []);

  const sendMessage = async () => {
    const trimmedInput = inputValue.trim();
    if (!trimmedInput || isStreaming || !currentConversation) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: [{ type: "text", message: trimmedInput }],
      role: "user",
      timestamp: new Date(),
    };

    // Add user message
    const updatedMessages = [...currentConversation.messages, userMessage];
    onUpdateConversation(selectedConversationId, updatedMessages);

    setInputValue("");
    setIsStreaming(true);
    setError(null);

    const assistantMessage: Message = {
      id: (Date.now() + 1).toString(),
      content: [],
      role: "assistant",
      timestamp: new Date(),
    };

    // Show assistant bubble immediately so loading copy appears during the fetch
    onUpdateConversation(selectedConversationId, [
      ...updatedMessages,
      assistantMessage,
    ]);

    try {
      // Sending doubles as the availability probe: a pre-flight health check only
      // added latency and turned slow cold starts into a false "unavailable".
      const responseStream = await chatAPI.sendMessage(trimmedInput);
      setIsBackendAvailable(true);
      
      const accumulatedContent: Message["content"] = [];

      for await (const chunk of responseStream) {
        if (chunk.type === 'text') {
          // Text events are deltas: append to the current text item.
          const last = accumulatedContent[accumulatedContent.length - 1];
          if (last?.type === 'text') {
            last.message += chunk.message;
          } else {
            accumulatedContent.push({ type: 'text', message: chunk.message });
          }
          const streamingMessage = {
            ...assistantMessage,
            content: accumulatedContent.map((c) => ({ ...c })),
          };
          const finalMessages = [...updatedMessages, streamingMessage];
          onUpdateConversation(selectedConversationId, finalMessages);
        } else if (chunk.type === 'source') {
          const s = chunk as ChatResponse;
          accumulatedContent.push({
            type: 'source',
            message: s.message,
            ...(typeof s.index === "number" ? { index: s.index } : {}),
            ...(typeof s.n === "number" ? { n: s.n } : {}),
            ...(typeof s.url === "string" ? { url: s.url } : {}),
            ...(typeof s.href === "string" ? { href: s.href } : {}),
            ...(typeof s.title === "string" ? { title: s.title } : {}),
          });
          const streamingMessage = {
            ...assistantMessage,
            content: accumulatedContent.map((c) => ({ ...c })),
          };
          const finalMessages = [...updatedMessages, streamingMessage];
          onUpdateConversation(selectedConversationId, finalMessages);
        } else if (chunk.type === 'done') {
          break;
        }
        // Unknown event types are ignored.
      }

      console.log("[chat] stream complete — full response", {
        userMessage: trimmedInput,
        assistantContent: accumulatedContent.map((c) => ({ ...c })),
      });
    } catch (error) {
      console.error("Error sending message:", error);
      setError(error instanceof Error ? error.message : "An error occurred while sending your message.");
      
      // Add error message to conversation
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: [{ type: "text", message: "Sorry, I encountered an error. Please try again." }],
        role: "assistant",
        timestamp: new Date(),
      };
      
      const finalMessages = [...updatedMessages, errorMessage];
      onUpdateConversation(selectedConversationId, finalMessages);
    } finally {
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
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
                  {message.role === "assistant" &&
                    isStreaming &&
                    message.id ===
                      currentConversation.messages[
                        currentConversation.messages.length - 1
                      ]?.id &&
                    message.content.length === 0 && (
                      <p className="italic text-muted-foreground">
                        Temoc is fetching the latest content from the
                        interwebs...
                      </p>
                    )}
                  {message.content.map((contentItem, index) => (
                    <div key={index}>
                      {contentItem.type === "text" ? (
                        <p className="whitespace-pre-wrap">
                          {message.role === "assistant" ? (
                            <AssistantFormattedText
                              text={contentItem.message}
                              content={message.content}
                            />
                          ) : (
                            contentItem.message
                          )}
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
          {/* Error message */}
          {error && (
            <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-700 text-sm">{error}</p>
            </div>
          )}
          
          {/* Backend status */}
          {!isBackendAvailable && (
            <div className="mb-3 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
              <p className="text-yellow-700 text-sm">
                Couldn’t reach the backend just now. Sending a message will try
                again.
              </p>
            </div>
          )}
          
          <div className="flex gap-2">
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask Temoc anything about UTD..."
              disabled={isStreaming}
              className="flex-1 border-utd-primary/30 focus:border-utd-primary focus:ring-utd-primary/20"
            />
            <Button
              onClick={sendMessage}
              disabled={!inputValue.trim() || isStreaming}
              size="icon"
              className="bg-utd-secondary hover:bg-utd-secondary/90 text-white disabled:opacity-50"
            >
              {isStreaming ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
