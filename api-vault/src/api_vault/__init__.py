"""
Api Vault - Convert expiring API quota into durable local artifacts.

A CLI tool that:
1. Inspects local git repositories
2. Detects stack, maturity, and gaps
3. Generates high-quality, repo-specific documentation and artifacts
4. Stores everything locally with deterministic caching and provenance
"""

__version__ = "1.0.0"
__author__ = "Api Vault Contributors"

from api_vault.schemas import (
    SCHEMA_VERSION,
    ArtifactFamily,
    ArtifactMeta,
    FileEntry,
    Plan,
    PlanJob,
    RepoIndex,
    RepoSignals,
    Report,
    ScanConfig,
    VersionedModel,
)

__all__ = [
    "__version__",
    "SCHEMA_VERSION",
    "ArtifactFamily",
    "ArtifactMeta",
    "FileEntry",
    "Plan",
    "PlanJob",
    "RepoIndex",
    "RepoSignals",
    "Report",
    "ScanConfig",
    "VersionedModel",
]
