"""
Context packager for preparing minimal excerpts for artifact generation.

Selects relevant portions of repository files and packages them
for inclusion in prompts, respecting byte limits and redacting secrets.
"""

from pathlib import Path

from api_vault.repo_scanner import get_file_content
from api_vault.schemas import ContextRef, FileEntry, RepoIndex, ScanConfig
from api_vault.secret_guard import get_safe_content, is_sensitive_file


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses a rough approximation of ~4 characters per token.

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    return len(text) // 4


def select_context_refs_for_artifact(
    artifact_name: str,
    artifact_family: str,
    index: RepoIndex,
    signals_data: dict,
    max_refs: int = 10,
) -> list[ContextRef]:
    """
    Select relevant context references for an artifact.

    Args:
        artifact_name: Name of the artifact to generate
        artifact_family: Family (docs, security, tests, etc.)
        index: Repository index
        signals_data: Extracted signals
        max_refs: Maximum number of references

    Returns:
        List of ContextRef objects
    """
    refs: list[ContextRef] = []

    # Get key files that are always relevant
    key_files = [
        ("README.md", "Primary documentation"),
        ("readme.md", "Primary documentation"),
        ("package.json", "Project configuration and dependencies"),
        ("pyproject.toml", "Project configuration and dependencies"),
        ("Cargo.toml", "Project configuration and dependencies"),
        ("go.mod", "Project configuration and dependencies"),
        ("Makefile", "Build and run commands"),
        ("Dockerfile", "Container configuration"),
        ("docker-compose.yml", "Service orchestration"),
    ]

    # Map artifact families to relevant file patterns
    family_patterns: dict[str, list[tuple[str, str]]] = {
        "docs": [
            ("*.md", "Documentation files"),
            ("docs/*", "Documentation folder"),
            ("README*", "Readme files"),
            ("src/index.*", "Main entrypoint"),
            ("src/main.*", "Main entrypoint"),
            ("main.*", "Main entrypoint"),
            ("app.*", "Application entrypoint"),
        ],
        "security": [
            ("SECURITY.md", "Security policy"),
            ("auth/*", "Authentication code"),
            ("**/auth*", "Authentication code"),
            ("**/middleware*", "Middleware code"),
            (".env.example", "Environment configuration"),
            ("config/*", "Configuration files"),
        ],
        "tests": [
            ("tests/*", "Test files"),
            ("test/*", "Test files"),
            ("__tests__/*", "Test files"),
            ("*_test.*", "Test files"),
            ("test_*", "Test files"),
            ("*.spec.*", "Test files"),
            ("conftest.py", "Test configuration"),
            ("jest.config.*", "Test configuration"),
            ("pytest.ini", "Test configuration"),
        ],
        "api": [
            ("openapi.*", "API specification"),
            ("swagger.*", "API specification"),
            ("routes/*", "API routes"),
            ("**/routes*", "API routes"),
            ("**/api/*", "API code"),
            ("**/controllers/*", "API controllers"),
            ("**/handlers/*", "API handlers"),
        ],
        "observability": [
            ("**/logging*", "Logging configuration"),
            ("**/logger*", "Logger implementation"),
            ("**/metrics*", "Metrics code"),
            ("**/telemetry*", "Telemetry code"),
            ("prometheus*", "Prometheus config"),
        ],
        "product": [
            ("src/components/*", "UI components"),
            ("src/pages/*", "Page components"),
            ("app/*", "Application code"),
            ("public/*", "Public assets"),
            ("styles/*", "Styling"),
        ],
    }

    # Artifact-specific context needs
    artifact_context: dict[str, list[tuple[str, str]]] = {
        "RUNBOOK.md": [
            ("Makefile", "Build commands"),
            ("package.json", "NPM scripts"),
            ("README.md", "Existing documentation"),
            (".github/workflows/*", "CI workflows"),
        ],
        "TROUBLESHOOTING.md": [
            ("*.log", "Log files"),
            (".github/workflows/*", "CI configuration"),
            ("Dockerfile", "Container setup"),
            ("docker-compose.yml", "Service setup"),
        ],
        "ARCHITECTURE_OVERVIEW.md": [
            ("src/**/__init__.py", "Package structure"),
            ("src/**/index.*", "Module entrypoints"),
            ("README.md", "Project description"),
        ],
        "THREAT_MODEL.md": [
            ("**/auth*", "Authentication"),
            ("**/middleware*", "Middleware"),
            ("**/api/*", "API endpoints"),
            ("**/database*", "Database access"),
        ],
        "SECURITY_CHECKLIST.md": [
            (".env.example", "Environment vars"),
            ("**/auth*", "Auth code"),
            ("SECURITY.md", "Existing policy"),
        ],
        "AUTHZ_AUTHN_NOTES.md": [
            ("**/auth*", "Auth implementation"),
            ("**/middleware*", "Auth middleware"),
            ("**/user*", "User handling"),
            ("**/session*", "Session handling"),
        ],
        "GOLDEN_PATH_TEST_PLAN.md": [
            ("tests/*", "Existing tests"),
            ("src/**/*.py", "Source code"),
            ("README.md", "Usage examples"),
        ],
        "MINIMUM_TESTS_SUGGESTION.md": [
            ("tests/*", "Existing tests"),
            ("src/**/*", "Source code"),
        ],
        "ENDPOINT_INVENTORY.md": [
            ("**/routes*", "Route definitions"),
            ("**/api/*", "API code"),
            ("**/controllers*", "Controllers"),
            ("openapi.*", "Existing spec"),
        ],
        "LOGGING_CONVENTIONS.md": [
            ("**/log*", "Logging code"),
            ("**/utils*", "Utility code"),
            ("**/config*", "Configuration"),
        ],
        "METRICS_PLAN.md": [
            ("**/metrics*", "Existing metrics"),
            ("**/telemetry*", "Telemetry"),
            ("**/health*", "Health checks"),
        ],
        "UX_COPY_BANK.md": [
            ("src/components/*", "UI components"),
            ("**/pages/*", "Pages"),
            ("public/locales/*", "Translations"),
        ],
    }

    file_paths = {f.path: f for f in index.files}

    # Add key files first
    for filename, reason in key_files:
        if filename in file_paths and not is_sensitive_file(filename):
            refs.append(
                ContextRef(
                    file_path=filename,
                    excerpt_type="head",
                    max_bytes=4096,
                    reason=reason,
                )
            )

    # Add family-specific patterns
    if artifact_family in family_patterns:
        for pattern, reason in family_patterns[artifact_family]:
            matches = _match_files(index.files, pattern)
            for match in matches[:3]:  # Limit per pattern
                if not is_sensitive_file(match.path) and match.path not in [r.file_path for r in refs]:
                    refs.append(
                        ContextRef(
                            file_path=match.path,
                            excerpt_type="head",
                            max_bytes=4096,
                            reason=reason,
                        )
                    )

    # Add artifact-specific patterns
    if artifact_name in artifact_context:
        for pattern, reason in artifact_context[artifact_name]:
            matches = _match_files(index.files, pattern)
            for match in matches[:2]:  # Limit per pattern
                if not is_sensitive_file(match.path) and match.path not in [r.file_path for r in refs]:
                    refs.append(
                        ContextRef(
                            file_path=match.path,
                            excerpt_type="head",
                            max_bytes=4096,
                            reason=reason,
                        )
                    )

    # Limit total refs
    return refs[:max_refs]


