"""
Custom exception hierarchy for Api Vault.

Provides structured error handling with error codes, recoverability hints,
and rich context for debugging.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Error codes for categorizing failures."""

    # Scan errors
    SCAN_PATH_NOT_FOUND = "scan_path_not_found"
    SCAN_PERMISSION_DENIED = "scan_permission_denied"
    SCAN_FILE_TOO_LARGE = "scan_file_too_large"
    SCAN_ENCODING_ERROR = "scan_encoding_error"

    # Secret detection errors
    SECRET_PATTERN_INVALID = "secret_pattern_invalid"
    SECRET_SCAN_FAILED = "secret_scan_failed"

    # Planning errors
    PLAN_NO_ARTIFACTS = "plan_no_artifacts"
    PLAN_BUDGET_TOO_LOW = "plan_budget_too_low"
    PLAN_INVALID_FAMILY = "plan_invalid_family"
    PLAN_SIGNALS_MISSING = "plan_signals_missing"

    # Generation errors
    GENERATION_API_ERROR = "generation_api_error"
    GENERATION_RATE_LIMITED = "generation_rate_limited"
    GENERATION_CONTEXT_TOO_LARGE = "generation_context_too_large"
    GENERATION_INVALID_RESPONSE = "generation_invalid_response"
    GENERATION_TIMEOUT = "generation_timeout"

    # Cache errors
    CACHE_CORRUPTED = "cache_corrupted"
    CACHE_WRITE_FAILED = "cache_write_failed"

    # Configuration errors
    CONFIG_INVALID = "config_invalid"
    CONFIG_MISSING_KEY = "config_missing_key"
    CONFIG_FILE_NOT_FOUND = "config_file_not_found"

    # General errors
    UNKNOWN = "unknown"


@dataclass
class ApiVaultError(Exception):
    """
    Base exception for all Api Vault errors.

    Attributes:
        message: Human-readable error message
        code: Error code for programmatic handling
        recoverable: Whether the operation can be retried
        context: Additional context for debugging
        suggestion: Suggested action to resolve the error
    """

    message: str
    code: ErrorCode = ErrorCode.UNKNOWN
    recoverable: bool = False
    context: dict[str, Any] = field(default_factory=dict)
    suggestion: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.code.value}] {self.message}"]
        if self.suggestion:
            parts.append(f"\nSuggestion: {self.suggestion}")
        return "".join(parts)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"code={self.code.value!r}, "
            f"recoverable={self.recoverable}"
            f")"
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for serialization."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "code": self.code.value,
            "recoverable": self.recoverable,
            "context": self.context,
            "suggestion": self.suggestion,
        }


@dataclass
class ScanError(ApiVaultError):
    """Repository scanning failed."""

    file_path: str | None = None

    def __post_init__(self) -> None:
        if self.file_path:
            self.context["file_path"] = self.file_path


@dataclass
class SecretDetectionError(ApiVaultError):
    """Secret detection or redaction failed."""

    pattern_name: str | None = None

    def __post_init__(self) -> None:
        if self.pattern_name:
            self.context["pattern_name"] = self.pattern_name


@dataclass
class PlanningError(ApiVaultError):
    """Plan creation failed."""

    budget_tokens: int | None = None
    requested_families: list[str] | None = None

    def __post_init__(self) -> None:
        if self.budget_tokens:
            self.context["budget_tokens"] = self.budget_tokens
        if self.requested_families:
            self.context["requested_families"] = self.requested_families


@dataclass
class GenerationError(ApiVaultError):
    """Artifact generation failed."""

    job_id: str | None = None
    artifact_name: str | None = None
    model: str | None = None
    retry_after: int | None = None

    def __post_init__(self) -> None:
        if self.job_id:
            self.context["job_id"] = self.job_id
        if self.artifact_name:
            self.context["artifact_name"] = self.artifact_name
        if self.model:
            self.context["model"] = self.model
        if self.retry_after:
            self.context["retry_after"] = self.retry_after


@dataclass
class CacheError(ApiVaultError):
    """Cache operation failed."""

    cache_key: str | None = None
    cache_path: str | None = None

    def __post_init__(self) -> None:
        if self.cache_key:
            self.context["cache_key"] = self.cache_key
        if self.cache_path:
            self.context["cache_path"] = self.cache_path


@dataclass
class ConfigError(ApiVaultError):
    """Configuration error."""

    config_path: str | None = None
    key: str | None = None

    def __post_init__(self) -> None:
        if self.config_path:
            self.context["config_path"] = self.config_path
        if self.key:
            self.context["key"] = self.key


# Factory functions for common errors
def path_not_found(path: str) -> ScanError:
    """Create error for missing path."""
    return ScanError(
        message=f"Path not found: {path}",
        code=ErrorCode.SCAN_PATH_NOT_FOUND,
        file_path=path,
        suggestion="Check that the path exists and is accessible.",
    )


def permission_denied(path: str) -> ScanError:
    """Create error for permission denied."""
    return ScanError(
        message=f"Permission denied: {path}",
        code=ErrorCode.SCAN_PERMISSION_DENIED,
        file_path=path,
        suggestion="Check file permissions or run with appropriate privileges.",
    )


def rate_limited(retry_after: int | None = None) -> GenerationError:
    """Create error for rate limiting."""
    return GenerationError(
        message="API rate limit exceeded",
        code=ErrorCode.GENERATION_RATE_LIMITED,
        recoverable=True,
        retry_after=retry_after,
        suggestion=f"Wait {retry_after} seconds before retrying." if retry_after else "Wait and retry.",
    )


def context_too_large(size: int, limit: int) -> GenerationError:
    """Create error for context exceeding limits."""
    return GenerationError(
        message=f"Context size ({size:,} tokens) exceeds limit ({limit:,} tokens)",
        code=ErrorCode.GENERATION_CONTEXT_TOO_LARGE,
        recoverable=False,
        context={"size": size, "limit": limit},
        suggestion="Reduce context size by using --max-excerpt or --docs-only flags.",
    )


def invalid_config(path: str, reason: str) -> ConfigError:
    """Create error for invalid configuration."""
    return ConfigError(
        message=f"Invalid configuration: {reason}",
        code=ErrorCode.CONFIG_INVALID,
        config_path=path,
        suggestion="Check the configuration file format and values.",
    )


def missing_api_key() -> ConfigError:
    """Create error for missing API key."""
    return ConfigError(
        message="ANTHROPIC_API_KEY environment variable not set",
        code=ErrorCode.CONFIG_MISSING_KEY,
        key="ANTHROPIC_API_KEY",
        suggestion="Set the ANTHROPIC_API_KEY environment variable or use --dry-run.",
    )


def budget_too_low(budget: int, minimum: int) -> PlanningError:
    """Create error for insufficient budget."""
    return PlanningError(
        message=f"Token budget ({budget:,}) is below minimum required ({minimum:,})",
        code=ErrorCode.PLAN_BUDGET_TOO_LOW,
        budget_tokens=budget,
        suggestion=f"Increase --budget-tokens to at least {minimum:,}.",
    )
