"""
Pydantic schemas for Api Vault data models.

All data structures used throughout the application are defined here
to ensure type safety, validation, and serialization consistency.

Schema Version History:
- 1.0.0: Initial release
- 1.1.0: Added schema versioning, plugin support
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

# Schema version for data compatibility
SCHEMA_VERSION = "1.1.0"
SCHEMA_VERSION_MAJOR = 1
SCHEMA_VERSION_MINOR = 1
SCHEMA_VERSION_PATCH = 0


class VersionedModel(BaseModel):
    """Base model with schema versioning support."""

    schema_version: str = Field(default=SCHEMA_VERSION, description="Schema version for compatibility")

    @classmethod
    def check_version_compatibility(cls, data: dict[str, Any]) -> tuple[bool, str]:
        """
        Check if data is compatible with current schema version.

        Returns:
            Tuple of (is_compatible, message)
        """
        data_version = data.get("schema_version", "1.0.0")
        try:
            parts = data_version.split(".")
            major = int(parts[0])
            minor = int(parts[1]) if len(parts) > 1 else 0

            if major != SCHEMA_VERSION_MAJOR:
                return False, f"Incompatible major version: {data_version} vs {SCHEMA_VERSION}"
            if minor > SCHEMA_VERSION_MINOR:
                return True, f"Data from newer minor version: {data_version} (current: {SCHEMA_VERSION})"
            return True, "Compatible"
        except (ValueError, IndexError):
            return False, f"Invalid version format: {data_version}"

    @classmethod
    def migrate_from_version(cls, data: dict[str, Any], from_version: str) -> dict[str, Any]:
        """
        Migrate data from an older schema version.

        Override in subclasses to handle specific migrations.
        """
        # Default: just update the version
        data["schema_version"] = SCHEMA_VERSION
        return data


class ArtifactFamily(str, Enum):
    """Categories of artifacts that can be generated."""

    DOCS = "docs"
    SECURITY = "security"
    TESTS = "tests"
    API = "api"
    OBSERVABILITY = "observability"
    PRODUCT = "product"


class FileEntry(BaseModel):
    """A single file in the repository index."""

    path: str = Field(..., description="Relative path from repo root")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    sha256: str = Field(..., min_length=64, max_length=64, description="SHA-256 hash of contents")
    is_binary: bool = Field(default=False, description="Whether file is binary")
    extension: str = Field(default="", description="File extension without dot")
    last_modified: datetime | None = Field(default=None, description="Last modification time")

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        """Ensure sha256 is lowercase hex."""
        if not all(c in "0123456789abcdef" for c in v.lower()):
            raise ValueError("sha256 must be hexadecimal")
        return v.lower()


class RepoIndex(BaseModel):
    """Complete index of a repository's files."""

    repo_path: str = Field(..., description="Absolute path to repository root")
    repo_name: str = Field(..., description="Repository directory name")
    scan_timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_files: int = Field(..., ge=0)
    total_size_bytes: int = Field(..., ge=0)
    files: list[FileEntry] = Field(default_factory=list)
    excluded_patterns: list[str] = Field(default_factory=list)
    git_commit_hash: str | None = Field(default=None, description="HEAD commit hash if git repo")
    git_branch: str | None = Field(default=None, description="Current branch name")


class LanguageStats(BaseModel):
    """Statistics about a detected programming language."""

    language: str = Field(..., description="Language name")
    file_count: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)
    percentage: float = Field(..., ge=0, le=100)
    extensions: list[str] = Field(default_factory=list)


class FrameworkDetection(BaseModel):
    """A detected framework or tool."""

    name: str = Field(..., description="Framework/tool name")
    category: str = Field(..., description="Category: framework, library, tool, service")
    confidence: float = Field(..., ge=0, le=1, description="Detection confidence 0-1")
    evidence: list[str] = Field(default_factory=list, description="Files/patterns that triggered detection")
    version: str | None = Field(default=None, description="Detected version if available")


class DocsMaturity(BaseModel):
    """Assessment of documentation maturity."""

    has_readme: bool = False
    has_contributing: bool = False
    has_changelog: bool = False
    has_license: bool = False
    has_docs_folder: bool = False
    has_api_docs: bool = False
    has_architecture_docs: bool = False
    readme_size_bytes: int = 0
    doc_file_count: int = 0
    maturity_score: float = Field(default=0, ge=0, le=1, description="Overall docs maturity 0-1")


class TestingMaturity(BaseModel):
    """Assessment of testing maturity."""

    has_test_folder: bool = False
    has_test_config: bool = False
    test_frameworks: list[str] = Field(default_factory=list)
    test_file_count: int = 0
    estimated_coverage: float | None = Field(default=None, ge=0, le=100)
    maturity_score: float = Field(default=0, ge=0, le=1)


