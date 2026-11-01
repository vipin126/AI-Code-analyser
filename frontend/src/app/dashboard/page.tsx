"use client";

import { useEffect, useState } from "react";
import RepositoryForm from "@/components/RepositoryForm";
import RepositoryCard from "@/components/RepositoryCard";
import { api } from "@/lib/api";
import { RepositoryItem } from "@/types";

function uniqueRepositories(repositories: RepositoryItem[]): RepositoryItem[] {
  return [...new Map(repositories.map((repo) => [repo.id, repo])).values()];
}

export default function DashboardPage() {
  const [repositories, setRepositories] = useState<RepositoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRepos = async () => {
    try {
      const data = await api.listRepositories();
      setRepositories(uniqueRepositories(data));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load repositories");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRepos();

    // Polling interval (every 4 seconds) to update active processing states
    const interval = setInterval(() => {
      api
        .listRepositories()
        .then((data) => setRepositories(uniqueRepositories(data)))
        .catch((err) => console.error("Failed to refresh repositories:", err));
    }, 4000);

    return () => clearInterval(interval);
  }, []);

  const handleCreated = (newRepo: RepositoryItem) => {
    setRepositories((prev) =>
      uniqueRepositories([newRepo, ...prev.filter((repo) => repo.id !== newRepo.id)])
    );
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteRepository(id);
      setRepositories((prev) => prev.filter((r) => r.id !== id));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete repository");
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Page Title & Intro */}
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-white">
          Repository Analyzer Dashboard
        </h1>
        <p className="mt-1 text-sm text-gray-400">
          Manage your parsed repositories, view ongoing ingestion tasks, and inspect
          architectural graphs.
        </p>
      </div>

      {/* Submission Form */}
      <RepositoryForm onSuccess={handleCreated} />

      {/* Repositories List */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-white">Analyzed Repositories</h2>
          <span className="text-xs text-gray-500">
            {repositories.length} {repositories.length === 1 ? "repository" : "repositories"}
          </span>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-400">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex h-40 items-center justify-center rounded-xl border border-gray-800 bg-gray-900/20 text-gray-400 text-sm">
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-primary-500 animate-ping" />
              Loading repositories...
            </span>
          </div>
        ) : repositories.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-gray-800 p-12 text-center">
            <div className="text-4xl mb-3">📂</div>
            <h3 className="font-semibold text-gray-300">No repositories added yet</h3>
            <p className="text-xs text-gray-500 max-w-sm mt-1">
              Submit your first public GitHub repository URL above to trigger the
              Tree-sitter AST and hybrid RAG indexing pipeline.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
            {repositories.map((repo) => (
              <RepositoryCard
                key={repo.id}
                repo={repo}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
