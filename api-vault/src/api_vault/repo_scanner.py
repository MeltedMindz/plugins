"""
Repository scanner for building file tree index.

Scans a local git repository to build a complete index of files,
computing hashes, detecting file types, and collecting metrics.
"""

import fnmatch
import hashlib
import os
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from api_vault.schemas import FileEntry, RepoIndex, ScanConfig


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except (OSError, IOError):
        return "0" * 64  # Return empty hash on read error


def is_binary_file(file_path: Path, sample_size: int = 8192) -> bool:
    """
    Detect if a file is binary by checking for null bytes.

    Args:
        file_path: Path to file
        sample_size: Number of bytes to sample

    Returns:
        True if file appears to be binary
    """
    try:
        with open(file_path, "rb") as f:
            sample = f.read(sample_size)
            # Check for null bytes (common in binary files)
            if b"\x00" in sample:
                return True
            # Check for high ratio of non-printable characters
            non_printable = sum(1 for b in sample if b < 32 and b not in (9, 10, 13))
            if len(sample) > 0 and non_printable / len(sample) > 0.3:
                return True
            return False
    except (OSError, IOError):
        return True  # Assume binary on read error


def should_exclude_path(path: Path, excluded_dirs: list[str], repo_root: Path) -> bool:
    """
    Check if a path should be excluded based on patterns.

    Args:
        path: Path to check
        excluded_dirs: List of patterns to exclude
        repo_root: Root of the repository

    Returns:
        True if path should be excluded
    """
    rel_path = path.relative_to(repo_root) if path.is_absolute() else path

    for part in rel_path.parts:
        for pattern in excluded_dirs:
            if fnmatch.fnmatch(part, pattern):
                return True
    return False


def should_exclude_file(file_path: Path, excluded_extensions: list[str]) -> bool:
    """
    Check if a file should be excluded based on extension.

    Args:
        file_path: Path to file
        excluded_extensions: List of extensions to exclude

    Returns:
        True if file should be excluded
    """
    ext = file_path.suffix.lower()
    return ext in excluded_extensions


def get_git_info(repo_path: Path) -> tuple[str | None, str | None]:
    """
    Get git commit hash and branch name.

    Args:
        repo_path: Path to repository

    Returns:
        Tuple of (commit_hash, branch_name) or (None, None) if not a git repo
    """
    commit_hash = None
    branch_name = None

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            commit_hash = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            branch_name = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return commit_hash, branch_name


