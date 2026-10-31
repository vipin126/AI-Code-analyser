"use client";

import Link from "next/link";
import { RepositoryItem, RepositoryStatus } from "@/types";

interface RepositoryCardProps {
  repo: RepositoryItem;
  onDelete?: (id: string) => void;
}

const statusConfig: Record<
  RepositoryStatus,
  { label: string; bg: string; text: string; border: string; animate: boolean }
> = {
  pending: {
    label: "Pending",
    bg: "bg-gray-500/10",
    text: "text-gray-400",
    border: "border-gray-500/30",
    animate: false,
  },
  cloning: {
    label: "Cloning...",
    bg: "bg-blue-500/10",
    text: "text-blue-400",
    border: "border-blue-500/30",
    animate: true,
  },
  parsing: {
    label: "Parsing AST...",
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    border: "border-amber-500/30",
    animate: true,
  },
  embedding: {
    label: "Embedding Chunks...",
    bg: "bg-purple-500/10",
    text: "text-purple-400",
    border: "border-purple-500/30",
    animate: true,
  },
  ready: {
    label: "Ready",
    bg: "bg-emerald-500/10",
    text: "text-emerald-400",
    border: "border-emerald-500/30",
    animate: false,
  },
  error: {
    label: "Failed",
    bg: "bg-red-500/10",
    text: "text-red-400",
    border: "border-red-500/30",
    animate: false,
  },
};

export default function RepositoryCard({ repo, onDelete }: RepositoryCardProps) {
  const status = statusConfig[repo.status] || statusConfig.pending;
  const progressPercent =
    repo.total_files > 0
      ? Math.round((repo.parsed_files / repo.total_files) * 100)
      : repo.status === "ready"
      ? 100
      : 0;

  return (
    <div className="flex flex-col justify-between rounded-xl border border-gray-800 bg-gray-900/40 p-5 backdrop-blur transition-all hover:border-gray-700 hover:bg-gray-900/60 shadow-sm">
      <div className="space-y-4">
        {/* Top Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <h3 className="font-semibold text-lg text-white truncate max-w-xs sm:max-w-md">
              {repo.name}
            </h3>
            <a
              href={repo.github_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-gray-500 hover:text-primary-400 transition-colors inline-flex items-center gap-1"
            >
              <span>{repo.github_url}</span>
              <span>↗</span>
            </a>
          </div>

          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${status.bg} ${status.text} ${status.border}`}
          >
            {status.animate && (
              <span className="h-1.5 w-1.5 rounded-full bg-current animate-ping" />
            )}
            {status.label}
          </span>
        </div>

        {repo.status === "error" && repo.error_message && (
          <p className="line-clamp-3 text-xs text-red-300" role="alert">
            {repo.error_message}
          </p>
        )}

        {/* Processing Stats / Progress Bar */}
        {repo.status !== "ready" && repo.status !== "error" && (
          <div className="space-y-1.5 pt-1">
            <div className="flex justify-between text-xs text-gray-400">
              <span>Progress</span>
              <span>{progressPercent}%</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
              <div
                className="h-full bg-primary-500 transition-all duration-300"
                style={{ width: `${Math.max(5, progressPercent)}%` }}
              />
            </div>
          </div>
        )}

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 gap-2 rounded-lg bg-gray-950/60 p-3 text-xs">
          <div>
            <span className="text-gray-500 block">Total Files</span>
            <span className="font-medium text-gray-200">{repo.total_files}</span>
          </div>
          <div>
            <span className="text-gray-500 block">Parsed AST Files</span>
            <span className="font-medium text-gray-200">{repo.parsed_files}</span>
          </div>
        </div>
      </div>

      {/* Action Footer */}
      <div className="mt-5 flex items-center justify-between border-t border-gray-800/80 pt-4">
        <span className="text-xs text-gray-500">
          {new Date(repo.created_at).toLocaleDateString()}
        </span>

        <div className="flex items-center gap-2">
          {onDelete && (
            <button
              onClick={() => onDelete(repo.id)}
              className="rounded-lg p-2 text-gray-400 hover:bg-red-500/10 hover:text-red-400 transition-colors text-xs"
              title="Delete repository"
            >
              ✕
            </button>
          )}

          <Link
            href={`/repository/${repo.id}`}
            className="rounded-lg bg-primary-600 px-3.5 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-primary-500 transition-colors"
          >
            Explore Repo →
          </Link>
        </div>
      </div>
    </div>
  );
}
