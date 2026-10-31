"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { RepositoryItem } from "@/types";

interface RepositoryFormProps {
  onSuccess: (newRepo: RepositoryItem) => void;
}

const QUICK_EXAMPLES = [
  "https://github.com/fastapi/fastapi",
  "https://github.com/pallets/flask",
  "https://github.com/expressjs/express",
];

export default function RepositoryForm({ onSuccess }: RepositoryFormProps) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const repo = await api.submitRepository(url.trim());
      setUrl("");
      onSuccess(repo);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to analyze repository");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 p-6 backdrop-blur">
      <h2 className="text-xl font-bold text-white mb-2">Ingest New Repository</h2>
      <p className="text-sm text-gray-400 mb-6">
        Enter a public GitHub repository URL to initiate AST dependency extraction,
        vector indexing, and architecture visualization.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repository"
            required
            disabled={loading}
            className="flex-1 rounded-lg border border-gray-800 bg-gray-950 px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !url.trim()}
            className="inline-flex items-center justify-center rounded-lg bg-primary-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-gray-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <svg
                  className="h-4 w-4 animate-spin text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Ingesting...
              </span>
            ) : (
              "Start Analysis →"
            )}
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400">
            {error}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 pt-2">
          <span className="text-xs text-gray-500">Quick Test Examples:</span>
          {QUICK_EXAMPLES.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setUrl(example)}
              className="rounded-md border border-gray-800 bg-gray-950 px-2.5 py-1 text-xs text-gray-400 hover:border-gray-700 hover:text-gray-200 transition-colors"
            >
              {example.replace("https://github.com/", "")}
            </button>
          ))}
        </div>
      </form>
    </div>
  );
}