def _match_files(files: list[FileEntry], pattern: str) -> list[FileEntry]:
    """
    Match files against a glob-like pattern.

    Args:
        files: List of file entries
        pattern: Glob pattern

    Returns:
        Matching files
    """
    import fnmatch

    matches: list[FileEntry] = []
    for f in files:
        if f.is_binary:
            continue
        if fnmatch.fnmatch(f.path, pattern) or fnmatch.fnmatch(f.path.lower(), pattern.lower()):
            matches.append(f)

    # Sort by size (smaller first) to get more files in context
    matches.sort(key=lambda x: x.size_bytes)
    return matches


def package_context(
    repo_path: Path,
    index: RepoIndex,
    context_refs: list[ContextRef],
    config: ScanConfig | None = None,
) -> tuple[str, list[str], int]:
    """
    Package context from files into a single string.

    Args:
        repo_path: Repository path
        index: Repository index
        context_refs: List of context references
        config: Scan configuration

    Returns:
        Tuple of (packaged_context, files_used, total_bytes)
    """
    if config is None:
        config = ScanConfig()

    file_map = {f.path: f for f in index.files}
    parts: list[str] = []
    files_used: list[str] = []
    total_bytes = 0

    for ref in context_refs:
        if total_bytes >= config.max_total_context_bytes:
            break

        if ref.file_path not in file_map:
            continue

        file_entry = file_map[ref.file_path]
        if file_entry.is_binary:
            continue

        # Check sensitive file
        if is_sensitive_file(ref.file_path):
            continue

        # Get content
        content = get_file_content(
            repo_path,
            file_entry,
            max_bytes=min(ref.max_bytes, config.max_excerpt_bytes),
            start_line=ref.start_line,
            end_line=ref.end_line,
        )

        if not content:
            continue

        # Redact secrets
        safe_content, _ = get_safe_content(content, ref.file_path)

        # Check if we'd exceed limit
        content_bytes = len(safe_content.encode("utf-8"))
        if total_bytes + content_bytes > config.max_total_context_bytes:
            # Truncate to fit
            remaining = config.max_total_context_bytes - total_bytes
            if remaining < 500:  # Not worth including
                continue
            safe_content = safe_content[:remaining]
            content_bytes = remaining

        # Format the excerpt
        header = f"### File: {ref.file_path}"
        if ref.reason:
            header += f" ({ref.reason})"
        header += "\n```\n"
        footer = "\n```\n"

        excerpt = header + safe_content + footer
        parts.append(excerpt)
        files_used.append(ref.file_path)
        total_bytes += content_bytes

    packaged = "\n".join(parts)
    return packaged, files_used, total_bytes


