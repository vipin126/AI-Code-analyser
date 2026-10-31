import Link from "next/link";

export default function Navbar() {
  return (
    <header className="sticky top-0 z-50 w-full border-b border-gray-800 bg-gray-950/80 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600/20 text-primary-400 font-bold text-lg">
            ⚡
          </div>
          <span className="text-lg font-bold tracking-tight text-white">
            CodeAnalyzer<span className="text-primary-400">.ai</span>
          </span>
        </Link>

        <nav className="flex items-center gap-6">
          <Link
            href="/dashboard"
            className="text-sm font-medium text-gray-300 hover:text-white transition-colors"
          >
            Dashboard
          </Link>
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-gray-800 bg-gray-900 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-gray-800 hover:text-white transition-colors"
          >
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