def scan_repository(
    repo_path: Path,
    config: ScanConfig | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> RepoIndex:
    """
    Scan a repository and build a complete file index.

    Args:
        repo_path: Path to repository root
        config: Scanning configuration
        progress_callback: Optional callback for progress updates, called with (current, total, file_path)

    Returns:
        RepoIndex with all file information
    """
    if config is None:
        config = ScanConfig()

    repo_path = Path(repo_path).resolve()
    if not repo_path.exists():
        raise ValueError(f"Repository path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"Repository path is not a directory: {repo_path}")

    files: list[FileEntry] = []
    total_size = 0

    # Get git info
    commit_hash, branch_name = get_git_info(repo_path)

    # Collect all files first for progress tracking
    all_files: list[Path] = []
    for root, dirs, filenames in os.walk(repo_path):
        root_path = Path(root)

        # Filter out excluded directories in-place
        dirs[:] = [
            d
            for d in dirs
            if not should_exclude_path(root_path / d, config.excluded_dirs, repo_path)
        ]

        for filename in filenames:
            file_path = root_path / filename
            if not should_exclude_file(file_path, config.excluded_extensions):
                all_files.append(file_path)

    total_files = len(all_files)

    for idx, file_path in enumerate(all_files):
        if progress_callback:
            progress_callback(idx + 1, total_files, str(file_path.relative_to(repo_path)))

        try:
            stat_info = file_path.stat()
            file_size = stat_info.st_size

            # Skip files larger than max size
            if file_size > config.max_file_size_bytes:
                continue

            # Get relative path
            rel_path = str(file_path.relative_to(repo_path))

            # Compute hash
            file_hash = compute_sha256(file_path)

            # Check if binary
            is_binary = is_binary_file(file_path)

            # Get extension
            extension = file_path.suffix.lstrip(".").lower() if file_path.suffix else ""

            # Get modification time
            mtime = datetime.fromtimestamp(stat_info.st_mtime)

            entry = FileEntry(
                path=rel_path,
                size_bytes=file_size,
                sha256=file_hash,
                is_binary=is_binary,
                extension=extension,
                last_modified=mtime,
            )
            files.append(entry)
            total_size += file_size

        except (OSError, IOError, PermissionError):
            # Skip files we can't access
            continue

    return RepoIndex(
        repo_path=str(repo_path),
        repo_name=repo_path.name,
        scan_timestamp=datetime.utcnow(),
        total_files=len(files),
        total_size_bytes=total_size,
        files=files,
        excluded_patterns=config.excluded_dirs + config.excluded_extensions,
        git_commit_hash=commit_hash,
        git_branch=branch_name,
    )


def get_file_content(
    repo_path: Path,
    file_entry: FileEntry,
    max_bytes: int = 8192,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str | None:
    """
    Get content from a file, optionally limited by lines or bytes.

    Args:
        repo_path: Repository root path
        file_entry: FileEntry to read
        max_bytes: Maximum bytes to return
        start_line: Optional start line (1-indexed)
        end_line: Optional end line (1-indexed)

    Returns:
        File content as string, or None if unreadable
    """
    if file_entry.is_binary:
        return None

    file_path = Path(repo_path) / file_entry.path

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            if start_line is not None or end_line is not None:
                lines = f.readlines()
                start = (start_line or 1) - 1
                end = end_line or len(lines)
                content = "".join(lines[start:end])
            else:
                content = f.read(max_bytes)

            # Ensure we don't exceed max_bytes
            if len(content.encode("utf-8")) > max_bytes:
                # Truncate to fit
                encoded = content.encode("utf-8")[:max_bytes]
                content = encoded.decode("utf-8", errors="replace")

            return content
    except (OSError, IOError, UnicodeDecodeError):
        return None


def get_files_by_extension(index: RepoIndex, extensions: list[str]) -> list[FileEntry]:
    """
    Filter files by extension.

    Args:
        index: Repository index
        extensions: List of extensions to filter by (without dot)

    Returns:
        List of matching FileEntry objects
    """
    extensions_lower = [ext.lower().lstrip(".") for ext in extensions]
    return [f for f in index.files if f.extension in extensions_lower]


def get_files_by_pattern(index: RepoIndex, pattern: str) -> list[FileEntry]:
    """
    Filter files by glob pattern.

    Args:
        index: Repository index
        pattern: Glob pattern to match against file paths

    Returns:
        List of matching FileEntry objects
    """
    return [f for f in index.files if fnmatch.fnmatch(f.path, pattern)]


def get_key_files(index: RepoIndex) -> dict[str, FileEntry | None]:
    """
    Get commonly important files from the index.

    Args:
        index: Repository index

    Returns:
        Dict mapping file type to FileEntry or None
    """
    key_patterns = {
        "readme": ["README.md", "README.rst", "README.txt", "README", "readme.md"],
        "license": ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING"],
        "contributing": ["CONTRIBUTING.md", "CONTRIBUTING.rst", "CONTRIBUTING"],
        "changelog": ["CHANGELOG.md", "CHANGELOG", "HISTORY.md", "NEWS.md", "CHANGES.md"],
        "security": ["SECURITY.md", "SECURITY"],
        "package_json": ["package.json"],
        "pyproject": ["pyproject.toml"],
        "setup_py": ["setup.py"],
        "cargo_toml": ["Cargo.toml"],
        "go_mod": ["go.mod"],
        "dockerfile": ["Dockerfile", "dockerfile"],
        "docker_compose": ["docker-compose.yml", "docker-compose.yaml", "compose.yml"],
        "makefile": ["Makefile", "makefile"],
        "gitignore": [".gitignore"],
        "env_example": [".env.example", ".env.sample", "env.example"],
    }

    result: dict[str, FileEntry | None] = {}

    for key, patterns in key_patterns.items():
        result[key] = None
        for pattern in patterns:
            for file_entry in index.files:
                # Check exact match or case-insensitive match
                if file_entry.path == pattern or file_entry.path.lower() == pattern.lower():
                    result[key] = file_entry
                    break
                # Also check if it's in the root directory with different path separator
                if file_entry.path.replace("\\", "/") == pattern:
                    result[key] = file_entry
                    break
            if result[key] is not None:
                break

    return result