def create_file_tree_context(index: RepoIndex, max_files: int = 100) -> str:
    """
    Create a file tree representation for context.

    Args:
        index: Repository index
        max_files: Maximum files to include

    Returns:
        File tree string
    """
    lines: list[str] = ["## Repository Structure", "```"]

    # Group files by directory
    dirs: dict[str, list[str]] = {}
    for f in index.files[:max_files]:
        parts = Path(f.path).parts
        if len(parts) == 1:
            dir_key = "."
            filename = parts[0]
        else:
            dir_key = str(Path(*parts[:-1]))
            filename = parts[-1]

        if dir_key not in dirs:
            dirs[dir_key] = []
        dirs[dir_key].append(filename)

    # Sort directories
    sorted_dirs = sorted(dirs.keys())

    for dir_path in sorted_dirs:
        if dir_path == ".":
            for filename in sorted(dirs[dir_path]):
                lines.append(filename)
        else:
            lines.append(f"{dir_path}/")
            for filename in sorted(dirs[dir_path])[:20]:  # Limit files per dir
                lines.append(f"  {filename}")
            if len(dirs[dir_path]) > 20:
                lines.append(f"  ... ({len(dirs[dir_path]) - 20} more)")

    if len(index.files) > max_files:
        lines.append(f"... ({len(index.files) - max_files} more files)")

    lines.append("```")
    return "\n".join(lines)


def create_signals_context(signals_data: dict) -> str:
    """
    Create a context string from extracted signals.

    Args:
        signals_data: Signals dictionary

    Returns:
        Formatted signals context
    """
    lines: list[str] = ["## Repository Analysis"]

    # Primary language
    if signals_data.get("primary_language"):
        lines.append(f"**Primary Language:** {signals_data['primary_language']}")

    # Languages
    if signals_data.get("languages"):
        langs = [f"{l['language']} ({l['percentage']:.1f}%)" for l in signals_data["languages"][:5]]
        lines.append(f"**Languages:** {', '.join(langs)}")

    # Frameworks
    if signals_data.get("frameworks"):
        frameworks = [f"{f['name']} ({f['confidence']:.0%})" for f in signals_data["frameworks"][:5]]
        lines.append(f"**Frameworks/Tools:** {', '.join(frameworks)}")

    # Package managers
    if signals_data.get("package_managers"):
        lines.append(f"**Package Managers:** {', '.join(signals_data['package_managers'])}")

    # Build tools
    if signals_data.get("build_tools"):
        lines.append(f"**Build Tools:** {', '.join(signals_data['build_tools'])}")

    # Characteristics
    chars = []
    if signals_data.get("has_api"):
        chars.append("API")
    if signals_data.get("has_web_ui"):
        chars.append("Web UI")
    if signals_data.get("has_cli"):
        chars.append("CLI")
    if signals_data.get("has_database"):
        chars.append("Database")
    if signals_data.get("has_auth"):
        chars.append("Authentication")
    if signals_data.get("is_monorepo"):
        chars.append("Monorepo")
    if chars:
        lines.append(f"**Project Type:** {', '.join(chars)}")

    # Maturity scores
    maturity_parts = []
    if "docs_maturity" in signals_data:
        score = signals_data["docs_maturity"].get("maturity_score", 0)
        maturity_parts.append(f"Docs: {score:.0%}")
    if "testing_maturity" in signals_data:
        score = signals_data["testing_maturity"].get("maturity_score", 0)
        maturity_parts.append(f"Tests: {score:.0%}")
    if "ci_maturity" in signals_data:
        score = signals_data["ci_maturity"].get("maturity_score", 0)
        maturity_parts.append(f"CI/CD: {score:.0%}")
    if "security_maturity" in signals_data:
        score = signals_data["security_maturity"].get("maturity_score", 0)
        maturity_parts.append(f"Security: {score:.0%}")
    if maturity_parts:
        lines.append(f"**Maturity:** {', '.join(maturity_parts)}")

    # Identified gaps
    if signals_data.get("identified_gaps"):
        lines.append("\n**Identified Gaps:**")
        for gap in signals_data["identified_gaps"][:5]:
            lines.append(f"- {gap}")

    return "\n".join(lines)


