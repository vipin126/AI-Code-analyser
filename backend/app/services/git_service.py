"""Git service — clone public GitHub repositories with safety guards and cleanup.

Handles:
- URL validation (public GitHub repos only)
- Shallow cloning to temporary directories
- Repository size guards (configurable max)
- File manifest extraction with language detection
- Deterministic cleanup of cloned data
"""

import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

from git import GitCommandError, Repo
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# ── Language Extension Mapping ───────────────────────────────
LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".vue": "vue",
    ".svelte": "svelte",
}

# File/directory patterns to skip during scanning
SKIP_DIRS: set[str] = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".tox", ".mypy_cache",
    "vendor", ".gradle", "target", "bin", "obj",
}

SKIP_FILES: set[str] = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock",
}

# Max repo size in bytes (default: 500MB)
MAX_REPO_SIZE_BYTES = 500 * 1024 * 1024


# ── Result Models ────────────────────────────────────────────

class FileInfo(BaseModel):
    """Metadata for a single file in the cloned repository."""

    path: str
    language: str
    size_bytes: int
    content_hash: str
    line_count: int


class CloneResult(BaseModel):
    """Result of a repository clone operation."""

    clone_path: str
    default_branch: str
    total_files: int
    files: list[FileInfo]
    language_stats: dict[str, int]
    total_size_bytes: int


class GitService:
    """Service for cloning and scanning GitHub repositories."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def validate_github_url(self, url: str) -> str:
        """Validate and normalize a GitHub repository URL.

        Args:
            url: The GitHub URL to validate.

        Returns:
            Normalized HTTPS clone URL.

        Raises:
            ValueError: If the URL is not a valid public GitHub repo URL.
        """
        url = str(url).rstrip("/")

        # Strip .git suffix if present
        if url.endswith(".git"):
            url = url[:-4]

        # Validate it's a GitHub URL with owner/repo pattern
        valid_prefixes = (
            "https://github.com/",
            "http://github.com/",
        )
        if not any(url.startswith(p) for p in valid_prefixes):
            raise ValueError(
                f"Invalid GitHub URL: {url}. Only public GitHub repos are supported."
            )

        # Ensure it has owner/repo structure
        path_parts = url.replace("https://github.com/", "").replace("http://github.com/", "")
        segments = [s for s in path_parts.split("/") if s]
        if len(segments) < 2:
            raise ValueError(
                f"Invalid GitHub URL format: {url}. Expected: https://github.com/owner/repo"
            )

        # Return normalized HTTPS URL
        owner, repo = segments[0], segments[1]
        return f"https://github.com/{owner}/{repo}.git"

    def clone_repository(self, repo_url: str) -> CloneResult:
        """Clone a public GitHub repository to a temporary directory.

        Performs a shallow clone (depth=1) to minimize disk and network usage.

        Args:
            repo_url: Public GitHub repository URL.

        Returns:
            CloneResult with file manifest and metadata.

        Raises:
            ValueError: If URL is invalid.
            GitCommandError: If clone fails.
            RuntimeError: If repository exceeds size limit.
        """
        clone_url = self.validate_github_url(repo_url)
        clone_dir = tempfile.mkdtemp(prefix="code_analyzer_")

        logger.info("Cloning repository %s to %s", clone_url, clone_dir)

        try:
            # Shallow clone — single branch, depth 1
            repo = Repo.clone_from(
                clone_url,
                clone_dir,
                depth=1,
                single_branch=True,
                no_checkout=False,
            )

            # Detect default branch
            default_branch = str(repo.active_branch)

            # Check total size
            total_size = self._get_directory_size(Path(clone_dir))
            if total_size > MAX_REPO_SIZE_BYTES:
                raise RuntimeError(
                    f"Repository size ({total_size / (1024*1024):.1f}MB) "
                    f"exceeds limit ({MAX_REPO_SIZE_BYTES / (1024*1024):.0f}MB)"
                )

            # Scan files and build manifest
            files = self._scan_files(Path(clone_dir))
            language_stats = self._compute_language_stats(files)

            result = CloneResult(
                clone_path=clone_dir,
                default_branch=default_branch,
                total_files=len(files),
                files=files,
                language_stats=language_stats,
                total_size_bytes=total_size,
            )

            logger.info(
                "Clone complete: %d files, %d languages, %.1f MB",
                result.total_files,
                len(result.language_stats),
                result.total_size_bytes / (1024 * 1024),
            )
            return result

        except GitCommandError as e:
            # Clean up on failure
            self.cleanup(Path(clone_dir))
            logger.error("Git clone failed for %s: %s", clone_url, e)
            raise
        except Exception:
            self.cleanup(Path(clone_dir))
            raise

    def cleanup(self, clone_path: Path) -> None:
        """Remove a cloned repository directory.

        Safe to call multiple times or on non-existent paths.

        Args:
            clone_path: Path to the cloned repository directory.
        """
        if clone_path.exists():
            try:
                shutil.rmtree(clone_path, ignore_errors=True)
                logger.info("Cleaned up clone directory: %s", clone_path)
            except Exception as e:
                logger.warning("Failed to clean up %s: %s", clone_path, e)

    def _scan_files(self, root: Path) -> list[FileInfo]:
        """Walk the cloned repository and collect metadata for source files.

        Skips hidden directories, dependency directories (node_modules, etc.),
        and lock files. Only includes files with recognized language extensions.

        Args:
            root: Root path of the cloned repository.

        Returns:
            List of FileInfo objects for each recognized source file.
        """
        files: list[FileInfo] = []

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories (modifies in-place for os.walk)
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]

            for filename in filenames:
                if filename in SKIP_FILES or filename.startswith("."):
                    continue

                file_path = Path(dirpath) / filename
                ext = file_path.suffix.lower()

                if ext not in LANGUAGE_EXTENSIONS:
                    continue

                try:
                    content = file_path.read_bytes()
                    relative_path = str(file_path.relative_to(root))
                    # Normalize to forward slashes for cross-platform consistency
                    relative_path = relative_path.replace("\\", "/")

                    files.append(FileInfo(
                        path=relative_path,
                        language=LANGUAGE_EXTENSIONS[ext],
                        size_bytes=len(content),
                        content_hash=hashlib.sha256(content).hexdigest(),
                        line_count=content.count(b"\n") + 1,
                    ))
                except (OSError, PermissionError) as e:
                    logger.warning("Skipping file %s: %s", file_path, e)

        return files

    def _compute_language_stats(self, files: list[FileInfo]) -> dict[str, int]:
        """Compute file count per language.

        Args:
            files: List of scanned file info objects.

        Returns:
            Dict mapping language name to file count, sorted descending.
        """
        stats: dict[str, int] = {}
        for f in files:
            stats[f.language] = stats.get(f.language, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))

    def _get_directory_size(self, path: Path) -> int:
        """Calculate total size of a directory tree in bytes.

        Args:
            path: Directory path to measure.

        Returns:
            Total size in bytes.
        """
        total = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for filename in filenames:
                fp = Path(dirpath) / filename
                try:
                    total += fp.stat().st_size
                except OSError:
                    pass
        return total
