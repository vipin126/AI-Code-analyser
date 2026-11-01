import Link from "next/link";

export default function HomePage() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col items-center justify-center p-8">
      {/* Hero Section */}
      <div className="text-center max-w-3xl mx-auto space-y-8">
        {/* Logo / Icon */}
        <div className="flex items-center justify-center">
          <div className="relative">
            <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-primary-500 to-blue-600 opacity-75 blur-lg" />
            <div className="relative flex h-20 w-20 items-center justify-center rounded-full bg-gray-900 text-4xl shadow-2xl">
              🔬
            </div>
          </div>
        </div>

        {/* Title */}
        <h1 className="text-5xl font-extrabold tracking-tight sm:text-6xl">
          <span className="bg-gradient-to-r from-primary-400 via-blue-400 to-indigo-400 bg-clip-text text-transparent">
            AI Codebase Architecture
          </span>
          <br />
          <span className="text-white">& Onboarding Analyzer</span>
        </h1>

        {/* Description */}
        <p className="text-lg text-gray-400 leading-relaxed max-w-2xl mx-auto">
          Ingest any public GitHub repository, extract Abstract Syntax Tree (AST)
          dependency graphs via Tree-sitter, render interactive Mermaid diagrams, and
          explore the codebase with hybrid RAG streaming chat.
        </p>

        {/* Action Buttons */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-2">
          <Link
            href="/dashboard"
            className="w-full sm:w-auto inline-flex items-center justify-center rounded-xl bg-primary-600 px-8 py-3.5 text-base font-semibold text-white shadow-lg hover:bg-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-gray-950 transition-all"
          >
            Launch Dashboard →
          </Link>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full sm:w-auto inline-flex items-center justify-center rounded-xl border border-gray-800 bg-gray-900 px-6 py-3.5 text-base font-semibold text-gray-300 hover:border-gray-700 hover:bg-gray-800 hover:text-white transition-all"
          >
            View on GitHub
          </a>
        </div>

        {/* Status Badge */}
        <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-4 py-1.5 text-xs font-medium text-emerald-400">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
          Phase 3 Production Pipeline Active
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 gap-4 pt-8 sm:grid-cols-3">
          <FeatureCard
            icon="🌳"
            title="Tree-sitter AST"
            description="Multi-language syntax parsing extracting classes, functions, and import edges"
          />
          <FeatureCard
            icon="🧠"
            title="Hybrid RAG"
            description="Combining local BM25 code search with structural AST matching"
          />
          <FeatureCard
            icon="📊"
            title="Interactive Visuals"
            description="Dynamic Mermaid.js dependency graphs and full file-level inspection"
          />
        </div>
      </div>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <div className="group rounded-xl border border-gray-800 bg-gray-900/30 p-6 text-left transition-all hover:border-primary-500/50 hover:bg-gray-900/60 shadow-sm">
      <div className="mb-3 text-2xl">{icon}</div>
      <h3 className="mb-1 font-semibold text-gray-200">{title}</h3>
      <p className="text-xs text-gray-400 leading-relaxed">{description}</p>
    </div>
  );
}