class CIMaturity(BaseModel):
    """Assessment of CI/CD maturity."""

    has_ci_config: bool = False
    ci_platforms: list[str] = Field(default_factory=list)
    has_deployment_config: bool = False
    has_docker: bool = False
    has_kubernetes: bool = False
    maturity_score: float = Field(default=0, ge=0, le=1)


class SecurityMaturity(BaseModel):
    """Assessment of security maturity."""

    has_security_policy: bool = False
    has_dependabot: bool = False
    has_codeowners: bool = False
    has_env_example: bool = False
    secrets_in_code_risk: float = Field(default=0, ge=0, le=1, description="Estimated risk of secrets")
    maturity_score: float = Field(default=0, ge=0, le=1)


class RepoSignals(BaseModel):
    """Extracted signals about repository characteristics."""

    repo_path: str
    repo_name: str
    scan_timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Language detection
    primary_language: str | None = None
    languages: list[LanguageStats] = Field(default_factory=list)

    # Framework/tool detection
    frameworks: list[FrameworkDetection] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    build_tools: list[str] = Field(default_factory=list)

    # Maturity assessments
    docs_maturity: DocsMaturity = Field(default_factory=DocsMaturity)
    testing_maturity: TestingMaturity = Field(default_factory=TestingMaturity)
    ci_maturity: CIMaturity = Field(default_factory=CIMaturity)
    security_maturity: SecurityMaturity = Field(default_factory=SecurityMaturity)

    # Project characteristics
    is_monorepo: bool = False
    has_api: bool = False
    has_web_ui: bool = False
    has_cli: bool = False
    has_database: bool = False
    has_auth: bool = False

    # Gaps identified
    identified_gaps: list[str] = Field(default_factory=list, description="Missing or weak areas")


class ScoreBreakdown(BaseModel):
    """Breakdown of how an artifact was scored."""

    reusability: float = Field(..., ge=0, le=10, description="How reusable is this artifact")
    time_saved: float = Field(..., ge=0, le=10, description="Time this saves for developers")
    leverage: float = Field(..., ge=0, le=10, description="Impact multiplier")
    context_cost: float = Field(..., ge=0, le=10, description="How much context needed (lower is better)")
    gap_weight: float = Field(..., ge=0, le=10, description="How much repo needs this")
    total_score: float = Field(..., ge=0, description="Weighted total score")

    def compute_total(self, weights: dict[str, float] | None = None) -> float:
        """Compute weighted total score."""
        if weights is None:
            weights = {
                "reusability": 1.0,
                "time_saved": 1.5,
                "leverage": 2.0,
                "context_cost": -0.5,  # Negative because lower is better
                "gap_weight": 1.5,
            }
        return (
            self.reusability * weights.get("reusability", 1.0)
            + self.time_saved * weights.get("time_saved", 1.0)
            + self.leverage * weights.get("leverage", 1.0)
            + self.context_cost * weights.get("context_cost", -0.5)
            + self.gap_weight * weights.get("gap_weight", 1.0)
        )


class ContextRef(BaseModel):
    """Reference to context that should be included for an artifact."""

    file_path: str = Field(..., description="Path to file")
    excerpt_type: str = Field(default="full", description="full, head, tail, or range")
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    max_bytes: int = Field(default=8192, description="Maximum bytes to include")
    reason: str = Field(default="", description="Why this context is needed")


class PlanJob(BaseModel):
    """A single artifact generation job in the plan."""

    id: str = Field(..., description="Unique job identifier")
    family: ArtifactFamily
    artifact_name: str = Field(..., description="Name of artifact to generate")
    output_path: str = Field(..., description="Relative path for output file")
    prompt_template_id: str = Field(..., description="ID of prompt template to use")
    max_output_tokens: int = Field(default=4096, ge=100, le=32000)
    context_refs: list[ContextRef] = Field(default_factory=list)
    score_breakdown: ScoreBreakdown
    reason: str = Field(..., description="Why this artifact was selected")
    estimated_input_tokens: int = Field(default=0, ge=0)
    dependencies: list[str] = Field(default_factory=list, description="Job IDs this depends on")


class Plan(VersionedModel):
    """Complete generation plan."""

    plan_id: str = Field(..., description="Unique plan identifier")
    repo_path: str
    repo_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    budget_tokens: int = Field(..., ge=0, description="Token budget for generation")
    budget_seconds: int = Field(..., ge=0, description="Time budget in seconds")
    families_requested: list[ArtifactFamily] = Field(default_factory=list)
    jobs: list[PlanJob] = Field(default_factory=list)
    total_estimated_tokens: int = Field(default=0, ge=0)
    jobs_within_budget: int = Field(default=0, ge=0)
    excluded_jobs: list[dict[str, Any]] = Field(
        default_factory=list, description="Jobs excluded due to budget"
    )


class RedactionEntry(BaseModel):
    """Record of a redacted secret."""

    file_path: str
    line_number: int
    pattern_name: str = Field(..., description="Name of pattern that matched")
    original_length: int = Field(..., ge=0)
    redacted_placeholder: str = Field(default="[REDACTED]")
    confidence: float = Field(default=1.0, ge=0, le=1)


