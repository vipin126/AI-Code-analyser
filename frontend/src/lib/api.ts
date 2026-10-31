import {
  CodeFileDetail,
  CodeFileListResponse,
  DependencyGraphData,
  RepositoryDetail,
  RepositoryItem,
  ChatSessionItem,
  ChatMessageItem,
  ContextChunk,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
    ...options,
  });

  if (!response.ok) {
    let errorDetail = `HTTP error ${response.status}`;
    try {
      const errorJson = await response.json();
      errorDetail = errorJson.detail || errorDetail;
    } catch {
      // ignore JSON parse failure
    }
    throw new Error(errorDetail);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const api = {
  // ── Repositories ───────────────────────────────────────────
  async listRepositories(): Promise<RepositoryItem[]> {
    return request<RepositoryItem[]>("/repositories");
  },

  async getRepository(id: string): Promise<RepositoryDetail> {
    return request<RepositoryDetail>(`/repositories/${id}`);
  },

  async submitRepository(url: string): Promise<RepositoryItem> {
    return request<RepositoryItem>("/repositories", {
      method: "POST",
      body: JSON.stringify({ url }),
    });
  },

  async deleteRepository(id: string): Promise<void> {
    return request<void>(`/repositories/${id}`, {
      method: "DELETE",
    });
  },

  // ── Analysis ───────────────────────────────────────────────
  async getDependencyGraph(repoId: string): Promise<DependencyGraphData> {
    return request<DependencyGraphData>(`/repositories/${repoId}/graph`);
  },

  async listFiles(
    repoId: string,
    language?: string,
    skip = 0,
    limit = 100
  ): Promise<CodeFileListResponse> {
    const params = new URLSearchParams();
    if (language) params.append("language", language);
    params.append("skip", skip.toString());
    params.append("limit", limit.toString());
    return request<CodeFileListResponse>(`/repositories/${repoId}/files?${params.toString()}`);
  },

  async getFileDetail(repoId: string, fileId: string): Promise<CodeFileDetail> {
    return request<CodeFileDetail>(`/repositories/${repoId}/files/${fileId}`);
  },

  // ── Chat ───────────────────────────────────────────────────
  async listChatSessions(repoId: string): Promise<ChatSessionItem[]> {
    return request<ChatSessionItem[]>(`/repositories/${repoId}/chat`);
  },

  async createChatSession(repoId: string, title = "New Chat"): Promise<ChatSessionItem> {
    return request<ChatSessionItem>(`/repositories/${repoId}/chat`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },

  async getChatMessages(
    repoId: string,
    sessionId: string
  ): Promise<{ session_id: string; title: string; messages: ChatMessageItem[] }> {
    return request<{ session_id: string; title: string; messages: ChatMessageItem[] }>(
      `/repositories/${repoId}/chat/${sessionId}`
    );
  },

  /**
   * Stream a chat message via SSE
   */
  async streamChatMessage(
    repoId: string,
    sessionId: string,
    content: string,
    handlers: {
      onContext?: (chunks: ContextChunk[]) => void;
      onToken?: (token: string) => void;
      onDone?: (messageId: string) => void;
      onError?: (error: string) => void;
    }
  ): Promise<void> {
    const url = `${API_BASE}/repositories/${repoId}/chat/${sessionId}/messages`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });

    if (!response.ok) {
      let err = `Failed to send message: ${response.statusText}`;
      try {
        const data = await response.json();
        err = data.detail || err;
      } catch {
        // ignore
      }
      handlers.onError?.(err);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      handlers.onError?.("No response body available to stream");
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        // Keep the incomplete part in buffer
        buffer = events.pop() || "";

        for (const rawEvent of events) {
          if (!rawEvent.trim()) continue;
          const lines = rawEvent.split("\n");
          let eventType = "message";
          let eventData = "";

          for (const line of lines) {
            if (line.startsWith("event: ")) {
              eventType = line.substring(7).trim();
            } else if (line.startsWith("data: ")) {
              eventData = line.substring(6).trim();
            }
          }

          if (!eventData) continue;

          try {
            const parsed = JSON.parse(eventData);
            if (eventType === "context") {
              handlers.onContext?.(parsed.chunks || []);
            } else if (eventType === "token") {
              handlers.onToken?.(parsed.content || "");
            } else if (eventType === "done") {
              handlers.onDone?.(parsed.message_id || "");
            } else if (eventType === "error") {
              handlers.onError?.(parsed.detail || "Streaming error");
            }
          } catch (e) {
            console.error("Failed to parse SSE event data:", eventData, e);
          }
        }
      }
    } catch (err) {
      handlers.onError?.(err instanceof Error ? err.message : String(err));
    }
  },
};
