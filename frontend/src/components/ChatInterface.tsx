"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ChatMessageItem, ContextChunk } from "@/types";

interface ChatInterfaceProps {
  repositoryId: string;
  repositoryName: string;
}

function removeUnansweredMessages(messages: ChatMessageItem[]): ChatMessageItem[] {
  const completedMessages = [...messages];
  while (
    completedMessages.length > 0 &&
    completedMessages[completedMessages.length - 1].role === "user"
  ) {
    completedMessages.pop();
  }
  return completedMessages;
}

export default function ChatInterface({
  repositoryId,
  repositoryName,
}: ChatInterfaceProps) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [isInitializing, setIsInitializing] = useState(true);
  const [initializationAttempt, setInitializationAttempt] = useState(0);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const [streamingChunks, setStreamingChunks] = useState<ContextChunk[]>([]);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  // Initialize or fetch first session
  useEffect(() => {
    let active = true;

    async function initChat() {
      setIsInitializing(true);
      setError(null);
      try {
        const sessions = await api.listChatSessions(repositoryId);
        if (sessions.length > 0) {
          const history = await api.getChatMessages(repositoryId, sessions[0].id);
          if (active) {
            setSessionId(sessions[0].id);
            setMessages(removeUnansweredMessages(history.messages));
          }
        } else {
          const newSession = await api.createChatSession(
            repositoryId,
            `Onboarding Chat - ${repositoryName}`
          );
          if (active) setSessionId(newSession.id);
        }
      } catch (err) {
        console.error("Failed to init chat session:", err);
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Failed to initialize the onboarding chat."
          );
        }
      } finally {
        if (active) setIsInitializing(false);
      }
    }

    void initChat();
    return () => {
      active = false;
    };
  }, [repositoryId, repositoryName, initializationAttempt]);

  const handleNewChat = async () => {
    if (isInitializing || isStreaming) return;
    setIsInitializing(true);
    setError(null);
    try {
      const newSession = await api.createChatSession(
        repositoryId,
        `Onboarding Chat - ${repositoryName}`
      );
      setSessionId(newSession.id);
      setMessages([]);
      setInput("");
      setStreamingContent("");
      setStreamingChunks([]);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start a new chat."
      );
    } finally {
      setIsInitializing(false);
    }
  };

  const handleSend = async (customPrompt?: string) => {
    const textToSend = customPrompt || input;
    if (!textToSend.trim() || !sessionId || isStreaming) return;

    setInput("");
    setError(null);

    // Optimistically add user message
    const tempUserMsg: ChatMessageItem = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: textToSend,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    setIsStreaming(true);
    setStreamingContent("");
    setStreamingChunks([]);

    let accumulatedContent = "";
    let accumulatedChunks: ContextChunk[] = [];

    await api.streamChatMessage(repositoryId, sessionId, textToSend, {
      onContext: (chunks) => {
        accumulatedChunks = chunks;
        setStreamingChunks(chunks);
      },
      onToken: (token) => {
        accumulatedContent += token;
        setStreamingContent((prev) => prev + token);
      },
      onDone: (messageId) => {
        setIsStreaming(false);
        const finalAssistantMsg: ChatMessageItem = {
          id: messageId,
          role: "assistant",
          content: accumulatedContent,
          context_chunks: accumulatedChunks.length > 0 ? { chunks: accumulatedChunks } : null,
          created_at: new Date().toISOString(),
        };
        setMessages((prev) => [...prev, finalAssistantMsg]);
        setStreamingContent("");
        setStreamingChunks([]);
      },
      onError: (err) => {
        setIsStreaming(false);
        setMessages((prev) => prev.filter((message) => message.id !== tempUserMsg.id));
        setStreamingContent("");
        setStreamingChunks([]);
        setError(err);
      },
    });
  };

  return (
    <div className="flex h-[680px] flex-col rounded-xl border border-gray-800 bg-gray-950/80 backdrop-blur">
      {/* Chat Header */}
      <div className="flex items-center justify-between border-b border-gray-800 px-6 py-4">
        <div>
          <h3 className="font-semibold text-white">Architecture & Onboarding Assistant</h3>
          <p className="text-xs text-gray-500">
            Powered by OpenRouter Gemma + local BM25 and AST search
          </p>
        </div>
        <button
          type="button"
          onClick={handleNewChat}
          disabled={isInitializing || isStreaming}
          className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs font-medium text-gray-300 hover:border-primary-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
        >
          New chat
        </button>
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center h-full text-center space-y-4">
            <div className="text-3xl">💡</div>
            <div className="max-w-md space-y-1">
              <h4 className="font-medium text-gray-200">Start exploring this codebase</h4>
              <p className="text-xs text-gray-500">
                Ask architectural questions or select a recommended query below:
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {[
                "What is the high-level architecture of this codebase?",
                "Which modules have the most incoming dependencies?",
                "Explain the primary entry points and data flow.",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => handleSend(suggestion)}
                  className="rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-1.5 text-xs text-gray-300 hover:border-primary-500 hover:text-white transition-all text-left"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${
              msg.role === "user" ? "items-end" : "items-start"
            }`}
          >
            <div
              className={`max-w-2xl rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-primary-600 text-white rounded-br-none"
                  : "bg-gray-900 text-gray-200 border border-gray-800 rounded-bl-none"
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>

              {/* Retrieved Context Preview for Assistant Messages */}
              {msg.context_chunks?.chunks && msg.context_chunks.chunks.length > 0 && (
                <div className="mt-3 pt-3 border-t border-gray-800 space-y-2">
                  <span className="text-[10px] uppercase font-bold text-gray-500 tracking-wider block">
                    Retrieved RAG Code Context:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {msg.context_chunks.chunks.map((chunk, idx) => (
                      <span
                        key={idx}
                        className="rounded border border-gray-700/60 bg-gray-950 px-2 py-0.5 text-[11px] text-gray-400"
                        title={chunk.content}
                      >
                        {chunk.file_path} ({chunk.method})
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <span className="text-[10px] text-gray-600 mt-1 px-1">
              {new Date(msg.created_at).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </div>
        ))}

        {/* Live Streaming Assistant Message */}
        {isStreaming && (
          <div className="flex flex-col items-start">
            <div className="max-w-2xl rounded-2xl bg-gray-900 border border-gray-800 px-4 py-3 text-sm text-gray-200 rounded-bl-none">
              {streamingChunks.length > 0 && (
                <div className="mb-3 pb-2 border-b border-gray-800">
                  <span className="text-[10px] text-primary-400 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-primary-400 animate-pulse" />
                    Retrieved {streamingChunks.length} hybrid code contexts
                  </span>
                </div>
              )}
              <div className="whitespace-pre-wrap">
                {streamingContent}
                <span className="inline-block h-4 w-1.5 bg-primary-400 animate-pulse ml-0.5" />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="border-t border-gray-800 p-4 bg-gray-950">
        {error && (
          <div className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-1.5 text-xs text-red-400">
            {error}
            {!sessionId && !isInitializing && (
              <button
                type="button"
                onClick={() => setInitializationAttempt((attempt) => attempt + 1)}
                className="ml-2 font-semibold text-red-300 underline hover:text-white"
              >
                Retry
              </button>
            )}
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-2"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              isInitializing
                ? "Connecting to onboarding chat..."
                : "Ask about architectural patterns, dependency flow, or onboarding..."
            }
            disabled={isStreaming || isInitializing || !sessionId}
            className="flex-1 rounded-lg border border-gray-800 bg-gray-900 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={isStreaming || isInitializing || !sessionId || !input.trim()}
            className="rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
