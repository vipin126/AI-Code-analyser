/**
 * Shared TypeScript interfaces for the AI Code Analyzer frontend.
 */

// ── Health Check ──────────────────────────────────────────
export interface HealthResponse {
  status: string;
}

export interface PingResponse {
  message: string;
  environment: string;
}

// ── API Error ─────────────────────────────────────────────
export interface ApiError {
  detail: string;
}

// ── Repository Types ─────────────────────────────────────
export type RepositoryStatus =
  | "pending"
  | "cloning"
  | "parsing"
  | "embedding"
  | "ready"
  | "error";

export interface RepositoryItem {
  id: string;
  name: string;
  github_url: string;
  status: RepositoryStatus;
  total_files: number;
  parsed_files: number;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface RepositoryDetail extends RepositoryItem {
  language_stats?: Record<string, number> | null;
  default_branch?: string | null;
}

export interface RepositoryCreateInput {
  url: string;
}

// ── Graph & Analysis Types ───────────────────────────────
export interface GraphNode {
  id: string;
  name: string;
  type: string;
  file_path: string;
  line_start: number;
  line_end: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface DependencyGraphData {
  repository_id: string;
  repository_name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
  language_stats: Record<string, number>;
}

export interface CodeFileSummary {
  id: string;
  file_path: string;
  language: string;
  line_count: number;
  size_bytes: number;
  node_count: number;
  dependency_count: number;
}

export interface CodeFileListResponse {
  repository_id: string;
  total: number;
  files: CodeFileSummary[];
}

export interface CodeFileDetail {
  id: string;
  file_path: string;
  language: string;
  line_count: number;
  size_bytes: number;
  content_hash: string;
  ast_data: {
    nodes?: Array<{
      name: string;
      type: string;
      file_path: string;
      line_start: number;
      line_end: number;
      docstring?: string | null;
      parameters?: string[] | null;
    }>;
  } | null;
  dependencies: {
    edges?: Array<{
      source: string;
      target: string;
      relationship: string;
    }>;
  } | null;
  embedding_id?: string | null;
  summary?: string | null;
}

// ── Chat Types ───────────────────────────────────────────
export interface ChatSessionItem {
  id: string;
  title: string;
  repository_id: string;
  message_count: number;
  created_at: string;
}

export interface ContextChunk {
  file_path: string;
  start_line: number;
  end_line: number;
  language: string;
  relevance_score: number;
  content: string;
  method: string;
}

export interface ChatMessageItem {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  context_chunks?: { chunks?: ContextChunk[] } | null;
  token_count?: number | null;
  created_at: string;
}
