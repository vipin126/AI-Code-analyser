"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import MermaidDiagram from "@/components/MermaidDiagram";
import ChatInterface from "@/components/ChatInterface";
import { api } from "@/lib/api";
import {
  CodeFileSummary,
  DependencyGraphData,
  RepositoryDetail,
} from "@/types";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function RepositoryDetailPage({ params }: PageProps) {
  const { id } = use(params);

  const [repo, setRepo] = useState<RepositoryDetail | null>(null);
  const [graphData, setGraphData] = useState<DependencyGraphData | null>(null);
  const [files, setFiles] = useState<CodeFileSummary[]>([]);
  const [activeTab, setActiveTab] = useState<"diagram" | "files" | "chat">("diagram");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        const repoDetail = await api.getRepository(id);
        setRepo(repoDetail);

        if (repoDetail.status === "ready") {
          try {
            const [graph, filesRes] = await Promise.all([
              api.getDependencyGraph(id),
              api.listFiles(id),
            ]);
            setGraphData(graph);
            setFiles(filesRes.files);
          } catch (e) {
            console.error("Secondary graph/file load error:", e);
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load repository");
      } finally {
        setLoading(false);
      }
    }

    loadData();

    // If still in progress, poll until ready
    const interval = setInterval(async () => {
      try {
        const update = await api.getRepository(id);
        setRepo(update);
        if (update.status === "ready" && !graphData) {
          const [graph, filesRes] = await Promise.all([
            api.getDependencyGraph(id),
            api.listFiles(id),
          ]);
          setGraphData(graph);
          setFiles(filesRes.files);
        }
        if (update.status === "ready" || update.status === "error") {
          clearInterval(interval);
        }
      } catch {
        // ignore polling failures
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [id, graphData]);

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center text-sm text-gray-400">
        <span className="inline-flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-primary-500 animate-ping" />
          Loading repository architecture...
        </span>
      </div>
    );
  }

  if (error || !repo) {
    return (
      <div className="mx-auto max-w-4xl px-4 py-16 text-center">
        <h2 className="text-xl font-bold text-white mb-2">Repository Not Found</h2>
        <p className="text-sm text-gray-400 mb-6">{error || "Could not retrieve repository details."}</p>
        <Link
          href="/dashboard"
          className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white hover:bg-primary-500"
        >
          ← Return to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Breadcrumb & Header */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <Link href="/dashboard" className="hover:text-gray-300">
            Dashboard
          </Link>
          <span>/</span>
          <span className="text-gray-300">{repo.name}</span>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white">{repo.name}</h1>
            <a
              href={repo.github_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-primary-400 hover:underline mt-1 inline-block"
            >
              {repo.github_url} ↗
            </a>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                repo.status === "ready"
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : repo.status === "error"
                  ? "bg-red-500/10 text-red-400 border border-red-500/30"
                  : "bg-blue-500/10 text-blue-400 border border-blue-500/30 animate-pulse"
              }`}
            >
              Status: {repo.status.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Language Statistics Badges */}
        {repo.language_stats && Object.keys(repo.language_stats).length > 0 && (
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="text-xs text-gray-500">Detected Languages:</span>
            {Object.entries(repo.language_stats).map(([lang, count]) => (
              <span
                key={lang}
                className="rounded-md border border-gray-800 bg-gray-900/60 px-2.5 py-0.5 text-xs text-gray-300"
              >
                {lang}: <strong className="text-white">{count}</strong>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-800">
        <nav className="flex space-x-8">
          <button
            onClick={() => setActiveTab("diagram")}
            className={`border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === "diagram"
                ? "border-primary-500 text-white"
                : "border-transparent text-gray-400 hover:border-gray-700 hover:text-gray-300"
            }`}
          >
            📊 Architecture Diagram
          </button>
          <button
            onClick={() => setActiveTab("files")}
            className={`border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === "files"
                ? "border-primary-500 text-white"
                : "border-transparent text-gray-400 hover:border-gray-700 hover:text-gray-300"
            }`}
          >
            📁 Files & AST Nodes ({files.length})
          </button>
          <button
            onClick={() => setActiveTab("chat")}
            className={`border-b-2 py-3 text-sm font-medium transition-colors ${
              activeTab === "chat"
                ? "border-primary-500 text-white"
                : "border-transparent text-gray-400 hover:border-gray-700 hover:text-gray-300"
            }`}
          >
            💬 AI Onboarding Chat
          </button>
        </nav>
      </div>

      {/* Tab Panels */}
      {repo.status === "error" ? (
        <div
          className="rounded-xl border border-red-500/30 bg-red-500/10 p-8 text-center space-y-3"
          role="alert"
        >
          <h3 className="font-semibold text-red-300">Repository analysis failed</h3>
          <p className="mx-auto max-w-2xl text-sm text-red-200">
            {repo.error_message || "An unexpected error stopped repository analysis."}
          </p>
          <p className="text-xs text-gray-400">
            Resolve the issue and submit the repository again from the dashboard.
          </p>
        </div>
      ) : repo.status !== "ready" ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-12 text-center space-y-3">
          <div className="h-6 w-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <h3 className="font-semibold text-white">Repository Ingestion In Progress</h3>
          <p className="text-xs text-gray-400 max-w-md mx-auto">
            Current stage: <strong className="text-primary-400">{repo.status}</strong>.
            Parsed {repo.parsed_files} of {repo.total_files} files.
            The interactive diagrams and RAG search will activate once finished.
          </p>
        </div>
      ) : (
        <>
          {activeTab === "diagram" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>
                  Visualizing {graphData?.node_count || 0} AST definition nodes and{" "}
                  {graphData?.edge_count || 0} dependency relationships.
                </span>
              </div>
              <MermaidDiagram graphData={graphData || undefined} />
            </div>
          )}

          {activeTab === "files" && (
            <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-950/60">
              <table className="min-w-full divide-y divide-gray-800 text-left text-xs">
                <thead className="bg-gray-900/70 text-gray-400">
                  <tr>
                    <th className="px-4 py-3 font-medium">File Path</th>
                    <th className="px-4 py-3 font-medium">Language</th>
                    <th className="px-4 py-3 font-medium">Lines</th>
                    <th className="px-4 py-3 font-medium">AST Nodes</th>
                    <th className="px-4 py-3 font-medium">Dependencies</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60 text-gray-300">
                  {files.map((file) => (
                    <tr key={file.id} className="hover:bg-gray-900/40">
                      <td className="px-4 py-3 font-mono text-white">{file.file_path}</td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-gray-800 px-2 py-0.5 text-[10px] text-gray-300">
                          {file.language}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-400">{file.line_count}</td>
                      <td className="px-4 py-3 text-primary-400 font-medium">
                        {file.node_count} nodes
                      </td>
                      <td className="px-4 py-3 text-gray-400">
                        {file.dependency_count} imports
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeTab === "chat" && (
            <ChatInterface repositoryId={repo.id} repositoryName={repo.name} />
          )}
        </>
      )}
    </div>
  );
}