class RedactionReport(BaseModel):
    """Report of all redactions performed."""

    scan_timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_redactions: int = Field(default=0, ge=0)
    files_affected: int = Field(default=0, ge=0)
    redactions: list[RedactionEntry] = Field(default_factory=list)
    patterns_matched: dict[str, int] = Field(default_factory=dict)


class ArtifactMeta(BaseModel):
    """Metadata for a generated artifact."""

    artifact_id: str
    job_id: str
    family: ArtifactFamily
    artifact_name: str
    output_path: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    request_hash: str = Field(..., description="Hash of the generation request for caching")
    model_used: str
    input_tokens: int = Field(..., ge=0)
    output_tokens: int = Field(..., ge=0)
    generation_time_seconds: float = Field(..., ge=0)
    context_files_used: list[str] = Field(default_factory=list)
    prompt_template_id: str
    success: bool = True
    error_message: str | None = None


class JobResult(BaseModel):
    """Result of executing a single job."""

    job_id: str
    status: str = Field(..., description="completed, skipped, failed, cached")
    artifact_path: str | None = None
    meta_path: str | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    generation_time_seconds: float = Field(default=0, ge=0)
    error_message: str | None = None
    cached: bool = False


class Report(VersionedModel):
    """Final execution report."""

    report_id: str
    repo_path: str
    repo_name: str
    plan_id: str
    started_at: datetime
    completed_at: datetime
    total_jobs: int = Field(..., ge=0)
    jobs_completed: int = Field(default=0, ge=0)
    jobs_skipped: int = Field(default=0, ge=0)
    jobs_failed: int = Field(default=0, ge=0)
    jobs_cached: int = Field(default=0, ge=0)
    total_input_tokens: int = Field(default=0, ge=0)
    total_output_tokens: int = Field(default=0, ge=0)
    total_generation_time_seconds: float = Field(default=0, ge=0)
    job_results: list[JobResult] = Field(default_factory=list)
    artifacts_generated: list[str] = Field(default_factory=list)
    redaction_summary: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ScanConfig(BaseModel):
    """Configuration for repository scanning."""

    max_file_size_bytes: int = Field(default=1_000_000, description="Max file size to read")
    max_excerpt_bytes: int = Field(default=8192, description="Max bytes per excerpt")
    max_total_context_bytes: int = Field(default=65536, description="Max context per job")
    excluded_dirs: list[str] = Field(
        default_factory=lambda: [
            "node_modules",
            "dist",
            "build",
            ".next",
            ".git",
            "coverage",
            "vendor",
            "__pycache__",
            "target",
            ".venv",
            "venv",
            ".tox",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "htmlcov",
            ".eggs",
            "*.egg-info",
        ]
    )
    excluded_extensions: list[str] = Field(
        default_factory=lambda: [
            ".pyc",
            ".pyo",
            ".so",
            ".dylib",
            ".dll",
            ".exe",
            ".bin",
            ".obj",
            ".o",
            ".a",
            ".lib",
            ".zip",
            ".tar",
            ".gz",
            ".rar",
            ".7z",
            ".jar",
            ".war",
            ".ear",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".svg",
            ".webp",
            ".mp3",
            ".mp4",
            ".avi",
            ".mov",
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".lock",
        ]
    )
    text_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".java",
            ".go",
            ".rs",
            ".c",
            ".cpp",
            ".h",
            ".hpp",
            ".cs",
            ".rb",
            ".php",
            ".swift",
            ".kt",
            ".scala",
            ".sh",
            ".bash",
            ".zsh",
            ".fish",
            ".ps1",
            ".bat",
            ".cmd",
            ".sql",
            ".graphql",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".ini",
            ".cfg",
            ".conf",
            ".xml",
            ".html",
            ".htm",
            ".css",
            ".scss",
            ".sass",
            ".less",
            ".md",
            ".markdown",
            ".rst",
            ".txt",
            ".csv",
            ".env",
            ".env.example",
            ".gitignore",
            ".dockerignore",
            ".editorconfig",
            "Dockerfile",
            "Makefile",
            "CMakeLists.txt",
            "Cargo.toml",
            "go.mod",
            "go.sum",
            "package.json",
            "tsconfig.json",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Gemfile",
            "Pipfile",
            "pom.xml",
            "build.gradle",
            ".gitattributes",
        ]
    )
    safe_mode: bool = Field(default=False, description="If true, send only file paths, no content")
    docs_only_mode: bool = Field(default=False, description="If true, only scan documentation files")


class CacheEntry(BaseModel):
    """A cached API response."""

    request_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    model: str
    input_tokens: int
    output_tokens: int
    response_text: str
    prompt_template_id: str
    context_hash: str = Field(..., description="Hash of context used")