def build_full_context(
    repo_path: Path,
    index: RepoIndex,
    signals_data: dict,
    context_refs: list[ContextRef],
    config: ScanConfig | None = None,
) -> tuple[str, list[str], int]:
    """
    Build complete context for artifact generation.

    Combines file tree, signals, and file excerpts.

    Args:
        repo_path: Repository path
        index: Repository index
        signals_data: Extracted signals
        context_refs: Context references
        config: Scan configuration

    Returns:
        Tuple of (full_context, files_used, estimated_tokens)
    """
    parts: list[str] = []

    # Add file tree (compact)
    tree_context = create_file_tree_context(index, max_files=50)
    parts.append(tree_context)

    # Add signals
    signals_context = create_signals_context(signals_data)
    parts.append(signals_context)

    # Add file excerpts
    excerpts, files_used, excerpt_bytes = package_context(
        repo_path, index, context_refs, config
    )
    if excerpts:
        parts.append("\n## Relevant Files\n")
        parts.append(excerpts)

    full_context = "\n\n".join(parts)
    estimated_tokens = estimate_tokens(full_context)

    return full_context, files_used, estimated_tokens


def build_base_context(
    repo_path: Path,
    index: RepoIndex,
    signals_data: dict,
    config: ScanConfig | None = None,
) -> tuple[str, int]:
    """
    Build the base repository context for Anthropic prompt caching.

    This context is shared across all artifact generations and cached
    server-side by Anthropic. Subsequent requests with the same prefix
    get a 90% discount on input tokens.

    Includes:
    - Repository file tree structure
    - Detected signals (languages, frameworks, maturity)
    - Key configuration files (package.json, pyproject.toml, etc.)

    Args:
        repo_path: Repository path
        index: Repository index
        signals_data: Extracted signals
        config: Scan configuration

    Returns:
        Tuple of (base_context, estimated_tokens)
    """
    if config is None:
        config = ScanConfig()

    parts: list[str] = [
        "# Repository Context",
        "",
        "You are analyzing a code repository. Below is the complete context about this repository.",
        "Use this information to generate accurate, repo-specific artifacts.",
        "",
    ]

    # Add file tree
    tree_context = create_file_tree_context(index, max_files=100)
    parts.append(tree_context)

    # Add signals
    signals_context = create_signals_context(signals_data)
    parts.append(signals_context)

    # Add key files that are always relevant (shared across all artifacts)
    key_files = [
        "README.md",
        "readme.md",
        "package.json",
        "pyproject.toml",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        ".github/workflows/ci.yml",
        ".github/workflows/ci.yaml",
    ]

    file_map = {f.path: f for f in index.files}
    key_excerpts: list[str] = []
    total_bytes = 0
    max_key_bytes = config.max_total_context_bytes // 2  # Reserve half for key files

    for filename in key_files:
        if total_bytes >= max_key_bytes:
            break

        if filename not in file_map:
            continue

        file_entry = file_map[filename]
        if file_entry.is_binary:
            continue

        if is_sensitive_file(filename):
            continue

        content = get_file_content(
            repo_path,
            file_entry,
            max_bytes=min(8192, config.max_excerpt_bytes),
        )

        if not content:
            continue

        safe_content, _ = get_safe_content(content, filename)
        content_bytes = len(safe_content.encode("utf-8"))

        if total_bytes + content_bytes > max_key_bytes:
            continue

        excerpt = f"### File: {filename}\n```\n{safe_content}\n```"
        key_excerpts.append(excerpt)
        total_bytes += content_bytes

    if key_excerpts:
        parts.append("\n## Key Configuration Files\n")
        parts.append("\n\n".join(key_excerpts))

    base_context = "\n\n".join(parts)
    estimated_tokens = estimate_tokens(base_context)

    return base_context, estimated_tokens
